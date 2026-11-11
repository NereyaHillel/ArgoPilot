import os
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from support import database_from

from db import get_db
from main import app

SERVICE_DIR = Path(__file__).resolve().parents[1]


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    on_postgres = bool(os.environ.get("TEST_DATABASE_URL"))
    skip_sqlite = pytest.mark.skip(reason="TEST_DATABASE_URL is set")
    skip_postgres = pytest.mark.skip(reason="TEST_DATABASE_URL is not set")
    for item in items:
        if on_postgres and "sqlite_only" in item.keywords:
            item.add_marker(skip_sqlite)
        if not on_postgres and "postgres_only" in item.keywords:
            item.add_marker(skip_postgres)


@pytest.fixture(autouse=True)
def _restore_dependencies() -> Iterator[None]:
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def seeded_db(tmp_path: Path) -> Path:
    # A fresh seed per test, so nothing ever writes to the real registry.db.
    path = tmp_path / "registry.db"
    subprocess.run(
        ["bash", str(SERVICE_DIR / "seed_registry.sh"), str(path)],
        check=True,
        capture_output=True,
    )
    return path


@pytest.fixture
def client(seeded_db: Path) -> TestClient:
    app.dependency_overrides[get_db] = database_from(seeded_db)
    return TestClient(app)
