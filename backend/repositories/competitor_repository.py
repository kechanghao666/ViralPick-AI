from __future__ import annotations

from typing import Any

from backend.db import execute_write, fetch_all


def list_competitors(
    product_id: str | None = None,
    category: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    filters: list[str] = []
    params: list[Any] = []
    if product_id:
        filters.append("c.product_id = ?")
        params.append(product_id)
    if category:
        filters.append("c.category = ?")
        params.append(category)
    where_sql = f"WHERE {' AND '.join(filters)}" if filters else ""
    return fetch_all(
        f"""
        SELECT
            c.product_id,
            p.product_name,
            p.platform AS product_platform,
            p.shop_name AS product_shop_name,
            p.brand AS product_brand,
            p.image_url AS product_image_url,
            p.selling_points AS product_selling_points,
            c.competitor_id,
            c.competitor_name,
            c.competitor_platform,
            c.competitor_shop_name,
            c.competitor_image_url,
            c.competitor_selling_point,
            c.category,
            p.avg_price AS product_price,
            c.competitor_price,
            p.total_sales_quantity AS product_sales_quantity,
            c.competitor_sales_quantity,
            p.rating AS product_rating,
            c.competitor_rating,
            p.positive_rate AS product_positive_rate,
            c.competitor_positive_rate,
            p.hot_potential_score,
            c.main_selling_point,
            c.data_type,
            c.note
        FROM competitors c
        JOIN products p ON p.product_id = c.product_id
        {where_sql}
        ORDER BY p.hot_potential_score DESC, c.competitor_id ASC
        LIMIT ?
        """,
        [*params, limit],
    )


def create_competitor(row: dict[str, Any]) -> None:
    execute_write(
        """
        INSERT INTO competitors (
            competitor_id,
            product_id,
            competitor_name,
            competitor_platform,
            competitor_shop_name,
            competitor_image_url,
            competitor_selling_point,
            category,
            competitor_price,
            competitor_sales_quantity,
            competitor_rating,
            competitor_positive_rate,
            main_selling_point,
            data_type,
            note
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            row["competitor_id"],
            row["product_id"],
            row["competitor_name"],
            row.get("competitor_platform", ""),
            row.get("competitor_shop_name", ""),
            row.get("competitor_image_url", ""),
            row.get("competitor_selling_point", ""),
            row.get("category", ""),
            row.get("competitor_price", 0),
            row.get("competitor_sales_quantity", 0),
            row.get("competitor_rating", 0),
            row.get("competitor_positive_rate", 0),
            row.get("main_selling_point", ""),
            row.get("data_type", "merchant input"),
            row.get("note", ""),
        ],
    )
