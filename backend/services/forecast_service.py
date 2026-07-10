from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import numpy as np

from backend.repositories import result_repository, sales_repository

try:
    from sklearn.linear_model import LinearRegression  # type: ignore
except ImportError:  # pragma: no cover - numpy fallback keeps local demo runnable.
    LinearRegression = None


def get_sales_forecast(
    product_id: str | None = None,
    category: str | None = None,
    days: int = 7,
    save_result: bool = True,
) -> dict[str, Any]:
    history = sales_repository.get_sales_trend(
        product_id=product_id,
        category=category,
        days=90,
    )
    sales_values = [float(item.get("sales_quantity") or 0) for item in history]
    gmv_values = [float(item.get("gmv") or 0) for item in history]
    last_date = _last_date(history)

    sales_forecast, model_name = _predict(sales_values, days)
    gmv_forecast, _ = _predict(gmv_values, days)
    forecast_rows = []
    for index in range(days):
        date_value = (last_date + timedelta(days=index + 1)).date().isoformat()
        forecast_rows.append(
            {
                "date": date_value,
                "sales_quantity": int(round(sales_forecast[index])),
                "gmv": round(gmv_forecast[index], 2),
            }
        )

    forecast = {
        "forecast_id": f"F-{uuid4().hex[:12]}",
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "scope": _scope(product_id=product_id, category=category),
        "horizon_days": days,
        "model_name": model_name,
        "history": history,
        "forecast": forecast_rows,
        "summary": _forecast_summary(history, forecast_rows),
    }
    if save_result:
        result_repository.save_forecast(forecast)
    return forecast


def _predict(values: list[float], days: int) -> tuple[list[float], str]:
    if not values:
        return [0.0 for _ in range(days)], "经营趋势预测"
    if len(values) == 1:
        return [max(values[0], 0.0) for _ in range(days)], "经营趋势预测"

    y = np.array(values, dtype=float)
    x = np.arange(len(values), dtype=float).reshape(-1, 1)
    future_x = np.arange(len(values), len(values) + days, dtype=float).reshape(-1, 1)

    if LinearRegression is not None:
        model = LinearRegression()
        model.fit(x, y)
        predicted = model.predict(future_x)
        model_name = "经营趋势预测"
    else:
        slope, intercept = np.polyfit(np.arange(len(values), dtype=float), y, deg=1)
        predicted = slope * future_x.flatten() + intercept
        model_name = "经营趋势预测"

    recent_avg = float(np.mean(y[-7:])) if len(y) >= 7 else float(np.mean(y))
    smoothed = [max(float(value), 0.0) for value in predicted]
    if recent_avg > 0:
        smoothed = [round(value * 0.7 + recent_avg * 0.3, 2) for value in smoothed]
    return smoothed, model_name


def _last_date(history: list[dict[str, Any]]) -> datetime:
    if not history:
        return datetime.now(UTC)
    return datetime.fromisoformat(history[-1]["date"])


def _scope(product_id: str | None, category: str | None) -> dict[str, Any]:
    if product_id:
        return {"type": "product", "product_id": product_id}
    if category:
        return {"type": "category", "category": category}
    return {"type": "global"}


def _forecast_summary(history: list[dict[str, Any]], forecast_rows: list[dict[str, Any]]) -> dict[str, Any]:
    recent_sales = [float(item.get("sales_quantity") or 0) for item in history[-7:]]
    forecast_sales = [float(item.get("sales_quantity") or 0) for item in forecast_rows]
    recent_avg = float(np.mean(recent_sales)) if recent_sales else 0
    forecast_avg = float(np.mean(forecast_sales)) if forecast_sales else 0
    if forecast_avg > recent_avg * 1.08:
        direction = "up"
        insight = "预测销量高于近期均值，短期趋势偏上行。"
    elif forecast_avg < recent_avg * 0.92:
        direction = "down"
        insight = "预测销量低于近期均值，短期存在下滑压力。"
    else:
        direction = "stable"
        insight = "预测销量接近近期均值，短期趋势相对稳定。"
    confidence = "medium" if len(history) >= 30 else "low"
    return {
        "recent_avg_sales": round(recent_avg, 2),
        "forecast_avg_sales": round(forecast_avg, 2),
        "trend_direction": direction,
        "confidence": confidence,
        "insight": insight,
    }
