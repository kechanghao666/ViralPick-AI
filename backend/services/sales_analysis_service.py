from __future__ import annotations

from typing import Any

from backend.repositories import product_repository, sales_repository


def get_sales_analysis() -> dict[str, Any]:
    return {
        "summary": sales_repository.get_sales_summary(),
        "rankings": {
            "sales": product_repository.rank_products(metric="sales", limit=10),
            "gmv": product_repository.rank_products(metric="gmv", limit=10),
            "rating": product_repository.rank_products(metric="rating", limit=10),
            "comments": product_repository.rank_products(metric="comments", limit=10),
            "hot_score": product_repository.rank_products(metric="hot_score", limit=10),
        },
        "category_share": sales_repository.get_category_share(),
        "price_bands": get_price_band_analysis()["items"],
        "rating_sales_relation": product_repository.get_rating_sales_buckets(),
        "comment_sales_relation": product_repository.get_comment_sales_buckets(),
    }


def get_price_band_analysis() -> dict[str, Any]:
    items = product_repository.get_price_band_summary()
    return {
        "bands": ["0-20", "20-50", "50-100", "100-200", "200+"],
        "items": items,
        "insight": _build_price_band_insight(items),
    }


def _build_price_band_insight(items: list[dict[str, Any]]) -> str:
    if not items:
        return "暂无价格区间数据。"
    top_by_gmv = max(items, key=lambda item: item.get("gmv") or 0)
    top_by_score = max(items, key=lambda item: item.get("avg_hot_potential_score") or 0)
    return (
        f"{top_by_gmv['price_band']} 价格带贡献最高销售额，"
        f"{top_by_score['price_band']} 价格带平均爆品潜力更强。"
    )

