from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pandas as pd


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.config import DATABASE_PATH


PROCESSED_DIR = ROOT_DIR / "data" / "processed"

BUSINESS_TABLES = {
    "orders_daily": PROCESSED_DIR / "orders_daily.csv",
    "inventory_daily": PROCESSED_DIR / "inventory_daily.csv",
    "after_sales": PROCESSED_DIR / "after_sales.csv",
    "ad_metrics": PROCESSED_DIR / "ad_metrics.csv",
    "traffic_metrics": PROCESSED_DIR / "traffic_metrics.csv",
    "content_metrics": PROCESSED_DIR / "content_metrics.csv",
}


def load_business_tables(db_path: Path = DATABASE_PATH) -> dict[str, int]:
    missing = [path for path in BUSINESS_TABLES.values() if not path.exists()]
    if missing:
        missing_text = "\n".join(str(path) for path in missing)
        raise FileNotFoundError(f"Missing processed business CSV files:\n{missing_text}")

    counts: dict[str, int] = {}
    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        for table_name, csv_path in BUSINESS_TABLES.items():
            frame = pd.read_csv(csv_path, encoding="utf-8-sig")
            connection.execute(f"DELETE FROM {table_name}")
            frame.to_sql(table_name, connection, if_exists="append", index=False)
            counts[table_name] = len(frame)
        connection.commit()
    return counts


def main() -> None:
    counts = load_business_tables()
    print(f"Business metrics loaded into: {DATABASE_PATH}")
    for table_name, count in counts.items():
        print(f"{table_name}: {count}")


if __name__ == "__main__":
    main()
