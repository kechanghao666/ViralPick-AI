from __future__ import annotations

import re
from pathlib import Path

import pandas as pd


ROOT_DIR = Path(__file__).resolve().parents[1]
PROCESSED_DIR = ROOT_DIR / "data" / "processed"

FORBIDDEN_COMMENT_CATEGORIES = {"酒店", "旅游", "餐饮", "游戏"}


def read_csv(name: str) -> pd.DataFrame:
    path = PROCESSED_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Missing processed dataset: {path}")
    return pd.read_csv(path, encoding="utf-8-sig")


def validate() -> list[str]:
    products = read_csv("products.csv")
    comments = read_csv("comments.csv")
    competitors = read_csv("competitors.csv")
    errors: list[str] = []
    chinese_pattern = re.compile(r"[\u4e00-\u9fff]")

    if products["product_name"].map(lambda value: not bool(chinese_pattern.search(str(value)))).any():
        errors.append("products.csv 商品名必须包含中文。")
    if products["image_url"].isna().any() or products["image_url"].astype(str).str.strip().eq("").any():
        errors.append("products.csv 每个商品必须有 image_url。")
    if products["image_url"].astype(str).str.lower().str.endswith(".svg").any():
        errors.append("products.csv must not continue using SVG placeholder product images.")

    source_text = " ".join(
        products.get(column, pd.Series(dtype=str)).astype(str).str.cat(sep=" ")
        for column in ["data_source", "source_dataset"]
    )
    if "UCI Online Retail" in source_text:
        errors.append("products.csv 不得继续引用 UCI Online Retail。")

    allowed_categories = set(products["category"].dropna().unique())
    invalid_comment_categories = set(comments["category_source"].dropna().unique()).difference(allowed_categories)
    if invalid_comment_categories:
        errors.append(f"comments.csv 评论类目不在商品类目中：{sorted(invalid_comment_categories)}")
    forbidden = set(comments["category_source"].dropna().unique()).intersection(FORBIDDEN_COMMENT_CATEGORIES)
    if forbidden:
        errors.append(f"comments.csv 包含非商品服务类目：{sorted(forbidden)}")

    category_map = products.set_index("product_id")["category"].to_dict()
    mismatch = [
        row["competitor_id"]
        for _, row in competitors.iterrows()
        if category_map.get(row["product_id"]) != row["category"]
    ]
    if mismatch:
        errors.append(f"competitors.csv 存在不同类目竞品：{mismatch[:5]}")
    return errors


def main() -> None:
    errors = validate()
    if errors:
        raise SystemExit("Domestic data validation failed:\n- " + "\n- ".join(errors))
    print("Domestic ecommerce data validation passed.")


if __name__ == "__main__":
    main()
