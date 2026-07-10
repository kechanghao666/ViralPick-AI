from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


@pytest.fixture(scope="session", autouse=True)
def initialized_database():
    subprocess.run(
        [sys.executable, "scripts/init_database.py", "--force"],
        cwd=ROOT_DIR,
        check=True,
    )


@pytest.fixture()
def client(initialized_database):
    from backend.app import create_app

    app = create_app()
    app.config.update(TESTING=True)
    return app.test_client()
