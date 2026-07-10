# ViralPick AI API 说明

统一响应格式：

```json
{
  "success": true,
  "data": {}
}
```

错误响应：

```json
{
  "success": false,
  "error": "错误信息"
}
```

## 经营驾驶舱

### `GET /api/dashboard/executive`

返回经营驾驶舱数据，包括核心指标、销售趋势、类目贡献、增长机会、风险提醒、今日动作、库存售后和投放内容摘要。

## 数据接入中心

### `GET /api/imports/schema`

返回支持的数据类型、标准字段、必填字段、字段别名和导入策略。

支持的数据类型：

- `products`
- `sales_daily`
- `orders_daily`
- `comments`
- `inventory_daily`
- `after_sales`
- `ad_metrics`
- `traffic_metrics`
- `competitors`
- `content_metrics`
- `video_metrics`

### `POST /api/imports/preview`

上传 CSV / Excel 文件，仅做识别和预览，不写入业务表。

表单参数：

- `file`：上传文件。
- `dataset_type`：可选。为空时自动识别。

返回内容：

- `preview_id`
- `dataset_type`
- `source_columns`
- `field_mapping`
- `preview_rows`
- `quality`
- `supported_datasets`

### `POST /api/imports/commit`

根据预览结果执行导入。

请求体：

```json
{
  "preview_id": "IP-xxx",
  "dataset_type": "sales_daily",
  "field_mapping": {
    "date": "统计日期",
    "product_id": "商品ID",
    "gmv": "支付金额"
  },
  "mode": "date_merge"
}
```

`mode` 支持：

- `replace`：覆盖导入。
- `append`：追加导入。
- `date_merge`：按日期和业务主键合并。

## 商品增长中心

- `GET /api/products`
- `GET /api/products/<product_id>`
- `GET /api/products/rankings`
- `GET /api/analysis/sales`
- `GET /api/analysis/price-bands`
- `GET /api/hot-products/scoring`

## 用户口碑中心

- `GET /api/comments/sentiment`
- `GET /api/comments/keywords`

## 竞品情报中心

### `GET /api/competitors/summary`

返回本品与竞品的价格、销量、评分、好评率、优势、短板、定价建议和差异化建议。

### `POST /api/competitors`

手动录入竞品。

请求体：

```json
{
  "product_id": "P0001",
  "competitor_name": "同类竞品",
  "competitor_platform": "天猫",
  "competitor_shop_name": "竞品旗舰店",
  "competitor_price": 49.9,
  "competitor_sales_quantity": 1200,
  "competitor_rating": 4.7,
  "competitor_positive_rate": 0.91,
  "competitor_selling_point": "组合装热卖"
}
```

## 投放内容中心

### `GET /api/marketing/summary`

返回广告花费、曝光、点击、转化、ROI、内容素材表现和优化建议。没有导入投放文件时，会使用内容运营明细生成基础展示。

## 趋势预测中心

- `GET /api/inventory/summary`
- `GET /api/forecast/sales?days=7|14|30`

`/api/inventory/summary` 返回库存关注、补货建议、滞销提醒、售后原因和售后动作。

## 经营报告中心

### `POST /api/reports/generate`

生成《店铺经营分析报告》。

请求体：

```json
{
  "product_id": "",
  "use_llm": true
}
```

报告章节：

- 经营概览
- 商品表现
- 增长机会
- 风险提醒
- 口碑分析
- 竞品分析
- 投放内容
- 库存售后
- 趋势预测
- 执行动作清单

### `GET /api/reports/<report_id>`

查询已生成报告。

### `GET /api/reports/<report_id>/export?format=docx|pdf|html|md`

导出报告。

## 经营资料库

### `GET /api/knowledge/status`

返回经营资料库状态，包括是否可用、资料条数和更新时间。

### `GET /api/knowledge/search`

检索经营资料库。

查询参数：

- `q` 或 `query`：检索问题。
- `product_id`：可选，限定当前商品相关资料。
- `limit`：可选，默认 5，最大 10。

### `POST /api/knowledge/rebuild`

根据当前业务数据重建经营资料库。该接口用于数据导入后刷新检索资料，前台页面不直接暴露技术过程。

## 智能经营助手

### `POST /api/assistant/chat`

请求体：

```json
{
  "message": "今天应该优先处理什么？",
  "product_id": "P0001",
  "page": "dashboard",
  "use_llm": true
}
```

助手可以回答通用问题，也可以结合当前页面、当前商品和经营数据生成建议。接口返回中包含内部状态字段，前端只展示最终回答。
