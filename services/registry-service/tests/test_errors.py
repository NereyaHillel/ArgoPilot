import sqlite3
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from support import FARM_DEMO, UNKNOWN_ID, database_from, plot_payload

import repository
from db import connect, get_db
from errors import register_error_handlers
from main import app

PROBLEM_FIELDS = {"type", "title", "status", "detail", "code"}


def assert_problem(response, status, code):
    assert response.status_code == status
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert set(body) == PROBLEM_FIELDS
    assert body["type"] == "about:blank"
    assert body["status"] == status
    assert body["code"] == code
    return body


def test_not_found_is_a_problem_document(client):
    body = assert_problem(client.get(f"/v1/farms/{UNKNOWN_ID}"), 404, "NOT_FOUND")

    assert body["title"] == "Not Found"
    assert body["detail"] == f"Farm {UNKNOWN_ID} not found"


def test_validation_failure_is_a_problem_document(client):
    body = assert_problem(client.post("/v1/plots", json=plot_payload(area_m2=0)), 422, "VALIDATION")

    assert body["title"] == "Unprocessable Entity"
    assert body["detail"] == "area_m2: Input should be greater than 0"


def test_conflict_is_a_problem_document(client):
    response = client.delete(f"/v1/farms/{FARM_DEMO}")

    body = assert_problem(response, 409, "CONFLICT")
    assert body["title"] == "Conflict"


def test_malformed_path_id_is_a_validation_problem(client):
    body = assert_problem(client.get("/v1/farms/not-a-uuid"), 422, "VALIDATION")

    assert body["detail"].startswith("farm_id: ")


def test_malformed_json_body_is_a_validation_problem(client):
    response = client.post(
        "/v1/farms", content="{not json", headers={"content-type": "application/json"}
    )

    body = assert_problem(response, 422, "VALIDATION")
    assert body["detail"].startswith("body: ")


def test_unknown_route_is_a_not_found_problem(client):
    assert_problem(client.get("/v1/unknown"), 404, "NOT_FOUND")


def test_wrong_method_is_a_405_problem_that_lists_allowed_methods(client):
    response = client.put(f"/v1/farms/{FARM_DEMO}")

    assert_problem(response, 405, "VALIDATION")
    assert set(response.headers["allow"].split(", ")) == {"GET", "PATCH", "DELETE"}


@pytest.mark.sqlite_only
def test_missing_database_file_returns_503_with_retry_after(tmp_path: Path):
    app.dependency_overrides[get_db] = database_from(tmp_path / "missing.db")

    response = TestClient(app).get("/v1/farms")

    body = assert_problem(response, 503, "UNAVAILABLE")
    assert body["title"] == "Service Unavailable"
    assert response.headers["retry-after"] == "5"
    assert not (tmp_path / "missing.db").exists()


@pytest.mark.sqlite_only
def test_locked_database_returns_503_with_retry_after(seeded_db: Path):
    blocker = sqlite3.connect(seeded_db, isolation_level=None)
    blocker.execute("BEGIN IMMEDIATE")

    def impatient_db():
        conn = connect(seeded_db)
        conn.execute("PRAGMA busy_timeout = 50")
        try:
            yield conn
        finally:
            conn.close()

    app.dependency_overrides[get_db] = impatient_db
    try:
        response = TestClient(app).post("/v1/farms", json={"name": "Blocked"})
    finally:
        blocker.execute("ROLLBACK")
        blocker.close()

    assert_problem(response, 503, "UNAVAILABLE")
    assert response.headers["retry-after"] == "5"


@pytest.mark.sqlite_only
def test_database_without_schema_returns_500_problem(tmp_path: Path):
    empty = tmp_path / "empty.db"
    sqlite3.connect(empty).close()
    app.dependency_overrides[get_db] = database_from(empty)

    response = TestClient(app, raise_server_exceptions=False).get("/v1/farms")

    body = assert_problem(response, 500, "UNAVAILABLE")
    assert body["detail"] == "Internal server error"
    assert "retry-after" not in response.headers


def test_unexpected_exception_returns_500_problem(client, monkeypatch):
    def broken(conn):
        raise RuntimeError("boom")

    monkeypatch.setattr(repository, "list_farms", broken)
    unguarded = TestClient(app, raise_server_exceptions=False)

    response = unguarded.get("/v1/farms")

    body = assert_problem(response, 500, "UNAVAILABLE")
    assert body["detail"] == "Internal server error"


def test_raising_fastapi_http_exception_still_returns_problem_document():
    # fastapi.HTTPException subclasses Starlette's, and FastAPI's default handler is keyed on
    # Starlette's class, so the override covers subclasses too. This guards that behavior.
    mini = FastAPI()
    register_error_handlers(mini)

    @mini.get("/gone")
    def gone():
        raise HTTPException(status_code=404, detail="gone")

    body = assert_problem(TestClient(mini).get("/gone"), 404, "NOT_FOUND")
    assert body["detail"] == "gone"


def test_body_that_is_not_utf8_json_is_a_422_validation_problem(client):
    # FastAPI raises its own 400 for this body. The handler maps it to 422, like malformed JSON.
    response = client.post(
        "/v1/farms", content=b'{"name": "\xff\xfe"}', headers={"content-type": "application/json"}
    )

    body = assert_problem(response, 422, "VALIDATION")
    assert body["detail"] == "body: could not be read as JSON"
