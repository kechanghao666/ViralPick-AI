from __future__ import annotations

from dataclasses import dataclass
import json
import re
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pandas as pd
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from backend.db import connection_scope, fetch_one
from backend.repositories import import_repository
from backend.services import local_knowledge_service


class ImportValidationError(Exception):
    def __init__(self, message: str, summary: dict[str, Any] | None = None, row_count: int = 0):
        super().__init__(message)
        self.summary = summary or {}
        self.row_count = row_count


class ImportNotFoundError(ImportValidationError):
    pass


@dataclass(frozen=True)
class CsvDownload:
    filename: str
    content: bytes
    mimetype: str = "text/csv; charset=utf-8"


MAX_ERROR_DETAILS = 500
ALLOWED_MODES = {"validate", "replace"}
ALLOWED_COMMIT_MODES = {"replace", "append", "date_merge"}


def _schema(
    label: str,
    table: str,
    columns: list[str],
    required: list[str],
    aliases: dict[str, list[str]],
    numeric: dict[str, str] | None = None,
    dates: list[str] | None = None,
    primary_key: str | None = None,
    merge_keys: list[str] | None = None,
    replace_supported: bool = True,
    requires_products: bool = False,
) -> dict[str, Any]:
    return {
        "label": label,
        "table": table,
        "columns": columns,
        "required": required,
        "aliases": aliases,
        "numeric": numeric or {},
        "dates": dates or [],
        "primary_key": primary_key,
        "merge_keys": merge_keys or [],
        "replace_supported": replace_supported,
        "requires_products": requires_products,
    }


DATASET_SCHEMAS: dict[str, dict[str, Any]] = {
    "products": _schema(
        label="商品基础数据",
        table="products",
        primary_key="product_id",
        replace_supported=False,
        required=["product_name"],
        columns=[
            "product_id",
            "stock_code",
            "product_name",
            "platform",
            "brand",
            "shop_name",
            "image_url",
            "selling_points",
            "source_dataset",
            "category",
            "avg_price",
            "total_sales_quantity",
            "total_gmv",
            "order_count",
            "active_days",
            "first_sale_date",
            "last_sale_date",
            "country_count",
            "buyer_count",
            "comment_count",
            "rating",
            "positive_rate",
            "sales_growth_rate",
            "gmv_growth_rate",
            "price_competitiveness",
            "hot_potential_score",
            "risk_level",
            "data_source",
        ],
        aliases={
            "product_id": ["商品id", "商品ID", "商品编号", "sku", "sku_id", "product_id", "item_id", "货号"],
            "stock_code": ["商家编码", "sku编码", "货号", "stock_code"],
            "product_name": ["商品名称", "宝贝标题", "标题", "商品标题", "product_name", "name", "item_name"],
            "platform": ["平台", "来源平台", "店铺平台", "platform"],
            "brand": ["品牌", "brand"],
            "shop_name": ["店铺", "店铺名称", "shop_name", "seller"],
            "image_url": ["图片", "商品图片", "主图", "image_url", "pic", "img"],
            "selling_points": ["卖点", "商品卖点", "核心卖点", "selling_points"],
            "source_dataset": ["数据来源", "来源", "source_dataset"],
            "category": ["类目", "分类", "商品类目", "category"],
            "avg_price": ["价格", "售价", "销售价", "单价", "avg_price", "price"],
            "total_sales_quantity": ["销量", "累计销量", "销售件数", "total_sales_quantity"],
            "total_gmv": ["销售额", "成交金额", "支付金额", "GMV", "total_gmv"],
            "order_count": ["订单数", "支付订单数", "order_count"],
            "active_days": ["销售天数", "active_days"],
            "first_sale_date": ["首次销售日期", "first_sale_date"],
            "last_sale_date": ["最近销售日期", "last_sale_date"],
            "buyer_count": ["买家数", "buyer_count"],
            "comment_count": ["评论数", "评价数", "comment_count"],
            "rating": ["评分", "商品评分", "rating"],
            "positive_rate": ["好评率", "positive_rate"],
            "sales_growth_rate": ["销量增长率", "sales_growth_rate"],
            "gmv_growth_rate": ["销售额增长率", "gmv_growth_rate"],
            "hot_potential_score": ["爆品分", "潜力分", "hot_potential_score"],
            "risk_level": ["风险等级", "risk_level"],
        },
        numeric={
            "avg_price": "float",
            "total_sales_quantity": "int",
            "total_gmv": "float",
            "order_count": "int",
            "active_days": "int",
            "country_count": "int",
            "buyer_count": "int",
            "comment_count": "int",
            "rating": "float",
            "positive_rate": "float",
            "sales_growth_rate": "float",
            "gmv_growth_rate": "float",
            "price_competitiveness": "float",
            "hot_potential_score": "float",
        },
        dates=["first_sale_date", "last_sale_date"],
    ),
    "sales_daily": _schema(
        label="每日销售数据",
        table="sales_daily",
        required=["date", "product_id"],
        requires_products=True,
        merge_keys=["date", "product_id"],
        columns=["date", "product_id", "product_name", "category", "sales_quantity", "gmv", "order_count", "avg_unit_price"],
        aliases={
            "date": ["日期", "统计日期", "date", "day"],
            "product_id": ["商品id", "商品ID", "商品编号", "sku", "product_id", "item_id"],
            "product_name": ["商品名称", "商品标题", "product_name", "name"],
            "category": ["类目", "分类", "category"],
            "sales_quantity": ["销量", "销售件数", "成交件数", "sales_quantity", "quantity"],
            "gmv": ["销售额", "支付金额", "成交金额", "GMV", "gmv"],
            "order_count": ["订单数", "支付订单数", "order_count"],
            "avg_unit_price": ["客单价", "件单价", "平均单价", "avg_unit_price"],
        },
        numeric={"sales_quantity": "int", "gmv": "float", "order_count": "int", "avg_unit_price": "float"},
        dates=["date"],
    ),
    "comments": _schema(
        label="用户评论数据",
        table="comments",
        primary_key="comment_id",
        required=["product_id", "review_text"],
        requires_products=True,
        columns=[
            "comment_id",
            "product_id",
            "mapped_product_category",
            "review_text",
            "sentiment",
            "sentiment_label",
            "rating",
            "category_source",
            "data_source",
        ],
        aliases={
            "comment_id": ["评论id", "评价id", "comment_id", "review_id"],
            "product_id": ["商品id", "商品ID", "商品编号", "product_id", "item_id"],
            "mapped_product_category": ["商品类目", "类目", "mapped_product_category"],
            "review_text": ["评论内容", "评价内容", "买家评价", "review_text", "content", "comment"],
            "sentiment": ["情感", "情绪", "sentiment"],
            "sentiment_label": ["情感标签", "sentiment_label"],
            "rating": ["评分", "星级", "rating"],
            "category_source": ["评论类目", "category_source"],
            "data_source": ["数据来源", "source", "data_source"],
        },
        numeric={"sentiment_label": "int", "rating": "int"},
    ),
    "competitors": _schema(
        label="市场对照数据",
        table="competitors",
        primary_key="competitor_id",
        required=["product_id", "competitor_name"],
        requires_products=True,
        columns=[
            "competitor_id",
            "product_id",
            "competitor_name",
            "competitor_platform",
            "competitor_shop_name",
            "competitor_image_url",
            "competitor_selling_point",
            "category",
            "competitor_price",
            "competitor_sales_quantity",
            "competitor_rating",
            "competitor_positive_rate",
            "main_selling_point",
            "data_type",
            "note",
        ],
        aliases={
            "competitor_id": ["对照商品id", "市场商品id", "competitor_id"],
            "product_id": ["本品id", "商品id", "product_id", "item_id"],
            "competitor_name": ["对照商品名称", "同类商品标题", "competitor_name"],
            "competitor_platform": ["对照平台", "平台", "competitor_platform"],
            "competitor_shop_name": ["对照店铺", "店铺", "competitor_shop_name"],
            "competitor_image_url": ["对照商品图片", "图片", "competitor_image_url"],
            "competitor_selling_point": ["对照商品卖点", "卖点", "competitor_selling_point"],
            "category": ["类目", "分类", "category"],
            "competitor_price": ["对照价格", "市场价格", "价格", "competitor_price"],
            "competitor_sales_quantity": ["对照销量", "市场销量", "销量", "competitor_sales_quantity"],
            "competitor_rating": ["对照评分", "市场评分", "评分", "competitor_rating"],
            "competitor_positive_rate": ["对照好评率", "市场好评率", "好评率", "competitor_positive_rate"],
            "main_selling_point": ["主卖点", "main_selling_point"],
        },
        numeric={
            "competitor_price": "float",
            "competitor_sales_quantity": "int",
            "competitor_rating": "float",
            "competitor_positive_rate": "float",
        },
    ),
    "orders_daily": _schema(
        label="订单经营数据",
        table="orders_daily",
        required=["date", "product_id"],
        requires_products=True,
        merge_keys=["date", "platform", "product_id"],
        columns=[
            "date",
            "platform",
            "product_id",
            "product_name",
            "order_count",
            "paid_amount",
            "customer_unit_price",
            "refund_amount",
            "conversion_rate",
        ],
        aliases={
            "date": ["日期", "统计日期", "date"],
            "platform": ["平台", "platform"],
            "product_id": ["商品id", "商品ID", "商品编号", "product_id", "item_id"],
            "product_name": ["商品名称", "商品标题", "product_name"],
            "order_count": ["订单数", "支付订单数", "order_count"],
            "paid_amount": ["支付金额", "成交金额", "销售额", "paid_amount", "gmv"],
            "customer_unit_price": ["客单价", "customer_unit_price"],
            "refund_amount": ["退款金额", "refund_amount"],
            "conversion_rate": ["转化率", "支付转化率", "conversion_rate"],
        },
        numeric={"order_count": "int", "paid_amount": "float", "customer_unit_price": "float", "refund_amount": "float", "conversion_rate": "float"},
        dates=["date"],
    ),
    "inventory_daily": _schema(
        label="库存数据",
        table="inventory_daily",
        required=["date", "product_id"],
        requires_products=True,
        merge_keys=["date", "product_id"],
        columns=["date", "product_id", "product_name", "stock_quantity", "available_stock", "replenishment_threshold", "stockout_risk", "slow_moving_days"],
        aliases={
            "date": ["日期", "统计日期", "date"],
            "product_id": ["商品id", "商品ID", "商品编号", "product_id", "item_id"],
            "product_name": ["商品名称", "product_name"],
            "stock_quantity": ["库存", "库存数量", "stock_quantity"],
            "available_stock": ["可售库存", "available_stock"],
            "replenishment_threshold": ["补货阈值", "安全库存", "replenishment_threshold"],
            "stockout_risk": ["缺货风险", "stockout_risk"],
            "slow_moving_days": ["滞销天数", "slow_moving_days"],
        },
        numeric={"stock_quantity": "int", "available_stock": "int", "replenishment_threshold": "int", "slow_moving_days": "int"},
        dates=["date"],
    ),
    "after_sales": _schema(
        label="售后退款数据",
        table="after_sales",
        primary_key="after_sale_id",
        required=["product_id", "reason"],
        requires_products=True,
        columns=["after_sale_id", "date", "platform", "product_id", "product_name", "refund_amount", "refund_count", "reason", "status"],
        aliases={
            "after_sale_id": ["售后id", "退款id", "after_sale_id"],
            "date": ["日期", "申请日期", "date"],
            "platform": ["平台", "platform"],
            "product_id": ["商品id", "商品ID", "商品编号", "product_id", "item_id"],
            "product_name": ["商品名称", "product_name"],
            "refund_amount": ["退款金额", "refund_amount"],
            "refund_count": ["退款件数", "退款数量", "refund_count"],
            "reason": ["退款原因", "售后原因", "原因", "reason"],
            "status": ["售后状态", "状态", "status"],
        },
        numeric={"refund_amount": "float", "refund_count": "int"},
        dates=["date"],
    ),
    "ad_metrics": _schema(
        label="广告投放数据",
        table="ad_metrics",
        required=["date", "product_id"],
        requires_products=True,
        merge_keys=["date", "platform", "campaign_name", "product_id"],
        columns=["date", "platform", "campaign_name", "product_id", "product_name", "spend", "impressions", "clicks", "conversions", "revenue", "roi"],
        aliases={
            "date": ["日期", "统计日期", "date"],
            "platform": ["平台", "platform"],
            "campaign_name": ["计划名称", "广告计划", "campaign_name"],
            "product_id": ["商品id", "商品ID", "商品编号", "product_id", "item_id"],
            "product_name": ["商品名称", "product_name"],
            "spend": ["花费", "广告花费", "消耗", "spend"],
            "impressions": ["曝光", "曝光量", "展现量", "impressions"],
            "clicks": ["点击", "点击量", "clicks"],
            "conversions": ["转化", "成交订单", "conversions"],
            "revenue": ["成交金额", "投放成交金额", "revenue"],
            "roi": ["ROI", "投产比", "roi"],
        },
        numeric={"spend": "float", "impressions": "int", "clicks": "int", "conversions": "int", "revenue": "float", "roi": "float"},
        dates=["date"],
    ),
    "traffic_metrics": _schema(
        label="流量转化数据",
        table="traffic_metrics",
        required=["date", "product_id"],
        requires_products=True,
        merge_keys=["date", "platform", "product_id"],
        columns=["date", "platform", "product_id", "product_name", "visitors", "page_views", "cart_adds", "favorites", "payment_conversion_rate"],
        aliases={
            "date": ["日期", "统计日期", "date"],
            "platform": ["平台", "platform"],
            "product_id": ["商品id", "商品ID", "商品编号", "product_id", "item_id"],
            "product_name": ["商品名称", "product_name"],
            "visitors": ["访客", "访客数", "UV", "visitors"],
            "page_views": ["浏览", "浏览量", "PV", "page_views"],
            "cart_adds": ["加购", "加购数", "cart_adds"],
            "favorites": ["收藏", "收藏数", "favorites"],
            "payment_conversion_rate": ["支付转化率", "转化率", "payment_conversion_rate"],
        },
        numeric={"visitors": "int", "page_views": "int", "cart_adds": "int", "favorites": "int", "payment_conversion_rate": "float"},
        dates=["date"],
    ),
    "content_metrics": _schema(
        label="内容运营数据",
        table="content_metrics",
        required=["date", "product_id"],
        requires_products=True,
        merge_keys=["date", "platform", "content_type", "topic", "product_id"],
        columns=["date", "platform", "content_type", "topic", "product_id", "product_name", "impressions", "interactions", "guided_revenue", "effect_score"],
        aliases={
            "date": ["日期", "统计日期", "date"],
            "platform": ["平台", "platform"],
            "content_type": ["内容类型", "素材类型", "content_type"],
            "topic": ["素材主题", "内容主题", "topic"],
            "product_id": ["商品id", "商品ID", "商品编号", "product_id", "item_id"],
            "product_name": ["商品名称", "product_name"],
            "impressions": ["曝光", "曝光量", "播放量", "impressions"],
            "interactions": ["互动", "互动量", "点赞评论收藏", "interactions"],
            "guided_revenue": ["引导成交", "引导成交金额", "guided_revenue"],
            "effect_score": ["素材效果分", "effect_score"],
        },
        numeric={"impressions": "int", "interactions": "int", "guided_revenue": "float", "effect_score": "float"},
        dates=["date"],
    ),
}

DATASET_SCHEMAS["video_metrics"] = _schema(
    label="内容运营明细",
    table="video_metrics",
    primary_key="video_id",
    required=["product_id", "content_topic"],
    requires_products=True,
    columns=["video_id", "product_id", "content_topic", "views", "likes", "favorites", "shares", "conversion_rate", "data_type", "note"],
    aliases={
        "video_id": ["内容id", "素材id", "video_id"],
        "product_id": ["商品id", "商品ID", "product_id"],
        "content_topic": ["内容主题", "素材主题", "content_topic"],
        "views": ["曝光", "播放量", "浏览量", "views"],
        "likes": ["点赞", "likes"],
        "favorites": ["收藏", "favorites"],
        "shares": ["转发", "分享", "shares"],
        "conversion_rate": ["转化率", "conversion_rate"],
        "data_type": ["数据类型", "data_type"],
        "note": ["备注", "note"],
    },
    numeric={"views": "int", "likes": "int", "favorites": "int", "shares": "int", "conversion_rate": "float"},
)


SAMPLE_ROWS: dict[str, dict[str, Any]] = {
    "products": {
        "product_id": "P9001",
        "stock_code": "SKU-9001",
        "product_name": "便携分格料理盒",
        "platform": "京东",
        "brand": "示例品牌",
        "shop_name": "示例品牌旗舰店",
        "image_url": "./assets/img/products/P9001.jpg",
        "selling_points": "便携分格|微波可用|上班族午餐",
        "source_dataset": "merchant authorized sample",
        "category": "家居日用",
        "avg_price": 39.9,
        "total_sales_quantity": 1200,
        "total_gmv": 47880.0,
        "order_count": 860,
        "active_days": 30,
        "first_sale_date": "2026-06-01",
        "last_sale_date": "2026-06-30",
        "country_count": 1,
        "buyer_count": 780,
        "comment_count": 160,
        "rating": 4.7,
        "positive_rate": 0.91,
        "sales_growth_rate": 0.18,
        "gmv_growth_rate": 0.22,
        "price_competitiveness": 83.5,
        "hot_potential_score": 86.0,
        "risk_level": "normal",
        "data_source": "merchant authorized sample",
    },
    "sales_daily": {
        "date": "2026-06-30",
        "product_id": "P0001",
        "product_name": "示例商品",
        "category": "家居日用",
        "sales_quantity": 48,
        "gmv": 1915.2,
        "order_count": 38,
        "avg_unit_price": 39.9,
    },
    "comments": {
        "comment_id": "C9001",
        "product_id": "P0001",
        "mapped_product_category": "家居日用",
        "review_text": "包装完整，做工扎实。",
        "sentiment": "positive",
        "sentiment_label": 1,
        "rating": 5,
        "category_source": "manual",
        "data_source": "merchant authorized sample",
    },
    "competitors": {
        "competitor_id": "CP9001",
        "product_id": "P0001",
        "competitor_name": "同类热卖款 A",
        "competitor_platform": "天猫",
        "competitor_shop_name": "同类热卖款旗舰店",
        "competitor_image_url": "./assets/img/products/P0001.jpg",
        "competitor_selling_point": "组合装热卖",
        "category": "家居日用",
        "competitor_price": 42.9,
        "competitor_sales_quantity": 980,
        "competitor_rating": 4.6,
        "competitor_positive_rate": 0.88,
        "main_selling_point": "高性价比",
        "data_type": "merchant authorized sample",
        "note": "市场对照信息来自商家整理或公开信息录入。",
    },
}


def supported_datasets() -> list[dict[str, Any]]:
    return [
        {
            "dataset_type": key,
            "label": schema["label"],
            "table": schema["table"],
            "replace_supported": bool(schema.get("replace_supported", True)),
            "required_columns": schema["required"],
            "columns": schema["columns"],
            "aliases": schema["aliases"],
            "merge_keys": schema.get("merge_keys", []),
        }
        for key, schema in DATASET_SCHEMAS.items()
    ]


def list_import_jobs(user: dict[str, Any] | None = None, limit: int = 20) -> dict[str, Any]:
    workspace_id = user.get("workspace_id") if user else None
    rows = import_repository.list_jobs(workspace_id=workspace_id, limit=limit)
    return {"items": [_public_job(row) for row in rows], "supported_datasets": supported_datasets()}


def export_template(dataset_type: str) -> CsvDownload:
    schema = _get_schema(dataset_type)
    columns = list(schema["columns"])
    sample = SAMPLE_ROWS.get(dataset_type, {column: "" for column in columns})
    frame = pd.DataFrame([{column: sample.get(column, "") for column in columns}], columns=columns)
    return CsvDownload(filename=f"viralpick-{dataset_type}-template.csv", content=_csv_bytes(frame))


def export_error_report(job_id: str, user: dict[str, Any]) -> CsvDownload:
    job = import_repository.get_job(str(job_id or "").strip())
    if not job or (job.get("workspace_id") and job.get("workspace_id") != user.get("workspace_id")):
        raise ImportNotFoundError(f"Import job not found: {job_id}")
    public_job = _public_job(job)
    summary = public_job.get("summary") or {}
    details = summary.get("error_details") or []
    if not details and summary.get("validation_errors"):
        details = [{"line_number": "", "field": "", "severity": "error", "message": message, "value": ""} for message in summary["validation_errors"]]
    if not details and public_job.get("error_message"):
        details = [{"line_number": "", "field": "", "severity": "error", "message": public_job["error_message"], "value": ""}]
    if not details:
        raise ImportValidationError("该导入任务没有可下载的错误报告")

    rows = [
        {
            "job_id": public_job.get("job_id"),
            "dataset_type": public_job.get("dataset_type"),
            "filename": public_job.get("filename"),
            "line_number": detail.get("line_number", ""),
            "field": detail.get("field", ""),
            "severity": detail.get("severity", "error"),
            "message": detail.get("message", ""),
            "value": detail.get("value", ""),
        }
        for detail in details
    ]
    frame = pd.DataFrame(rows, columns=["job_id", "dataset_type", "filename", "line_number", "field", "severity", "message", "value"])
    return CsvDownload(filename=f"viralpick-{public_job.get('job_id')}-errors.csv", content=_csv_bytes(frame))


def get_import_schema() -> dict[str, Any]:
    return {
        "datasets": supported_datasets(),
        "modes": [
            {"mode": "replace", "label": "覆盖导入"},
            {"mode": "append", "label": "追加导入"},
            {"mode": "date_merge", "label": "按日期合并"},
        ],
    }


def preview_import(uploaded_file: FileStorage, dataset_type: str | None = None) -> dict[str, Any]:
    if not uploaded_file or not uploaded_file.filename:
        raise ImportValidationError("请上传 CSV 或 Excel 文件")
    filename = secure_filename(uploaded_file.filename) or "upload"
    frame = _read_upload(uploaded_file)
    requested = str(dataset_type or "").strip()
    detected_type = requested if requested and requested in DATASET_SCHEMAS else _detect_dataset_type(frame)
    schema = _get_schema(detected_type)
    mapping = _suggest_mapping(frame.columns, schema)
    mapped = _map_frame(frame, schema, mapping)
    quality = _quality_check(mapped, schema, strict=False)
    preview_id = f"IP-{uuid4().hex[:18]}"
    preview = {
        "preview_id": preview_id,
        "filename": filename,
        "dataset_type": detected_type,
        "dataset_label": schema["label"],
        "row_count": len(frame),
        "source_columns": list(frame.columns),
        "field_mapping": mapping,
        "preview_rows": _preview_rows(mapped),
        "quality": quality,
        "supported_datasets": supported_datasets(),
        "created_at": _now_iso(),
    }
    _save_preview(preview_id, filename, detected_type, frame, preview)
    return preview


def commit_import(
    preview_id: str,
    dataset_type: str,
    field_mapping: dict[str, str] | None,
    mode: str,
    user: dict[str, Any] | None = None,
) -> dict[str, Any]:
    mode = str(mode or "append").strip().lower()
    if mode not in ALLOWED_COMMIT_MODES:
        raise ImportValidationError("mode must be replace, append, or date_merge")
    preview = _load_preview(preview_id)
    if not preview:
        raise ImportNotFoundError(f"Import preview not found: {preview_id}")

    schema = _get_schema(dataset_type or preview["dataset_type"])
    source_rows = preview["raw_rows"]
    frame = pd.DataFrame(source_rows)
    mapping = field_mapping or preview.get("field_mapping") or {}
    mapped = _map_frame(frame, schema, mapping)
    mapped, summary = _validate_commit_frame(mapped, schema, mode)

    job_id = f"I-{uuid4().hex[:18]}"
    import_repository.create_job(
        {
            "job_id": job_id,
            "workspace_id": user.get("workspace_id") if user else None,
            "user_id": user.get("user_id") if user else None,
            "dataset_type": dataset_type,
            "filename": preview["filename"],
            "mode": mode,
            "status": "running",
            "row_count": 0,
            "summary_json": _dumps({"stage": "commit", "preview_id": preview_id}),
            "created_at": _now_iso(),
        }
    )
    try:
        write_result = _write_table(schema, mapped, mode)
        summary["write_result"] = write_result
        summary["preview_id"] = preview_id
        summary["knowledge_base"] = _refresh_knowledge_base()
        import_repository.update_job(
            job_id=job_id,
            status="completed",
            row_count=len(mapped),
            summary_json=_dumps(summary),
            completed_at=_now_iso(),
        )
        _mark_preview_committed(preview_id, job_id)
        return _public_job(import_repository.get_job(job_id) or {})
    except ImportValidationError as exc:
        import_repository.update_job(
            job_id=job_id,
            status="failed",
            row_count=exc.row_count,
            error_message=str(exc),
            summary_json=_dumps(exc.summary or summary),
            completed_at=_now_iso(),
        )
        raise
    except Exception as exc:
        message = f"导入失败：{exc}"
        import_repository.update_job(
            job_id=job_id,
            status="failed",
            row_count=0,
            error_message=message,
            summary_json=_dumps({"validation_errors": [message]}),
            completed_at=_now_iso(),
        )
        raise ImportValidationError(message) from exc


def _refresh_knowledge_base() -> dict[str, Any]:
    try:
        status = local_knowledge_service.rebuild_knowledge_base()
        return {
            "ready": bool(status.get("ready")),
            "document_count": int(status.get("document_count") or 0),
            "updated_at": status.get("updated_at"),
        }
    except Exception as exc:
        return {
            "ready": False,
            "document_count": 0,
            "updated_at": None,
            "error": str(exc),
        }


def run_import(uploaded_file: FileStorage, dataset_type: str, mode: str, user: dict[str, Any]) -> dict[str, Any]:
    dataset_type = str(dataset_type or "").strip()
    mode = str(mode or "validate").strip().lower()
    schema = _get_schema(dataset_type)
    if mode not in ALLOWED_MODES:
        raise ImportValidationError("mode must be validate or replace")
    if not uploaded_file or not uploaded_file.filename:
        raise ImportValidationError("请上传 CSV 文件")

    filename = secure_filename(uploaded_file.filename) or "upload.csv"
    if not filename.lower().endswith(".csv"):
        raise ImportValidationError("当前接口仅支持 CSV 文件，Excel 请使用智能导入流程")

    job_id = f"I-{uuid4().hex[:18]}"
    import_repository.create_job(
        {
            "job_id": job_id,
            "workspace_id": user.get("workspace_id"),
            "user_id": user.get("user_id"),
            "dataset_type": dataset_type,
            "filename": filename,
            "mode": mode,
            "status": "running",
            "row_count": 0,
            "summary_json": _dumps({"stage": "received", "warnings": []}),
            "created_at": _now_iso(),
        }
    )

    try:
        frame = _read_csv(uploaded_file)
        frame, summary = _validate_frame_strict(frame, dataset_type, schema, mode)
        if mode == "replace":
            _write_table(schema, frame, "replace")
            status = "completed"
            summary["write_result"] = f"{schema['label']}已替换为上传 CSV 内容"
        else:
            status = "validated"
            summary["write_result"] = "已完成校验，未写入业务数据表"
        import_repository.update_job(job_id, status, len(frame), _dumps(summary), _now_iso())
        return _public_job(import_repository.get_job(job_id) or {})
    except ImportValidationError as exc:
        summary = exc.summary or {"validation_errors": [str(exc)]}
        import_repository.update_job(job_id, "failed", exc.row_count, _dumps(summary), _now_iso(), str(exc))
        raise
    except Exception as exc:
        message = f"导入失败：{exc}"
        import_repository.update_job(job_id, "failed", 0, _dumps({"validation_errors": [message]}), _now_iso(), message)
        raise ImportValidationError(message) from exc


def _get_schema(dataset_type: str) -> dict[str, Any]:
    key = str(dataset_type or "").strip()
    schema = DATASET_SCHEMAS.get(key)
    if not schema:
        raise ImportValidationError(f"不支持的数据类型：{key or '空'}")
    return schema


def _read_upload(uploaded_file: FileStorage) -> pd.DataFrame:
    filename = str(uploaded_file.filename or "").lower()
    if filename.endswith(".xlsx") or filename.endswith(".xls"):
        try:
            uploaded_file.stream.seek(0)
            frame = pd.read_excel(uploaded_file.stream)
        except Exception as exc:
            raise ImportValidationError(f"Excel 读取失败：{exc}") from exc
    elif filename.endswith(".csv"):
        frame = _read_csv(uploaded_file)
    else:
        raise ImportValidationError("请上传 CSV 或 Excel 文件")
    frame.columns = [str(column).strip().lstrip("\ufeff") for column in frame.columns]
    if frame.empty:
        raise ImportValidationError("文件至少需要 1 行数据")
    return frame


def _read_csv(uploaded_file: FileStorage) -> pd.DataFrame:
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "utf-8", "gbk"):
        try:
            uploaded_file.stream.seek(0)
            return pd.read_csv(uploaded_file.stream, encoding=encoding)
        except UnicodeDecodeError as exc:
            last_error = exc
            continue
        except pd.errors.EmptyDataError as exc:
            raise ImportValidationError("CSV 文件为空") from exc
        except Exception as exc:
            raise ImportValidationError(f"CSV 读取失败：{exc}") from exc
    raise ImportValidationError("CSV 编码无法识别，建议使用 UTF-8 或 GBK") from last_error


def _detect_dataset_type(frame: pd.DataFrame) -> str:
    normalized_columns = {_normalize_column(column) for column in frame.columns}
    best_type = "products"
    best_score = -1
    for dataset_type, schema in DATASET_SCHEMAS.items():
        score = 0
        for field, aliases in schema["aliases"].items():
            alias_set = {_normalize_column(alias) for alias in [field, *aliases]}
            if normalized_columns.intersection(alias_set):
                score += 3 if field in schema["required"] else 1
        if score > best_score:
            best_type = dataset_type
            best_score = score
    return best_type


def _suggest_mapping(columns: list[str] | pd.Index, schema: dict[str, Any]) -> dict[str, str]:
    source_by_norm = {_normalize_column(column): str(column) for column in columns}
    mapping: dict[str, str] = {}
    for field, aliases in schema["aliases"].items():
        candidates = [field, *aliases]
        for candidate in candidates:
            source = source_by_norm.get(_normalize_column(candidate))
            if source:
                mapping[field] = source
                break
    return mapping


def _map_frame(frame: pd.DataFrame, schema: dict[str, Any], mapping: dict[str, str]) -> pd.DataFrame:
    rows: dict[str, Any] = {}
    for field in schema["columns"]:
        source = mapping.get(field)
        if source and source in frame.columns:
            rows[field] = frame[source]
        else:
            rows[field] = [_default_value(field, schema, index) for index in range(len(frame))]
    mapped = pd.DataFrame(rows, columns=schema["columns"]).astype(object)
    _fill_derived_defaults(mapped, schema)
    return mapped


def _quality_check(frame: pd.DataFrame, schema: dict[str, Any], strict: bool) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    details: list[dict[str, Any]] = []
    _check_required(frame, schema, errors, details)
    _check_primary_key(frame, schema.get("primary_key"), errors if strict else warnings, details)
    _check_types(frame, schema, errors if strict else warnings, details, mutate=False)
    if schema.get("requires_products"):
        missing = _missing_product_ids(frame)
        if missing:
            message = f"存在无法匹配的商品 ID：{', '.join(missing[:8])}"
            (errors if strict else warnings).append(message)
    return {
        "status": "failed" if errors else ("warning" if warnings else "passed"),
        "errors": errors,
        "warnings": warnings,
        "error_details": details[:MAX_ERROR_DETAILS],
        "row_count": len(frame),
        "required_columns": schema["required"],
    }


def _validate_commit_frame(frame: pd.DataFrame, schema: dict[str, Any], mode: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    errors: list[str] = []
    details: list[dict[str, Any]] = []
    if mode == "replace" and not schema.get("replace_supported", True):
        errors.append("该数据类型暂不支持覆盖导入，请使用追加或按日期合并")
    _check_required(frame, schema, errors, details)
    _check_primary_key(frame, schema.get("primary_key"), errors, details)
    _check_types(frame, schema, errors, details, mutate=True)
    if schema.get("requires_products"):
        missing = _missing_product_ids(frame)
        if missing:
            errors.append(f"存在无法匹配的商品 ID：{', '.join(missing[:8])}")
            missing_set = set(missing)
            for index, value in frame["product_id"].astype(str).items():
                if value.strip() in missing_set:
                    _add_error_detail(details, "商品 ID 不存在", "product_id", _csv_line(index), value)
    summary = {
        "dataset_type": schema["table"],
        "mode": mode,
        "row_count": len(frame),
        "required_columns": schema["required"],
        "received_columns": schema["columns"],
        "validation_errors": errors,
        "error_details": details,
        "preview": _preview_rows(frame),
    }
    if errors:
        raise ImportValidationError(errors[0], summary=summary, row_count=len(frame))
    return frame, summary


def _validate_frame_strict(frame: pd.DataFrame, dataset_type: str, schema: dict[str, Any], mode: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    columns = list(schema["columns"])
    errors: list[str] = []
    details: list[dict[str, Any]] = []
    warnings: list[str] = []
    missing = [column for column in columns if column not in frame.columns]
    extra = [column for column in frame.columns if column not in columns]
    if missing:
        _add_error(errors, details, f"缺少必需字段：{', '.join(missing)}", field=",".join(missing))
    if extra:
        warnings.append(f"已忽略额外字段：{', '.join(extra)}")
    if mode == "replace" and not schema.get("replace_supported", True):
        _add_error(errors, details, "该数据类型暂不支持在线替换")

    summary = {
        "dataset_type": dataset_type,
        "mode": mode,
        "row_count": len(frame),
        "required_columns": columns,
        "received_columns": list(frame.columns),
        "extra_columns": extra,
        "warnings": warnings,
    }
    if errors:
        summary["validation_errors"] = errors
        summary["error_details"] = details
        raise ImportValidationError(errors[0], summary=summary, row_count=len(frame))
    frame = frame[columns].copy()
    _check_required(frame, {"required": columns}, errors, details)
    _check_primary_key(frame, schema.get("primary_key"), errors, details)
    _check_types(frame, schema, errors, details, mutate=True)
    if schema.get("requires_products"):
        missing_products = _missing_product_ids(frame)
        if missing_products:
            _add_error(errors, details, f"存在未注册商品 ID：{', '.join(missing_products[:8])}", field="product_id")
    summary["preview"] = _preview_rows(frame)
    summary["validation_errors"] = errors
    summary["error_details"] = details
    if errors:
        raise ImportValidationError(errors[0], summary=summary, row_count=len(frame))
    return frame, summary


def _check_required(frame: pd.DataFrame, schema: dict[str, Any], errors: list[str], details: list[dict[str, Any]]) -> None:
    for column in schema.get("required", []):
        if column not in frame.columns:
            _add_error(errors, details, f"缺少必需字段：{column}", field=column)
            continue
        blank = frame[column].isna() | (frame[column].astype(str).str.strip() == "")
        if int(blank.sum()):
            _add_error(errors, details, f"{column} 存在空值", field=column)
            for index in frame.index[blank].tolist()[:20]:
                _add_error_detail(details, "必填字段为空", column, _csv_line(index))


def _check_primary_key(frame: pd.DataFrame, primary_key: str | None, messages: list[str], details: list[dict[str, Any]]) -> None:
    if not primary_key or primary_key not in frame.columns:
        return
    duplicated = frame[primary_key].astype(str).duplicated(keep=False)
    if duplicated.any():
        values = frame.loc[duplicated, primary_key].astype(str).head(5).tolist()
        messages.append(f"{primary_key} 存在重复值：{', '.join(values)}")
        for index, value in frame.loc[duplicated, primary_key].astype(str).items():
            _add_error_detail(details, "主键重复", primary_key, _csv_line(index), value)


def _check_types(frame: pd.DataFrame, schema: dict[str, Any], messages: list[str], details: list[dict[str, Any]], mutate: bool) -> None:
    for column, kind in schema.get("numeric", {}).items():
        if column not in frame.columns:
            continue
        parsed = pd.to_numeric(frame[column], errors="coerce")
        invalid = parsed.isna() & ~(frame[column].isna() | (frame[column].astype(str).str.strip() == ""))
        if invalid.any():
            messages.append(f"{column} 存在非数字内容")
            for index, value in frame.loc[invalid, column].astype(str).items():
                _add_error_detail(details, "数字格式不正确", column, _csv_line(index), value)
        elif mutate:
            frame[column] = parsed.fillna(0).astype(int if kind == "int" else float)

    for column in schema.get("dates", []):
        if column not in frame.columns:
            continue
        parsed = pd.to_datetime(frame[column], errors="coerce")
        invalid = parsed.isna() & ~(frame[column].isna() | (frame[column].astype(str).str.strip() == ""))
        if invalid.any():
            messages.append(f"{column} 存在日期格式异常")
            for index, value in frame.loc[invalid, column].astype(str).items():
                _add_error_detail(details, "日期格式不正确，建议使用 YYYY-MM-DD", column, _csv_line(index), value)
        elif mutate:
            frame[column] = parsed.dt.strftime("%Y-%m-%d")

    if mutate:
        for column in frame.columns:
            if column not in schema.get("numeric", {}) and column not in schema.get("dates", []):
                frame[column] = frame[column].astype("string").fillna("").str.strip()


def _missing_product_ids(frame: pd.DataFrame) -> list[str]:
    if "product_id" not in frame.columns:
        return []
    ids = sorted({str(value).strip() for value in frame["product_id"].dropna().tolist() if str(value).strip()})
    existing: set[str] = set()
    for index in range(0, len(ids), 800):
        existing.update(import_repository.existing_product_ids(ids[index : index + 800]))
    return [product_id for product_id in ids if product_id not in existing]


def _write_table(schema: dict[str, Any], frame: pd.DataFrame, mode: str) -> str:
    table = schema["table"]
    clean = frame[schema["columns"]].where(pd.notna(frame), None)
    with connection_scope() as connection:
        try:
            connection.execute("BEGIN")
            if mode == "replace":
                _delete_table_for_replace(connection, table)
            elif mode == "date_merge":
                _delete_merge_rows(connection, table, clean, schema.get("merge_keys") or [])
            clean.to_sql(table, connection, if_exists="append", index=False)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    labels = {"replace": "覆盖导入", "append": "追加导入", "date_merge": "按日期合并"}
    return f"{labels.get(mode, mode)}完成，共写入 {len(frame)} 行"


def _delete_table_for_replace(connection, table: str) -> None:
    if table == "products":
        for child in [
            "sales_daily",
            "comments",
            "video_metrics",
            "competitors",
            "orders_daily",
            "inventory_daily",
            "after_sales",
            "ad_metrics",
            "traffic_metrics",
            "content_metrics",
            "forecast_results",
        ]:
            connection.execute(f"DELETE FROM {child}")
    connection.execute(f"DELETE FROM {table}")


def _delete_merge_rows(connection, table: str, frame: pd.DataFrame, merge_keys: list[str]) -> None:
    if not merge_keys:
        return
    where = " AND ".join(f"{key} = ?" for key in merge_keys)
    for _, row in frame[merge_keys].drop_duplicates().iterrows():
        connection.execute(f"DELETE FROM {table} WHERE {where}", [row[key] for key in merge_keys])


def _save_preview(preview_id: str, filename: str, dataset_type: str, frame: pd.DataFrame, preview: dict[str, Any]) -> None:
    raw_rows = _json_safe_rows(frame)
    with connection_scope() as connection:
        connection.execute(
            """
            INSERT INTO import_previews (
                preview_id, filename, dataset_type, source_columns_json, field_mapping_json,
                preview_rows_json, raw_rows_json, quality_json, status, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                preview_id,
                filename,
                dataset_type,
                _dumps({"columns": preview["source_columns"]}),
                _dumps(preview["field_mapping"]),
                _dumps({"rows": preview["preview_rows"]}),
                _dumps({"rows": raw_rows}),
                _dumps(preview["quality"]),
                "previewed",
                preview["created_at"],
            ],
        )
        connection.commit()


def _load_preview(preview_id: str) -> dict[str, Any] | None:
    row = fetch_one("SELECT * FROM import_previews WHERE preview_id = ?", [str(preview_id or "").strip()])
    if not row:
        return None
    return {
        "preview_id": row["preview_id"],
        "filename": row["filename"],
        "dataset_type": row["dataset_type"],
        "source_columns": json.loads(row["source_columns_json"]).get("columns", []),
        "field_mapping": json.loads(row["field_mapping_json"] or "{}"),
        "raw_rows": json.loads(row["raw_rows_json"]).get("rows", []),
        "quality": json.loads(row["quality_json"] or "{}"),
    }


def _mark_preview_committed(preview_id: str, job_id: str) -> None:
    with connection_scope() as connection:
        connection.execute(
            "UPDATE import_previews SET status = ?, committed_job_id = ? WHERE preview_id = ?",
            ["committed", job_id, preview_id],
        )
        connection.commit()


def _fill_derived_defaults(frame: pd.DataFrame, schema: dict[str, Any]) -> None:
    today = datetime.now(UTC).date().isoformat()
    table = schema["table"]
    if table == "products":
        for index in frame.index:
            if not str(frame.at[index, "product_id"]).strip():
                frame.at[index, "product_id"] = f"P-IMP-{uuid4().hex[:8].upper()}"
            product_name = str(frame.at[index, "product_name"] or "").strip()
            frame.at[index, "stock_code"] = frame.at[index, "stock_code"] or frame.at[index, "product_id"]
            frame.at[index, "category"] = frame.at[index, "category"] or "未分类"
            frame.at[index, "platform"] = frame.at[index, "platform"] or "多平台"
            frame.at[index, "shop_name"] = frame.at[index, "shop_name"] or "自营店铺"
            frame.at[index, "brand"] = frame.at[index, "brand"] or "自有品牌"
            frame.at[index, "selling_points"] = frame.at[index, "selling_points"] or product_name
            frame.at[index, "source_dataset"] = frame.at[index, "source_dataset"] or "merchant import"
            frame.at[index, "data_source"] = frame.at[index, "data_source"] or "merchant import"
            frame.at[index, "first_sale_date"] = frame.at[index, "first_sale_date"] or today
            frame.at[index, "last_sale_date"] = frame.at[index, "last_sale_date"] or today
            frame.at[index, "risk_level"] = frame.at[index, "risk_level"] or "normal"
            frame.at[index, "rating"] = frame.at[index, "rating"] or 4.6
            frame.at[index, "positive_rate"] = frame.at[index, "positive_rate"] or 0.9
            frame.at[index, "price_competitiveness"] = frame.at[index, "price_competitiveness"] or 80
    for pk in ("comment_id", "competitor_id", "after_sale_id", "video_id"):
        if pk in frame.columns:
            prefix = {"comment_id": "C", "competitor_id": "CP", "after_sale_id": "AS", "video_id": "CT"}[pk]
            for index in frame.index:
                if not str(frame.at[index, pk]).strip():
                    frame.at[index, pk] = f"{prefix}-IMP-{uuid4().hex[:10].upper()}"
    if "date" in frame.columns:
        frame["date"] = frame["date"].replace("", today).fillna(today)
    if "sentiment" in frame.columns:
        frame["sentiment"] = frame["sentiment"].replace("", "neutral").fillna("neutral")
    if "sentiment_label" in frame.columns:
        frame["sentiment_label"] = pd.to_numeric(frame["sentiment_label"].replace("", 0), errors="coerce").fillna(0).astype(int)
    if "rating" in frame.columns:
        frame["rating"] = pd.to_numeric(frame["rating"].replace("", 5), errors="coerce").fillna(5).astype(float)


def _default_value(field: str, schema: dict[str, Any], index: int) -> Any:
    if field in schema.get("numeric", {}):
        return 0
    if field in schema.get("dates", []):
        return datetime.now(UTC).date().isoformat()
    return ""


def _normalize_column(value: Any) -> str:
    text = str(value or "").strip().lower()
    return re.sub(r"[\s_\-:/（）()【】\[\].,，。]+", "", text)


def _add_error(errors: list[str], details: list[dict[str, Any]], message: str, field: str = "", line_number: int | str = "", value: Any = "") -> None:
    if message not in errors:
        errors.append(message)
    _add_error_detail(details, message, field, line_number, value)


def _add_error_detail(details: list[dict[str, Any]], message: str, field: str = "", line_number: int | str = "", value: Any = "") -> None:
    if len(details) >= MAX_ERROR_DETAILS:
        return
    details.append({"line_number": line_number, "field": field, "severity": "error", "message": message, "value": "" if value is None else str(value)})


def _csv_line(index: Any) -> int:
    try:
        return int(index) + 2
    except (TypeError, ValueError):
        return 0


def _csv_bytes(frame: pd.DataFrame) -> bytes:
    return frame.to_csv(index=False, lineterminator="\n").encode("utf-8-sig")


def _preview_rows(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return _json_safe_rows(frame.head(8))


def _json_safe_rows(frame: pd.DataFrame) -> list[dict[str, Any]]:
    rows = frame.where(pd.notna(frame), None).to_dict(orient="records")
    return [{key: _plain_value(value) for key, value in row.items()} for row in rows]


def _plain_value(value: Any) -> Any:
    if hasattr(value, "item"):
        return value.item()
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    return value


def _public_job(row: dict[str, Any]) -> dict[str, Any]:
    summary = {}
    if row.get("summary_json"):
        try:
            summary = json.loads(row["summary_json"])
        except json.JSONDecodeError:
            summary = {}
    return {
        "job_id": row.get("job_id"),
        "workspace_id": row.get("workspace_id"),
        "user_id": row.get("user_id"),
        "dataset_type": row.get("dataset_type"),
        "filename": row.get("filename"),
        "mode": row.get("mode"),
        "status": row.get("status"),
        "row_count": row.get("row_count", 0),
        "error_message": row.get("error_message"),
        "summary": summary,
        "created_at": row.get("created_at"),
        "completed_at": row.get("completed_at"),
    }


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)
