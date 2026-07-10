from __future__ import annotations

from typing import Any
from uuid import uuid4

from backend.repositories import competitor_repository
from backend.services import product_service


class CompetitorError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def get_competitor_summary(
    product_id: str | None = None,
    category: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    rows = competitor_repository.list_competitors(product_id=product_id, category=category, limit=limit)
    items = [_summarize_row(row) for row in rows]
    return {
        "product_id": product_id,
        "category": category,
        "items": items,
        "data_note": "竞品信息用于同类商品横向比较，可来自商家整理、公开信息或手动录入。",
    }


def create_competitor(payload: dict[str, Any]) -> dict[str, Any]:
    product_id = str(payload.get("product_id") or "").strip()
    competitor_name = str(payload.get("competitor_name") or "").strip()
    if not product_id:
        raise CompetitorError("product_id is required")
    if not competitor_name:
        raise CompetitorError("competitor_name is required")
    product = product_service.get_product(product_id)
    if not product:
        raise CompetitorError(f"Product not found: {product_id}", status_code=404)

    row = {
        "competitor_id": str(payload.get("competitor_id") or "").strip() or f"CP-MANUAL-{uuid4().hex[:10].upper()}",
        "product_id": product_id,
        "competitor_name": competitor_name,
        "competitor_platform": str(payload.get("competitor_platform") or payload.get("platform") or "").strip(),
        "competitor_shop_name": str(payload.get("competitor_shop_name") or payload.get("shop_name") or "").strip(),
        "competitor_image_url": str(payload.get("competitor_image_url") or payload.get("image_url") or product.get("image_url") or "").strip(),
        "competitor_selling_point": str(payload.get("competitor_selling_point") or payload.get("selling_point") or "").strip(),
        "category": str(payload.get("category") or product.get("category") or "").strip(),
        "competitor_price": _float(payload.get("competitor_price") or payload.get("price")) or float(product.get("avg_price") or 0),
        "competitor_sales_quantity": _int(payload.get("competitor_sales_quantity") or payload.get("sales_quantity")),
        "competitor_rating": _float(payload.get("competitor_rating") or payload.get("rating")) or 4.5,
        "competitor_positive_rate": _float(payload.get("competitor_positive_rate") or payload.get("positive_rate")) or 0.88,
        "main_selling_point": str(payload.get("main_selling_point") or payload.get("competitor_selling_point") or "").strip(),
        "data_type": "merchant input",
        "note": str(payload.get("note") or "商家手动录入").strip(),
    }
    competitor_repository.create_competitor(row)
    return _summarize_row(
        {
            **row,
            "product_name": product.get("product_name"),
            "product_platform": product.get("platform"),
            "product_shop_name": product.get("shop_name"),
            "product_brand": product.get("brand"),
            "product_image_url": product.get("image_url"),
            "product_selling_points": product.get("selling_points"),
            "product_price": product.get("avg_price"),
            "product_sales_quantity": product.get("total_sales_quantity"),
            "product_rating": product.get("rating"),
            "product_positive_rate": product.get("positive_rate"),
            "hot_potential_score": product.get("hot_potential_score"),
        }
    )


def _summarize_row(row: dict[str, Any]) -> dict[str, Any]:
    product_price = float(row.get("product_price") or 0)
    competitor_price = float(row.get("competitor_price") or 0)
    price_gap = round(product_price - competitor_price, 2)
    price_gap_rate = round(price_gap / competitor_price, 4) if competitor_price else 0

    advantages: list[str] = []
    shortcomings: list[str] = []
    if product_price < competitor_price:
        advantages.append("本品价格低于竞品，具备价格吸引力。")
    elif product_price > competitor_price:
        shortcomings.append("本品价格高于竞品，需要强化差异化卖点。")

    if int(row.get("product_sales_quantity") or 0) >= int(row.get("competitor_sales_quantity") or 0):
        advantages.append("本品销量表现不弱于竞品。")
    else:
        shortcomings.append("竞品销量更高，建议复盘内容投放和渠道效率。")

    if float(row.get("product_rating") or 0) >= float(row.get("competitor_rating") or 0):
        advantages.append("本品评分表现更稳。")
    else:
        shortcomings.append("评分低于竞品，需要优先处理用户体验问题。")

    if float(row.get("product_positive_rate") or 0) >= float(row.get("competitor_positive_rate") or 0):
        advantages.append("本品好评率具备优势。")
    else:
        shortcomings.append("好评率低于竞品，需要排查差评关键词和售后反馈。")

    return {
        **row,
        "price_gap": price_gap,
        "price_gap_rate": price_gap_rate,
        "advantages": advantages or ["暂无明显优势，需要继续寻找差异化卖点。"],
        "shortcomings": shortcomings or ["暂无明显短板，建议保持当前商品体验并扩大内容测试。"],
        "pricing_suggestion": _pricing_suggestion(price_gap_rate),
        "differentiation_suggestion": _differentiation_suggestion(row),
    }


def _pricing_suggestion(price_gap_rate: float) -> str:
    if price_gap_rate > 0.15:
        return "价格明显高于竞品，建议用优惠券、组合装或赠品降低用户感知门槛。"
    if price_gap_rate < -0.15:
        return "价格明显低于竞品，可测试小幅提价或升级套装提升利润。"
    return "价格与竞品接近，应重点通过内容卖点和评价证明提升转化。"


def _differentiation_suggestion(row: dict[str, Any]) -> str:
    selling_point = row.get("competitor_selling_point") or row.get("main_selling_point") or "核心卖点"
    product_points = row.get("product_selling_points") or "本品体验、价格和口碑"
    return f"竞品主打「{selling_point}」，本品应围绕「{product_points}」强化场景、评价和购买理由。"


def _float(value: Any) -> float:
    try:
        return round(float(value), 4)
    except (TypeError, ValueError):
        return 0.0


def _int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0
