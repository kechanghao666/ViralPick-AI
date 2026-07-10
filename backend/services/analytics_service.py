from __future__ import annotations

from typing import Any

from backend.repositories import comment_repository, competitor_repository, product_repository, sales_repository


MAX_LIMIT = 100


def clamp_limit(value: str | int | None, default: int = 10, maximum: int = MAX_LIMIT) -> int:
    try:
        limit = int(value) if value is not None else default
    except (TypeError, ValueError):
        return default
    return max(1, min(limit, maximum))


def get_overview() -> dict[str, Any]:
    summary = product_repository.get_overview_summary()
    risk_distribution = product_repository.get_risk_distribution()
    top_categories = product_repository.get_category_summary()[:5]
    top_hot_products = get_hot_products(limit=5)
    return {
        "summary": summary,
        "risk_distribution": risk_distribution,
        "top_categories": top_categories,
        "top_hot_products": top_hot_products,
    }


def get_product_rankings(metric: str = "gmv", limit: int = 10) -> list[dict[str, Any]]:
    return product_repository.rank_products(metric=metric, limit=limit)


def get_category_summary() -> list[dict[str, Any]]:
    return product_repository.get_category_summary()


def get_hot_products(limit: int = 10) -> list[dict[str, Any]]:
    return product_repository.rank_products(metric="hot_score", limit=limit)


def get_sentiment_summary(product_id: str | None = None) -> dict[str, Any]:
    return {
        "summary": comment_repository.get_sentiment_summary(product_id=product_id),
        "by_source_category": comment_repository.get_sentiment_by_source(product_id=product_id),
        "sample_comments": comment_repository.list_comments(product_id=product_id, limit=10),
    }


def get_sales_trend(product_id: str | None = None, days: int = 30) -> list[dict[str, Any]]:
    return sales_repository.get_sales_trend(product_id=product_id, days=days)


def get_competitors(product_id: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    return competitor_repository.list_competitors(product_id=product_id, limit=limit)


def get_product_detail(product_id: str) -> dict[str, Any] | None:
    product = product_repository.get_product(product_id)
    if not product:
        return None
    return {
        "product": product,
        "recent_sales_trend": get_sales_trend(product_id=product_id, days=30),
        "sentiment": get_sentiment_summary(product_id=product_id),
        "competitors": get_competitors(product_id=product_id, limit=10),
    }
