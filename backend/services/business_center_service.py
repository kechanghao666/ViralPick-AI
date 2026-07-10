from __future__ import annotations

from typing import Any

from backend.db import fetch_all, fetch_one
from backend.services.analytics_service import get_category_summary, get_hot_products, get_overview, get_sales_trend
from backend.services import hot_score_service


def get_executive_dashboard() -> dict[str, Any]:
    overview = get_overview()
    summary = overview.get("summary") or {}
    order_summary = _order_summary()
    inventory = get_inventory_summary()
    marketing = get_marketing_summary()
    risks = _risk_signals()
    opportunities = _growth_opportunities()
    actions = _today_actions(opportunities, risks, inventory, marketing)
    return {
        "headline": {
            "gmv": _num(order_summary.get("paid_amount"), summary.get("total_gmv")),
            "orders": _num(order_summary.get("order_count"), summary.get("total_sales_quantity")),
            "customer_unit_price": _num(order_summary.get("customer_unit_price")),
            "conversion_rate": _num(order_summary.get("conversion_rate")),
            "refund_rate": _num(order_summary.get("refund_rate")),
            "roi": marketing.get("summary", {}).get("roi", 0),
            "product_count": summary.get("product_count", 0),
            "risk_count": len(risks) or summary.get("high_risk_product_count", 0),
            "opportunity_count": len(opportunities),
        },
        "sales_trend": get_sales_trend(days=30),
        "top_categories": get_category_summary()[:6],
        "top_products": get_hot_products(limit=6),
        "risks": risks,
        "opportunities": opportunities,
        "today_actions": actions,
        "inventory": inventory,
        "marketing": marketing,
    }


def get_marketing_summary() -> dict[str, Any]:
    ad_summary = fetch_one(
        """
        SELECT
            ROUND(COALESCE(SUM(spend), 0), 2) AS spend,
            COALESCE(SUM(impressions), 0) AS impressions,
            COALESCE(SUM(clicks), 0) AS clicks,
            COALESCE(SUM(conversions), 0) AS conversions,
            ROUND(COALESCE(SUM(revenue), 0), 2) AS revenue
        FROM ad_metrics
        """
    ) or {}
    content_summary = fetch_one(
        """
        SELECT
            COALESCE(SUM(impressions), 0) AS impressions,
            COALESCE(SUM(interactions), 0) AS interactions,
            ROUND(COALESCE(SUM(guided_revenue), 0), 2) AS guided_revenue,
            ROUND(COALESCE(AVG(effect_score), 0), 2) AS avg_effect_score
        FROM content_metrics
        """
    ) or {}
    if not _has_metric(ad_summary, "spend") and not _has_metric(content_summary, "impressions"):
        fallback = fetch_one(
            """
            SELECT
                COALESCE(SUM(views), 0) AS impressions,
                COALESCE(SUM(likes + favorites + shares), 0) AS interactions,
                ROUND(COALESCE(AVG(conversion_rate), 0), 4) AS conversion_rate
            FROM video_metrics
            """
        ) or {}
        content_summary = {
            "impressions": fallback.get("impressions", 0),
            "interactions": fallback.get("interactions", 0),
            "guided_revenue": 0,
            "avg_effect_score": round(min(100, float(fallback.get("conversion_rate") or 0) * 1800), 2),
        }
    spend = float(ad_summary.get("spend") or 0)
    raw_revenue = float(ad_summary.get("revenue") or content_summary.get("guided_revenue") or 0)
    revenue = _normalize_attributed_revenue(raw_revenue, spend)
    clicks = int(ad_summary.get("clicks") or 0)
    impressions = int(ad_summary.get("impressions") or content_summary.get("impressions") or 0)
    conversions = int(ad_summary.get("conversions") or 0)
    return {
        "summary": {
            "spend": round(spend, 2),
            "impressions": impressions,
            "clicks": clicks,
            "ctr": round(clicks / impressions, 4) if impressions else 0,
            "conversions": conversions,
            "conversion_rate": round(conversions / clicks, 4) if clicks else 0,
            "revenue": round(revenue, 2),
            "roi": round(revenue / spend, 2) if spend else 0,
            "content_interactions": int(content_summary.get("interactions") or 0),
            "content_effect_score": content_summary.get("avg_effect_score", 0),
        },
        "campaigns": fetch_all(
            """
            SELECT
                campaign_name,
                platform,
                ROUND(SUM(spend), 2) AS spend,
                SUM(impressions) AS impressions,
                SUM(clicks) AS clicks,
                SUM(conversions) AS conversions,
                ROUND(SUM(revenue), 2) AS revenue,
                ROUND(CASE WHEN SUM(spend) > 0 THEN SUM(revenue) / SUM(spend) ELSE 0 END, 2) AS roi
            FROM ad_metrics
            GROUP BY campaign_name, platform
            ORDER BY roi DESC, revenue DESC
            LIMIT 10
            """
        ),
        "content_items": _content_items(),
        "suggestions": _marketing_suggestions(spend, revenue, clicks, impressions, content_summary),
    }


def get_inventory_summary() -> dict[str, Any]:
    inventory_summary = fetch_one(
        """
        SELECT
            COUNT(*) AS sku_count,
            SUM(CASE WHEN available_stock <= replenishment_threshold THEN 1 ELSE 0 END) AS replenishment_count,
            SUM(CASE WHEN slow_moving_days >= 14 THEN 1 ELSE 0 END) AS slow_moving_count,
            SUM(CASE WHEN stockout_risk IN ('high', '高', '高风险') THEN 1 ELSE 0 END) AS stockout_count
        FROM inventory_daily
        WHERE date = (SELECT MAX(date) FROM inventory_daily)
        """
    ) or {}
    after_sales = fetch_one(
        """
        SELECT
            COALESCE(SUM(refund_count), 0) AS refund_count,
            ROUND(COALESCE(SUM(refund_amount), 0), 2) AS refund_amount
        FROM after_sales
        """
    ) or {}
    if not _has_metric(inventory_summary, "sku_count"):
        fallback = fetch_one(
            """
            SELECT
                COUNT(*) AS sku_count,
                SUM(CASE WHEN risk_level = 'high' THEN 1 ELSE 0 END) AS stockout_count,
                SUM(CASE WHEN sales_growth_rate < -0.1 THEN 1 ELSE 0 END) AS slow_moving_count,
                SUM(CASE WHEN sales_growth_rate > 0.15 THEN 1 ELSE 0 END) AS replenishment_count
            FROM products
            """
        ) or {}
        inventory_summary = fallback
    return {
        "summary": {
            "sku_count": int(inventory_summary.get("sku_count") or 0),
            "replenishment_count": int(inventory_summary.get("replenishment_count") or 0),
            "slow_moving_count": int(inventory_summary.get("slow_moving_count") or 0),
            "stockout_count": int(inventory_summary.get("stockout_count") or 0),
            "refund_count": int(after_sales.get("refund_count") or 0),
            "refund_amount": float(after_sales.get("refund_amount") or 0),
        },
        "replenishment_items": _replenishment_items(),
        "after_sales_reasons": fetch_all(
            """
            SELECT reason, SUM(refund_count) AS refund_count, ROUND(SUM(refund_amount), 2) AS refund_amount
            FROM after_sales
            GROUP BY reason
            ORDER BY refund_count DESC, refund_amount DESC
            LIMIT 8
            """
        ),
        "actions": _inventory_actions(inventory_summary, after_sales),
    }


def _order_summary() -> dict[str, Any]:
    row = fetch_one(
        """
        SELECT
            COALESCE(SUM(order_count), 0) AS order_count,
            ROUND(COALESCE(SUM(paid_amount), 0), 2) AS paid_amount,
            ROUND(CASE WHEN SUM(order_count) > 0 THEN SUM(paid_amount) / SUM(order_count) ELSE 0 END, 2) AS customer_unit_price,
            ROUND(CASE WHEN SUM(paid_amount) > 0 THEN SUM(refund_amount) / SUM(paid_amount) ELSE 0 END, 4) AS refund_rate,
            ROUND(COALESCE(AVG(conversion_rate), 0), 4) AS conversion_rate
        FROM orders_daily
        """
    ) or {}
    if _has_metric(row, "paid_amount"):
        return row
    return fetch_one(
        """
        SELECT
            COALESCE(SUM(order_count), 0) AS order_count,
            ROUND(COALESCE(SUM(gmv), 0), 2) AS paid_amount,
            ROUND(CASE WHEN SUM(order_count) > 0 THEN SUM(gmv) / SUM(order_count) ELSE 0 END, 2) AS customer_unit_price,
            0 AS refund_rate,
            0 AS conversion_rate
        FROM sales_daily
        """
    ) or {}


def _normalize_attributed_revenue(raw_revenue: float, spend: float) -> float:
    if raw_revenue <= 0 or spend <= 0:
        return round(max(raw_revenue, 0), 2)
    paid_row = fetch_one(
        """
        SELECT ROUND(COALESCE(SUM(paid_amount), 0), 2) AS paid_amount
        FROM orders_daily
        """
    ) or {}
    paid_amount = float(paid_row.get("paid_amount") or 0)
    roi_cap = spend * 5.8
    store_cap = paid_amount * 0.18 if paid_amount else raw_revenue
    return round(min(raw_revenue, roi_cap, store_cap), 2)


def _risk_signals() -> list[dict[str, Any]]:
    return fetch_all(
        """
        SELECT
            product_id,
            product_name,
            category,
            risk_level,
            rating,
            positive_rate,
            sales_growth_rate,
            hot_potential_score,
            image_url
        FROM products
        WHERE risk_level = 'high' OR positive_rate < 0.75 OR sales_growth_rate < -0.12
        ORDER BY risk_level DESC, positive_rate ASC, sales_growth_rate ASC
        LIMIT 8
        """
    )


def _growth_opportunities() -> list[dict[str, Any]]:
    scored = hot_score_service.get_hot_scoring(limit=20).get("items") or []
    opportunities = []
    for item in scored:
        total_score = float(item.get("total_score") or 0)
        if total_score < 75:
            continue
        opportunities.append(
            {
                **item,
                "hot_potential_score": total_score,
                "sales_growth_rate": item.get("sales_growth_rate", 0),
                "gmv_growth_rate": item.get("gmv_growth_rate", 0),
            }
        )
    if opportunities:
        return opportunities[:8]
    return fetch_all(
        """
        SELECT
            product_id,
            product_name,
            category,
            platform,
            shop_name,
            total_gmv,
            sales_growth_rate,
            gmv_growth_rate,
            hot_potential_score,
            image_url
        FROM products
        WHERE hot_potential_score >= 70 OR sales_growth_rate > 0.12
        ORDER BY hot_potential_score DESC, sales_growth_rate DESC
        LIMIT 8
        """
    )


def _today_actions(opportunities: list[dict[str, Any]], risks: list[dict[str, Any]], inventory: dict[str, Any], marketing: dict[str, Any]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    if opportunities:
        top = opportunities[0]
        actions.append({"level": "high", "title": "放大增长商品", "content": f"优先复盘「{top['product_name']}」的价格、库存和投放承接。"})
    if risks:
        risk = risks[0]
        actions.append({"level": "warn", "title": "处理风险商品", "content": f"核查「{risk['product_name']}」近期评价、售后和转化变化。"})
    if inventory.get("summary", {}).get("replenishment_count", 0):
        actions.append({"level": "high", "title": "确认补货节奏", "content": "对高增长且库存紧张的商品先确认供应和发货时效。"})
    if marketing.get("summary", {}).get("roi", 0) < 1 and marketing.get("summary", {}).get("spend", 0) > 0:
        actions.append({"level": "warn", "title": "收紧低效投放", "content": "暂停低转化计划，把预算转向高互动素材和高毛利商品。"})
    if not actions:
        actions.append({"level": "normal", "title": "保持经营节奏", "content": "继续跟踪销售、口碑、竞品和库存变化，优先维护高潜商品。"})
    return actions[:5]


def _content_items() -> list[dict[str, Any]]:
    rows = fetch_all(
        """
        SELECT content_type, topic, product_name, impressions, interactions, guided_revenue, effect_score
        FROM content_metrics
        ORDER BY effect_score DESC, guided_revenue DESC, interactions DESC
        LIMIT 10
        """
    )
    if rows:
        return rows
    return fetch_all(
        """
        SELECT
            '内容素材' AS content_type,
            content_topic AS topic,
            p.product_name,
            views AS impressions,
            likes + favorites + shares AS interactions,
            0 AS guided_revenue,
            ROUND(conversion_rate * 100, 2) AS effect_score
        FROM video_metrics v
        JOIN products p ON p.product_id = v.product_id
        ORDER BY effect_score DESC, interactions DESC
        LIMIT 10
        """
    )


def _replenishment_items() -> list[dict[str, Any]]:
    rows = fetch_all(
        """
        SELECT product_id, product_name, available_stock, replenishment_threshold, stockout_risk, slow_moving_days
        FROM inventory_daily
        WHERE date = (SELECT MAX(date) FROM inventory_daily)
        ORDER BY available_stock <= replenishment_threshold DESC, slow_moving_days DESC
        LIMIT 10
        """
    )
    if rows:
        return rows
    return fetch_all(
        """
        SELECT
            product_id,
            product_name,
            0 AS available_stock,
            0 AS replenishment_threshold,
            CASE WHEN sales_growth_rate > 0.15 THEN '关注补货' WHEN sales_growth_rate < -0.1 THEN '滞销关注' ELSE '正常' END AS stockout_risk,
            CASE WHEN sales_growth_rate < -0.1 THEN 14 ELSE 0 END AS slow_moving_days
        FROM products
        ORDER BY sales_growth_rate DESC, hot_potential_score DESC
        LIMIT 10
        """
    )


def _marketing_suggestions(spend: float, revenue: float, clicks: int, impressions: int, content_summary: dict[str, Any]) -> list[str]:
    suggestions: list[str] = []
    ctr = clicks / impressions if impressions else 0
    if spend and revenue / spend < 1:
        suggestions.append("优先压缩低投产计划，把预算转向成交承接更好的商品。")
    if impressions and ctr < 0.02:
        suggestions.append("当前点击效率偏低，建议重做首图、标题利益点和前 3 秒内容钩子。")
    if int(content_summary.get("interactions") or 0) > 0:
        suggestions.append("复用高互动内容主题，扩展测评、对比、场景使用三类素材。")
    if not suggestions:
        suggestions.append("维持小步快跑测试节奏，按 ROI、点击率和成交贡献筛选素材。")
    return suggestions


def _inventory_actions(inventory_summary: dict[str, Any], after_sales: dict[str, Any]) -> list[str]:
    actions: list[str] = []
    if int(inventory_summary.get("replenishment_count") or 0):
        actions.append("优先确认补货阈值以下商品的供应、发货和活动库存。")
    if int(inventory_summary.get("slow_moving_count") or 0):
        actions.append("对滞销商品做价格、套装和内容卖点复盘，避免继续压货。")
    if int(after_sales.get("refund_count") or 0):
        actions.append("把退款原因和差评关键词联动排查，先处理高频体验问题。")
    if not actions:
        actions.append("库存和售后未出现集中异常，继续跟踪高增长商品的供给承接。")
    return actions


def _has_metric(row: dict[str, Any], key: str) -> bool:
    try:
        return float(row.get(key) or 0) > 0
    except (TypeError, ValueError):
        return False


def _num(*values: Any) -> float:
    for value in values:
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if number:
            return round(number, 4)
    return 0
