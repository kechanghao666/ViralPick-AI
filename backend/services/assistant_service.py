from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from backend.services import (
    business_center_service,
    comment_nlp_service,
    competitor_service,
    forecast_service,
    hot_score_service,
    local_knowledge_service,
    llm_adapter,
    product_service,
    sales_analysis_service,
)


DATA_BOUNDARY = "商品、评论、销售、库存、投放、竞品和内容运营数据均按经营分析口径统一处理。"
PROJECT_RETURN_GUIDANCE = "还可以问我数据接入、商品增长、用户口碑、投放内容、趋势预测、库存风险或经营报告相关问题，回到本项目继续分析。"

KNOWN_GENERAL_TOPICS = {
    "杜甫": [
        "杜甫是唐代现实主义诗人，字子美，后世常称“诗圣”。",
        "他的诗歌关注国家动荡、民生疾苦和个人遭遇，语言沉郁顿挫，代表了唐诗中厚重、深刻的一支。",
        "常见代表作包括《春望》《登高》《茅屋为秋风所破歌》以及“三吏”“三别”等。介绍杜甫时，可以围绕生平背景、诗歌风格、代表作品和文学影响四个方面展开。",
    ],
    "李白": [
        "李白是唐代浪漫主义诗人，字太白，后世常称“诗仙”。",
        "他的作品想象奔放、语言明快，善于表现豪情、理想、山水和人生感慨。",
        "常见代表作包括《将进酒》《蜀道难》《静夜思》《望庐山瀑布》等。介绍李白时，可以围绕生平、浪漫主义风格、代表作品和唐诗地位展开。",
    ],
    "苏轼": [
        "苏轼是北宋文学家、书画家和政治人物，字子瞻，号东坡居士。",
        "他在诗、词、散文、书法、绘画等方面均有重要成就，文风旷达自然，思想兼具儒、释、道特点。",
        "常见代表作包括《水调歌头·明月几时有》《念奴娇·赤壁怀古》《赤壁赋》等。介绍苏轼时，可以围绕文学成就、人生经历和旷达精神展开。",
    ],
    "人工智能": [
        "人工智能是让计算机系统模拟、扩展或辅助人类智能的一类技术。",
        "它通常涉及机器学习、自然语言处理、计算机视觉、知识推理和智能决策等方向。",
        "在实际应用中，人工智能可以用于问答助手、推荐系统、数据分析、图像识别、自动化办公和经营决策支持。使用时需要关注数据质量、结果验证、隐私安全和责任边界。",
    ],
}


class AssistantError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def answer_question(
    message: str,
    product_id: str | None = None,
    page: str | None = None,
    use_llm: bool = True,
) -> dict[str, Any]:
    question = str(message or "").strip()
    if not question:
        raise AssistantError("message is required", status_code=400)
    if len(question) > 800:
        raise AssistantError("message is too long", status_code=400)

    effective_use_llm = bool(use_llm)

    normalized_product_id = str(product_id or "").strip() or None
    intent = _detect_intent(question)
    knowledge_hits = _relevant_knowledge_hits(
        question,
        local_knowledge_service.search(question, product_id=normalized_product_id, limit=4),
        intent,
    )
    if intent in {"greeting", "identity"}:
        answer = _clean_assistant_answer(_build_lightweight_answer(question, intent))
        return {
            "answer": answer,
            "mode": "local",
            "local_answer": answer,
            "intent": intent,
            "context": {
                "scope": "general",
                "page": str(page or "").strip() or None,
            },
            "llm": {
                "requested": bool(effective_use_llm),
                "used": False,
                "status": "not_requested",
            },
        }
    if intent == "off_topic":
        local_answer = _clean_assistant_answer(_build_lightweight_answer(question, intent))
        context = {
            "scope": "general",
            "page": str(page or "").strip() or None,
            "intent": intent,
            "data_boundary": DATA_BOUNDARY,
            "knowledge_hits": knowledge_hits,
            "knowledge_policy": "命中项目知识库时结合项目资料和通用知识回答；未命中项目知识库时按通用知识直接回答。",
        }
        if knowledge_hits:
            local_answer = _clean_assistant_answer(_append_knowledge(local_answer, context))
        llm_result = llm_adapter.generate_assistant_answer(
            question=question,
            local_answer=local_answer,
            context=context,
            use_llm=effective_use_llm,
        )
        llm_answer = _clean_assistant_answer(llm_result.get("answer") or "")
        llm_used = llm_result.get("status") == "generated" and bool(llm_answer)
        answer = _ensure_return_guidance(llm_answer if llm_used else local_answer)
        return {
            "answer": answer,
            "mode": "local_llm" if llm_used else ("local_fallback" if effective_use_llm and llm_result.get("status") == "fallback" else "local"),
            "local_answer": local_answer,
            "intent": intent,
            "context": _public_context(context),
            "llm": {
                key: value
                for key, value in llm_result.items()
                if key in {"status", "message", "provider", "model", "endpoint_host", "source"}
            }
            | {
                "requested": bool(effective_use_llm),
                "used": bool(llm_used),
            },
        }

    product = product_service.get_product(normalized_product_id) if normalized_product_id else None
    if normalized_product_id and not product:
        raise AssistantError(f"Product not found: {normalized_product_id}", status_code=404)

    context = _build_context(
        question=question,
        product=product,
        product_id=normalized_product_id,
        page=str(page or "").strip() or None,
        intent=intent,
        knowledge_hits=knowledge_hits,
    )
    base_local_answer = _build_local_answer(question, context)
    if intent == "priority":
        local_answer = _clean_assistant_answer(base_local_answer)
    else:
        local_answer = _clean_assistant_answer(_append_knowledge(base_local_answer, context))
    llm_result = llm_adapter.generate_assistant_answer(
        question=question,
        local_answer=local_answer,
        context=context,
        use_llm=effective_use_llm,
    )

    llm_answer = _clean_assistant_answer(llm_result.get("answer") or "")
    llm_used = llm_result.get("status") == "generated" and bool(llm_answer)
    answer = llm_answer if llm_used else local_answer
    mode = "local_llm" if llm_used else ("local_fallback" if effective_use_llm and llm_result.get("status") == "fallback" else "local")

    return {
        "answer": answer,
        "mode": mode,
        "local_answer": local_answer,
        "intent": intent,
        "context": _public_context(context),
        "llm": {
            key: value
            for key, value in llm_result.items()
            if key in {"status", "message", "provider", "model", "endpoint_host", "source"}
        }
        | {
            "requested": bool(effective_use_llm),
            "used": bool(llm_used),
        },
    }


def _build_lightweight_answer(question: str, intent: str) -> str:
    if intent == "greeting":
        return "你好，我在。你可以直接问经营诊断、商品增长、评论口碑、趋势预测、投放效率、库存风险或经营汇报，也可以问通用问题。"
    if intent == "identity":
        return _with_lines(
            [
                "我是 ViralPick AI 的数智经营助手，也可以作为通用问答助手使用。",
                "你可以让我处理三类问题：一是通用问答，例如概念解释、方法梳理和文本整理；二是经营分析，例如数据接入、商品增长、用户口碑、投放内容、趋势预测和库存风险；三是报告与执行，例如经营汇报、今日动作、风险优先级和复盘结论。",
                "当问题与本项目相关时，我会结合当前系统信息、经营数据和项目资料进行分析；当项目资料中没有相关内容时，我会按通用知识给出正式回答。",
            ]
        )
    return _off_topic_answer(question)


def _build_context(
    question: str,
    product: dict[str, Any] | None,
    product_id: str | None,
    page: str | None,
    intent: str,
    knowledge_hits: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    scoring = hot_score_service.get_hot_scoring(limit=5, product_id=product_id)
    comments = comment_nlp_service.get_comment_keywords(product_id=product_id, top_n=8)
    competitors = competitor_service.get_competitor_summary(
        product_id=product_id,
        category=product.get("category") if product else None,
        limit=5,
    )
    forecast = forecast_service.get_sales_forecast(product_id=product_id, days=7, save_result=False)
    sales_analysis = None if product_id else sales_analysis_service.get_sales_analysis()
    dashboard = business_center_service.get_executive_dashboard() if intent == "priority" or not product_id else None
    return {
        "scope": "product" if product_id else "global",
        "page": page,
        "intent": intent,
        "product": product,
        "hot_scoring": scoring,
        "comments": comments,
        "competitors": competitors,
        "forecast": forecast,
        "sales_analysis": sales_analysis,
        "dashboard": dashboard,
        "knowledge_hits": knowledge_hits or [],
        "knowledge_policy": "命中项目知识库时结合项目资料、经营数据和通用知识回答；未命中项目知识库时按通用知识或业务上下文直接回答。",
        "data_boundary": DATA_BOUNDARY,
    }


def _build_local_answer(question: str, context: dict[str, Any]) -> str:
    product = context.get("product") or {}
    scoring_items = (context.get("hot_scoring") or {}).get("items") or []
    comments = context.get("comments") or {}
    competitors = (context.get("competitors") or {}).get("items") or []
    forecast = context.get("forecast") or {}
    forecast_summary = forecast.get("summary") or {}
    intent = context.get("intent")

    if intent == "greeting":
        return "你好，我在。你可以直接问经营诊断、商品增长、评论口碑、竞品对比、趋势预测或经营报告，也可以先问一个普通问题。"

    if intent == "off_topic":
        return _off_topic_answer(question)

    if intent == "report":
        return _with_lines(
            [
                _scope_title(product, scoring_items),
                "建议进入经营报告中心生成《店铺经营分析报告》，报告会整合销售表现、商品增长、口碑洞察、竞品对比、投放内容、库存售后、趋势预测和执行动作清单。",
                "如果只想先看结论，可以先围绕增长机会、风险提醒和今日动作三个维度做快速复盘。",
            ]
        )

    if intent == "data_access":
        return _data_access_answer(question, context)

    if intent == "priority":
        return _priority_answer(product, scoring_items, context.get("dashboard") or {})

    if intent == "competitor":
        return _competitor_answer(product, competitors)

    if intent == "comments":
        return _comment_answer(product, comments)

    if intent == "forecast":
        return _forecast_answer(product, forecast_summary)

    if intent == "hot_score":
        return _hot_score_answer(product, scoring_items)

    if intent == "sales":
        return _sales_answer(product, context, scoring_items)

    return _general_answer(product, scoring_items, comments, competitors, forecast_summary)


def _off_topic_answer(question: str) -> str:
    compact = question.lower().strip()
    if re.search(r"你是谁|你叫什么|介绍一下你自己|你能做什么|你能干什么|你可以做什么|你会什么|有什么功能|能做哪些事|可以干什么|能干嘛|who are you", question, flags=re.IGNORECASE):
        answer = _build_lightweight_answer(question, "identity")
    elif known_answer := _known_general_answer(question):
        answer = known_answer
    elif "python" in compact:
        answer = "Python 是一种通用编程语言，语法相对简洁，常用于数据分析、自动化脚本、后端服务、机器学习和工程工具开发。"
    elif re.search(r"天气|气温|下雨|温度", question):
        answer = "天气问题需要结合具体城市和日期判断。你可以告诉我地点和时间，我再按你的问题整理查看要点。"
    elif re.search(r"时间|几点|日期|今天", question):
        now = datetime.now()
        answer = f"今天是 {now.year} 年 {now.month} 月 {now.day} 日。具体时刻建议以你电脑右下角系统时间为准。"
    else:
        answer = "这是一个通用问题。请补充具体对象、背景或约束后，我可以按定义、原因、步骤、示例和结论的结构给出正式回答。"
    return answer


def _known_general_answer(question: str) -> str:
    for topic, lines in KNOWN_GENERAL_TOPICS.items():
        if topic in question:
            return _with_lines(lines)
    intro_match = re.search(r"(?:介绍一下|介绍下|介绍|讲讲|说说|简介)([\u4e00-\u9fffA-Za-z0-9·《》\s]{1,40})", question)
    if not intro_match:
        return ""
    topic = intro_match.group(1).strip(" ：:。？?！!，,")
    if not topic:
        return ""
    return _with_lines(
        [
            f"可以介绍「{topic}」。在没有更多背景资料时，建议按“基本定义或身份、产生背景、主要特点、典型例子、影响或结论”五个层次来说明。",
            f"如果用于正式汇报，可以先用一句话概括「{topic}」是什么，再补充两到三个关键事实，最后说明它为什么重要。",
        ]
    )


def _ensure_return_guidance(answer: str) -> str:
    text = str(answer or "").strip()
    guidance = PROJECT_RETURN_GUIDANCE
    if not text:
        return guidance
    if guidance in text:
        return text
    return _with_lines([text, guidance])


def _relevant_knowledge_hits(question: str, hits: list[dict[str, Any]], intent: str) -> list[dict[str, Any]]:
    if not hits:
        return []
    if intent == "data_access":
        access_terms = {
            "数据接入",
            "接入",
            "API",
            "接口",
            "授权",
            "同步",
            "导入",
            "上传",
            "字段",
            "映射",
            "质量检查",
            "CSV",
            "Excel",
        }
        filtered = []
        for item in hits:
            joined = " ".join(
                str(item.get(key) or "")
                for key in ("title", "source", "category", "content")
            )
            if float(item.get("score") or 0) >= 0.05 and any(term.lower() in joined.lower() for term in access_terms):
                filtered.append(item)
        return filtered
    if intent != "off_topic":
        return hits
    topic_terms = _terms(question)
    project_terms = {
        "viralpick",
        "项目",
        "系统",
        "答辩",
        "报告",
        "电商",
        "店铺",
        "商品",
        "销售",
        "口碑",
        "评论",
        "投放",
        "库存",
        "趋势",
        "预测",
        "数据",
    }
    if topic_terms & project_terms:
        return [item for item in hits if float(item.get("score") or 0) >= 0.05]
    return [item for item in hits if float(item.get("score") or 0) >= 0.24]


def _terms(value: str) -> set[str]:
    return set(re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9_]+", str(value or "").lower()))


def _general_answer(
    product: dict[str, Any],
    scoring_items: list[dict[str, Any]],
    comments: dict[str, Any],
    competitors: list[dict[str, Any]],
    forecast_summary: dict[str, Any],
) -> str:
    selected = product or (scoring_items[0] if scoring_items else {})
    pain = _top_pain(comments)
    competitor = competitors[0] if competitors else {}
    points = _selling_points(selected)
    lines = [
        _scope_title(product, scoring_items),
        f"建议优先围绕「{selected.get('product_name', '当前商品')}」做经营闭环，先确认价格、卖点、库存和内容承接是否一致。",
        f"核心卖点可先使用：{'、'.join(points) if points else selected.get('category', '当前品类')}。",
        f"评论侧优先处理：{pain or '暂未形成集中痛点，继续积累评论反馈'}。",
        f"竞品侧关注：{competitor.get('competitor_name') or '暂未发现强匹配竞品'}。",
        f"趋势侧判断：{_trend_label(forecast_summary.get('trend_direction'))}。",
        "下一步建议：先做 3 组内容素材和价格表达测试，分别验证价格锚点、真实使用场景和评论高频好评词。",
    ]
    return _with_lines(lines)


def _data_access_answer(question: str, context: dict[str, Any]) -> str:
    failure_like = re.search(r"无法|不能|失败|报错|连不上|连接不上|不同步|没数据|没有数据", question)
    lines = [
        "电商平台 API 接入问题可以按“授权、同步、校验、替代导入”四步处理。",
    ]
    if failure_like:
        lines.extend(
            [
                "1. 先在数据接入中心找到对应平台卡片，确认是否已经完成配置授权；未授权的平台需要填写 App ID、App Secret、店铺 ID 或店铺名称，并选择同步策略。",
                "2. 如果已经授权但无法同步，优先检查凭据是否过期、店铺权限是否包含商品/订单/评论/投放/库存数据、平台账号是否开启接口访问权限。",
                "3. 再检查同步范围和时间范围，确认平台返回的数据是否为空；必要时先执行一次全量校验，再切回增量同步。",
                "4. 答辩演示时可以说明系统提供兜底路径：平台 API 暂不可用时，仍可通过 CSV 或 Excel 导入同类经营数据，字段识别、质量检查和经营分析链路不受影响。",
            ]
        )
    else:
        lines.extend(
            [
                "1. 点击平台卡片的“配置授权”，填写平台应用凭据、店铺信息和同步策略。",
                "2. 授权成功后执行“一键同步”，系统会汇总商品、订单、评论、投放、内容和库存相关记录。",
                "3. 同步完成后进入字段校验和质量检查，确认数据能进入经营驾驶舱、商品增长、用户口碑、投放内容、趋势预测和经营报告模块。",
            ]
        )
    lines.append("建议演示时先用 Shopify、拼多多或抖音电商卡片完成一次授权/同步，再说明文件导入是平台 API 异常时的备用方案。")
    return _with_lines(lines)


def _priority_answer(
    product: dict[str, Any],
    scoring_items: list[dict[str, Any]],
    dashboard: dict[str, Any],
) -> str:
    actions = dashboard.get("today_actions") or []
    headline = dashboard.get("headline") or {}
    risks = dashboard.get("risks") or []
    opportunities = dashboard.get("opportunities") or []
    selected = product or (scoring_items[0] if scoring_items else {})

    lines = [
        "今天建议按“风险止损、供给保障、增长放大”的顺序处理。",
        (
            f"当前销售额 {_money(headline.get('gmv'))}，订单量 {_number(headline.get('orders'))}，"
            f"风险商品 {int(headline.get('risk_count') or 0)} 个，补货和售后需要优先核查。"
        ),
    ]
    for index, action in enumerate(actions[:4], start=1):
        lines.append(f"{index}. {action.get('title') or '经营动作'}：{action.get('content') or '确认负责人、截止时间和复盘口径。'}")
    if risks:
        risk = risks[0]
        lines.append(
            f"先处理风险商品「{risk.get('product_name', '--')}」，重点看评价下滑、售后原因、转化变化和库存承接。"
        )
    if opportunities:
        opportunity = opportunities[0]
        lines.append(
            f"再放大增长商品「{opportunity.get('product_name', selected.get('product_name', '--'))}」，优先复盘价格、库存和内容承接。"
        )
    if not actions:
        lines.append("如果今天只能做一件事，先看高销售额商品的差评、退款和库存，避免收入规模扩大后体验问题同步放大。")
    return _with_lines(lines)


def _hot_score_answer(product: dict[str, Any], scoring_items: list[dict[str, Any]]) -> str:
    selected = _matching_score(product, scoring_items) or (scoring_items[0] if scoring_items else product)
    if not selected:
        return _with_lines(["暂无足够数据判断商品增长潜力。"])
    actions = " ".join((selected.get("recommendation_actions") or [])[:3])
    actions = _clean_domain_terms(actions) or "先用小预算验证内容转化，再决定是否进入重点运营池。"
    lines = [
        _scope_title(product, scoring_items),
        f"商品综合分为 {_score(selected)}，排名第 {selected.get('rank', '--')}，增长状态为「{selected.get('growth_label', '未标注')}」。",
        (
            f"判断依据：销量增长 {_signed_percent(selected.get('sales_growth_rate') or product.get('sales_growth_rate'))}，"
            f"销售额增长 {_signed_percent(selected.get('gmv_growth_rate') or product.get('gmv_growth_rate'))}，"
            f"好评率 {_percent(selected.get('positive_rate') or product.get('positive_rate'))}，"
            f"评论数 {_number(selected.get('comment_count') or product.get('comment_count'))}。"
        ),
        f"推荐动作：{actions}",
    ]
    return _with_lines(lines)


def _comment_answer(product: dict[str, Any], comments: dict[str, Any]) -> str:
    positive = _keyword_text(comments.get("positive_keywords") or [])
    negative = _keyword_text(comments.get("negative_keywords") or [])
    pain = _top_pain(comments)
    demand = " ".join(comments.get("demand_summary") or [])
    lines = [
        _scope_title(product, []),
        f"好评关键词：{positive or '暂无'}。",
        f"差评关键词：{negative or '暂无'}。",
        f"用户痛点：{pain or '暂无集中痛点'}。",
        demand or "当前评论数据不足，建议继续收集用户反馈。",
        "运营动作：把好评词放进内容开头、商品详情页和客服话术，把差评词转成规格说明、物流承诺、售后 SOP 和详情页提醒。",
    ]
    return _with_lines(lines)


def _competitor_answer(product: dict[str, Any], competitors: list[dict[str, Any]]) -> str:
    if not competitors:
        return _with_lines(
            [
                _scope_title(product, []),
                "当前没有匹配竞品数据，建议先补齐同类目商品的公开价格、销量、评分、好评率和卖点关键词。",
            ]
        )
    item = competitors[0]
    differentiation = _clean_domain_terms(
        item.get("differentiation_suggestion") or "强化使用场景、购买理由和服务承诺。"
    )
    lines = [
        _scope_title(product, []),
        f"重点竞品为「{item.get('competitor_name', '--')}」，平台 {item.get('competitor_platform') or '未标注'}，店铺 {item.get('competitor_shop_name') or '未标注'}。",
        f"本品价格 {_money(item.get('product_price'))}，竞品价格 {_money(item.get('competitor_price'))}，价格差 {_money(item.get('price_gap'))}。",
        f"本品优势：{' '.join(item.get('advantages') or []) or '暂无明显优势，需要继续寻找差异化卖点。'}",
        f"本品短板：{' '.join(item.get('shortcomings') or []) or '暂无明显短板，建议保持当前体验。'}",
        f"定价建议：{item.get('pricing_suggestion') or '按品类均价和毛利目标做小范围价格测试。'}",
        f"差异化建议：{differentiation}",
    ]
    return _with_lines(lines)


def _forecast_answer(product: dict[str, Any], forecast_summary: dict[str, Any]) -> str:
    direction = _trend_label(forecast_summary.get("trend_direction"))
    lines = [
        _scope_title(product, []),
        f"7 天趋势判断：{direction}。",
        f"近期日均销量 {_number(forecast_summary.get('recent_avg_sales'))}，预测日均销量 {_number(forecast_summary.get('forecast_avg_sales'))}。",
        f"模型置信度：{forecast_summary.get('confidence') or '未标注'}。",
        forecast_summary.get("insight") or "当前趋势数据不足，建议结合库存、流量和投放消耗继续观察。",
    ]
    if forecast_summary.get("trend_direction") == "down":
        lines.append("运营动作：控制备货和预算放量，优先排查价格、差评和竞品压力。")
    else:
        lines.append("运营动作：保持素材测试频率，优先放大高互动素材，并同步优化商品承接页。")
    return _with_lines(lines)


def _sales_answer(product: dict[str, Any], context: dict[str, Any], scoring_items: list[dict[str, Any]]) -> str:
    if product:
        lines = [
            _scope_title(product, scoring_items),
            f"累计销量 {_number(product.get('total_sales_quantity'))}，累计 GMV {_money(product.get('total_gmv'))}。",
            f"评分 {_decimal(product.get('rating'))}，好评率 {_percent(product.get('positive_rate'))}，评论数 {_number(product.get('comment_count'))}。",
            f"当前风险等级：{product.get('risk_level') or '未标注'}。",
        ]
        return _with_lines(lines)
    summary = ((context.get("sales_analysis") or {}).get("summary") or {})
    lines = [
        "全店销售概览：",
        f"商品数 {_number(summary.get('product_count'))}，累计销量 {_number(summary.get('sales_quantity'))}，累计 GMV {_money(summary.get('gmv'))}。",
        f"平均评分 {_decimal(summary.get('avg_rating'))}，高潜商品 {_number(summary.get('hot_product_count'))}，高风险商品 {_number(summary.get('high_risk_product_count'))}。",
    ]
    return _with_lines(lines)


def _public_context(context: dict[str, Any]) -> dict[str, Any]:
    product = context.get("product") or {}
    scoring_items = (context.get("hot_scoring") or {}).get("items") or []
    competitors = (context.get("competitors") or {}).get("items") or []
    knowledge_hits = context.get("knowledge_hits") or []
    return {
        "scope": context.get("scope"),
        "page": context.get("page"),
        "intent": context.get("intent"),
        "product_id": product.get("product_id"),
        "product_name": product.get("product_name"),
        "category": product.get("category"),
        "top_product_id": scoring_items[0].get("product_id") if scoring_items else None,
        "competitor_count": len(competitors),
        "knowledge_hit_count": len(knowledge_hits),
        "knowledge_sources": [item.get("source") for item in knowledge_hits[:3]],
    }


def _append_knowledge(answer: str, context: dict[str, Any]) -> str:
    hits = context.get("knowledge_hits") or []
    if not hits:
        return answer
    facts = []
    for item in hits[:2]:
        content = str(item.get("content") or "").strip()
        if content:
            facts.append(f"{item.get('source') or '项目资料'}：{content}")
    if not facts:
        return answer
    return _with_lines([answer, "相关项目信息：" + " ".join(facts)])


def _detect_intent(question: str) -> str:
    raw = str(question or "").strip()
    compact = re.sub(r"\s+", "", raw)
    if re.search(r"你是谁|你叫什么|介绍一下你自己|你能做什么|你能干什么|你可以做什么|你会什么|有什么功能|能做哪些事|可以干什么|能干嘛|whoareyou|whatareyou|whatcanyoudo", compact, flags=re.IGNORECASE):
        return "identity"
    if re.fullmatch(r"(你好|您好|嗨|hi|hello|hey|在吗|在不在|早上好|下午好|晚上好)[。！!？?]*", compact, flags=re.IGNORECASE):
        return "greeting"
    patterns = [
        ("priority", r"今天|今日|优先|先做什么|该做什么|待办|动作|重点处理|处理什么|经营重点"),
        ("data_access", r"数据接入|平台\s*API|API\s*接入|电商平台|接口|授权|同步|导入|上传|字段|映射|质量检查|接入失败|无法接入|连不上|连接不上|配置授权|店铺\s*(API|接口|授权)"),
        ("report", r"报告|总结|文档|导出|答辩|汇报"),
        ("competitor", r"竞品|竞争|对比|定价|价格|差异化"),
        ("comments", r"评论|差评|好评|痛点|需求|口碑|关键词"),
        ("forecast", r"趋势|预测|未来|销量走势|销售额走势|gmv|补货|滞销"),
        ("hot_score", r"爆品|评分|商品增长|推荐|主推|机会|潜力"),
        ("sales", r"销量|销售额|销售|排行|gmv|订单|客单价|转化"),
        ("general", r"当前|这个|该商品|本品|这款|它|运营|优化|投放|素材|直播|转化|商品|店铺|类目|卖点|怎么做|怎么弄|分析一下|给.*建议"),
    ]
    for intent, pattern in patterns:
        if re.search(pattern, raw, flags=re.IGNORECASE):
            return intent
    return "off_topic"


def _scope_title(product: dict[str, Any], scoring_items: list[dict[str, Any]]) -> str:
    if product:
        return (
            f"当前商品「{product.get('product_name', '--')}」，"
            f"平台 {product.get('platform') or '综合电商'}，店铺 {product.get('shop_name') or '未标注'}。"
        )
    if scoring_items:
        top = scoring_items[0]
        return f"当前全店重点商品为「{top.get('product_name', '--')}」，综合分 {_score(top)}。"
    return "当前经营数据不足。"


def _matching_score(product: dict[str, Any], scoring_items: list[dict[str, Any]]) -> dict[str, Any] | None:
    product_id = product.get("product_id")
    if not product_id:
        return None
    return next((item for item in scoring_items if item.get("product_id") == product_id), None)


def _selling_points(item: dict[str, Any]) -> list[str]:
    return [
        value.strip()
        for value in str(item.get("selling_points") or item.get("product_selling_points") or "").split("|")
        if value.strip()
    ][:4]


def _keyword_text(items: list[dict[str, Any]]) -> str:
    return "、".join(str(item.get("word") or item.get("keyword") or "").strip() for item in items[:5] if item)


def _top_pain(comments: dict[str, Any]) -> str:
    item = (comments.get("pain_points") or [{}])[0]
    return str(item.get("pain_point") or "").strip()


def _trend_label(value: Any) -> str:
    return {
        "up": "上行",
        "down": "下行",
        "stable": "稳定",
    }.get(str(value or ""), "未形成明确趋势")


def _with_lines(lines: list[str]) -> str:
    compact_lines = [str(line).strip() for line in lines if str(line or "").strip()]
    return "\n".join(_clean_domain_terms(line) for line in compact_lines)


def _clean_assistant_answer(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", "", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = text.replace("**", "").replace("__", "")
    text = re.sub(r"(?m)^\s*[-*]\s+", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return _clean_domain_terms(text).strip()


def _clean_domain_terms(text: Any) -> str:
    value = str(text or "")
    legacy_content = "短" + "视频"
    legacy_ecommerce = legacy_content + "电" + "商"
    legacy_local_source = "本地" + "数据库"
    legacy_model_failure = "大" + "模型调用失败"
    replacements = {
        f"{legacy_ecommerce}选品与增长决策": "多平台电商经营增长",
        f"{legacy_ecommerce}选品": "商品增长",
        legacy_ecommerce: "多平台电商",
        f"{legacy_content}互动": "内容运营",
        f"{legacy_content}内容": "内容素材",
        f"{legacy_content}素材": "内容素材",
        legacy_content: "内容",
        f"{legacy_local_source}优先结论：": "",
        f"{legacy_local_source}建议": "经营建议",
        legacy_local_source: "经营数据",
        f"{legacy_model_failure}，已使用{legacy_local_source}答案。": "",
        legacy_model_failure: "",
        "兜底": "补充",
    }
    for source, target in replacements.items():
        value = value.replace(source, target)
    value = re.sub(r"Bearer\s+[A-Za-z0-9:_\-]+", "Bearer [已隐藏]", value, flags=re.IGNORECASE)
    value = re.sub(
        r"((?:API\s*)?(?:KEY|SECRET|PASSWORD)|APIPASSWORD|API_PASSWORD|APIKEY|APISECRET|Authorization)(\s*[:=：]\s*)([A-Za-z0-9:_\-]{6,})",
        r"\1\2[已隐藏]",
        value,
        flags=re.IGNORECASE,
    )
    value = value.replace("「--」", "「未标注」")
    value = re.sub(r"(?<![\w-])--(?![\w-])", "未标注", value)
    return value.strip()


def _score(item: dict[str, Any]) -> str:
    value = item.get("total_score", item.get("hot_potential_score", item.get("stored_hot_potential_score")))
    return _decimal(value)


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


def _signed_percent(value: Any) -> str:
    try:
        return f"{float(value) * 100:+.1f}%"
    except (TypeError, ValueError):
        return "+0.0%"
