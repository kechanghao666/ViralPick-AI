from __future__ import annotations

from scripts.validate_domestic_data import validate


def test_domestic_ecommerce_processed_data_passes_quality_gate():
    assert validate() == []


def test_product_images_use_real_jpg_assets():
    import pandas as pd

    products = pd.read_csv("data/processed/products.csv", encoding="utf-8-sig")
    assert products["image_url"].str.endswith(".jpg").all()
