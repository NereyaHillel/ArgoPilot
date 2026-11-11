import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.conninfo import make_conninfo
from support import database_from_url
from test_errors import assert_problem

import db
import repository
from db import PG_WRITE_LOCK_KEY, get_db
from main import app
from seed_registry_pg import TABLES

pytestmark = pytest.mark.postgres_only


def request_with(url: str, method: str = "GET", path: str = "/v1/farms", **kwargs):
    app.dependency_overrides[get_db] = database_from_url(url)
    return TestClient(app, raise_server_exceptions=False).request(method, path, **kwargs)


def assert_unavailable(response):
    body = assert_problem(response, 503, "UNAVAILABLE")
    assert body["detail"] == "Registry database is unavailable; retry later"
    assert response.headers["retry-after"] == "5"


def assert_internal_error(response):
    body = assert_problem(response, 500, "UNAVAILABLE")
    assert body["detail"] == "Internal server error"
    assert "retry-after" not in response.headers


def test_unreachable_server_returns_503(db_url):
    assert_unavailable(request_with(make_conninfo(db_url, port=1)))


def test_nonexistent_database_returns_503(db_url):
    assert_unavailable(request_with(make_conninfo(db_url, dbname="no_such_database_test")))


def test_wrong_password_returns_500(db_url):
    assert_internal_error(request_with(make_conninfo(db_url, password="wrong")))


def test_database_without_schema_returns_500(db_url):
    with psycopg.connect(db_url) as conn:
        conn.execute(f"DROP TABLE {', '.join(TABLES)} CASCADE")

    assert_internal_error(request_with(db_url))


def test_write_lock_timeout_returns_503(db_url, monkeypatch):
    monkeypatch.setattr(db, "PG_LOCK_TIMEOUT", "100ms")
    with psycopg.connect(db_url) as blocker:
        blocker.execute(f"SELECT pg_advisory_lock({PG_WRITE_LOCK_KEY})")

        response = request_with(db_url, "POST", json={"name": "Blocked"})

    assert_unavailable(response)


def test_backend_killed_mid_request_returns_503(db_url, monkeypatch):
    insert_farm = repository.insert_farm

    def kill_then_insert(conn, farm):
        pid = conn.execute("SELECT pg_backend_pid() AS pid").fetchone()["pid"]
        with psycopg.connect(db_url, autocommit=True) as killer:
            killer.execute("SELECT pg_terminate_backend(%s, 5000)", (pid,))
        insert_farm(conn, farm)

    monkeypatch.setattr(repository, "insert_farm", kill_then_insert)

    assert_unavailable(request_with(db_url, "POST", json={"name": "Killed"}))
