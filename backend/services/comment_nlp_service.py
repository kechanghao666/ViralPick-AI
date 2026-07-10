from __future__ import annotations

import re
from collections import Counter
from typing import Iterable

from backend.repositories import comment_repository

try:
    import jieba  # type: ignore
except ImportError:  # pragma: no cover - fallback keeps the demo runnable.
    jieba = None


STOPWORDS = {
    "一个",
    "一些",
    "不是",
    "但是",
    "就是",
    "这个",
    "那个",
    "还是",
    "可以",
    "没有",
    "非常",
    "比较",
    "感觉",
    "东西",
    "商品",
    "产品",
    "时候",
    "已经",
    "因为",
    "所以",
    "如果",
    "我们",
    "你们",
    "他们",
    "这次",
    "下次",
    "真的",
    "有点",
    "收到",
}

CONTEXT_STOPWORDS = {
    "官方",
    "旗舰店",
    "品牌店",
    "专卖店",
    "热卖款",
    "同类热卖款",
    "优选",
    "经典款",
    "组合装",
    "套装",
    "家庭装",
}

PAIN_HINTS = {
    "质量": "质量稳定性",
    "物流": "物流时效",
    "快递": "物流体验",
    "包装": "包装保护",
    "客服": "客服响应",
    "售后": "售后服务",
    "价格": "价格敏感",
    "贵": "价格敏感",
    "尺寸": "尺寸适配",
    "味道": "使用体验",
    "不好": "体验不佳",
    "差": "体验不佳",
    "破": "破损风险",
}


def get_comment_keywords(
    product_id: str | None = None,
    top_n: int = 20,
) -> dict:
    positive_comments = comment_repository.list_comments(
        product_id=product_id,
        sentiment="positive",
        limit=1000,
    )
    negative_comments = comment_repository.list_comments(
        product_id=product_id,
        sentiment="negative",
        limit=1000,
    )
    all_comments = positive_comments + negative_comments
    context_terms = _comment_context_terms(all_comments)

    positive_keywords = _keyword_counts(
        (item["review_text"] for item in positive_comments),
        top_n,
        context_terms,
    )
    negative_keywords = _keyword_counts(
        (item["review_text"] for item in negative_comments),
        top_n,
        context_terms,
    )
    pain_points = _build_pain_points(negative_keywords)
    demand_summary = _build_demand_summary(positive_keywords, negative_keywords)

    return {
        "product_id": product_id,
        "summary": comment_repository.get_sentiment_summary(product_id=product_id),
        "positive_keywords": positive_keywords,
        "negative_keywords": negative_keywords,
        "pain_points": pain_points,
        "demand_summary": demand_summary,
        "sample_comments": all_comments[:10],
    }


def _keyword_counts(
    texts: Iterable[str],
    top_n: int,
    context_terms: set[str] | None = None,
) -> list[dict]:
    counter: Counter[str] = Counter()
    for text in texts:
        counter.update(
            token
            for token in _tokenize(text)
            if not _is_context_noise(token, context_terms or set())
        )
    return [{"word": word, "count": count} for word, count in counter.most_common(top_n)]


def _tokenize(text: str) -> list[str]:
    cleaned = re.sub(r"[^\w\u4e00-\u9fff]+", " ", text or "")
    if jieba is not None:
        tokens = [token.strip() for token in jieba.cut(cleaned)]
    else:
        tokens = re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z]{2,}", cleaned)
    return [
        token
        for token in tokens
        if len(token) >= 2
        and token not in STOPWORDS
        and not token.isdigit()
        and not re.fullmatch(r"[A-Za-z_]+", token)
    ]


def _comment_context_terms(comments: list[dict]) -> set[str]:
    terms: set[str] = set(CONTEXT_STOPWORDS)
    for item in comments:
        for key in ("product_name", "brand", "category", "category_source"):
            value = str(item.get(key) or "").strip()
            if not value:
                continue
            terms.add(value)
            terms.update(part for part in re.findall(r"[\u4e00-\u9fffA-Za-z0-9]+", value) if len(part) >= 2)
    return terms


def _is_context_noise(token: str, context_terms: set[str]) -> bool:
    if token in context_terms:
        return True
    return any(len(token) >= 3 and len(term) >= 4 and token in term for term in context_terms)


def _build_pain_points(negative_keywords: list[dict]) -> list[dict]:
    buckets: dict[str, int] = {}
    for item in negative_keywords:
        word = item["word"]
        count = int(item["count"])
        matched = False
        for hint, label in PAIN_HINTS.items():
            if hint in word:
                buckets[label] = buckets.get(label, 0) + count
                matched = True
        if not matched and count >= 2:
            buckets[word] = buckets.get(word, 0) + count
    return [
        {"pain_point": label, "evidence_count": count}
        for label, count in sorted(buckets.items(), key=lambda pair: pair[1], reverse=True)[:8]
    ]


def _build_demand_summary(positive_keywords: list[dict], negative_keywords: list[dict]) -> list[str]:
    summaries: list[str] = []
    if positive_keywords:
        top_words = "、".join(item["word"] for item in positive_keywords[:5])
        summaries.append(f"用户正向反馈集中在 {top_words}，适合强化为内容卖点。")
    if negative_keywords:
        top_words = "、".join(item["word"] for item in negative_keywords[:5])
        summaries.append(f"负向反馈集中在 {top_words}，需要在详情页、客服话术和供应链环节处理。")
    if not summaries:
        summaries.append("暂无足够评论文本，建议继续积累用户反馈后再判断需求方向。")
    return summaries
