from __future__ import annotations

from typing import Any

from flask import jsonify


def ok(data: Any, status: int = 200):
    return jsonify({"success": True, "data": data}), status


def error(message: str, status: int = 400):
    return jsonify({"success": False, "error": message}), status

