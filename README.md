# AgroPilot

AgroPilot helps growers manage agricultural crops with AI.

This repository holds the platform's backend services. The first one is **registry-service**. It stores farms and their plots, plus reference catalogues of crops, soils, and drip emitters. Other services will read this data to plan irrigation and give recommendations.

## Tech stack

- Python 3.12, FastAPI, Pydantic v2
- SQLite (`registry.db`)
- [uv](https://docs.astral.sh/uv/) for dependencies
- pytest for tests, Locust for load tests

## Repository layout

```
services/
  registry-service/     FastAPI service: farms, plots, catalogues
    routers/            HTTP endpoints
    schemas.py          Request/response models and validation
    repository.py       SQL queries
    db.py               Connections and transactions
    errors.py           RFC 9457 error responses
    seed_registry.sh    Builds registry.db with sample data
    tests/              pytest suite
    scripts/            Load test (Locust)
docs/
  judgment-log.md       Design decisions and why they were made
  project-overview.md   Business and technical overview
```

## Getting started

Requirements: Python 3.12, `uv`, and the `sqlite3` CLI.

```bash
cd services/registry-service
uv sync
bash seed_registry.sh          # creates registry.db (deletes any existing one)
uv run uvicorn main:app --host 127.0.0.1 --port 8080
```

- Health check: http://127.0.0.1:8080/health → `{"status": "ok"}`
- Interactive API docs: http://127.0.0.1:8080/docs

## API

| Resource | Endpoints |
| --- | --- |
| Farms | `POST` `GET` `/v1/farms` · `GET` `PATCH` `DELETE` `/v1/farms/{id}` |
| Plots | `POST` `GET` `/v1/plots[?farm_id=]` · `GET` `PATCH` `DELETE` `/v1/plots/{id}` |
| Catalogues (read-only) | `GET` `/v1/crops`, `/v1/soils`, `/v1/emitters` and `/{id}` |

All errors use the [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457) `application/problem+json` format with a `code` of `VALIDATION`, `NOT_FOUND`, `CONFLICT`, or `UNAVAILABLE`.

## Tests

```bash
cd services/registry-service
uv run pytest
```

Each test runs against a freshly seeded copy of the database, so `registry.db` is never modified.

## Performance

`GET` requests must have a p95 latency of at most 100 ms at 10 requests per second. Measured with Locust on the seeded data: **p95 = 20 ms, 0 failures**.

## Documentation

- [docs/project-overview.md](docs/project-overview.md): what the project does and how it is built
- [docs/judgment-log.md](docs/judgment-log.md): decisions made where the spec was open
