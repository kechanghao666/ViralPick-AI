# ViralPick AI 数据库设计

数据库采用 SQLite。当前阶段优先保证本地可运行、可展示、可导入和可答辩，后续可平滑扩展到 MySQL 或其他关系型数据库。

## 核心业务表

### `products`

商品主表，保存商品名称、平台、品牌、店铺、图片、卖点、类目、价格、销量、销售额、评分、好评率、增长率、爆品潜力分和风险等级。

### `sales_daily`

每日销售明细，按日期和商品记录销量、销售额、订单数和平均单价。

### `comments`

用户评论表，保存评论内容、情感标签、评分、评论类目和商品关联。

### `competitors`

竞品表，保存同类竞品的名称、平台、店铺、图片、卖点、价格、销量、评分、好评率和主卖点。支持导入和手动录入。

### `video_metrics`

历史兼容表，用于保存已有内容互动数据。前端统一展示为内容运营数据。

## 新增经营数据表

### `orders_daily`

订单经营聚合表。

主要字段：

- `date`
- `platform`
- `product_id`
- `product_name`
- `order_count`
- `paid_amount`
- `customer_unit_price`
- `refund_amount`
- `conversion_rate`

### `inventory_daily`

库存表。

主要字段：

- `date`
- `product_id`
- `product_name`
- `stock_quantity`
- `available_stock`
- `replenishment_threshold`
- `stockout_risk`
- `slow_moving_days`

### `after_sales`

售后退款表。

主要字段：

- `after_sale_id`
- `date`
- `platform`
- `product_id`
- `product_name`
- `refund_amount`
- `refund_count`
- `reason`
- `status`

### `ad_metrics`

广告投放表。

主要字段：

- `date`
- `platform`
- `campaign_name`
- `product_id`
- `product_name`
- `spend`
- `impressions`
- `clicks`
- `conversions`
- `revenue`
- `roi`

### `traffic_metrics`

流量转化表。

主要字段：

- `date`
- `platform`
- `product_id`
- `product_name`
- `visitors`
- `page_views`
- `cart_adds`
- `favorites`
- `payment_conversion_rate`

### `content_metrics`

内容运营表。

主要字段：

- `date`
- `platform`
- `content_type`
- `topic`
- `product_id`
- `product_name`
- `impressions`
- `interactions`
- `guided_revenue`
- `effect_score`

## 导入相关表

### `import_previews`

保存智能导入预览结果，支持“先识别、再确认、后写入”的流程。

主要字段：

- `preview_id`
- `filename`
- `dataset_type`
- `source_columns_json`
- `field_mapping_json`
- `preview_rows_json`
- `raw_rows_json`
- `quality_json`
- `status`
- `committed_job_id`
- `created_at`

### `import_jobs`

保存导入执行记录，包括文件名、数据类型、导入策略、状态、行数、错误信息和汇总 JSON。

## 结果表

### `forecast_results`

保存销量和销售额预测结果。

### `analysis_reports`

保存《店铺经营分析报告》的结构化 JSON 和 Markdown 内容。

## 兼容保留表

项目仍保留认证、团队、审计、品牌、调度、分享和自动化相关表，原因是这些能力已经存在于历史版本中，保留可以避免破坏旧测试和后续扩展。但当前产品主流程不展示这些后台管理功能。

## 视图

### `v_product_performance`

聚合商品主表和内容互动数据，为商品增长中心、爆品评分和经营驾驶舱提供统一查询入口。

### `v_category_summary`

按类目聚合商品数、销量、销售额、均价、评分、好评率和潜力分。

## 迁移

新增业务表由迁移 `20260703_001_business_center_tables` 管理。已有数据库升级时执行：

```bash
python scripts/migrate_database.py
```

重新生成本地库时执行：

```bash
python scripts/init_database.py --force
```
