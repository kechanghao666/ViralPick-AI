from __future__ import annotations

from typing import Any

from backend.db import fetch_all, fetch_one


PRODUCT_SORT_COLUMNS = {
    "gmv": "total_gmv",
    "sales": "total_sales_quantity",
    "rating": "rating",
    "comments": "comment_count",
    "hot_score": "hot_potential_score",
    "price": "avg_price",
    "growth": "sales_growth_rate",
}


def _product_select() -> str:
    return """
        product_id,
        product_name,
        platform,
        brand,
        shop_name,
        image_url,
        selling_points,
        source_dataset,
        category,
        avg_price,
        total_sales_quantity,
        total_gmv,
        rating,
        positive_rate,
        comment_count,
        sales_growth_rate,
        gmv_growth_rate,
        price_competitiveness,
        hot_potential_score,
        risk_level,
        video_views,
        video_likes,
        video_favorites,
        video_shares,
        video_conversion_rate
    """


def list_products(
    keyword: str | None = None,
    category: str | None = None,
    risk_level: str | None = None,
    sort: str = "hot_score",
    order: str = "desc",
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    filters: list[str] = []
    params: list[Any] = []
    if keyword:
        filters.append("(product_name LIKE ? OR product_id LIKE ?)")
        keyword_pattern = f"%{keyword.strip()}%"
        params.extend([keyword_pattern, keyword_pattern])
    if category:
        filters.append("category = ?")
        params.append(category)
    if risk_level:
        filters.append("risk_level = ?")
        params.append(risk_level)

    where_sql = f"WHERE {' AND '.join(filters)}" if filters else ""
    sort_column = PRODUCT_SORT_COLUMNS.get(sort, "hot_potential_score")
    sort_order = "ASC" if order == "asc" else "DESC"
    offset = (page - 1) * page_size

    total_row = fetch_one(
        f"SELECT COUNT(*) AS total FROM v_product_performance {where_sql}",
        params,
    )
    items = fetch_all(
        f"""
        SELECT {_product_select()}
        FROM v_product_performance
        {where_sql}
        ORDER BY {sort_column} {sort_order}, product_id ASC
        LIMIT ? OFFSET ?
        """,
        [*params, page_size, offset],
    )
    total = int((total_row or {}).get("total", 0))
    return {
        "items": items,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": (total + page_size - 1) // page_size if page_size else 0,
        },
        "filters": {
            "keyword": keyword,
            "category": category,
            "risk_level": risk_level,
            "sort": sort,
            "order": order,
        },
    }


def get_product(product_id: str) -> dict[str, Any] | None:
    return fetch_one(
        f"""
        SELECT {_product_select()}
        FROM v_product_performance
        WHERE product_id = ?
        """,
        [product_id],
    )


def list_products_for_scoring() -> list[dict[str, Any]]:
    return fetch_all(
        f"""
        SELECT {_product_select()}
        FROM v_product_performance
        ORDER BY hot_potential_score DESC, total_gmv DESC
        """
    )


def rank_products(metric: str = "gmv", limit: int = 10) -> list[dict[str, Any]]:
    sort_column = PRODUCT_SORT_COLUMNS.get(metric, "total_gmv")
    return fetch_all(
        f"""
        SELECT {_product_select()}
        FROM v_product_performance
        ORDER BY {sort_column} DESC, product_id ASC
        LIMIT ?
        """,
        [limit],
    )


def get_overview_summary() -> dict[str, Any]:
    return fetch_one(
        """
        SELECT
            COUNT(*) AS product_count,
            COALESCE(SUM(total_sales_quantity), 0) AS total_sales_quantity,
            ROUND(COALESCE(SUM(total_gmv), 0), 2) AS total_gmv,
            ROUND(COALESCE(AVG(rating), 0), 2) AS avg_rating,
            ROUND(COALESCE(AVG(positive_rate), 0), 4) AS avg_positive_rate,
            COUNT(CASE WHEN hot_potential_score >= 75 THEN 1 END) AS hot_product_count,
            COUNT(CASE WHEN risk_level = 'high' THEN 1 END) AS high_risk_product_count
        FROM products
        """
    ) or {}


def get_risk_distribution() -> list[dict[str, Any]]:
    return fetch_all(
        """
        SELECT risk_level, COUNT(*) AS product_count
        FROM products
        GROUP BY risk_level
        ORDER BY product_count DESC
        """
    )


def get_category_summary() -> list[dict[str, Any]]:
    return fetch_all(
        """
        SELECT
            category,
            product_count,
            sales_quantity,
            gmv,
            avg_price,
            avg_rating,
            avg_positive_rate,
            avg_hot_potential_score
        FROM v_category_summary
        ORDER BY gmv DESC
        """
    )


def get_price_band_summary() -> list[dict[str, Any]]:
    return fetch_all(
        """
        SELECT
            CASE
                WHEN avg_price < 20 THEN '0-20'
                WHEN avg_price < 50 THEN '20-50'
                WHEN avg_price < 100 THEN '50-100'
                WHEN avg_price < 200 THEN '100-200'
                ELSE '200+'
            END AS price_band,
            CASE
                WHEN avg_price < 20 THEN 1
                WHEN avg_price < 50 THEN 2
                WHEN avg_price < 100 THEN 3
                WHEN avg_price < 200 THEN 4
                ELSE 5
            END AS sort_key,
            COUNT(*) AS product_count,
            SUM(total_sales_quantity) AS sales_quantity,
            ROUND(SUM(total_gmv), 2) AS gmv,
            ROUND(AVG(avg_price), 2) AS avg_price,
            ROUND(AVG(hot_potential_score), 2) AS avg_hot_potential_score
        FROM products
        GROUP BY price_band, sort_key
        ORDER BY sort_key ASC
        """
    )


def get_rating_sales_buckets() -> list[dict[str, Any]]:
    return fetch_all(
        """
        SELECT
            CASE
                WHEN rating < 2 THEN '1-2'
                WHEN rating < 3 THEN '2-3'
                WHEN rating < 4 THEN '3-4'
                WHEN rating < 4.5 THEN '4.0-4.5'
                ELSE '4.5-5.0'
            END AS rating_band,
            COUNT(*) AS product_count,
            ROUND(AVG(total_sales_quantity), 2) AS avg_sales_quantity,
            ROUND(AVG(total_gmv), 2) AS avg_gmv,
            ROUND(AVG(hot_potential_score), 2) AS avg_hot_potential_score
        FROM products
        GROUP BY rating_band
        ORDER BY MIN(rating) ASC
        """
    )


def get_comment_sales_buckets() -> list[dict[str, Any]]:
    return fetch_all(
        """
        SELECT
            CASE
                WHEN comment_count < 10 THEN '0-9'
                WHEN comment_count < 30 THEN '10-29'
                WHEN comment_count < 60 THEN '30-59'
                WHEN comment_count < 100 THEN '60-99'
                ELSE '100+'
            END AS comment_band,
            COUNT(*) AS product_count,
            ROUND(AVG(total_sales_quantity), 2) AS avg_sales_quantity,
            ROUND(AVG(total_gmv), 2) AS avg_gmv,
            ROUND(AVG(rating), 2) AS avg_rating
        FROM products
        GROUP BY comment_band
        ORDER BY MIN(comment_count) ASC
        """
    )
