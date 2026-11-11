# Registry PostgreSQL Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let `services/registry-service` run on an existing PostgreSQL database in production while local runs and tests keep using SQLite, chosen by `DATABASE_URL` from `.env`, with identical API behaviour.

**Architecture:** `db.py` becomes the only place that knows about backends: it opens a SQLite or Postgres connection from the `DATABASE_URL` scheme, hides placeholder differences behind a small `PgConnection` adapter, provides `write_transaction`, and classifies driver errors (unique, foreign key, unavailable). `repository.py` and the routers stay hand-written SQL with no ORM and only change where SQLite-specific. A hand-run Python script creates and seeds the Postgres tables and refuses to touch a database that already has them.

**Tech Stack:** Python 3.12, FastAPI, sqlite3, psycopg 3 (`psycopg[binary]`), python-dotenv, pytest, Docker (throwaway Postgres 16 for verification).

**Spec:** `docs/superpowers/specs/2026-11-11-postgres-support-design.md`. All paths below are relative to `services/registry-service/` unless they start with `docs/`. Run commands from that directory.

## Global Constraints

- Existing endpoints keep the same status codes, `application/problem+json` bodies, `code` values and `Retry-After: 5` on 503. The only deliberate behaviour change is Task 1 (NUL characters, 422).
- No ORM, no migration framework, no app-created tables, no data migration from `registry.db`.
- Without `DATABASE_URL` the app uses `registry.db` next to the code. Local runs and tests use SQLite.
- The Postgres setup script must never delete or overwrite existing data: if any registry table exists it stops with a clear message and changes nothing.
- 503 + `Retry-After: 5` on Postgres: SQLSTATE class `08` and connection failures, `57P01`, `57P02`, `57P03`, `53300`, `55P03`, `57014`, `40P01`, `40001`, `3D000`. Everything else is 500, including bad credentials (`28xxx`) and missing tables (`42P01`).
- Lists keep SQLite's byte-wise `ORDER BY name, id` on Postgres (`COLLATE "C"`). Ids and `planting_date` stay `TEXT`; `REAL` becomes `DOUBLE PRECISION`; `INTEGER` stays `INTEGER`.
- The test suite must never touch the database named by `DATABASE_URL`. The Postgres test database comes only from `TEST_DATABASE_URL`, and test fixtures that drop tables refuse any database whose name does not contain `test`.
- If Docker is unavailable when a step needs it, stop and report the Postgres side as unverified. Do not install another Postgres.
- Commit messages end with the line `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.

## Review Focus

Failure modes the spec implies but a straight reading of the requirements would not test:

1. Ordering and text round-trip: names like `Apple`, `banana`, `éclair`, an emoji, a 10,000-character name and `'; DROP TABLE farms;--` list in the same order and come back byte-identical on both backends (Task 4).
2. Float round-trip: `area_m2 = 1234.5678901234567` and `lat = 31.123456789012345` return exactly as sent (Task 4).
3. Two simultaneous creates of the same plot name give one 201 and one 409, never a 500 (Task 4).
4. A Postgres connection killed mid-request (`pg_terminate_backend`) gives 503 with `Retry-After`, not 500 (Task 5).
5. `DATABASE_URL` with an unsupported scheme fails fast with a clear error, and the `postgres://` alias is accepted like `postgresql://` (Task 2).

---

### Task 1: Reject NUL characters in text fields (both backends)

**Files:**
- Modify: `schemas.py`
- Test: `tests/test_nul_characters.py`

**Interfaces:**
- Produces: `schemas.RefId` (`Annotated[str, AfterValidator]` rejecting `"\x00"`), and `Name` additionally rejects it. Error detail format: `"<field>: must not contain NUL characters"`, status 422, code `VALIDATION`.

- [ ] **Step 1: Write the failing tests** in `tests/test_nul_characters.py`, using the `client` fixture and `plot_payload` from `tests/support.py`. Cases, each asserting status 422, `code == "VALIDATION"` and `detail == "<field>: must not contain NUL characters"`: `POST /v1/farms` name `"a\u0000b"`; `PATCH /v1/farms/{FARM_DEMO}` name `"a\u0000b"`; `POST /v1/plots` with `name`, `crop_id`, `soil_id`, `emitter_id` each containing NUL (parametrised); `PATCH /v1/plots/{PLOT_NORTH}` with the same four fields. Also one test that a name with no NUL still returns 201.
- [ ] **Step 2: Run** `uv run pytest tests/test_nul_characters.py -v`. Expected: FAIL (today the farm POST returns 201).
- [ ] **Step 3: Implement** a `_no_nul(value: str) -> str` validator raising `PydanticCustomError("nul", "must not contain NUL characters")`; call it from `_not_blank` or chain it into `Name`; define `RefId = Annotated[str, AfterValidator(_no_nul)]` and use it for `crop_id`, `soil_id`, `emitter_id` in `PlotCreate` and `PlotUpdate`.
- [ ] **Step 4: Run** `uv run pytest -v`. Expected: all pass (new and existing).
- [ ] **Step 5: Commit** `feat: reject NUL characters in text fields`.

---

### Task 2: Read `DATABASE_URL` from `.env`

**Files:**
- Create: `config.py`, `.env.example`, `tests/test_config.py`
- Modify: `pyproject.toml` (add `python-dotenv`), `uv.lock` (via `uv lock`)

**Interfaces:**
- Produces: `config.database_url(env_file: Path = ENV_FILE) -> str` and `config.DEFAULT_SQLITE_URL: str`. Rules: a real process environment variable beats `.env`; with neither set it returns `sqlite:///` + absolute path of `registry.db` next to the code; it returns the URL unchanged when the scheme is `sqlite`, `postgresql` or `postgres`; any other scheme raises `ValueError` whose message names the scheme.
- `ENV_FILE` is `.env` in the service directory.

- [ ] **Step 1: Write the failing tests** in `tests/test_config.py` (use `monkeypatch` and `tmp_path` env files): default when nothing is set; value read from an env file; process env wins over the file; `postgres://u:p@h/db` accepted; `mysql://h/db` raises `ValueError` matching `mysql`.
- [ ] **Step 2: Run** `uv run pytest tests/test_config.py -v`. Expected: FAIL (module missing).
- [ ] **Step 3: Implement** `config.py` with `python-dotenv`'s `dotenv_values(env_file)` (do not mutate `os.environ`). Add the dependency with `uv add python-dotenv`. Write `.env.example` with two commented examples: `DATABASE_URL=sqlite:///registry.db` and `DATABASE_URL=postgresql://user:password@host:5432/registry`.
- [ ] **Step 4: Run** `uv run pytest tests/test_config.py -v`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: read DATABASE_URL from .env`.

---

### Task 3: Postgres setup script and throwaway database

**Files:**
- Create: `seed_registry_pg.py`, `docker-compose.test.yml`, `tests/test_seed_postgres.py`
- Modify: `pyproject.toml` (add `psycopg[binary]`; register pytest markers `sqlite_only` and `postgres_only`), `tests/conftest.py` (marker skipping, see below), `uv.lock`

**Interfaces:**
- Consumes: `config.database_url()`.
- Produces in `seed_registry_pg.py`: `TABLES = ("plots", "farms", "crops", "soils", "emitters")`; `class DatabaseNotEmpty(Exception)`; `seed(conn: psycopg.Connection) -> None` (runs DDL plus seed rows in one transaction; raises `DatabaseNotEmpty` naming the existing tables, changing nothing, if any of `TABLES` exists in the current schema); `main() -> int` (reads `config.database_url()`, returns 1 with a message on a non-Postgres URL or on `DatabaseNotEmpty`, 0 and a row-count summary on success).
- Produces in `docker-compose.test.yml`: service `postgres` (image `postgres:16`), host port `55432`, user/password `registry`, database `registry_test`. The test URL is `postgresql://registry:registry@localhost:55432/registry_test`.
- Produces in `conftest.py`: `pytest_collection_modifyitems` skips `sqlite_only` tests when `TEST_DATABASE_URL` is set and `postgres_only` tests when it is not.
- Schema: identical tables, columns and constraints to `seed_registry.sh` (primary keys, the four foreign keys from `plots`, `UNIQUE (farm_id, name)`, `NOT NULL` everywhere) and identical seed rows (2 farms, 4 plots, 2 crops, 3 soils, 4 emitters, same ids).

- [ ] **Step 1: Check Docker.** Run `docker compose -f docker-compose.test.yml up -d --wait` after creating the compose file. Expected: container healthy. If `docker` is missing, stop and report (see Global Constraints).
- [ ] **Step 2: Write the failing tests** in `tests/test_seed_postgres.py` (all `postgres_only`, connecting with `psycopg` to `TEST_DATABASE_URL`; each starts by dropping the five tables, guarded by the "name contains test" rule): seeding an empty database creates the five tables with the expected row counts; every row equals the corresponding row in a SQLite file built by `seed_registry.sh` (parity test, compare `SELECT *` ordered by `id` per table); a second `seed()` raises `DatabaseNotEmpty` and leaves the data intact (insert an extra farm first and assert it survives); `main()` returns 1 and prints a message when run against a seeded database.
- [ ] **Step 3: Run** `TEST_DATABASE_URL=... uv run pytest tests/test_seed_postgres.py -v`. Expected: FAIL (module missing).
- [ ] **Step 4: Implement** `seed_registry_pg.py` and the marker plumbing. Keep the DDL and `INSERT` rows in the script as SQL text mirroring `seed_registry.sh` (the parity test guards drift). Use `to_regclass` or `information_schema.tables` for the existence check.
- [ ] **Step 5: Run** the command from Step 3, then `uv run pytest -v` without `TEST_DATABASE_URL`. Expected: Postgres tests PASS in the first run; in the second they are skipped and everything else passes.
- [ ] **Step 6: Commit** `feat: add Postgres setup script and test database`.

---

### Task 4: Run the app on Postgres

**Files:**
- Modify: `db.py`, `repository.py`, `routers/farms.py`, `routers/plots.py` (type hints only), `tests/conftest.py`, `tests/support.py`, `tests/test_constraints.py`, `tests/test_errors.py` (mark SQLite-specific tests `sqlite_only`)
- Create: `tests/test_backend_parity.py`

**Interfaces:**
- Consumes: `config.database_url()`, `seed_registry_pg.seed`.
- Produces in `db.py`: `connect_url(url: str) -> Conn` (`sqlite:` goes to the existing `connect(path)`; relative paths resolve against the service directory; `postgresql:`/`postgres:` opens a `psycopg` connection with `autocommit=True` and `dict_row`); `Conn = sqlite3.Connection | PgConnection`; `class PgConnection` with `execute(sql: str, params: tuple | dict = ()) -> psycopg.Cursor` (rewrites `?` to `%s` and `:name` to `%(name)s`) and `close() -> None`; `get_db()` now calls `connect_url(config.database_url())`; `write_transaction(conn: Conn)` (SQLite unchanged; Postgres: `BEGIN`, `SET LOCAL lock_timeout = '5s'`, `SELECT pg_advisory_xact_lock(<fixed constant>)`, then `COMMIT` / `ROLLBACK` on error, so writers are serialised like SQLite's `BEGIN IMMEDIATE`); `INTEGRITY_ERRORS: tuple[type[Exception], ...]`; `is_unique_violation(exc: Exception) -> bool`; `is_foreign_key_violation(exc: Exception) -> bool`.
- `conftest.py`: fixture `db_url` (SQLite temp file URL from `seed_registry.sh`, or, when `TEST_DATABASE_URL` is set, a freshly dropped and re-seeded Postgres database); `client` and the `conn` fixture in `test_constraints.py` use it. `support.database_from_url(url)` mirrors `database_from(path)`. `seeded_db` (Path) stays for SQLite-only tests.

- [ ] **Step 1: Write the failing parity tests** in `tests/test_backend_parity.py` (use `client`, run on both backends, expected values written literally): list order of farms `Apple`, `banana`, `éclair`, `😀`, 10,000-character name and `'; DROP TABLE farms;--` equals byte-wise sorted order and every name round-trips identically via `GET /v1/farms`; `area_m2 = 1234.5678901234567` and `lat = 31.123456789012345` round-trip exactly through POST and GET; two threads POSTing the same plot name to the same farm produce exactly one 201 and one 409 (`code == "CONFLICT"`), no 500. Also change `test_constraints.py`'s `conn` fixture to `connect_url(db_url)`.
- [ ] **Step 2: Run** the full suite with `TEST_DATABASE_URL` set. Expected: widespread FAIL (Postgres backend not implemented), SQLite run still PASS.
- [ ] **Step 3: Implement** the `db.py` interfaces above. In `repository.py`: replace `sqlite3.Connection` hints with `Conn`; replace `except sqlite3.IntegrityError` blocks with `except INTEGRITY_ERRORS` plus `is_unique_violation` / `is_foreign_key_violation`; make `count_plots` use `SELECT COUNT(*) AS n` and read `["n"]`; rewrite `plot_name_taken` without `IS NOT ?` (omit the `id != ?` clause when `plot_id is None`); add `COLLATE "C"` handling so Postgres list queries order byte-wise (apply the collation only on Postgres, for example through a small helper in `db.py`, keeping SQLite SQL unchanged).
- [ ] **Step 4: Run** `uv run pytest -v` (SQLite) and the same with `TEST_DATABASE_URL=postgresql://registry:registry@localhost:55432/registry_test`. Expected: both PASS (SQLite-only tests skipped on Postgres).
- [ ] **Step 5: Commit** `feat: run registry on PostgreSQL via DATABASE_URL`.

---

### Task 5: Postgres error mapping

**Files:**
- Modify: `db.py` (add `is_unavailable`), `errors.py`
- Create: `tests/test_postgres_errors.py`

**Interfaces:**
- Consumes: `db.connect_url`, `db.write_transaction`.
- Produces: `db.is_unavailable(exc: Exception) -> bool` (SQLite: existing `SQLITE_CANTOPEN`/`SQLITE_BUSY`/`SQLITE_LOCKED` rule; Postgres: the SQLSTATE list in Global Constraints, plus `OperationalError` with no SQLSTATE except authentication failures). `errors.register_error_handlers` registers one handler for `sqlite3.Error` and `psycopg.Error` that returns `UnavailableProblem("Registry database is unavailable; retry later")` when `is_unavailable` is true, otherwise the existing 500 problem. `UNAVAILABLE_SQLITE_ERRORS` moves into `db.py`.

- [ ] **Step 1: Write the failing tests** in `tests/test_postgres_errors.py` (all `postgres_only`; each asserts the problem document via the helper pattern in `tests/test_errors.py`): wrong port in `get_db` override gives 503, `UNAVAILABLE`, `Retry-After: 5`; a second connection holding `pg_advisory_lock` on the same key makes a POST return 503 with `Retry-After` after the 5s lock timeout (shorten with a test override of the timeout if the builder exposes one); an unseeded empty database gives 500 `UNAVAILABLE` with detail `Internal server error` and no `Retry-After`; wrong password gives 500 (not 503); killing the request's backend with `pg_terminate_backend` between statements (monkeypatch a repository function to do it) gives 503 with `Retry-After`; a nonexistent database name gives 503.
- [ ] **Step 2: Run** with `TEST_DATABASE_URL` set. Expected: FAIL.
- [ ] **Step 3: Implement** `is_unavailable` and the combined handler. Libpq connection-phase failures carry no SQLSTATE; verify the wrong-password case against the Docker database and distinguish it from "connection refused" with the message text (`authentication failed`) if no better signal exists.
- [ ] **Step 4: Run** both backends' suites. Expected: PASS, including the original SQLite 503/500 tests unchanged.
- [ ] **Step 5: Commit** `feat: map PostgreSQL errors to the existing 503/500 problems`.

---

### Task 6: Docs and end-to-end verification

**Files:**
- Modify: `README.md` (repo root), `docs/` only if it already documents the database

- [ ] **Step 1: Update the README:** database section (SQLite default, Postgres in production), `DATABASE_URL` and `.env.example`, how to run `seed_registry_pg.py` (and that it refuses non-empty databases), `docker compose -f docker-compose.test.yml up -d --wait` and the `TEST_DATABASE_URL` test command; replace the "SQLite only" requirement lines accordingly.
- [ ] **Step 2: Full suites.** Run `uv run pytest -v` and the Postgres run from Task 4. Expected: both PASS.
- [ ] **Step 3: Manual comparison.** Seed the Docker database with `DATABASE_URL=<test url> uv run python seed_registry_pg.py` and confirm a second run refuses. Start the app against SQLite and then Postgres (`DATABASE_URL=<test url> uv run uvicorn main:app`), and compare `GET /v1/farms`, `/v1/plots`, `/v1/crops`, `/v1/soils`, `/v1/emitters` responses with `diff`. Expected: identical bodies.
- [ ] **Step 4: Performance check.** Rerun the Locust scenario in `scripts/locustfile.py` against the Postgres-backed app at 10 requests per second. Expected: p95 at most 100 ms, 0 failures (the README's existing requirement). If it fails because of per-request connections, add a connection pool in `db.py` and rerun; report the numbers either way.
- [ ] **Step 5: Commit** `docs: document PostgreSQL setup and testing`.
