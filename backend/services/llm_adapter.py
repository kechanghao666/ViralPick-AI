from __future__ import annotations

import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

from backend.config import APP_ENV, BASE_DIR


DEFAULT_PROVIDER = "spark-x"
DEFAULT_MODEL = "spark-x"
DEFAULT_ENDPOINT = "https://spark-api-open.xf-yun.com/x2/chat/completions"
ASSISTANT_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="assistant-llm")


@dataclass(frozen=True)
class LlmConfig:
    enabled: bool
    provider: str
    model: str
    endpoint: str
    api_password: str
    timeout_seconds: int
    source: str

    @property
    def configured(self) -> bool:
        return bool(self.endpoint and self.api_password)


def get_status() -> dict[str, Any]:
    config = _load_config()
    parsed_endpoint = urlparse(config.endpoint) if config.endpoint else None
    return {
        "enabled": config.enabled,
        "configured": config.configured,
        "provider": config.provider,
        "model": config.model,
        "endpoint_host": parsed_endpoint.netloc if parsed_endpoint else None,
        "endpoint_scheme": parsed_endpoint.scheme if parsed_endpoint else None,
        "supports_report_generation": config.configured,
        "supports_assistant": config.configured,
        "reason": "ready" if config.configured else "not_ready",
        "source": config.source,
    }


def generate_report_markdown(
    title: str,
    sections: list[dict[str, Any]],
    context: dict[str, Any],
    use_llm: bool | None = None,
) -> dict[str, Any]:
    config = _load_config()
    requested = config.enabled if use_llm is None else bool(use_llm)
    if not requested:
        return _status("disabled", config, "智能增强未启用")
    if not config.configured:
        return _status("not_configured", config, "暂时无法生成增强内容")

    prompt = _build_prompt(title=title, sections=sections, context=context)
    report_timeout = min(config.timeout_seconds, _env_int("VIRALPICK_REPORT_LLM_TIMEOUT_SECONDS", 8))
    future = ASSISTANT_EXECUTOR.submit(_request_report_completion, config, prompt, report_timeout)
    try:
        content = future.result(timeout=report_timeout)
    except TimeoutError:
        return _status("fallback", config, "已生成标准分析报告")
    except Exception as exc:
        return _status("fallback", config, _safe_error_message(exc, config))

    if not content:
        return _status("fallback", config, "已生成标准分析报告")
    return {
        **_status("generated", config, "增强分析报告已生成"),
        "markdown": content.strip(),
    }

    try:
        response = requests.post(
            config.endpoint,
            headers={
                "Authorization": f"Bearer {config.api_password}",
                "Content-Type": "application/json",
            },
            json={
                "model": config.model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "你是多平台电商经营数据分析专家。只基于用户提供的结构化数据生成报告，"
                            "不要编造不存在的数据或平台来源。输出中文 Markdown。"
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.25,
                "thinking": {"type": "disabled"},
                "stream": False,
            },
            timeout=config.timeout_seconds,
        )
        response.raise_for_status()
        content = _extract_content(response.json())
    except Exception as exc:
        return _status("fallback", config, _safe_error_message(exc, config))

    if not content:
        return _status("fallback", config, "已生成标准分析报告")
    return {
        **_status("generated", config, "增强分析报告已生成"),
        "markdown": content.strip(),
    }


def generate_assistant_answer(
    question: str,
    local_answer: str,
    context: dict[str, Any],
    use_llm: bool | None = None,
) -> dict[str, Any]:
    config = _load_config()
    requested = config.enabled if use_llm is None else bool(use_llm)
    if not requested:
        return _status("disabled", config, "已生成经营建议")
    if not config.configured:
        return _status("not_configured", config, "已生成经营建议")

    prompt = _build_assistant_prompt(
        question=question,
        local_answer=local_answer,
        context=context,
    )
    assistant_timeout = min(config.timeout_seconds, _env_int("VIRALPICK_ASSISTANT_LLM_TIMEOUT_SECONDS", 20))
    future = ASSISTANT_EXECUTOR.submit(_request_assistant_completion, config, prompt, assistant_timeout)
    try:
        content = future.result(timeout=assistant_timeout)
    except (TimeoutError, Exception):
        return _status("fallback", config, "已生成经营建议")

    if not content:
        return _status("fallback", config, "已生成经营建议")
    return {
        **_status("generated", config, "已生成经营建议"),
        "answer": content.strip(),
    }


def _request_report_completion(config: LlmConfig, prompt: str, timeout_seconds: int) -> str:
    response = requests.post(
        config.endpoint,
        headers={
            "Authorization": f"Bearer {config.api_password}",
            "Content-Type": "application/json",
        },
        json={
            "model": config.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是多平台电商经营数据分析专家。只基于用户提供的结构化数据生成报告，"
                        "不要编造不存在的数据或平台来源。输出中文 Markdown。"
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.25,
            "thinking": {"type": "disabled"},
            "stream": False,
        },
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    return _extract_content(response.json()).strip()


def _request_assistant_completion(config: LlmConfig, prompt: str, timeout_seconds: int) -> str:
    response = requests.post(
        config.endpoint,
        headers={
            "Authorization": f"Bearer {config.api_password}",
            "Content-Type": "application/json",
        },
        json={
            "model": config.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是 ViralPick AI 的通用智能助手，也熟悉多平台电商经营分析。"
                        "用户问题与经营资料相关时，结合给定资料库命中和业务上下文回答；资料不足或问题无关时，直接用通用知识回答。"
                        "不要编造未提供的真实经营数据、销量、平台抓取结果或密钥信息。"
                        "回答直接自然，不要提及内部查询链路、接口状态、配置状态或失败回退。"
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "thinking": {"type": "disabled"},
            "stream": False,
        },
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    return _extract_content(response.json()).strip()


def _load_config() -> LlmConfig:
    file_config = _load_file_config()
    endpoint_from_env = os.getenv("VIRALPICK_LLM_ENDPOINT")
    password_from_env = os.getenv("VIRALPICK_LLM_API_PASSWORD")
    endpoint = endpoint_from_env or file_config.get("endpoint") or DEFAULT_ENDPOINT
    api_password = password_from_env or file_config.get("api_password") or ""
    enabled = _env_flag("VIRALPICK_LLM_ENABLED", default=False)
    source = "environment" if password_from_env else file_config.get("source", "environment")
    return LlmConfig(
        enabled=enabled,
        provider=os.getenv("VIRALPICK_LLM_PROVIDER", DEFAULT_PROVIDER),
        model=os.getenv("VIRALPICK_LLM_MODEL", DEFAULT_MODEL),
        endpoint=endpoint,
        api_password=api_password,
        timeout_seconds=_env_int("VIRALPICK_LLM_TIMEOUT_SECONDS", 60),
        source=source if api_password else "environment",
    )


def _load_file_config() -> dict[str, str]:
    configured_path = os.getenv("VIRALPICK_LLM_CONFIG_FILE")
    candidate = Path(configured_path.strip().strip("\"'")) if configured_path else BASE_DIR.parent / "API.txt"
    if APP_ENV == "production" and not configured_path:
        return {}
    if not candidate.exists():
        return {}

    text = _read_text(candidate)
    api_password = _match_first(
        text,
        [
            r"API\s*PASSWORD[^\w\r\n]*([A-Za-z0-9:_\-]{10,})",
            r"APIPASSWORD[^\w\r\n]*([A-Za-z0-9:_\-]{10,})",
            r"api_password[^\w\r\n]*([A-Za-z0-9:_\-]{10,})",
        ],
    )
    endpoint = _match_first(
        text,
        [
            r"X2[^\r\n]*(https://[^\s\r\n]+/chat/completions)",
            r"(https://[^\s\r\n]+/x2/chat/completions)",
            r"(https://[^\s\r\n]+/v2/chat/completions)",
        ],
    )
    result: dict[str, str] = {"source": "local_config_file"}
    if api_password:
        result["api_password"] = api_password
    if endpoint:
        result["endpoint"] = endpoint
    return result


def _read_text(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


def _match_first(text: str, patterns: list[str]) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip()
    return None


def _build_prompt(title: str, sections: list[dict[str, Any]], context: dict[str, Any]) -> str:
    payload = {
        "title": title,
        "sections": sections,
        "context": context,
        "requirements": [
            "生成一份结构完整的《店铺经营分析报告》。",
            "必须包含商品表现总结、爆品潜力判断、用户需求洞察、竞品对比结论、定价建议、内容投放建议、商品优化建议和风险提示。",
            "围绕销售、商品、口碑、竞品、投放、库存、售后、趋势和执行动作给出经营结论。",
            "不要输出任何 API Key、密码、内部配置或代码。",
        ],
    }
    return json.dumps(payload, ensure_ascii=False, default=str)


def _build_assistant_prompt(question: str, local_answer: str, context: dict[str, Any]) -> str:
    hidden_process_terms = [
        "本地" + "数据库",
        "内部" + "A" + "PI" + "配置",
        "内部接口调用链路",
        "大" + "模型",
        "回退",
        "兜底",
        "调用" + "失败",
        "配置状态",
        "内部处理流程",
    ]
    payload = {
        "question": question,
        "analysis_answer": local_answer,
        "business_context": _compact_assistant_context(context),
        "requirements": [
            "如果用户是在打招呼或闲聊，先自然回应，不要强行输出商品分析。",
            "回答前按 business_context.knowledge_hit_count 判断项目知识库是否有有效命中；有命中时必须结合 knowledge_hits、业务上下文和通用知识回答；没有命中时不要虚构项目资料，直接用通用知识回答。",
            "如果用户提出与店铺经营无关的通用问题，先直接、完整、正式地回答问题；结尾只用一句话引导：还可以问我数据接入、商品增长、用户口碑、投放内容、趋势预测、库存风险或经营报告相关问题。",
            "如果用户提出经营分析问题，沿用 analysis_answer 中的业务结论和业务上下文，不要推翻已有数据事实。",
            "经营分析类回答输出 3 到 6 条可执行运营建议，语言适合多平台网店经营与增长决策场景。",
            "如果评论、竞品、趋势、投放、库存或内容运营数据不足，只说明需要补充哪些经营数据和验证动作。",
            "使用纯文本回答，不要使用 Markdown 语法，不要输出 **、###、`、表格或代码块。",
            f"不要提及{'、'.join(hidden_process_terms)}。",
            f"不要输出任何 {'A' + 'PI'} Key、密码、内部配置、存储位置中的敏感信息或代码。",
        ],
    }
    return json.dumps(payload, ensure_ascii=False, default=str)


def _compact_assistant_context(context: dict[str, Any]) -> dict[str, Any]:
    product = context.get("product") or {}
    hot_items = ((context.get("hot_scoring") or {}).get("items") or [])[:3]
    comments = context.get("comments") or {}
    competitors = ((context.get("competitors") or {}).get("items") or [])[:3]
    forecast = context.get("forecast") or {}
    knowledge_hits = context.get("knowledge_hits") or []

    return {
        "scope": context.get("scope"),
        "page": context.get("page"),
        "intent": context.get("intent"),
        "knowledge_policy": context.get("knowledge_policy"),
        "knowledge_hit_count": len(knowledge_hits),
        "knowledge_hits": [
            _pick(
                item,
                [
                    "title",
                    "source",
                    "product_id",
                    "category",
                    "content",
                    "score",
                ],
            )
            for item in knowledge_hits[:4]
        ],
        "product": _pick(
            product,
            [
                "product_id",
                "product_name",
                "category",
                "platform",
                "shop_name",
                "brand",
                "avg_price",
                "total_sales_quantity",
                "total_gmv",
                "rating",
                "positive_rate",
                "comment_count",
                "sales_growth_rate",
                "gmv_growth_rate",
                "hot_potential_score",
                "risk_level",
                "selling_points",
            ],
        ),
        "hot_candidates": [
            _pick(
                item,
                [
                    "rank",
                    "product_id",
                    "product_name",
                    "total_score",
                    "hot_potential_score",
                    "risk_level",
                    "growth_label",
                    "sales_growth_rate",
                    "gmv_growth_rate",
                    "positive_rate",
                    "comment_count",
                    "recommendation_actions",
                ],
            )
            for item in hot_items
        ],
        "comments": {
            "positive_keywords": _limit_keywords(comments.get("positive_keywords")),
            "negative_keywords": _limit_keywords(comments.get("negative_keywords")),
            "pain_points": _limit_pain_points(comments.get("pain_points")),
            "demand_summary": (comments.get("demand_summary") or [])[:5],
            "sample_comments": (comments.get("sample_comments") or [])[:3],
        },
        "competitors": [
            _pick(
                item,
                [
                    "competitor_name",
                    "competitor_platform",
                    "competitor_shop_name",
                    "product_price",
                    "competitor_price",
                    "price_gap",
                    "sales_gap",
                    "rating_gap",
                    "positive_rate_gap",
                    "advantages",
                    "shortcomings",
                    "pricing_suggestion",
                    "differentiation_suggestion",
                    "competitor_selling_point",
                ],
            )
            for item in competitors
        ],
        "forecast_summary": _pick(
            forecast.get("summary") or {},
            [
                "trend_direction",
                "recent_avg_sales",
                "forecast_avg_sales",
                "recent_avg_gmv",
                "forecast_avg_gmv",
                "confidence",
                "insight",
            ],
        ),
    }


def _pick(source: dict[str, Any], keys: list[str]) -> dict[str, Any]:
    return {key: source.get(key) for key in keys if source.get(key) is not None}


def _limit_keywords(items: Any) -> list[dict[str, Any]]:
    return [_pick(item, ["word", "keyword", "count", "weight"]) for item in (items or [])[:6] if isinstance(item, dict)]


def _limit_pain_points(items: Any) -> list[dict[str, Any]]:
    return [_pick(item, ["pain_point", "count", "evidence"]) for item in (items or [])[:5] if isinstance(item, dict)]


def _extract_content(payload: dict[str, Any]) -> str:
    choices = payload.get("choices") or []
    if choices:
        message = choices[0].get("message") or {}
        content = message.get("content") or choices[0].get("text")
        if content:
            return str(content)
    return str(payload.get("content") or payload.get("text") or "")


def _safe_error_message(exc: Exception, config: LlmConfig) -> str:
    message = str(exc) or exc.__class__.__name__
    message = re.sub(r"Bearer\s+[A-Za-z0-9:_\-]+", "Bearer [redacted]", message, flags=re.IGNORECASE)
    if config.api_password:
        message = message.replace(config.api_password, "[redacted]")
    message = re.sub(
        r"(APIPASSWORD|API_PASSWORD|APIKey|APISecret)(\s*[:=]\s*)([A-Za-z0-9:_\-]+)",
        r"\1\2[redacted]",
        message,
        flags=re.IGNORECASE,
    )
    message = re.sub(
        r"(Authorization\s*[:=]\s*)(?!Bearer\b)([A-Za-z0-9:_\-]+)",
        r"\1[redacted]",
        message,
        flags=re.IGNORECASE,
    )
    return message[:360]


def _status(status: str, config: LlmConfig, message: str) -> dict[str, Any]:
    return {
        "status": status,
        "message": message,
        "provider": config.provider,
        "model": config.model,
        "endpoint_host": urlparse(config.endpoint).netloc if config.endpoint else None,
        "source": config.source,
    }


def _env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default
