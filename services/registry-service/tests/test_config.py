from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import config
from main import app


@pytest.fixture(autouse=True)
def no_process_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)


def write_env(tmp_path: Path, content: str) -> Path:
    env_file = tmp_path / ".env"
    env_file.write_text(content)
    return env_file


def test_defaults_to_sqlite_file_next_to_the_code(tmp_path):
    url = config.database_url(tmp_path / "missing.env")

    assert url == config.DEFAULT_SQLITE_URL
    assert url == "sqlite:///" + str(Path(config.__file__).resolve().parent / "registry.db")


def test_reads_value_from_env_file(tmp_path):
    env_file = write_env(tmp_path, "DATABASE_URL=postgresql://u:p@h:5432/db\n")

    assert config.database_url(env_file) == "postgresql://u:p@h:5432/db"


def test_process_environment_beats_env_file(tmp_path, monkeypatch):
    env_file = write_env(tmp_path, "DATABASE_URL=postgresql://file/db\n")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///from-process.db")

    assert config.database_url(env_file) == "sqlite:///from-process.db"


def test_accepts_postgres_scheme(tmp_path):
    env_file = write_env(tmp_path, "DATABASE_URL=postgres://u:p@h/db\n")

    assert config.database_url(env_file) == "postgres://u:p@h/db"


def test_rejects_unsupported_scheme(tmp_path):
    env_file = write_env(tmp_path, "DATABASE_URL=mysql://h/db\n")

    with pytest.raises(ValueError, match="mysql"):
        config.database_url(env_file)


def test_rejects_value_without_scheme(tmp_path):
    env_file = write_env(tmp_path, "DATABASE_URL=registry.db\n")

    with pytest.raises(ValueError, match="no scheme"):
        config.database_url(env_file)


def test_empty_process_value_is_an_error_not_a_fallthrough(tmp_path, monkeypatch):
    env_file = write_env(tmp_path, "DATABASE_URL=postgresql://file/db\n")
    monkeypatch.setenv("DATABASE_URL", "")

    with pytest.raises(ValueError, match="empty DATABASE_URL"):
        config.database_url(env_file)


def test_empty_env_file_value_is_an_error(tmp_path):
    env_file = write_env(tmp_path, "DATABASE_URL=\n")

    with pytest.raises(ValueError, match="empty DATABASE_URL"):
        config.database_url(env_file)


def test_startup_fails_on_unsupported_scheme(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "mysql://h/db")

    with pytest.raises(ValueError, match="'mysql'"), TestClient(app):
        pass


def test_requests_use_the_url_resolved_at_startup(db_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", db_url)
    with TestClient(app) as client:
        # Changing the variable after startup has no effect: the URL is read once.
        monkeypatch.setenv("DATABASE_URL", "mysql://h/db")

        response = client.get("/v1/farms")

    assert response.status_code == 200
