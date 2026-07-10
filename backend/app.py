from __future__ import annotations

import sys
from pathlib import Path

from flask import Flask, g, jsonify, redirect, send_from_directory


if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from backend.config import (
    API_HOST,
    API_PORT,
    APP_ENV,
    APP_NAME,
    APP_VERSION,
    AUTH_REQUIRED,
    DATABASE_PATH,
    DEBUG,
    FRONTEND_DIR,
    MAX_UPLOAD_MB,
    RATE_LIMIT_AUTH_PER_WINDOW,
    RATE_LIMIT_DEFAULT_PER_WINDOW,
    RATE_LIMIT_ENABLED,
    RATE_LIMIT_WINDOW_SECONDS,
    RATE_LIMIT_WRITE_PER_WINDOW,
    SERVE_FRONTEND,
)
from backend.logging_config import configure_logging
from backend.middleware import register_request_middleware
from backend.routes.api import api_bp


def create_app() -> Flask:
    configure_logging()
    app = Flask(__name__, static_folder=None)
    app.config["JSON_AS_ASCII"] = False
    app.config["APP_ENV"] = APP_ENV
    app.config["APP_VERSION"] = APP_VERSION
    app.config["AUTH_REQUIRED"] = AUTH_REQUIRED
    app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024
    app.config["RATE_LIMIT_ENABLED"] = RATE_LIMIT_ENABLED
    app.config["RATE_LIMIT_WINDOW_SECONDS"] = RATE_LIMIT_WINDOW_SECONDS
    app.config["RATE_LIMIT_DEFAULT_PER_WINDOW"] = RATE_LIMIT_DEFAULT_PER_WINDOW
    app.config["RATE_LIMIT_AUTH_PER_WINDOW"] = RATE_LIMIT_AUTH_PER_WINDOW
    app.config["RATE_LIMIT_WRITE_PER_WINDOW"] = RATE_LIMIT_WRITE_PER_WINDOW
    app.register_blueprint(api_bp)
    register_request_middleware(app)

    @app.get("/")
    def index():
        if SERVE_FRONTEND and (FRONTEND_DIR / "index.html").exists():
            return send_from_directory(FRONTEND_DIR, "index.html")
        return redirect("/api/health")

    @app.get("/<path:path>")
    def frontend_assets(path: str):
        if path.startswith("api/"):
            return jsonify(
                {
                    "success": False,
                    "error": "Not found",
                    "request_id": getattr(g, "request_id", None),
                }
            ), 404
        if SERVE_FRONTEND and (FRONTEND_DIR / path).exists():
            return send_from_directory(FRONTEND_DIR, path)
        if SERVE_FRONTEND and (FRONTEND_DIR / "index.html").exists():
            return send_from_directory(FRONTEND_DIR, "index.html")
        return jsonify({"success": False, "error": "Not found"}), 404

    @app.errorhandler(404)
    def not_found(_error):
        return jsonify(
            {
                "success": False,
                "error": "Not found",
                "request_id": getattr(g, "request_id", None),
            }
        ), 404

    @app.errorhandler(413)
    def payload_too_large(_error):
        return jsonify(
            {
                "success": False,
                "error": f"Uploaded file is too large. Limit: {MAX_UPLOAD_MB} MB",
                "request_id": getattr(g, "request_id", None),
            }
        ), 413

    @app.errorhandler(Exception)
    def internal_error(error):
        app.logger.exception("Unhandled API error")
        message = str(error) if DEBUG else "Internal server error"
        return jsonify(
            {
                "success": False,
                "error": message,
                "request_id": getattr(g, "request_id", None),
            }
        ), 500

    if not DATABASE_PATH.exists():
        app.logger.warning(
            "SQLite database does not exist at %s. Run `python scripts/init_database.py` first.",
            DATABASE_PATH,
        )

    return app


app = create_app()


if __name__ == "__main__":
    print(f"Starting {APP_NAME} API with database: {DATABASE_PATH}")
    app.run(host=API_HOST, port=API_PORT, debug=DEBUG)
