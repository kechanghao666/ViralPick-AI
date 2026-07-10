from __future__ import annotations

from typing import Any

from backend.db import fetch_all, fetch_one


def get_sentiment_summary(product_id: str | None = None) -> dict[str, Any]:
    params: list[Any] = []
    where_sql = ""
    if product_id:
        where_sql = "WHERE product_id = ?"
        params.append(product_id)
    return fetch_one(
        f"""
        SELECT
            COUNT(*) AS comment_count,
            SUM(CASE WHEN sentiment = 'positive' THEN 1 ELSE 0 END) AS positive_count,
            SUM(CASE WHEN sentiment = 'negative' THEN 1 ELSE 0 END) AS negative_count,
            ROUND(AVG(sentiment_label), 4) AS positive_rate,
            ROUND(AVG(rating), 2) AS avg_rating
        FROM comments
        {where_sql}
        """,
        params,
    ) or {}


def get_sentiment_by_source(product_id: str | None = None) -> list[dict[str, Any]]:
    params: list[Any] = []
    where_sql = ""
    if product_id:
        where_sql = "WHERE product_id = ?"
        params.append(product_id)
    return fetch_all(
        f"""
        SELECT
            category_source,
            COUNT(*) AS comment_count,
            ROUND(AVG(sentiment_label), 4) AS positive_rate
        FROM comments
        {where_sql}
        GROUP BY category_source
        ORDER BY comment_count DESC
        LIMIT 10
        """,
        params,
    )


def list_comments(
    product_id: str | None = None,
    sentiment: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    filters: list[str] = []
    params: list[Any] = []
    if product_id:
        filters.append("c.product_id = ?")
        params.append(product_id)
    if sentiment:
        filters.append("c.sentiment = ?")
        params.append(sentiment)
    where_sql = f"WHERE {' AND '.join(filters)}" if filters else ""
    return fetch_all(
        f"""
        SELECT
            c.comment_id,
            c.product_id,
            p.product_name,
            p.brand,
            p.category,
            c.review_text,
            c.sentiment,
            c.rating,
            c.category_source
        FROM comments c
        LEFT JOIN products p ON p.product_id = c.product_id
        {where_sql}
        ORDER BY c.comment_id ASC
        LIMIT ?
        """,
        [*params, limit],
    )
