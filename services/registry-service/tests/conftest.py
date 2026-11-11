import os
import subprocess
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient
from support import database_from_url

from db import get_db
from main import app
from seed_registry_pg import TABLES, seed

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
def db_url(request: pytest.FixtureRequest) -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        return f"sqlite:///{request.getfixturevalue('seeded_db')}"
    # Only ever drop tables in the test database, never the one DATABASE_URL names.
    name = psycopg.conninfo.conninfo_to_dict(url)["dbname"]
    assert "test" in name, f"refusing to drop tables in {name!r}"
    with psycopg.connect(url) as conn:
        conn.execute(f"DROP TABLE IF EXISTS {', '.join(TABLES)} CASCADE")
        seed(conn)
    return url


@pytest.fixture
def client(db_url: str) -> TestClient:
    app.dependency_overrides[get_db] = database_from_url(db_url)
    return TestClient(app)
