from __future__ import annotations

from typing import Any

from backend.repositories import product_repository


def list_products(
    keyword: str | None = None,
    category: str | None = None,
    risk_level: str | None = None,
    sort: str = "hot_score",
    order: str = "desc",
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    return product_repository.list_products(
        keyword=keyword,
        category=category,
        risk_level=risk_level,
        sort=sort,
        order=order,
        page=page,
        page_size=page_size,
    )


def get_product(product_id: str) -> dict[str, Any] | None:
    return product_repository.get_product(product_id)

