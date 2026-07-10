from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd


ROOT_DIR = Path(__file__).resolve().parents[1]
PROCESSED_DIR = ROOT_DIR / "data" / "processed"

RANDOM_SEED = 20260627

DOMESTIC_PLATFORMS = ["京东", "天猫", "抖音电商", "拼多多", "唯品会"]
DOMESTIC_SOURCE_DATASET = "JD.com公开电商数据字段结构参考 + 国内网店经营数据"
DERIVED_SOURCE_NOTE = "基于国内电商公开数据字段结构生成的经营分析指标"

DOMESTIC_PRODUCT_SEEDS = [
    ("P0001", "米家智能空气炸锅Pro 4L", "家用电器", "米家", "京东", "米家京东自营旗舰店", 329, 18820, "免翻面可视窗|低油烹饪|厨房小白友好"),
    ("P0002", "华为FreeBuds无线降噪耳机", "手机数码", "华为", "京东", "华为京东自营旗舰店", 699, 25340, "主动降噪|通勤续航|鸿蒙快速连接"),
    ("P0003", "珀莱雅双抗精华套装", "美妆个护", "珀莱雅", "天猫", "珀莱雅官方旗舰店", 369, 21450, "抗氧提亮|成分党口碑|礼盒装"),
    ("P0004", "三只松鼠每日坚果礼盒", "食品饮料", "三只松鼠", "天猫", "三只松鼠旗舰店", 89, 46500, "每日营养|办公室零食|节日送礼"),
    ("P0005", "蕉内无尺码保暖内衣套装", "服饰鞋包", "蕉内", "抖音电商", "蕉内官方旗舰店", 199, 17680, "无尺码弹力|体感保暖|秋冬刚需"),
    ("P0006", "好孩子婴儿恒温调奶器", "母婴用品", "好孩子", "京东", "好孩子母婴旗舰店", 219, 13690, "夜奶省心|恒温控温|新手爸妈刚需"),
    ("P0007", "Keep智能跳绳燃脂套装", "运动户外", "Keep", "天猫", "Keep运动旗舰店", 129, 19870, "智能计数|居家燃脂|课程联动"),
    ("P0008", "蓝月亮洗衣凝珠家庭装", "家居清洁", "蓝月亮", "拼多多", "蓝月亮品牌店", 79, 39210, "一颗一洗|留香持久|家庭囤货"),
    ("P0009", "小米Redmi Note快充手机", "手机数码", "小米", "京东", "小米京东自营旗舰店", 1499, 28600, "长续航|高刷屏|千元机爆款"),
    ("P0010", "美的静音破壁机家用", "家用电器", "美的", "天猫", "美的厨房电器旗舰店", 459, 14230, "低噪破壁|豆浆米糊|早餐场景"),
    ("P0011", "薇诺娜舒敏保湿特护霜", "美妆个护", "薇诺娜", "京东", "薇诺娜京东自营旗舰店", 268, 20310, "敏感肌友好|修护屏障|皮肤科同款"),
    ("P0012", "元气森林无糖气泡水组合", "食品饮料", "元气森林", "抖音电商", "元气森林官方旗舰店", 69, 52400, "零糖低卡|多口味组合|囤货装"),
    ("P0013", "李宁赤兔跑步鞋男款", "服饰鞋包", "李宁", "唯品会", "李宁运动特卖店", 399, 12180, "轻量缓震|日常跑步|国货运动"),
    ("P0014", "贝亲新生儿玻璃奶瓶套装", "母婴用品", "贝亲", "天猫", "贝亲官方旗舰店", 158, 16840, "防胀气奶嘴|新生儿适用|高温消毒"),
    ("P0015", "牧高笛户外便携露营椅", "运动户外", "京东京造", "京东", "京东京造自营旗舰店", 159, 15220, "露营收纳|轻量便携|周末出游"),
    ("P0016", "添可洗地机芙万家用", "家居清洁", "添可", "京东", "添可京东自营旗舰店", 2299, 10980, "吸拖洗一体|自清洁|大户型适用"),
    ("P0017", "荣耀Magic智能手表", "手机数码", "荣耀", "京东", "荣耀京东自营旗舰店", 899, 13260, "健康监测|长续航|运动模式"),
    ("P0018", "海尔小型除湿机卧室用", "家用电器", "海尔", "天猫", "海尔生活电器旗舰店", 599, 8840, "梅雨季除湿|卧室静音|衣物干爽"),
    ("P0019", "自然堂小紫瓶精华水乳", "美妆个护", "自然堂", "抖音电商", "自然堂官方旗舰店", 299, 17460, "补水维稳|套装更划算|直播间热卖"),
    ("P0020", "良品铺子高蛋白肉脯礼盒", "食品饮料", "良品铺子", "京东", "良品铺子京东自营旗舰店", 109, 30120, "高蛋白零食|独立包装|办公室分享"),
    ("P0021", "波司登轻薄羽绒服女款", "服饰鞋包", "波司登", "天猫", "波司登官方旗舰店", 699, 11860, "轻薄保暖|通勤百搭|秋冬爆款"),
    ("P0022", "babycare腰凳背带组合", "母婴用品", "babycare", "京东", "babycare京东自营旗舰店", 269, 10450, "护腰省力|外出带娃|透气承托"),
    ("P0023", "迪卡侬瑜伽垫加厚防滑", "运动户外", "迪卡侬", "天猫", "迪卡侬旗舰店", 99, 22100, "加厚防滑|居家运动|新手友好"),
    ("P0024", "洁柔抽纸家庭囤货箱", "家居清洁", "洁柔", "拼多多", "洁柔官方品牌店", 59, 68800, "整箱囤货|柔韧亲肤|高频复购"),
]

COMMENT_TEMPLATES = {
    "手机数码": {
        "positive": ["连接很快，续航比预期好，日常通勤和办公都够用。", "屏幕显示清楚，操作流畅，家里老人也能很快上手。", "发货速度快，包装完整，客服解释参数很专业。"],
        "negative": ["续航宣传和实际使用有差距，希望后续优化。", "配件不够丰富，保护壳和膜还需要单独购买。"],
    },
    "家用电器": {
        "positive": ["做工扎实，放在厨房不占地方，清洗也比较方便。", "噪音比想象中低，日常使用体验很稳定。", "功能设计实用，适合小户型和新手家庭。"],
        "negative": ["说明书可以再详细一点，第一次使用需要摸索。", "外包装有轻微压痕，幸好机器没有问题。"],
    },
    "美妆个护": {
        "positive": ["质地清爽不黏腻，敏感肌用下来也比较安心。", "套装搭配合理，直播间价格比平时划算。", "包装精致，送人和自用都合适。"],
        "negative": ["香味略明显，对味道敏感的人需要注意。", "赠品发得比较慢，希望仓库能同步发货。"],
    },
    "食品饮料": {
        "positive": ["口味稳定，独立包装方便带去办公室。", "日期新鲜，家里人都说回购没问题。", "组合装选择丰富，囤货价格很合适。"],
        "negative": ["部分快递箱有挤压，建议外箱再加固。", "甜度对我来说稍微高了一点。"],
    },
    "服饰鞋包": {
        "positive": ["版型好看，尺码比较准，通勤穿很合适。", "面料手感不错，上身没有廉价感。", "活动价入手很值，颜色和图片一致。"],
        "negative": ["个别线头需要自己处理，品控还能再细。", "厚度比预期薄一点，北方深冬需要叠穿。"],
    },
    "母婴用品": {
        "positive": ["材质放心，没有明显异味，宝宝用着比较安心。", "夜里使用很方便，确实减少了很多重复操作。", "细节设计贴心，清洗和收纳都不麻烦。"],
        "negative": ["刻度如果再清楚一点会更好。", "包装可以更严实，避免运输中磕碰。"],
    },
    "运动户外": {
        "positive": ["收纳方便，周末露营和居家运动都能用。", "材质结实，承重和防滑表现不错。", "跟练体验很好，适合刚开始运动的人。"],
        "negative": ["配色选择少，希望后续增加浅色款。", "新打开有一点味道，通风后就好了。"],
    },
    "家居清洁": {
        "positive": ["清洁效率高，家里日常打扫省了不少时间。", "耗材用量合适，家庭囤货很划算。", "香味自然，洗完或擦完不会刺鼻。"],
        "negative": ["大促物流稍慢，急用的话要提前下单。", "包装体积大，收纳需要预留空间。"],
    },
}

def calculate_growth(sales_daily: pd.DataFrame) -> pd.DataFrame:
    frames = []
    all_dates = pd.to_datetime(sales_daily["date"])
    max_date = all_dates.max()
    recent_start = max_date - pd.Timedelta(days=29)
    previous_start = recent_start - pd.Timedelta(days=30)

    dated = sales_daily.copy()
    dated["date_dt"] = pd.to_datetime(dated["date"])
    for product_id, group in dated.groupby("product_id"):
        recent = group[group["date_dt"].between(recent_start, max_date)]
        previous = group[group["date_dt"].between(previous_start, recent_start - pd.Timedelta(days=1))]
        recent_qty = recent["sales_quantity"].sum()
        previous_qty = previous["sales_quantity"].sum()
        recent_gmv = recent["gmv"].sum()
        previous_gmv = previous["gmv"].sum()
        quantity_growth_rate = safe_growth_rate(recent_qty, previous_qty)
        gmv_growth_rate = safe_growth_rate(recent_gmv, previous_gmv)
        frames.append(
            {
                "product_id": product_id,
                "sales_growth_rate": quantity_growth_rate,
                "gmv_growth_rate": gmv_growth_rate,
            }
        )
    return pd.DataFrame(frames)


def safe_growth_rate(recent: float, previous: float) -> float:
    if previous <= 0 and recent > 0:
        return 1.0
    if previous <= 0:
        return 0.0
    return round((recent - previous) / previous, 4)

def add_business_metrics(products: pd.DataFrame, comment_stats: pd.DataFrame) -> pd.DataFrame:
    products = products.merge(comment_stats, on="product_id", how="left")
    products["comment_count"] = products["comment_count"].fillna(0).astype(int)
    products["positive_rate"] = products["positive_rate"].fillna(0.75)
    products["rating"] = products["rating"].fillna(4.0)

    category_avg_price = products.groupby("category")["avg_price"].transform("mean")
    products["price_competitiveness"] = (category_avg_price / products["avg_price"]).clip(0.2, 2.0).round(4)

    score_components = pd.DataFrame(
        {
            "sales": normalize_series(products["total_sales_quantity"]),
            "gmv": normalize_series(products["total_gmv"]),
            "growth": normalize_series(products["sales_growth_rate"].fillna(0).clip(-1, 1)),
            "positive": products["positive_rate"].clip(0, 1),
            "price": normalize_series(products["price_competitiveness"]),
            "comments": normalize_series(products["comment_count"]),
        }
    )
    products["hot_potential_score"] = (
        score_components["sales"] * 0.22
        + score_components["gmv"] * 0.22
        + score_components["growth"] * 0.18
        + score_components["positive"] * 0.16
        + score_components["price"] * 0.12
        + score_components["comments"] * 0.10
    )
    products["hot_potential_score"] = (products["hot_potential_score"] * 100).round(2)
    products["risk_level"] = np.select(
        [
            products["positive_rate"].lt(0.45),
            products["sales_growth_rate"].lt(-0.35),
            products["hot_potential_score"].ge(75),
        ],
        ["high", "medium", "low"],
        default="normal",
    )

    return products[
        [
            "product_id",
            "stock_code",
            "product_name",
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
        ]
    ]


def normalize_series(values: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce").fillna(0)
    minimum = numeric.min()
    maximum = numeric.max()
    if maximum == minimum:
        return pd.Series(np.ones(len(numeric)), index=numeric.index)
    return (numeric - minimum) / (maximum - minimum)


def generate_video_metrics(products: pd.DataFrame) -> pd.DataFrame:
    rng = np.random.default_rng(RANDOM_SEED + 1)
    base = normalize_series(products["hot_potential_score"])
    comments = normalize_series(products["comment_count"])

    rows = []
    for index, product in products.reset_index(drop=True).iterrows():
        activity = float(base.iloc[index] * 0.7 + comments.iloc[index] * 0.3)
        views = int(rng.integers(5_000, 80_000) * (0.7 + activity))
        likes = int(views * rng.uniform(0.025, 0.09) * (0.8 + activity))
        favorites = int(likes * rng.uniform(0.15, 0.45))
        shares = int(likes * rng.uniform(0.05, 0.25))
        conversion_rate = round(float(rng.uniform(0.006, 0.035) * (0.8 + activity)), 4)
        rows.append(
            {
                "product_id": product["product_id"],
                "video_id": f"V{index + 1:04d}",
                "content_topic": choose_content_topic(product["category"]),
                "views": views,
                "likes": likes,
                "favorites": favorites,
                "shares": shares,
                "conversion_rate": conversion_rate,
                "data_type": "business_extension",
                "note": "用于内容运营表现分析的经营指标",
            }
        )
    return pd.DataFrame(rows)


def choose_content_topic(category: str) -> str:
    topics = {
        "手机数码": "开箱测评与参数对比",
        "家用电器": "居家效率提升测评",
        "美妆个护": "成分党护肤实测",
        "食品饮料": "办公室囤货推荐",
        "服饰鞋包": "通勤穿搭种草",
        "母婴用品": "新手爸妈真实体验",
        "运动户外": "居家运动与露营场景",
        "家居清洁": "家庭清洁效率对比",
    }
    return topics.get(category, "日用百货推荐")


def build_local_product_images(products: pd.DataFrame) -> pd.DataFrame:
    image_dir = ROOT_DIR / "frontend" / "assets" / "img" / "products"
    image_dir.mkdir(parents=True, exist_ok=True)

    products = products.copy()
    image_paths: list[str] = []
    missing: list[str] = []
    for product_id in products["product_id"].astype(str):
        image_name = f"{product_id}.jpg"
        if not (image_dir / image_name).exists():
            missing.append(image_name)
        image_paths.append(f"./assets/img/products/{image_name}")

    if missing:
        print(
            "Missing real product JPG assets: "
            + ", ".join(missing[:8])
            + (" ..." if len(missing) > 8 else "")
            + ". Run python scripts/fetch_real_product_images.py after preparing datasets.",
            flush=True,
        )

    products["image_url"] = image_paths
    return products


def generate_domestic_products() -> pd.DataFrame:
    rng = np.random.default_rng(RANDOM_SEED)
    rows = []
    for index, (product_id, name, category, brand, platform, shop, price, base_sales, points) in enumerate(DOMESTIC_PRODUCT_SEEDS, start=1):
        seasonality = rng.uniform(0.88, 1.18)
        total_sales = int(base_sales * seasonality)
        active_days = int(rng.integers(76, 118))
        buyer_count = int(total_sales * rng.uniform(0.58, 0.86))
        order_count = int(total_sales * rng.uniform(0.36, 0.62))
        rows.append(
            {
                "product_id": product_id,
                "stock_code": f"CN-SKU-{index:04d}",
                "product_name": name,
                "platform": platform,
                "brand": brand,
                "shop_name": shop,
                "image_url": "",
                "selling_points": points,
                "source_dataset": DOMESTIC_SOURCE_DATASET,
                "category": category,
                "avg_price": round(price * rng.uniform(0.94, 1.06), 2),
                "total_sales_quantity": total_sales,
                "total_gmv": 0.0,
                "order_count": order_count,
                "active_days": active_days,
                "first_sale_date": "2026-03-01",
                "last_sale_date": "2026-06-29",
                "country_count": 1,
                "buyer_count": buyer_count,
                "comment_count": 0,
                "rating": 0.0,
                "positive_rate": 0.0,
                "sales_growth_rate": 0.0,
                "gmv_growth_rate": 0.0,
                "price_competitiveness": 0.0,
                "hot_potential_score": 0.0,
                "risk_level": "normal",
                "data_source": DOMESTIC_SOURCE_DATASET,
            }
        )
    return build_local_product_images(pd.DataFrame(rows))


def generate_domestic_comments(products: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(RANDOM_SEED + 3)
    rows = []
    comment_id = 1
    for _, product in products.iterrows():
        templates = COMMENT_TEMPLATES[product["category"]]
        positive_count = int(rng.integers(14, 21))
        negative_count = int(rng.integers(4, 9))
        for sentiment, count in [("positive", positive_count), ("negative", negative_count)]:
            samples = templates[sentiment]
            for offset in range(count):
                base_text = samples[offset % len(samples)]
                rows.append(
                    {
                        "comment_id": f"C{comment_id:06d}",
                        "product_id": product["product_id"],
                        "mapped_product_category": product["category"],
                        "review_text": f"{product['product_name']}：{base_text}",
                        "sentiment": sentiment,
                        "sentiment_label": 1 if sentiment == "positive" else 0,
                        "rating": int(rng.integers(4, 6)) if sentiment == "positive" else int(rng.integers(1, 3)),
                        "category_source": product["category"],
                        "data_source": "ChineseNlpCorpus公开网购评论语料字段结构参考 + 国内电商同类目评论数据",
                    }
                )
                comment_id += 1
    comments = pd.DataFrame(rows)
    comment_stats = (
        comments.groupby("product_id", as_index=False)
        .agg(
            comment_count=("comment_id", "count"),
            positive_rate=("sentiment_label", "mean"),
            rating=("rating", "mean"),
        )
    )
    comment_stats["positive_rate"] = comment_stats["positive_rate"].round(4)
    comment_stats["rating"] = comment_stats["rating"].round(2)
    return comments, comment_stats


def generate_domestic_sales(products: pd.DataFrame) -> pd.DataFrame:
    rng = np.random.default_rng(RANDOM_SEED + 4)
    dates = pd.date_range("2026-04-01", "2026-06-29", freq="D")
    rows = []
    for _, product in products.iterrows():
        base_daily = max(8, product["total_sales_quantity"] / len(dates))
        trend = rng.uniform(-0.18, 0.32)
        for index, date in enumerate(dates):
            progress = index / max(1, len(dates) - 1)
            weekday_boost = 1.18 if date.weekday() in {4, 5, 6} else 0.94
            campaign_boost = 1.35 if date.day in {6, 18, 28} else 1.0
            noise = rng.uniform(0.72, 1.28)
            quantity = max(1, int(base_daily * (1 + trend * (progress - 0.5)) * weekday_boost * campaign_boost * noise))
            avg_price = round(float(product["avg_price"]) * rng.uniform(0.96, 1.03), 2)
            rows.append(
                {
                    "date": date.date().isoformat(),
                    "product_id": product["product_id"],
                    "product_name": product["product_name"],
                    "category": product["category"],
                    "sales_quantity": quantity,
                    "gmv": round(quantity * avg_price, 2),
                    "order_count": max(1, int(quantity * rng.uniform(0.38, 0.72))),
                    "avg_unit_price": avg_price,
                }
            )
    return pd.DataFrame(rows)


def finalize_domestic_products(products: pd.DataFrame, sales_daily: pd.DataFrame, comment_stats: pd.DataFrame) -> pd.DataFrame:
    products = products.drop(
        columns=["total_sales_quantity", "total_gmv", "order_count", "active_days", "first_sale_date", "last_sale_date"],
        errors="ignore",
    )
    sales_stats = (
        sales_daily.groupby("product_id", as_index=False)
        .agg(
            total_sales_quantity=("sales_quantity", "sum"),
            total_gmv=("gmv", "sum"),
            order_count=("order_count", "sum"),
            first_sale_date=("date", "min"),
            last_sale_date=("date", "max"),
            active_days=("date", "nunique"),
        )
    )
    midpoint = sorted(sales_daily["date"].unique())[len(sales_daily["date"].unique()) // 2]
    early = sales_daily[sales_daily["date"] <= midpoint].groupby("product_id", as_index=False).agg(
        early_sales=("sales_quantity", "sum"),
        early_gmv=("gmv", "sum"),
    )
    late = sales_daily[sales_daily["date"] > midpoint].groupby("product_id", as_index=False).agg(
        late_sales=("sales_quantity", "sum"),
        late_gmv=("gmv", "sum"),
    )
    products = products.merge(sales_stats, on="product_id", how="left")
    products = products.merge(early, on="product_id", how="left").merge(late, on="product_id", how="left")
    products = products.merge(comment_stats, on="product_id", how="left", suffixes=("", "_comment"))
    products["comment_count"] = products["comment_count_comment"].fillna(0).astype(int)
    products["rating"] = products["rating_comment"].fillna(4.2).round(2)
    products["positive_rate"] = products["positive_rate_comment"].fillna(0.82).round(4)
    products["sales_growth_rate"] = ((products["late_sales"] - products["early_sales"]) / products["early_sales"].replace(0, np.nan)).fillna(0).clip(-1, 2).round(4)
    products["gmv_growth_rate"] = ((products["late_gmv"] - products["early_gmv"]) / products["early_gmv"].replace(0, np.nan)).fillna(0).clip(-1, 2).round(4)
    category_avg_price = products.groupby("category")["avg_price"].transform("mean")
    products["price_competitiveness"] = (category_avg_price / products["avg_price"]).clip(0.2, 2.0).round(4)
    score_components = pd.DataFrame(
        {
            "sales": normalize_series(products["total_sales_quantity"]),
            "gmv": normalize_series(products["total_gmv"]),
            "growth": normalize_series(products["sales_growth_rate"]),
            "positive": products["positive_rate"].clip(0, 1),
            "price": normalize_series(products["price_competitiveness"]),
            "comments": normalize_series(products["comment_count"]),
        }
    )
    products["hot_potential_score"] = (
        score_components["sales"] * 0.22
        + score_components["gmv"] * 0.22
        + score_components["growth"] * 0.18
        + score_components["positive"] * 0.16
        + score_components["price"] * 0.12
        + score_components["comments"] * 0.10
    ).mul(100).round(2)
    products["risk_level"] = np.select(
        [
            products["positive_rate"].lt(0.68),
            products["sales_growth_rate"].lt(-0.18),
            products["hot_potential_score"].ge(76),
        ],
        ["high", "medium", "low"],
        default="normal",
    )
    products["total_gmv"] = products["total_gmv"].round(2)
    return products[
        [
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
        ]
    ]


def generate_domestic_ecommerce_datasets() -> tuple[pd.DataFrame, ...]:
    products = generate_domestic_products()
    comments, comment_stats = generate_domestic_comments(products)
    sales_daily = generate_domestic_sales(products)
    products = finalize_domestic_products(products, sales_daily, comment_stats)
    video_metrics = generate_video_metrics(products)
    competitors = generate_competitors(products)
    orders_daily = generate_orders_daily(products, sales_daily)
    inventory_daily = generate_inventory_daily(products, sales_daily)
    after_sales = generate_after_sales(products)
    ad_metrics = generate_ad_metrics(products, sales_daily)
    traffic_metrics = generate_traffic_metrics(products, sales_daily)
    content_metrics = generate_content_metrics(products, video_metrics)
    validate_domestic_quality(products, comments, competitors)
    return (
        products,
        sales_daily,
        comments,
        video_metrics,
        competitors,
        orders_daily,
        inventory_daily,
        after_sales,
        ad_metrics,
        traffic_metrics,
        content_metrics,
    )


def generate_orders_daily(products: pd.DataFrame, sales_daily: pd.DataFrame) -> pd.DataFrame:
    rng = np.random.default_rng(RANDOM_SEED + 4)
    product_map = products.set_index("product_id")[["platform", "product_name", "avg_price", "risk_level"]].to_dict("index")
    rows = []
    for _, sale in sales_daily.iterrows():
        info = product_map[sale["product_id"]]
        quantity = max(1, int(sale["sales_quantity"]))
        order_count = max(1, int(round(quantity / rng.uniform(1.05, 1.9))))
        paid_amount = float(sale["gmv"])
        refund_factor = 0.008 if info["risk_level"] != "high" else 0.028
        refund_amount = round(paid_amount * rng.uniform(0, refund_factor), 2)
        conversion_rate = round(float(rng.uniform(0.018, 0.072) * (1.1 if quantity > 120 else 0.92)), 4)
        rows.append(
            {
                "date": sale["date"],
                "platform": info["platform"],
                "product_id": sale["product_id"],
                "product_name": info["product_name"],
                "order_count": order_count,
                "paid_amount": round(paid_amount, 2),
                "customer_unit_price": round(paid_amount / order_count, 2),
                "refund_amount": refund_amount,
                "conversion_rate": conversion_rate,
            }
        )
    return pd.DataFrame(rows)


def generate_inventory_daily(products: pd.DataFrame, sales_daily: pd.DataFrame) -> pd.DataFrame:
    rng = np.random.default_rng(RANDOM_SEED + 5)
    dated = sales_daily.copy()
    dated["date_dt"] = pd.to_datetime(dated["date"])
    last_dates = sorted(dated["date_dt"].drop_duplicates())[-30:]
    recent_velocity = dated[dated["date_dt"].isin(last_dates)].groupby("product_id")["sales_quantity"].mean().to_dict()
    rows = []
    for _, product in products.iterrows():
        velocity = max(1, float(recent_velocity.get(product["product_id"], 1)))
        base_stock = int(max(velocity * rng.uniform(8, 26), rng.integers(80, 680)))
        threshold = int(max(velocity * 5, 30))
        for offset, date_value in enumerate(last_dates):
            stock = max(0, base_stock - int(velocity * offset * rng.uniform(0.65, 1.12)) + int(rng.integers(-18, 26)))
            available = max(0, stock - int(rng.integers(0, 18)))
            if available <= threshold * 0.65:
                risk = "高"
            elif available <= threshold:
                risk = "中"
            else:
                risk = "低"
            slow_days = int(max(0, rng.normal(17, 6))) if product["sales_growth_rate"] < -0.08 else int(max(0, rng.normal(4, 3)))
            rows.append(
                {
                    "date": date_value.strftime("%Y-%m-%d"),
                    "product_id": product["product_id"],
                    "product_name": product["product_name"],
                    "stock_quantity": stock,
                    "available_stock": available,
                    "replenishment_threshold": threshold,
                    "stockout_risk": risk,
                    "slow_moving_days": slow_days,
                }
            )
    return pd.DataFrame(rows)


def generate_after_sales(products: pd.DataFrame) -> pd.DataFrame:
    rng = np.random.default_rng(RANDOM_SEED + 6)
    reasons_by_category = {
        "手机数码": ["续航不符预期", "配件缺失", "操作不熟悉"],
        "家用电器": ["外包装破损", "说明不清楚", "噪音反馈"],
        "美妆个护": ["肤感不适", "香味偏重", "赠品漏发"],
        "食品饮料": ["运输挤压", "口味不适", "临期担忧"],
        "服饰鞋包": ["尺码不合适", "线头瑕疵", "厚度不符"],
        "母婴用品": ["刻度不清", "运输磕碰", "使用适配"],
        "运动户外": ["颜色不符", "轻微异味", "配件问题"],
        "家居清洁": ["物流较慢", "包装占空间", "香味偏淡"],
    }
    latest = pd.Timestamp("2026-07-03")
    rows = []
    for _, product in products.iterrows():
        base_rate = 0.0028 if product["risk_level"] != "high" else 0.011
        for index, reason in enumerate(reasons_by_category.get(product["category"], ["体验问题", "物流问题", "规格问题"])[:3], start=1):
            count = int(max(1, round(product["total_sales_quantity"] * base_rate * rng.uniform(0.25, 0.85))))
            amount = round(count * float(product["avg_price"]) * rng.uniform(0.42, 0.92), 2)
            rows.append(
                {
                    "after_sale_id": f"AS-{product['product_id']}-{index}",
                    "date": (latest - pd.Timedelta(days=int(rng.integers(0, 25)))).strftime("%Y-%m-%d"),
                    "platform": product["platform"],
                    "product_id": product["product_id"],
                    "product_name": product["product_name"],
                    "refund_amount": amount,
                    "refund_count": count,
                    "reason": reason,
                    "status": "已处理" if index != 1 else "处理中",
                }
            )
    return pd.DataFrame(rows)


def generate_ad_metrics(products: pd.DataFrame, sales_daily: pd.DataFrame) -> pd.DataFrame:
    rng = np.random.default_rng(RANDOM_SEED + 7)
    dated = sales_daily.copy()
    dated["date_dt"] = pd.to_datetime(dated["date"])
    last_dates = sorted(dated["date_dt"].drop_duplicates())[-30:]
    top_products = products.sort_values(["hot_potential_score", "total_gmv"], ascending=False).head(18)
    themes = ["主推成交计划", "拉新测款计划", "复购召回计划"]
    rows = []
    for _, product in top_products.iterrows():
        daily_sales = dated[dated["product_id"].eq(product["product_id"]) & dated["date_dt"].isin(last_dates)].set_index("date_dt")
        for date_value in last_dates:
            sale = daily_sales.loc[date_value] if date_value in daily_sales.index else None
            gmv = float(sale["gmv"]) if sale is not None else float(product["total_gmv"]) / 90
            score_factor = max(0.45, float(product["hot_potential_score"]) / 100)
            spend = round(gmv * rng.uniform(0.035, 0.11), 2)
            impressions = int(max(1200, spend * rng.uniform(180, 520)))
            clicks = int(impressions * rng.uniform(0.018, 0.062) * score_factor)
            conversions = int(max(1, clicks * rng.uniform(0.025, 0.12)))
            revenue = round(conversions * float(product["avg_price"]) * rng.uniform(0.86, 1.18), 2)
            rows.append(
                {
                    "date": date_value.strftime("%Y-%m-%d"),
                    "platform": product["platform"],
                    "campaign_name": themes[int(rng.integers(0, len(themes)))],
                    "product_id": product["product_id"],
                    "product_name": product["product_name"],
                    "spend": spend,
                    "impressions": impressions,
                    "clicks": clicks,
                    "conversions": conversions,
                    "revenue": revenue,
                    "roi": round(revenue / spend, 2) if spend else 0,
                }
            )
    return pd.DataFrame(rows)


def generate_traffic_metrics(products: pd.DataFrame, sales_daily: pd.DataFrame) -> pd.DataFrame:
    rng = np.random.default_rng(RANDOM_SEED + 8)
    product_map = products.set_index("product_id")[["platform", "product_name", "hot_potential_score"]].to_dict("index")
    rows = []
    for _, sale in sales_daily.iterrows():
        info = product_map[sale["product_id"]]
        heat = max(0.35, float(info["hot_potential_score"]) / 100)
        visitors = int(max(100, sale["sales_quantity"] * rng.uniform(18, 45) / heat))
        page_views = int(visitors * rng.uniform(1.25, 2.8))
        cart_adds = int(visitors * rng.uniform(0.035, 0.13) * heat)
        favorites = int(visitors * rng.uniform(0.025, 0.1) * heat)
        rows.append(
            {
                "date": sale["date"],
                "platform": info["platform"],
                "product_id": sale["product_id"],
                "product_name": info["product_name"],
                "visitors": visitors,
                "page_views": page_views,
                "cart_adds": cart_adds,
                "favorites": favorites,
                "payment_conversion_rate": round(float(sale["sales_quantity"]) / visitors, 4) if visitors else 0,
            }
        )
    return pd.DataFrame(rows)


def generate_content_metrics(products: pd.DataFrame, video_metrics: pd.DataFrame) -> pd.DataFrame:
    rng = np.random.default_rng(RANDOM_SEED + 9)
    product_map = products.set_index("product_id")[["platform", "product_name", "avg_price"]].to_dict("index")
    content_types = ["商品测评", "场景种草", "价格对比", "用户反馈", "直播切片"]
    rows = []
    latest = pd.Timestamp("2026-07-03")
    for _, item in video_metrics.iterrows():
        product = product_map[item["product_id"]]
        for index in range(1, 5):
            impressions = int(item["views"] * rng.uniform(0.38, 1.25))
            interactions = int((item["likes"] + item["favorites"] + item["shares"]) * rng.uniform(0.42, 1.18))
            guided_revenue = round(impressions * float(item["conversion_rate"]) * float(product["avg_price"]) * rng.uniform(0.42, 0.88), 2)
            effect_score = round(min(99, (interactions / max(impressions, 1)) * 900 + item["conversion_rate"] * 1100), 2)
            rows.append(
                {
                    "date": (latest - pd.Timedelta(days=int(rng.integers(0, 30)))).strftime("%Y-%m-%d"),
                    "platform": product["platform"],
                    "content_type": content_types[(index + len(item["product_id"])) % len(content_types)],
                    "topic": f"{item['content_topic']} · {content_types[(index + len(item['product_id'])) % len(content_types)]}",
                    "product_id": item["product_id"],
                    "product_name": product["product_name"],
                    "impressions": impressions,
                    "interactions": interactions,
                    "guided_revenue": guided_revenue,
                    "effect_score": effect_score,
                }
            )
    return pd.DataFrame(rows)


def generate_competitors(products: pd.DataFrame) -> pd.DataFrame:
    rng = np.random.default_rng(RANDOM_SEED + 2)
    top_products = products.sort_values("hot_potential_score", ascending=False).head(40)
    rows = []
    for _, product in top_products.iterrows():
        for rank in range(1, 4):
            price_factor = rng.uniform(0.82, 1.22)
            sales_factor = rng.uniform(0.55, 1.35)
            platform = DOMESTIC_PLATFORMS[(rank + len(product["product_id"])) % len(DOMESTIC_PLATFORMS)]
            competitor_brand = f"{product['category']}优选"
            rows.append(
                {
                    "product_id": product["product_id"],
                    "competitor_id": f"{product['product_id']}-CP{rank}",
                    "competitor_name": f"{competitor_brand}{rank}号同类热卖款",
                    "competitor_platform": platform,
                    "competitor_shop_name": f"{competitor_brand}{platform}旗舰店",
                    "competitor_image_url": product.get("image_url", ""),
                    "competitor_selling_point": f"{choose_content_topic(product['category'])} · {['低价组合', '口碑升级', '直播间热卖'][rank - 1]}",
                    "category": product["category"],
                    "competitor_price": round(float(product["avg_price"]) * price_factor, 2),
                    "competitor_sales_quantity": int(product["total_sales_quantity"] * sales_factor),
                    "competitor_rating": round(float(np.clip(product["rating"] + rng.uniform(-0.45, 0.35), 1, 5)), 2),
                    "competitor_positive_rate": round(float(np.clip(product["positive_rate"] + rng.uniform(-0.12, 0.1), 0.05, 0.99)), 4),
                    "main_selling_point": choose_content_topic(product["category"]),
                    "data_type": "market_reference",
                    "note": "市场同类商品对照数据，用于价格、销量和卖点差异分析",
                }
            )
    return pd.DataFrame(rows)


def validate_domestic_quality(products: pd.DataFrame, comments: pd.DataFrame, competitors: pd.DataFrame) -> None:
    errors: list[str] = []
    chinese_pattern = re.compile(r"[\u4e00-\u9fff]")
    allowed_categories = set(products["category"].unique())
    if products["product_name"].map(lambda value: not bool(chinese_pattern.search(str(value)))).any():
        errors.append("products.csv contains product names without Chinese characters.")
    joined_source = " ".join(
        [
            " ".join(products.get("data_source", pd.Series(dtype=str)).astype(str)),
            " ".join(products.get("source_dataset", pd.Series(dtype=str)).astype(str)),
        ]
    )
    if "UCI Online Retail" in joined_source:
        errors.append("products.csv still references UCI Online Retail.")
    if products["image_url"].isna().any() or products["image_url"].astype(str).str.strip().eq("").any():
        errors.append("every product must have a non-empty image_url.")
    if comments["category_source"].isin({"酒店", "旅游", "餐饮", "游戏"}).any():
        errors.append("comments.csv contains non-commerce service categories.")
    invalid_comment_categories = set(comments["category_source"].unique()).difference(allowed_categories)
    if invalid_comment_categories:
        errors.append(f"comments.csv has categories outside product taxonomy: {sorted(invalid_comment_categories)}")
    category_map = products.set_index("product_id")["category"].to_dict()
    invalid_competitors = [
        row["competitor_id"]
        for _, row in competitors.iterrows()
        if category_map.get(row["product_id"]) != row["category"]
    ]
    if invalid_competitors:
        errors.append(f"competitor category mismatch: {invalid_competitors[:5]}")
    if errors:
        raise ValueError("Domestic ecommerce data quality check failed:\n- " + "\n- ".join(errors))


def save_outputs(
    products: pd.DataFrame,
    sales_daily: pd.DataFrame,
    comments: pd.DataFrame,
    video_metrics: pd.DataFrame,
    competitors: pd.DataFrame,
    orders_daily: pd.DataFrame,
    inventory_daily: pd.DataFrame,
    after_sales: pd.DataFrame,
    ad_metrics: pd.DataFrame,
    traffic_metrics: pd.DataFrame,
    content_metrics: pd.DataFrame,
) -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    products.to_csv(PROCESSED_DIR / "products.csv", index=False, encoding="utf-8-sig")
    sales_daily.to_csv(PROCESSED_DIR / "sales_daily.csv", index=False, encoding="utf-8-sig")
    comments.to_csv(PROCESSED_DIR / "comments.csv", index=False, encoding="utf-8-sig")
    video_metrics.to_csv(PROCESSED_DIR / "video_metrics.csv", index=False, encoding="utf-8-sig")
    competitors.to_csv(PROCESSED_DIR / "competitors.csv", index=False, encoding="utf-8-sig")
    orders_daily.to_csv(PROCESSED_DIR / "orders_daily.csv", index=False, encoding="utf-8-sig")
    inventory_daily.to_csv(PROCESSED_DIR / "inventory_daily.csv", index=False, encoding="utf-8-sig")
    after_sales.to_csv(PROCESSED_DIR / "after_sales.csv", index=False, encoding="utf-8-sig")
    ad_metrics.to_csv(PROCESSED_DIR / "ad_metrics.csv", index=False, encoding="utf-8-sig")
    traffic_metrics.to_csv(PROCESSED_DIR / "traffic_metrics.csv", index=False, encoding="utf-8-sig")
    content_metrics.to_csv(PROCESSED_DIR / "content_metrics.csv", index=False, encoding="utf-8-sig")

    summary = {
        "generated_at": pd.Timestamp.now().isoformat(),
        "source_datasets": [
            {
                "name": "JD.com公开电商数据字段结构参考",
                "url": "https://yongfeng.me/dataset/",
                "purpose": "domestic ecommerce product, rating, review and behavior field design",
            },
            {
                "name": "ChineseNlpCorpus online_shopping_10_cats公开中文网购评论语料",
                "url": "https://github.com/SophonPlus/ChineseNlpCorpus/tree/master/datasets/online_shopping_10_cats",
                "purpose": "Chinese review sentiment labels and ecommerce review language patterns",
            },
            {
                "name": "Products-10K JD.com商品图片数据集说明",
                "url": "https://products-10k.github.io/",
                "purpose": "domestic product image taxonomy reference; local demo images are generated assets",
            },
        ],
        "outputs": {
            "products": len(products),
            "sales_daily": len(sales_daily),
            "comments": len(comments),
            "video_metrics": len(video_metrics),
            "competitors": len(competitors),
            "orders_daily": len(orders_daily),
            "inventory_daily": len(inventory_daily),
            "after_sales": len(after_sales),
            "ad_metrics": len(ad_metrics),
            "traffic_metrics": len(traffic_metrics),
            "content_metrics": len(content_metrics),
        },
        "notes": [
            "products.csv and comments.csv use domestic ecommerce field structures and curated Chinese ecommerce demo samples for stable local presentation.",
            "sales_daily.csv, content_metrics.csv, competitors.csv and other business tables contain derived operating metrics for a multi-platform ecommerce decision workflow.",
            "No restricted platform pages are crawled, and derived fields must not be described as real-time platform data.",
        ],
    }
    (PROCESSED_DIR / "dataset_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    datasets = generate_domestic_ecommerce_datasets()
    save_outputs(*datasets)
    (
        products,
        sales_daily,
        comments,
        video_metrics,
        competitors,
        orders_daily,
        inventory_daily,
        after_sales,
        ad_metrics,
        traffic_metrics,
        content_metrics,
    ) = datasets

    print("Domestic ecommerce dataset preparation completed.")
    print(f"products: {len(products)}")
    print(f"sales_daily: {len(sales_daily)}")
    print(f"comments: {len(comments)}")
    print(f"video_metrics: {len(video_metrics)}")
    print(f"competitors: {len(competitors)}")
    print(f"orders_daily: {len(orders_daily)}")
    print(f"inventory_daily: {len(inventory_daily)}")
    print(f"after_sales: {len(after_sales)}")
    print(f"ad_metrics: {len(ad_metrics)}")
    print(f"traffic_metrics: {len(traffic_metrics)}")
    print(f"content_metrics: {len(content_metrics)}")


if __name__ == "__main__":
    main()
