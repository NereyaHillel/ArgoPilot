# Registry service: PostgreSQL support — design

## Intent

The registry service stores everything in one SQLite file (`registry.db`), built by `seed_registry.sh`. That is fine on a laptop but not for production. The service must be able to run against an existing PostgreSQL database in production while keeping SQLite for local runs and tests.

## Goals

1. Every existing endpoint behaves exactly as today: same status codes, same `application/problem+json` bodies and `code` values, same `Retry-After: 5` on 503. Response bodies and list ordering stay identical on both databases.
2. `DATABASE_URL`, read from the `.env` file (and the process environment), selects the database by URL scheme: `sqlite:` for the local file, `postgresql:` for Postgres.
3. With no `DATABASE_URL`, the app uses `registry.db` next to the code, as today. Local runs and the test suite keep using SQLite.
4. The Postgres schema and seed data are identical in content to the SQLite ones (same tables, columns, constraints, seed rows).
5. A hand-run setup script creates the Postgres tables and seed rows from `DATABASE_URL`.

## Non-goals

- No ORM, no migration framework, no connection pool unless the builder finds it necessary for correctness.
- The app never creates or alters tables on startup.
- No changes to routes, schemas, or API behaviour.
- No data migration from an existing `registry.db` into Postgres.

## Anti-goals (would be a failure even if tests pass)

- The Postgres setup script ever deleting or overwriting existing data. The SQLite script's "delete and recreate" behaviour must not be copied.
- Any observable difference in API output between SQLite and Postgres (error text, ordering, number formatting, date format).
- A database error being reported as 500 where today it is 503, or the reverse.

## Decided by the user

- Hand-run setup script, not app-created tables.
- The script must refuse to touch a database that already has the tables: it stops with a clear message and changes nothing.
- The Postgres database is empty and already exists; the script fills it with the same schema and seed data as `seed_registry.sh`.
- Docker is used to run a throwaway Postgres for verification.

## Calls made by the author (not yet confirmed by the user)

- Keep the hand-written SQL; add psycopg 3 as the Postgres driver. No ORM.
- The URL scheme picks the backend inside `db.py`; routers keep using the `DbConn` dependency and `write_transaction`.
- Add `.env.example` showing both URL styles (`.env` is already gitignored). Load `.env` with python-dotenv (or equivalent small loader).
- Existing tests stay on SQLite. The same suite is made runnable against Postgres by pointing it at a throwaway database (see Verification).
- Update the README for the new setup and run instructions.
- **503 vs 500 on Postgres.** 503 with `Retry-After: 5`: connection failures (SQLSTATE class 08, including refused connection and DNS failure), server shutdown/restart (57P01–57P03), too many connections (53300), lock timeout (55P03), statement timeout (57014), deadlock (40P01), serialization failure (40001), and "database does not exist" (3D000, the analogue of SQLite's missing file). Everything else is 500, including bad credentials (28xxx, a config bug) and missing tables (42P01, matching today's "database without schema returns 500" test).
- **Docker.** The user enables Docker Desktop's WSL integration. If Docker is still unavailable when the work reaches verification, stop and report the Postgres side as unverified rather than substituting another Postgres install.
- **Docker** and **503 list** above are author calls to check while reading.

## Decided by the user (after review)

- **NUL characters in text.** SQLite accepts a NUL character in text today (`POST /v1/farms` with name `"a\u0000b"` returns 201); Postgres text columns reject it. Decision: reject NUL in string fields with the usual 422 VALIDATION problem on both backends, so they behave identically. This is the one deliberate change to existing behaviour; it applies to every user-supplied string field (farm and plot names, and any other free-text input). Add a test for it.

## Constraints and traps found in the code

- **Error mapping.** `errors.py` maps `sqlite3.Error` with `sqlite_errorname` in `SQLITE_CANTOPEN / BUSY / LOCKED` to 503 + `Retry-After`; other DB errors become 500. `repository.py` turns `IntegrityError` (unique, foreign key) into 409 and 422 problems. Postgres equivalents (connection failure, lock/statement timeout, unique violation, foreign-key violation) must map to the same outcomes. Any other Postgres error stays 500.
- **Transactions.** `write_transaction` uses `BEGIN IMMEDIATE` so checks inside a write are not invalidated by another writer. Postgres has no equivalent; the builder must pick a mechanism that keeps the same guarantee for the check-then-write flows in the farms and plots routers (e.g. locking, or relying on the unique/foreign-key constraints and mapping their violations to the same problems).
- **Placeholders.** SQL uses `?` and `:name`; psycopg uses `%s` / `%(name)s`.
- **Ordering.** Lists use `ORDER BY name, id`. SQLite compares bytes; Postgres uses the database collation. Ordering must match SQLite's (e.g. `COLLATE "C"`).
- **Types.** Keep the API output identical: ids and `planting_date` stay text; `REAL` columns map to `double precision`; `INTEGER` stays integer. Floats such as `area_m2` must serialize the same way.
- **Foreign keys.** Enforced per connection by a PRAGMA in SQLite; always on in Postgres.
- **Seed script portability.** `seed_registry.sh` uses the `sqlite3` CLI. The Postgres script must not need more than what the builder can reasonably require (e.g. `psql`, or a small Python script using the driver already installed); the builder chooses.
- **Tests.** `tests/conftest.py` builds a fresh SQLite file per test via `seed_registry.sh` and overrides `get_db`. Tests that rely on SQLite-specific behaviour (e.g. simulating a locked or missing file for the 503 tests) need Postgres equivalents when run against Postgres.

## Verification

- The existing suite passes unchanged on SQLite.
- The same suite (or an equivalent parametrised version) passes against a throwaway Postgres in Docker, including the 409, 422 and 503 cases.
- A test shows the setup script refuses to run against a database that already has the tables, and leaves its data intact.
- Manual check: start the app with `DATABASE_URL` set to the Docker Postgres and compare responses with the SQLite run.

## Environment note

`docker` is not currently available inside this WSL distro (Docker Desktop's WSL integration is not enabled). Postgres verification needs that turned on, or another way to run a Postgres container.

## Left to the builder

Choice of `.env` loader, connection handling (per request vs pool), how Postgres emulates the write-lock behaviour, structure of the Postgres setup script and the shared schema definition, how the test suite switches backends, and the exact timeout values used to detect "busy".
