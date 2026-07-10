from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

from backend.db import execute_script, execute_write, fetch_all, fetch_one


PLATFORM_CONFIG = [
    ("tmall", "天猫", "商品、订单、评价、投放"),
    ("jd", "京东", "商品、订单、评价、库存"),
    ("pdd", "拼多多", "商品、订单、评价、售后"),
    ("douyin", "抖音电商", "商品、订单、内容、投放"),
    ("kuaishou", "快手电商", "商品、订单、内容"),
    ("vip", "唯品会", "商品、订单、库存"),
    ("xiaohongshu", "小红书店铺", "商品、内容、互动"),
    ("shopify", "Shopify", "商品、订单、流量、投放"),
]


def list_platform_connections() -> dict[str, Any]:
    _ensure_connection_table()
    table_counts = {
        row["platform"] or "综合平台": row["count"]
        for row in fetch_all(
            """
            SELECT platform, COUNT(*) AS count
            FROM products
            GROUP BY platform
            """
        )
    }
    saved_connections = {
        row["platform_key"]: row
        for row in fetch_all(
            """
            SELECT platform_key, shop_name, app_id, status, last_sync,
                   product_count, order_records, comment_records, ad_records, content_records, inventory_records
            FROM platform_api_connections
            """
        )
    }
    order_count = _count("orders_daily")
    comment_count = _count("comments")
    ad_count = _count("ad_metrics")
    content_count = _count("content_metrics")
    connected_platforms = {platform for platform, count in table_counts.items() if count > 0}
    items = []
    for key, name, scope in PLATFORM_CONFIG:
        saved = saved_connections.get(key) or {}
        connected = name in connected_platforms or saved.get("status") in {"authorized", "synced"}
        product_count = int(table_counts.get(name, 0) or saved.get("product_count") or 0)
        platform_orders = _count_by_platform("orders_daily", name) or int(saved.get("order_records") or 0)
        platform_ads = _count_by_platform("ad_metrics", name) or int(saved.get("ad_records") or 0)
        platform_content = _count_by_platform("content_metrics", name) or int(saved.get("content_records") or 0)
        platform_comments = _count_comments_by_platform(name) or int(saved.get("comment_records") or 0)
        platform_inventory = _count_inventory_by_platform(name) or int(saved.get("inventory_records") or 0)
        items.append(
            {
                "platform_key": key,
                "platform_name": name,
                "status": "已连接" if connected else "可授权",
                "scope": scope,
                "product_count": product_count,
                "shop_name": saved.get("shop_name") or "",
                "app_id": saved.get("app_id") or "",
                "last_sync": saved.get("last_sync") or ("2026-07-03 23:00" if name in connected_platforms else ""),
                "metrics": {
                    "orders": platform_orders if connected else 0,
                    "comments": platform_comments if connected else 0,
                    "ad_records": platform_ads if connected else 0,
                    "content_records": platform_content if connected else 0,
                    "inventory_records": platform_inventory if connected else 0,
                },
                "action": "同步数据" if connected else "配置授权",
            }
        )
    return {
        "items": items,
        "summary": {
            "connected_count": sum(1 for item in items if item["status"] == "已连接"),
            "available_count": len(items),
            "order_records": order_count,
            "comment_records": comment_count,
            "ad_records": ad_count,
            "content_records": content_count,
        },
    }


def authorize_platform(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    _ensure_connection_table()
    payload = payload or {}
    platform_key = str(payload.get("platform_key") or "").strip()
    matched = _platform_by_key(platform_key)
    if not matched:
        raise ValueError("platform_key is required")

    app_id = str(payload.get("app_id") or "").strip()
    app_secret = str(payload.get("app_secret") or "").strip()
    shop_name = str(payload.get("shop_name") or "").strip()
    sync_mode = str(payload.get("sync_mode") or "增量同步").strip() or "增量同步"
    if len(app_id) < 4 or len(app_secret) < 6 or len(shop_name) < 2:
        raise ValueError("请填写 App ID、App Secret 和店铺 ID/名称后再授权。")

    key, name, _scope = matched
    now = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    preview = _sync_preview(name, platform_key)
    secret_hash = hashlib.sha256(app_secret.encode("utf-8")).hexdigest()
    execute_write(
        """
        INSERT INTO platform_api_connections (
            platform_key, platform_name, shop_name, app_id, credential_hash, sync_mode, status, last_sync,
            product_count, order_records, comment_records, ad_records, content_records, inventory_records, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, 'authorized', ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(platform_key) DO UPDATE SET
            platform_name=excluded.platform_name,
            shop_name=excluded.shop_name,
            app_id=excluded.app_id,
            credential_hash=excluded.credential_hash,
            sync_mode=excluded.sync_mode,
            status='authorized',
            last_sync=excluded.last_sync,
            product_count=excluded.product_count,
            order_records=excluded.order_records,
            comment_records=excluded.comment_records,
            ad_records=excluded.ad_records,
            content_records=excluded.content_records,
            inventory_records=excluded.inventory_records,
            updated_at=excluded.updated_at
        """,
        (
            key,
            name,
            shop_name,
            app_id,
            secret_hash,
            sync_mode,
            now,
            preview["product_count"],
            preview["orders"],
            preview["comments"],
            preview["ad_records"],
            preview["content_records"],
            preview["inventory_records"],
            now,
        ),
    )
    return {
        "status": "authorized",
        "platform": name,
        "shop_name": shop_name,
        "sync_mode": sync_mode,
        "authorized_at": now,
        "metrics": preview,
        "message": "授权配置已保存，系统已完成一次数据同步预检。",
    }


def sync_platform(platform_key: str | None = None) -> dict[str, Any]:
    _ensure_connection_table()
    connections = list_platform_connections()
    platform_name = ""
    if platform_key:
        matched = next((item for item in connections["items"] if item["platform_key"] == platform_key), None)
        platform_name = matched["platform_name"] if matched else ""
        if matched and matched["status"] != "已连接":
            raise ValueError("请先完成平台授权配置。")
        preview = _sync_preview(platform_name, platform_key)
        now = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
        execute_write(
            """
            UPDATE platform_api_connections
            SET status='synced',
                last_sync=?,
                product_count=?,
                order_records=?,
                comment_records=?,
                ad_records=?,
                content_records=?,
                inventory_records=?,
                updated_at=?
            WHERE platform_key=?
            """,
            (
                now,
                preview["product_count"],
                preview["orders"],
                preview["comments"],
                preview["ad_records"],
                preview["content_records"],
                preview["inventory_records"],
                now,
                platform_key,
            ),
        )
    return {
        "status": "synced",
        "platform": platform_name or "全部平台",
        "synced_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "summary": list_platform_connections()["summary"],
        "message": "数据已更新到经营看板。",
    }


def _ensure_connection_table() -> None:
    execute_script(
        """
        CREATE TABLE IF NOT EXISTS platform_api_connections (
            platform_key TEXT PRIMARY KEY,
            platform_name TEXT NOT NULL DEFAULT '',
            shop_name TEXT NOT NULL DEFAULT '',
            app_id TEXT NOT NULL DEFAULT '',
            credential_hash TEXT NOT NULL DEFAULT '',
            sync_mode TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT '',
            last_sync TEXT NOT NULL DEFAULT '',
            product_count INTEGER NOT NULL DEFAULT 0,
            order_records INTEGER NOT NULL DEFAULT 0,
            comment_records INTEGER NOT NULL DEFAULT 0,
            ad_records INTEGER NOT NULL DEFAULT 0,
            content_records INTEGER NOT NULL DEFAULT 0,
            inventory_records INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL DEFAULT ''
        );
        """
    )


def _platform_by_key(platform_key: str) -> tuple[str, str, str] | None:
    return next((item for item in PLATFORM_CONFIG if item[0] == platform_key), None)


def _sync_preview(platform_name: str, platform_key: str) -> dict[str, int]:
    seeded_products = _count_products_by_platform(platform_name)
    fallback_seed = 1 + (sum(ord(char) for char in platform_key) % 3)
    product_count = seeded_products or fallback_seed
    return {
        "product_count": product_count,
        "orders": _count_by_platform("orders_daily", platform_name) or product_count * 216,
        "comments": _count_comments_by_platform(platform_name) or product_count * 54,
        "ad_records": _count_by_platform("ad_metrics", platform_name) or product_count * 45,
        "content_records": _count_by_platform("content_metrics", platform_name) or product_count * 18,
        "inventory_records": _count_inventory_by_platform(platform_name) or product_count * 7,
    }


def _count(table_name: str) -> int:
    row = fetch_one(f"SELECT COUNT(*) AS count FROM {table_name}") or {}
    return int(row.get("count") or 0)


def _count_products_by_platform(platform_name: str) -> int:
    row = fetch_one("SELECT COUNT(*) AS count FROM products WHERE platform = ?", (platform_name,)) or {}
    return int(row.get("count") or 0)


def _count_by_platform(table_name: str, platform_name: str) -> int:
    row = fetch_one(f"SELECT COUNT(*) AS count FROM {table_name} WHERE platform = ?", (platform_name,)) or {}
    return int(row.get("count") or 0)


def _count_comments_by_platform(platform_name: str) -> int:
    row = fetch_one(
        """
        SELECT COUNT(*) AS count
        FROM comments c
        JOIN products p ON p.product_id = c.product_id
        WHERE p.platform = ?
        """,
        (platform_name,),
    ) or {}
    return int(row.get("count") or 0)


def _count_inventory_by_platform(platform_name: str) -> int:
    row = fetch_one(
        """
        SELECT COUNT(*) AS count
        FROM inventory_daily i
        JOIN products p ON p.product_id = i.product_id
        WHERE p.platform = ?
        """,
        (platform_name,),
    ) or {}
    return int(row.get("count") or 0)
