from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from backend.repositories import result_repository
from backend.services import (
    business_center_service,
    comment_nlp_service,
    competitor_service,
    forecast_service,
    hot_score_service,
    llm_adapter,
    product_service,
    sales_analysis_service,
)


REPORT_TITLE = "《店铺经营分析报告》"


def generate_report(product_id: str | None = None, use_llm: bool | None = None) -> dict[str, Any] | None:
    product = product_service.get_product(product_id) if product_id else None
    if product_id and not product:
        return None

    title = REPORT_TITLE
    hot_scoring = hot_score_service.get_hot_scoring(limit=10, product_id=product_id)
    comments = comment_nlp_service.get_comment_keywords(product_id=product_id, top_n=12)
    competitors = competitor_service.get_competitor_summary(product_id=product_id, limit=10)
    forecast = forecast_service.get_sales_forecast(product_id=product_id, days=7, save_result=True)
    sales_analysis = sales_analysis_service.get_sales_analysis()
    dashboard = business_center_service.get_executive_dashboard()
    marketing = business_center_service.get_marketing_summary()
    inventory = business_center_service.get_inventory_summary()
    visuals = _build_visuals(
        dashboard=dashboard,
        marketing=marketing,
        inventory=inventory,
    )

    sections = _build_sections(
        product=product,
        hot_scoring=hot_scoring,
        comments=comments,
        competitors=competitors,
        forecast=forecast,
        sales_analysis=sales_analysis,
        dashboard=dashboard,
        marketing=marketing,
        inventory=inventory,
    )
    base_markdown = _to_markdown(title, sections, visuals)
    ai_generation = llm_adapter.generate_report_markdown(
        title=title,
        sections=sections,
        context={
            "scope": "product" if product_id else "global",
            "product": product,
            "dashboard": dashboard,
            "hot_scoring": hot_scoring,
            "comments": comments,
            "competitors": competitors,
            "forecast": forecast,
            "sales_analysis": sales_analysis,
            "marketing": marketing,
            "inventory": inventory,
        },
        use_llm=use_llm,
    )
    report = {
        "report_id": f"R-{uuid4().hex[:12]}",
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "scope_type": "product" if product_id else "global",
        "product_id": product_id,
        "category": product.get("category") if product else None,
        "title": title,
        "sections": sections,
        "visuals": visuals,
        "markdown": base_markdown,
        "base_markdown": base_markdown,
        "enhanced_markdown": ai_generation.get("markdown"),
        "ai_generation": {key: value for key, value in ai_generation.items() if key != "markdown"},
        "data_disclaimer": "报告基于当前已接入的店铺经营数据生成，适合作为经营复盘和行动优先级参考。",
    }
    result_repository.save_report(report)
    return report


def get_report(report_id: str) -> dict[str, Any] | None:
    return result_repository.get_report(report_id)


def _build_sections(
    product: dict[str, Any] | None,
    hot_scoring: dict[str, Any],
    comments: dict[str, Any],
    competitors: dict[str, Any],
    forecast: dict[str, Any],
    sales_analysis: dict[str, Any],
    dashboard: dict[str, Any],
    marketing: dict[str, Any],
    inventory: dict[str, Any],
) -> list[dict[str, Any]]:
    hot_item = _matching_hot_item(product, hot_scoring) or (hot_scoring.get("items") or [None])[0]
    competitor_item = (competitors.get("items") or [None])[0]
    headline = dashboard.get("headline") or {}
    return [
        {
            "heading": "经营概览",
            "content": (
                f"当前店铺销售额 {_money(headline.get('gmv'))}，订单量 {_number(headline.get('orders'))}，"
                f"客单价 {_money(headline.get('customer_unit_price'))}，高潜商品 {_number(headline.get('opportunity_count'))} 个，"
                f"风险商品 {_number(headline.get('risk_count'))} 个。"
            ),
            "evidence": {"headline": headline},
        },
        {
            "heading": "商品表现",
            "content": _product_performance(product, sales_analysis, hot_item),
            "evidence": {"top_products": sales_analysis.get("rankings", {}).get("gmv", [])[:5]},
        },
        {
            "heading": "增长机会",
            "content": _growth_summary(hot_item, dashboard.get("opportunities") or []),
            "evidence": {"hot_scoring": hot_scoring.get("items", [])[:5]},
        },
        {
            "heading": "风险提醒",
            "content": _risk_summary(hot_item, forecast, dashboard.get("risks") or []),
            "evidence": {"risks": dashboard.get("risks", [])[:5]},
        },
        {
            "heading": "口碑分析",
            "content": _comment_summary(comments),
            "evidence": {
                "positive_keywords": comments.get("positive_keywords", [])[:8],
                "negative_keywords": comments.get("negative_keywords", [])[:8],
                "pain_points": comments.get("pain_points", [])[:5],
            },
        },
        {
            "heading": "竞品分析",
            "content": _competitor_summary(competitor_item),
            "evidence": {"competitors": competitors.get("items", [])[:5]},
        },
        {
            "heading": "投放内容",
            "content": _marketing_summary(marketing),
            "evidence": marketing.get("summary", {}),
        },
        {
            "heading": "库存售后",
            "content": _inventory_summary(inventory),
            "evidence": inventory.get("summary", {}),
        },
        {
            "heading": "趋势预测",
            "content": _forecast_summary(forecast),
            "evidence": forecast.get("summary", {}),
        },
        {
            "heading": "执行动作清单",
            "content": _action_summary(dashboard.get("today_actions") or [], inventory.get("actions") or [], marketing.get("suggestions") or []),
            "evidence": {"today_actions": dashboard.get("today_actions") or []},
        },
    ]


def _matching_hot_item(product: dict[str, Any] | None, hot_scoring: dict[str, Any]) -> dict[str, Any] | None:
    if not product:
        return None
    for item in hot_scoring.get("items") or []:
        if item.get("product_id") == product.get("product_id"):
            return item
    return None


def _product_performance(product: dict[str, Any] | None, sales_analysis: dict[str, Any], hot_item: dict[str, Any] | None) -> str:
    if product:
        return (
            f"{product['product_name']} 累计销量 {_number(product['total_sales_quantity'])}，销售额 {_money(product['total_gmv'])}，"
            f"评分 {_decimal(product['rating'])}，好评率 {_percent(product['positive_rate'])}。"
        )
    summary = sales_analysis.get("summary", {})
    leader = hot_item.get("product_name") if hot_item else "头部商品"
    return (
        f"当前覆盖 {_number(summary.get('product_count'))} 个商品，累计销量 {_number(summary.get('sales_quantity'))}，"
        f"销售额 {_money(summary.get('gmv'))}。{leader} 是现阶段需要重点复盘的商品。"
    )


def _growth_summary(hot_item: dict[str, Any] | None, opportunities: list[dict[str, Any]]) -> str:
    if hot_item:
        actions = "；".join((hot_item.get("recommendation_actions") or [])[:2]).rstrip("。；; ")
        return f"高潜商品为「{hot_item.get('product_name')}」，综合分 {hot_item.get('total_score')}，建议优先执行：{actions or '围绕价格、卖点和内容承接做小步测试'}。"
    if opportunities:
        names = "、".join(item.get("product_name", "") for item in opportunities[:3])
        return f"建议优先观察 {names}，围绕销量增长、内容承接和库存供给判断是否进入主推。"
    return "暂未发现明显高潜商品，建议继续观察销量、评论和竞品价格变化。"


def _risk_summary(hot_item: dict[str, Any] | None, forecast: dict[str, Any], risks: list[dict[str, Any]]) -> str:
    items: list[str] = []
    if hot_item and hot_item.get("risk_level") == "high":
        items.append("当前重点商品存在较高风险，需要先处理评价、售后或价格承接问题。")
    if forecast.get("summary", {}).get("trend_direction") == "down":
        items.append("短期趋势偏弱，应控制备货和投放节奏。")
    if risks:
        items.append(f"风险商品集中在「{risks[0].get('product_name')}」等 SKU，需要安排复盘。")
    return " ".join(items) if items else "当前未发现集中高风险信号，但仍需持续跟踪价格、评价、库存和竞品变化。"


def _comment_summary(comments: dict[str, Any]) -> str:
    positive = "、".join(item.get("word", "") for item in (comments.get("positive_keywords") or [])[:4])
    negative = "、".join(item.get("word", "") for item in (comments.get("negative_keywords") or [])[:4])
    pain = "、".join(item.get("pain_point", "") for item in (comments.get("pain_points") or [])[:3])
    return f"好评集中在 {positive or '商品体验'}，差评集中在 {negative or '少量体验问题'}。优先处理 {pain or '评价中反复出现的问题'}，并把高频好评词转化为商品详情和内容卖点。"


def _competitor_summary(competitor_item: dict[str, Any] | None) -> str:
    if not competitor_item:
        return "当前竞品信息不足，建议先录入同类商品的价格、销量、评分、好评率和核心卖点。"
    return (
        f"重点竞品为「{competitor_item.get('competitor_name')}」，价格差 {_money(competitor_item.get('price_gap'))}。"
        f"{competitor_item.get('pricing_suggestion')} {competitor_item.get('differentiation_suggestion')}"
    )


def _marketing_summary(marketing: dict[str, Any]) -> str:
    summary = marketing.get("summary") or {}
    suggestions = " ".join((marketing.get("suggestions") or [])[:2])
    return (
        f"当前投放花费 {_money(summary.get('spend'))}，曝光 {_number(summary.get('impressions'))}，"
        f"点击率 {_percent(summary.get('ctr'))}，ROI {_decimal(summary.get('roi'))}。{suggestions}"
    )


def _inventory_summary(inventory: dict[str, Any]) -> str:
    summary = inventory.get("summary") or {}
    actions = " ".join((inventory.get("actions") or [])[:2])
    return (
        f"当前库存关注商品 {_number(summary.get('replenishment_count'))} 个，滞销关注 {_number(summary.get('slow_moving_count'))} 个，"
        f"售后退款 {_number(summary.get('refund_count'))} 笔。{actions}"
    )


def _forecast_summary(forecast: dict[str, Any]) -> str:
    summary = forecast.get("summary") or {}
    direction = {"up": "上行", "down": "下行", "stable": "稳定"}.get(summary.get("trend_direction"), "稳定")
    return (
        f"未来 7 天销量趋势判断为{direction}，近期日均销量 {_number(summary.get('recent_avg_sales'))}，"
        f"预测日均销量 {_number(summary.get('forecast_avg_sales'))}。{summary.get('insight') or '建议结合库存和投放节奏继续观察。'}"
    )


def _action_summary(today_actions: list[dict[str, Any]], inventory_actions: list[str], marketing_suggestions: list[str]) -> str:
    actions = [item.get("content", "") for item in today_actions[:3]]
    actions.extend(inventory_actions[:1])
    actions.extend(marketing_suggestions[:1])
    cleaned = [action for action in actions if action]
    return " ".join(f"{index + 1}. {action}" for index, action in enumerate(cleaned[:5])) or "持续跟踪销售、商品、口碑、竞品、库存和投放变化。"


def _build_visuals(
    dashboard: dict[str, Any],
    marketing: dict[str, Any],
    inventory: dict[str, Any],
) -> dict[str, Any]:
    headline = dashboard.get("headline") or {}
    marketing_summary = marketing.get("summary") or {}
    inventory_summary = inventory.get("summary") or {}
    trend_rows = (dashboard.get("sales_trend") or [])[-12:]
    category_rows = (dashboard.get("top_categories") or [])[:6]
    actions = (dashboard.get("today_actions") or [])[:5]
    return {
        "kpis": [
            {"label": "销售额", "value": _money(headline.get("gmv")), "desc": "收入规模"},
            {"label": "订单量", "value": _number(headline.get("orders")), "desc": "成交活跃度"},
            {"label": "投产比", "value": _decimal(marketing_summary.get("roi")), "desc": "预算回报"},
            {"label": "风险商品", "value": _number(headline.get("risk_count")), "desc": "优先处理"},
            {"label": "补货关注", "value": _number(inventory_summary.get("replenishment_count")), "desc": "避免断货"},
            {"label": "售后笔数", "value": _number(inventory_summary.get("refund_count")), "desc": "体验问题"},
        ],
        "trend": [
            {
                "date": row.get("date"),
                "value": float(row.get("gmv") or row.get("sales_quantity") or 0),
                "display": _money(row.get("gmv") or row.get("sales_quantity")),
            }
            for row in trend_rows
        ],
        "categories": [
            {
                "category": row.get("category"),
                "value": float(row.get("gmv") or 0),
                "display": _money(row.get("gmv")),
            }
            for row in category_rows
        ],
        "actions": [
            {
                "title": item.get("title") or f"动作 {index + 1}",
                "content": item.get("content") or "",
                "level": item.get("level") or "normal",
            }
            for index, item in enumerate(actions)
        ],
    }


def _to_markdown(title: str, sections: list[dict[str, Any]], visuals: dict[str, Any]) -> str:
    lines = [f"# {title}", "", "## 核心指标"]
    for item in visuals.get("kpis") or []:
        lines.append(f"- {item['label']}：{item['value']}（{item['desc']}）")
    lines.extend(["", "## 收入走势"])
    for item in visuals.get("trend") or []:
        lines.append(f"- {item['date']}：{item['display']}")
    lines.extend(["", "## 类目贡献"])
    for item in visuals.get("categories") or []:
        lines.append(f"- {item['category']}：{item['display']}")
    lines.append("")
    for section in sections:
        lines.extend([f"## {section['heading']}", section["content"], ""])
    return "\n".join(lines).strip()


def _number(value: Any) -> str:
    try:
        return f"{float(value):,.0f}"
    except (TypeError, ValueError):
        return "0"


def _money(value: Any) -> str:
    try:
        return f"¥{float(value):,.0f}"
    except (TypeError, ValueError):
        return "¥0"


def _decimal(value: Any) -> str:
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "0.00"


def _percent(value: Any) -> str:
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return "0.0%"
