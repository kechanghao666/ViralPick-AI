# ViralPick AI 数据准备说明

本目录用于保存项目运行所需的经营数据。当前数据准备流程围绕国内电商/网购平台主题构建，明确区分公开数据集字段结构参考、经营分析数据和市场对照指标。

## 数据来源

### JD.com 公开电商数据字段结构参考

- 地址：https://yongfeng.me/dataset/
- 用途：商品基础字段、购买行为、评分和评论结构参考。
- 处理方式：本项目保留国内电商语义字段，生成可稳定运行的商品、销售和评分数据。

### ChineseNlpCorpus online_shopping_10_cats

- 地址：https://github.com/SophonPlus/ChineseNlpCorpus/tree/master/datasets/online_shopping_10_cats
- 用途：中文网购评论、情感标签和关键词分析结构参考。
- 处理方式：只保留与商品类目匹配的国内网购评论样式，不使用酒店、旅游、餐饮服务、游戏等非商品服务内容。

### Products-10K

- 地址：https://products-10k.github.io/
- 用途：JD.com 场景商品图片数据集结构参考。
- 处理方式：当前版本为每个商品匹配公开可访问商品图并保存为本地 JPG，`data/processed/product_image_sources.json` 记录图片来源页面和原图地址。正式生产环境应替换为授权素材或平台接口返回的合规图片资源。

## 生成文件

运行：

```bash
python scripts/prepare_datasets.py
```

生成结果位于 `data/processed/`：

- `products.csv`：商品主表，用于商品管理、销售分析、爆品评分。
- `sales_daily.csv`：商品每日销售明细，用于趋势分析和预测。
- `comments.csv`：中文评论数据，用于情感分析、关键词提取和痛点总结。
- `video_metrics.csv`：内容运营数据，用于内容热度和商品评分。
- `competitors.csv`：同类目市场对照数据，用于价格、销量和卖点差异参考。
- `dataset_summary.json`：数据来源、生成时间和数据规模摘要。

初始化 SQLite：

```bash
python scripts/init_database.py --force
```

数据库默认生成到：

```text
data/database/viralpick.db
```

该数据库由 CSV 生成，属于可再生文件，不需要提交到 Git。

## 合规边界

`products.csv` 和 `comments.csv` 使用国内公开电商数据集字段结构参考，所有展示商品均为中文网购商品。`sales_daily.csv`、`video_metrics.csv` 和 `competitors.csv` 中的趋势、内容运营和市场对照指标用于经营分析，不能标注为真实平台实时抓取数据。
