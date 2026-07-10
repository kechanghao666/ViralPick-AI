from __future__ import annotations

import json
import math
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.config import BASE_DIR
from backend.db import fetch_all, fetch_one


KNOWLEDGE_DIR = BASE_DIR / "data" / "knowledge"
KNOWLEDGE_PATH = KNOWLEDGE_DIR / "vector_knowledge_base.json"
VECTOR_INDEX_TYPE = "local_tfidf_char_ngram"
VECTOR_NGRAM_RANGE = (2, 4)


def get_status() -> dict[str, Any]:
    payload = _load_payload()
    documents = payload.get("documents") or []
    if not documents:
        try:
            payload = _write_payload(_build_documents())
            documents = payload.get("documents") or []
        except Exception:
            documents = []
    elif not _index_matches(payload.get("index"), documents):
        try:
            payload = _write_payload(documents)
            documents = payload.get("documents") or []
        except Exception:
            pass
    index = payload.get("index") or {}
    return {
        "ready": bool(documents),
        "vector_ready": _index_matches(index, documents),
        "index_type": index.get("type") or VECTOR_INDEX_TYPE,
        "document_count": len(documents),
        "updated_at": payload.get("updated_at"),
        "source": "经营资料库",
    }


def rebuild_knowledge_base() -> dict[str, Any]:
    payload = _write_payload(_build_documents())
    documents = payload.get("documents") or []
    index = payload.get("index") or {}
    return {
        "ready": bool(documents),
        "vector_ready": _index_matches(index, documents),
        "index_type": index.get("type") or VECTOR_INDEX_TYPE,
        "document_count": len(documents),
        "updated_at": payload.get("updated_at"),
        "source": "经营资料库",
    }


def _write_payload(documents: list[dict[str, Any]]) -> dict[str, Any]:
    payload = {
        "version": 2,
        "updated_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "documents": documents,
        "index": _build_vector_index(documents),
    }
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    KNOWLEDGE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def search(question: str, product_id: str | None = None, limit: int = 5) -> list[dict[str, Any]]:
    query = str(question or "").strip()
    if not query:
        return []
    payload = _load_payload()
    documents = payload.get("documents") or []
    if not documents or not _index_matches(payload.get("index"), documents):
        payload = _write_payload(_build_documents() if not documents else documents)
        documents = payload.get("documents") or []
    scoped = _prioritize_scope(documents, product_id)
    if not scoped:
        return []
    return _vector_search(query, scoped, limit=limit, index=payload.get("index"))


def _load_payload() -> dict[str, Any]:
    if not KNOWLEDGE_PATH.exists():
        return {"documents": []}
    try:
        return json.loads(KNOWLEDGE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"documents": []}


def _build_documents() -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    documents.extend(_product_documents())
    documents.extend(_competitor_documents())
    documents.extend(_category_documents())
    documents.extend(_price_band_documents())
    documents.extend(_comment_documents())
    documents.extend(_comment_detail_documents())
    documents.extend(_marketing_documents())
    documents.extend(_inventory_documents())
    return [doc for doc in documents if doc.get("content")]


def _product_documents() -> list[dict[str, Any]]:
    rows = fetch_all(
        """
        SELECT product_id, product_name, platform, brand, shop_name, selling_points,
               category, avg_price, total_sales_quantity, total_gmv, rating,
               positive_rate, comment_count, sales_growth_rate, gmv_growth_rate,
               hot_potential_score, risk_level
        FROM v_product_performance
        ORDER BY hot_potential_score DESC, total_gmv DESC
        """
    )
    docs: list[dict[str, Any]] = []
    for row in rows:
        docs.append(
            _doc(
                doc_id=f"product:{row['product_id']}",
                title=f"{row['product_name']} 商品经营画像",
                source="商品增长中心",
                product_id=row["product_id"],
                content=(
                    f"{row['product_name']} 属于{row['category']}，平台{row.get('platform') or '综合电商'}，"
                    f"店铺{row.get('shop_name') or '未标注'}，品牌{row.get('brand') or '未标注'}。"
                    f"当前价格{_money(row.get('avg_price'))}，累计销量{_number(row.get('total_sales_quantity'))}，"
                    f"销售额{_money(row.get('total_gmv'))}，评分{_decimal(row.get('rating'))}，"
                    f"好评率{_percent(row.get('positive_rate'))}，评论{_number(row.get('comment_count'))}条，"
                    f"销量增长{_signed_percent(row.get('sales_growth_rate'))}，销售额增长{_signed_percent(row.get('gmv_growth_rate'))}，"
                    f"增长分{_decimal(row.get('hot_potential_score'))}，风险等级{row.get('risk_level') or 'normal'}。"
                    f"核心卖点：{_selling_points(row.get('selling_points'))}。"
                ),
            )
        )
    return docs


def _competitor_documents() -> list[dict[str, Any]]:
    rows = fetch_all(
        """
        SELECT
            c.competitor_id,
            c.product_id,
            p.product_name,
            p.category,
            p.avg_price AS product_price,
            p.total_sales_quantity AS product_sales_quantity,
            p.rating AS product_rating,
            p.positive_rate AS product_positive_rate,
            p.selling_points AS product_selling_points,
            c.competitor_name,
            c.competitor_platform,
            c.competitor_shop_name,
            c.competitor_selling_point,
            c.competitor_price,
            c.competitor_sales_quantity,
            c.competitor_rating,
            c.competitor_positive_rate,
            c.main_selling_point,
            c.note
        FROM competitors c
        JOIN products p ON p.product_id = c.product_id
        ORDER BY p.hot_potential_score DESC, c.competitor_sales_quantity DESC
        LIMIT 160
        """
    )
    docs: list[dict[str, Any]] = []
    for row in rows:
        product_price = float(row.get("product_price") or 0)
        competitor_price = float(row.get("competitor_price") or 0)
        price_gap = product_price - competitor_price
        sales_gap = int(row.get("product_sales_quantity") or 0) - int(row.get("competitor_sales_quantity") or 0)
        docs.append(
            _doc(
                doc_id=f"competitor:{row['competitor_id']}",
                title=f"{row['product_name']} 与 {row['competitor_name']} 竞品对照",
                source="竞品情报中心",
                product_id=row["product_id"],
                category=row["category"],
                content=(
                    f"{row['product_name']} 对照竞品 {row['competitor_name']}，"
                    f"竞品平台{row.get('competitor_platform') or '未标注'}，店铺{row.get('competitor_shop_name') or '未标注'}。"
                    f"本品价格{_money(product_price)}，竞品价格{_money(competitor_price)}，价格差{_money(price_gap)}。"
                    f"本品销量{_number(row.get('product_sales_quantity'))}，竞品销量{_number(row.get('competitor_sales_quantity'))}，销量差{_number(sales_gap)}。"
                    f"本品评分{_decimal(row.get('product_rating'))}，竞品评分{_decimal(row.get('competitor_rating'))}，"
                    f"本品好评率{_percent(row.get('product_positive_rate'))}，竞品好评率{_percent(row.get('competitor_positive_rate'))}。"
                    f"竞品主卖点：{row.get('competitor_selling_point') or row.get('main_selling_point') or '暂无明确卖点'}。"
                    f"本品卖点：{_selling_points(row.get('product_selling_points'))}。"
                    f"补充备注：{row.get('note') or '用于定价、卖点和内容差异化判断'}。"
                ),
            )
        )
    return docs


def _category_documents() -> list[dict[str, Any]]:
    rows = fetch_all(
        """
        SELECT category, product_count, sales_quantity, gmv, avg_price,
               avg_rating, avg_positive_rate, avg_hot_potential_score
        FROM v_category_summary
        ORDER BY gmv DESC
        """
    )
    return [
        _doc(
            doc_id=f"category:{row['category']}",
            title=f"{row['category']} 类目经营表现",
            source="经营驾驶舱",
            category=row["category"],
            content=(
                f"{row['category']} 类目包含{_number(row.get('product_count'))}个商品，"
                f"销量{_number(row.get('sales_quantity'))}，销售额{_money(row.get('gmv'))}，"
                f"均价{_money(row.get('avg_price'))}，平均评分{_decimal(row.get('avg_rating'))}，"
                f"好评率{_percent(row.get('avg_positive_rate'))}，平均增长分{_decimal(row.get('avg_hot_potential_score'))}。"
            ),
        )
        for row in rows
    ]


def _price_band_documents() -> list[dict[str, Any]]:
    rows = fetch_all(
        """
        SELECT
            CASE
                WHEN avg_price < 20 THEN '0-20'
                WHEN avg_price < 50 THEN '20-50'
                WHEN avg_price < 100 THEN '50-100'
                WHEN avg_price < 200 THEN '100-200'
                ELSE '200+'
            END AS price_band,
            COUNT(*) AS product_count,
            SUM(total_sales_quantity) AS sales_quantity,
            ROUND(SUM(total_gmv), 2) AS gmv,
            ROUND(AVG(hot_potential_score), 2) AS score
        FROM products
        GROUP BY price_band
        ORDER BY gmv DESC
        """
    )
    return [
        _doc(
            doc_id=f"price:{row['price_band']}",
            title=f"{row['price_band']} 价格带表现",
            source="商品增长中心",
            content=(
                f"{row['price_band']} 元价格带覆盖{_number(row.get('product_count'))}个商品，"
                f"销量{_number(row.get('sales_quantity'))}，销售额{_money(row.get('gmv'))}，"
                f"平均增长分{_decimal(row.get('score'))}。"
            ),
        )
        for row in rows
    ]


def _comment_documents() -> list[dict[str, Any]]:
    rows = fetch_all(
        """
        SELECT p.product_id, p.product_name, p.category,
               COUNT(c.comment_id) AS comment_count,
               AVG(CASE WHEN c.sentiment = 'positive' OR c.sentiment_label = 1 THEN 1.0 ELSE 0 END) AS positive_rate,
               GROUP_CONCAT(CASE WHEN c.sentiment = 'negative' OR c.sentiment_label = 0 THEN c.review_text END, '；') AS negative_examples,
               GROUP_CONCAT(CASE WHEN c.sentiment = 'positive' OR c.sentiment_label = 1 THEN c.review_text END, '；') AS positive_examples
        FROM products p
        LEFT JOIN comments c ON c.product_id = p.product_id
        GROUP BY p.product_id
        ORDER BY comment_count DESC, p.total_gmv DESC
        LIMIT 40
        """
    )
    docs: list[dict[str, Any]] = []
    for row in rows:
        docs.append(
            _doc(
                doc_id=f"comment:{row['product_id']}",
                title=f"{row['product_name']} 口碑摘要",
                source="用户口碑中心",
                product_id=row["product_id"],
                category=row["category"],
                content=(
                    f"{row['product_name']} 评论{_number(row.get('comment_count'))}条，"
                    f"好评率{_percent(row.get('positive_rate'))}。"
                    f"好评反馈：{_short_text(row.get('positive_examples'))}。"
                    f"差评关注：{_short_text(row.get('negative_examples'))}。"
                ),
            )
        )
    return docs


def _comment_detail_documents() -> list[dict[str, Any]]:
    rows = fetch_all(
        """
        SELECT c.comment_id, c.product_id, p.product_name, p.category,
               c.review_text, c.sentiment, c.sentiment_label, c.rating
        FROM comments c
        JOIN products p ON p.product_id = c.product_id
        WHERE TRIM(COALESCE(c.review_text, '')) <> ''
        ORDER BY c.rowid DESC
        LIMIT 800
        """
    )
    docs: list[dict[str, Any]] = []
    for row in rows:
        sentiment = "好评" if row.get("sentiment") == "positive" or row.get("sentiment_label") == 1 else "差评关注"
        docs.append(
            _doc(
                doc_id=f"comment-detail:{row['comment_id']}",
                title=f"{row['product_name']} 评论线索",
                source="用户口碑中心",
                product_id=row["product_id"],
                category=row["category"],
                content=(
                    f"{row['product_name']} 的一条{sentiment}评论："
                    f"{_short_text(row.get('review_text'), max_len=220)}。"
                    f"评分{_decimal(row.get('rating'))}，可用于判断用户体验、卖点表达和售后风险。"
                ),
            )
        )
    return docs


def _marketing_documents() -> list[dict[str, Any]]:
    rows = fetch_all(
        """
        SELECT product_id, product_name,
               SUM(spend) AS spend,
               SUM(impressions) AS impressions,
               SUM(clicks) AS clicks,
               SUM(conversions) AS conversions,
               SUM(revenue) AS revenue,
               AVG(roi) AS roi
        FROM ad_metrics
        GROUP BY product_id
        ORDER BY revenue DESC
        LIMIT 40
        """
    )
    return [
        _doc(
            doc_id=f"marketing:{row['product_id']}",
            title=f"{row['product_name']} 投放表现",
            source="投放内容中心",
            product_id=row["product_id"],
            content=(
                f"{row['product_name']} 投放花费{_money(row.get('spend'))}，曝光{_number(row.get('impressions'))}，"
                f"点击{_number(row.get('clicks'))}，转化{_number(row.get('conversions'))}，"
                f"成交金额{_money(row.get('revenue'))}，投产比{_decimal(row.get('roi'))}。"
            ),
        )
        for row in rows
    ]


def _inventory_documents() -> list[dict[str, Any]]:
    rows = fetch_all(
        """
        SELECT i.product_id, i.product_name,
               AVG(i.available_stock) AS available_stock,
               MAX(i.stockout_risk) AS stockout_risk,
               MAX(i.slow_moving_days) AS slow_moving_days,
               COALESCE(SUM(a.refund_count), 0) AS refund_count,
               COALESCE(SUM(a.refund_amount), 0) AS refund_amount,
               GROUP_CONCAT(DISTINCT a.reason) AS reasons
        FROM inventory_daily i
        LEFT JOIN after_sales a ON a.product_id = i.product_id
        GROUP BY i.product_id
        ORDER BY stockout_risk DESC, refund_count DESC
        LIMIT 40
        """
    )
    return [
        _doc(
            doc_id=f"inventory:{row['product_id']}",
            title=f"{row['product_name']} 库存售后信号",
            source="趋势预测中心",
            product_id=row["product_id"],
            content=(
                f"{row['product_name']} 平均可售库存{_number(row.get('available_stock'))}，"
                f"缺货风险{_percent(row.get('stockout_risk'))}，滞销天数{_number(row.get('slow_moving_days'))}，"
                f"售后{_number(row.get('refund_count'))}笔，退款金额{_money(row.get('refund_amount'))}，"
                f"主要原因：{row.get('reasons') or '暂无集中原因'}。"
            ),
        )
        for row in rows
    ]


def _build_vector_index(documents: list[dict[str, Any]]) -> dict[str, Any]:
    document_count = len(documents)
    doc_ids = [str(doc.get("doc_id") or "") for doc in documents]
    if not documents:
        return {
            "type": VECTOR_INDEX_TYPE,
            "ngram_range": list(VECTOR_NGRAM_RANGE),
            "document_count": 0,
            "doc_ids": [],
            "vocabulary": {},
            "idf": [],
            "vectors": [],
        }

    document_terms: list[Counter[str]] = []
    document_frequency: Counter[str] = Counter()
    for document in documents:
        term_counts = Counter(_char_wb_ngrams(_search_text(document)))
        document_terms.append(term_counts)
        document_frequency.update(term_counts.keys())

    vocabulary_terms = sorted(document_frequency)
    vocabulary = {term: index for index, term in enumerate(vocabulary_terms)}
    idf = [math.log((1 + document_count) / (1 + document_frequency[term])) + 1 for term in vocabulary_terms]
    vectors: list[dict[str, Any]] = []

    for doc_id, term_counts in zip(doc_ids, document_terms, strict=True):
        weights = {
            vocabulary[term]: count * idf[vocabulary[term]]
            for term, count in term_counts.items()
            if term in vocabulary
        }
        normalized = _normalize_sparse_vector(weights)
        indices = sorted(normalized)
        vectors.append(
            {
                "doc_id": doc_id,
                "indices": indices,
                "values": [round(normalized[index], 8) for index in indices],
            }
        )

    return {
        "type": VECTOR_INDEX_TYPE,
        "ngram_range": list(VECTOR_NGRAM_RANGE),
        "document_count": document_count,
        "doc_ids": doc_ids,
        "vocabulary": vocabulary,
        "idf": [round(value, 8) for value in idf],
        "vectors": vectors,
    }


def _search_text(document: dict[str, Any]) -> str:
    return " ".join(
        str(document.get(key) or "")
        for key in ("title", "source", "category", "content")
    )


def _char_wb_ngrams(value: Any, ngram_range: tuple[int, int] = VECTOR_NGRAM_RANGE) -> list[str]:
    text = str(value or "").lower()
    tokens = re.findall(r"[\u4e00-\u9fff]+|[a-z0-9_]+", text)
    ngrams: list[str] = []
    min_n, max_n = ngram_range
    for token in tokens:
        padded = f" {token} "
        for ngram_size in range(min_n, max_n + 1):
            if len(padded) < ngram_size:
                continue
            ngrams.extend(padded[index : index + ngram_size] for index in range(len(padded) - ngram_size + 1))
    return ngrams


def _normalize_sparse_vector(weights: dict[int, float]) -> dict[int, float]:
    norm = math.sqrt(sum(value * value for value in weights.values()))
    if not norm:
        return {}
    return {index: value / norm for index, value in weights.items() if value}


def _query_vector(query: str, index: dict[str, Any]) -> dict[int, float]:
    vocabulary = index.get("vocabulary") or {}
    idf = index.get("idf") or []
    if not vocabulary or not idf:
        return {}
    ngram_range_value = index.get("ngram_range") or list(VECTOR_NGRAM_RANGE)
    ngram_range = (int(ngram_range_value[0]), int(ngram_range_value[1]))
    term_counts = Counter(_char_wb_ngrams(query, ngram_range=ngram_range))
    weights: dict[int, float] = {}
    for term, count in term_counts.items():
        term_index = vocabulary.get(term)
        if term_index is None or term_index >= len(idf):
            continue
        weights[int(term_index)] = count * float(idf[term_index])
    return _normalize_sparse_vector(weights)


def _indexed_vector_search(
    query: str,
    documents: list[dict[str, Any]],
    limit: int,
    index: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not index or index.get("type") != VECTOR_INDEX_TYPE:
        return []
    requested_docs = {str(doc.get("doc_id") or ""): doc for doc in documents if doc.get("doc_id")}
    indexed_ids = set(index.get("doc_ids") or [])
    if not requested_docs or not set(requested_docs).issubset(indexed_ids):
        return []

    query_vector = _query_vector(query, index)
    if not query_vector:
        return []

    scored: list[tuple[float, dict[str, Any]]] = []
    for vector in index.get("vectors") or []:
        doc_id = str(vector.get("doc_id") or "")
        document = requested_docs.get(doc_id)
        if not document:
            continue
        score = 0.0
        for vector_index, value in zip(vector.get("indices") or [], vector.get("values") or [], strict=False):
            score += query_vector.get(int(vector_index), 0.0) * float(value)
        if score > 0:
            scored.append((score, document))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [_result(document, score) for score, document in scored[:limit]]


def _index_matches(index: Any, documents: list[dict[str, Any]]) -> bool:
    if not isinstance(index, dict):
        return False
    doc_ids = [str(doc.get("doc_id") or "") for doc in documents]
    vectors = index.get("vectors") or []
    return (
        index.get("type") == VECTOR_INDEX_TYPE
        and index.get("document_count") == len(documents)
        and index.get("doc_ids") == doc_ids
        and isinstance(index.get("vocabulary"), dict)
        and isinstance(index.get("idf"), list)
        and isinstance(vectors, list)
        and len(vectors) == len(documents)
    )


def _vector_search(
    query: str,
    documents: list[dict[str, Any]],
    limit: int,
    index: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    indexed_results = _indexed_vector_search(query, documents, limit, index)
    if indexed_results:
        return indexed_results
    return _fallback_sklearn_vector_search(query, documents, limit) or _token_search(query, documents, limit)


def _fallback_sklearn_vector_search(query: str, documents: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    texts = [f"{doc.get('title', '')} {doc.get('content', '')}" for doc in documents]
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity

        vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), lowercase=True)
        matrix = vectorizer.fit_transform(texts + [query])
        similarities = cosine_similarity(matrix[-1], matrix[:-1]).ravel()
        ranked = sorted(enumerate(similarities), key=lambda item: item[1], reverse=True)
        return [_result(documents[index], float(score)) for index, score in ranked[:limit] if score > 0]
    except Exception:
        return []


def _token_search(query: str, documents: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    query_terms = set(_terms(query))
    scored: list[tuple[int, dict[str, Any]]] = []
    for doc in documents:
        terms = set(_terms(f"{doc.get('title', '')} {doc.get('content', '')}"))
        score = len(query_terms & terms)
        if score:
            scored.append((score, doc))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [_result(doc, min(1.0, score / max(len(query_terms), 1))) for score, doc in scored[:limit]]


def _prioritize_scope(documents: list[dict[str, Any]], product_id: str | None) -> list[dict[str, Any]]:
    if not product_id:
        return documents
    scoped = [doc for doc in documents if doc.get("product_id") == product_id]
    general = [doc for doc in documents if not doc.get("product_id")]
    return scoped + general


def _doc(
    doc_id: str,
    title: str,
    source: str,
    content: str,
    product_id: str | None = None,
    category: str | None = None,
) -> dict[str, Any]:
    return {
        "doc_id": doc_id,
        "title": title,
        "source": source,
        "product_id": product_id,
        "category": category,
        "content": re.sub(r"\s+", " ", content).strip(),
    }


def _result(document: dict[str, Any], score: float) -> dict[str, Any]:
    return {
        "title": document.get("title"),
        "source": document.get("source"),
        "product_id": document.get("product_id"),
        "category": document.get("category"),
        "content": document.get("content"),
        "score": round(float(score), 4) if math.isfinite(float(score)) else 0,
    }


def _terms(value: str) -> list[str]:
    return re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9_]+", value.lower())


def _selling_points(value: Any) -> str:
    points = [item.strip() for item in str(value or "").split("|") if item.strip()]
    return "、".join(points[:5]) or "暂无明确卖点"


def _short_text(value: Any, max_len: int = 140) -> str:
    text = re.sub(r"\s+", " ", str(value or "").replace("；；", "；")).strip("； ")
    if not text:
        return "暂无集中反馈"
    return text[:max_len] + ("…" if len(text) > max_len else "")


def _number(value: Any) -> str:
    try:
        return f"{float(value or 0):,.0f}"
    except (TypeError, ValueError):
        return "0"


def _money(value: Any) -> str:
    try:
        return f"¥{float(value or 0):,.0f}"
    except (TypeError, ValueError):
        return "¥0"


def _decimal(value: Any) -> str:
    try:
        return f"{float(value or 0):.2f}"
    except (TypeError, ValueError):
        return "0.00"


def _percent(value: Any) -> str:
    try:
        return f"{float(value or 0) * 100:.1f}%"
    except (TypeError, ValueError):
        return "0.0%"


def _signed_percent(value: Any) -> str:
    try:
        return f"{float(value or 0) * 100:+.1f}%"
    except (TypeError, ValueError):
        return "+0.0%"
