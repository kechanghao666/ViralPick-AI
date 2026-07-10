from __future__ import annotations

from typing import Iterable


def parse_int(
    value: str | int | None,
    default: int,
    minimum: int = 1,
    maximum: int | None = None,
) -> int:
    try:
        parsed = int(value) if value is not None else default
    except (TypeError, ValueError):
        parsed = default
    if parsed < minimum:
        parsed = minimum
    if maximum is not None:
        parsed = min(parsed, maximum)
    return parsed


def parse_pagination(args) -> tuple[int, int]:
    page = parse_int(args.get("page"), default=1, minimum=1)
    page_size = parse_int(args.get("page_size"), default=20, minimum=1, maximum=100)
    return page, page_size


def parse_sort_order(value: str | None) -> str:
    return "asc" if str(value or "").lower() == "asc" else "desc"


def require_choice(value: str | None, allowed: Iterable[str], default: str) -> str:
    if value in allowed:
        return str(value)
    return default


def parse_horizon(value: str | int | None) -> int | None:
    try:
        days = int(value) if value is not None else 7
    except (TypeError, ValueError):
        return None
    return days if days in {7, 14, 30} else None

