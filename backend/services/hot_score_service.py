from __future__ import annotations

from typing import Any

from backend.repositories import product_repository
from backend.services import scoring_model_service


def get_hot_scoring(
    limit: int = 20,
    product_id: str | None = None,
) -> dict[str, Any]:
    products = product_repository.list_products_for_scoring()
    scoring_model = scoring_model_service.get_active_model()
    weights = scoring_model["weights"]
    scored = _score_products(products, weights)
    if product_id:
        scored = [item for item in scored if item["product_id"] == product_id]
    return {
        "model": scoring_model,
        "weights": weights,
        "formula": "weighted_score = sum(component_score * component_weight)",
        "items": scored[:limit],
        "data_note": "内容运营指标用于衡量曝光、互动和转化承接效果。",
    }


def _score_products(products: list[dict[str, Any]], weights: dict[str, float]) -> list[dict[str, Any]]:
    if not products:
        return []

    sales_growth_scores = _normalize([_clip(item.get("sales_growth_rate"), -1, 1) for item in products])
    gmv_growth_scores = _normalize([_clip(item.get("gmv_growth_rate"), -1, 1) for item in products])
    comment_scores = _normalize([item.get("comment_count") or 0 for item in products])
    price_scores = _normalize([item.get("price_competitiveness") or 0 for item in products])
    video_scores = _normalize([_video_interaction(item) for item in products])
    conversion_scores = _normalize([item.get("video_conversion_rate") or 0 for item in products])

    scored_items: list[dict[str, Any]] = []
    for index, product in enumerate(products):
        components = {
            "sales_growth": sales_growth_scores[index],
            "gmv_growth": gmv_growth_scores[index],
            "positive_rate": round(float(product.get("positive_rate") or 0) * 100, 2),
            "comment_heat": comment_scores[index],
            "price_competitiveness": price_scores[index],
            "video_interaction": video_scores[index],
            "conversion_rate": conversion_scores[index],
        }
        total_score = round(
            sum(components[key] * float(weights.get(key, 0)) for key in components),
            2,
        )
        scored_items.append(
            {
                "product_id": product["product_id"],
                "product_name": product["product_name"],
                "platform": product.get("platform", ""),
                "brand": product.get("brand", ""),
                "shop_name": product.get("shop_name", ""),
                "image_url": product.get("image_url", ""),
                "selling_points": product.get("selling_points", ""),
                "source_dataset": product.get("source_dataset", ""),
                "category": product["category"],
                "avg_price": product["avg_price"],
                "total_sales_quantity": product["total_sales_quantity"],
                "total_gmv": product["total_gmv"],
                "rating": product["rating"],
                "positive_rate": product["positive_rate"],
                "risk_level": product["risk_level"],
                "stored_hot_potential_score": product["hot_potential_score"],
                "scoring_components": components,
                "total_score": total_score,
                "growth_label": _growth_label(product),
                "recommendation_actions": _recommendation_actions(product, total_score),
            }
        )

    scored_items.sort(key=lambda item: (-item["total_score"], -float(item.get("total_gmv") or 0), item["product_id"]))
    for rank, item in enumerate(scored_items, start=1):
        item["rank"] = rank
    return scored_items


def _normalize(values: list[float]) -> list[float]:
    if not values:
        return []
    minimum = min(values)
    maximum = max(values)
    if maximum == minimum:
        return [100.0 for _ in values]
    return [round((value - minimum) / (maximum - minimum) * 100, 2) for value in values]


def _clip(value: Any, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 0.0
    return min(max(number, minimum), maximum)


def _video_interaction(product: dict[str, Any]) -> float:
    return (
        float(product.get("video_views") or 0) * 0.10
        + float(product.get("video_likes") or 0) * 0.45
        + float(product.get("video_favorites") or 0) * 0.25
        + float(product.get("video_shares") or 0) * 0.20
    )


def _growth_label(product: dict[str, Any]) -> str:
    sales_growth = float(product.get("sales_growth_rate") or 0)
    gmv_growth = float(product.get("gmv_growth_rate") or 0)
    if sales_growth >= 0.3 and gmv_growth >= 0.3:
        return "高增长"
    if sales_growth < -0.2 or gmv_growth < -0.2:
        return "下滑预警"
    return "稳定增长"


def _recommendation_actions(product: dict[str, Any], score: float) -> list[str]:
    actions: list[str] = []
    if score >= 80:
        actions.append("进入重点运营池，增加内容投放和库存准备。")
    elif score >= 65:
        actions.append("保持观察，优先测试达人种草和组合促销。")
    else:
        actions.append("暂不作为核心爆品，先优化卖点表达和评论问题。")

    if float(product.get("positive_rate") or 0) < 0.6:
        actions.append("好评率偏低，优先排查质量、物流和售后反馈。")
    if float(product.get("price_competitiveness") or 0) < 0.8:
        actions.append("价格竞争力不足，建议评估优惠券或套装定价。")
    if float(product.get("video_conversion_rate") or 0) < 0.01:
        actions.append("内容转化偏弱，建议重做开头卖点和购买理由。")
    return actions
