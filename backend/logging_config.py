from __future__ import annotations

import logging
import sys

from backend.config import LOG_LEVEL


def configure_logging() -> None:
    root = logging.getLogger()
    if root.handlers:
        root.setLevel(LOG_LEVEL)
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s [%(name)s] %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )
    root.addHandler(handler)
    root.setLevel(LOG_LEVEL)
