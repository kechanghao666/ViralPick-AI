from __future__ import annotations

from typing import Any

from backend.db import fetch_all, fetch_one


def get_sales_trend(
    product_id: str | None = None,
    category: str | None = None,
    days: int = 30,
) -> list[dict[str, Any]]:
    base_filters: list[str] = []
    params: list[Any] = []
    if product_id:
        base_filters.append("product_id = ?")
        params.append(product_id)
    if category:
        base_filters.append("category = ?")
        params.append(category)

    where_sql = f"WHERE {' AND '.join(base_filters)}" if base_filters else ""
    scoped_filter_sql = f"AND {' AND '.join(base_filters)}" if base_filters else ""
    return fetch_all(
        f"""
        WITH max_date AS (
            SELECT MAX(date) AS latest_date
            FROM sales_daily
            {where_sql}
        ),
        scoped_sales AS (
            SELECT s.*
            FROM sales_daily s
            CROSS JOIN max_date
            WHERE max_date.latest_date IS NOT NULL
              AND s.date >= date(max_date.latest_date, '-' || (? - 1) || ' day')
              {scoped_filter_sql}
        )
        SELECT
            date,
            SUM(sales_quantity) AS sales_quantity,
            ROUND(SUM(gmv), 2) AS gmv,
            SUM(order_count) AS order_count
        FROM scoped_sales
        GROUP BY date
        ORDER BY date ASC
        """,
        [*params, days, *params],
    )


def get_sales_summary(
    product_id: str | None = None,
    category: str | None = None,
) -> dict[str, Any]:
    filters: list[str] = []
    params: list[Any] = []
    if product_id:
        filters.append("product_id = ?")
        params.append(product_id)
    if category:
        filters.append("category = ?")
        params.append(category)
    where_sql = f"WHERE {' AND '.join(filters)}" if filters else ""
    return fetch_one(
        f"""
        SELECT
            COUNT(DISTINCT product_id) AS product_count,
            COUNT(DISTINCT date) AS active_days,
            COALESCE(SUM(sales_quantity), 0) AS sales_quantity,
            ROUND(COALESCE(SUM(gmv), 0), 2) AS gmv,
            COALESCE(SUM(order_count), 0) AS order_count,
            ROUND(COALESCE(AVG(avg_unit_price), 0), 2) AS avg_unit_price
        FROM sales_daily
        {where_sql}
        """,
        params,
    ) or {}


def get_category_share() -> list[dict[str, Any]]:
    totals = fetch_one(
        """
        SELECT
            COALESCE(SUM(sales_quantity), 0) AS total_sales_quantity,
            COALESCE(SUM(gmv), 0) AS total_gmv
        FROM v_category_summary
        """
    ) or {}
    total_sales = float(totals.get("total_sales_quantity") or 0)
    total_gmv = float(totals.get("total_gmv") or 0)
    rows = fetch_all(
        """
        SELECT category, product_count, sales_quantity, gmv
        FROM v_category_summary
        ORDER BY gmv DESC
        """
    )
    for row in rows:
        row["sales_share"] = round((row["sales_quantity"] or 0) / total_sales, 4) if total_sales else 0
        row["gmv_share"] = round((row["gmv"] or 0) / total_gmv, 4) if total_gmv else 0
    return rows

