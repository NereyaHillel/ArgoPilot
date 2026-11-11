# AgroPilot — P1 Registry Service: Project Overview

## 1. Context: the business

**AgroPilot** helps growers manage agricultural crops with AI. Before any AI can give advice about a field, the platform needs a reliable **system of record** that describes the field: which farm it belongs to, what grows there, in what soil, and with what irrigation hardware.

**P1** builds that foundation: the **registry service**, a REST API that manages:

| Data | Owned by | What it describes |
| --- | --- | --- |
| **Farms** | Grower (full CRUD) | A grower's farm: `id`, `name` |
| **Plots** | Grower (full CRUD) | A field inside a farm: area, crop, planting date, soil, drip layout (row and emitter spacing, emitter model), GPS location |
| **Crops** | Platform (read-only) | `tomato`, `bell-pepper` |
| **Soils** | Platform (read-only) | `sand`, `loam`, `clay-loam`, each with `available_water_mm_per_m`, the depth of water the soil holds for plants |
| **Emitters** | Platform (read-only) | DripNet PC drippers with `flow_lph` from 0.6 to 2.0 L/h |

**Why these fields matter to the business:** together they describe a plot's water situation. The soil says how much water the root zone can store. The emitter flow and the spacing say how fast the drip system applies water: `flow_lph / (row_spacing_m × emitter_spacing_m)` = mm/h, so 1.0 L/h on 1.5 m × 0.4 m ≈ 1.67 mm/h. The crop and planting date give the growth stage, and the location links the plot to weather data. Later services (irrigation planning, AI recommendations) will read this data, so bad data here produces bad advice downstream. That is why the spec puts so much weight on validation. *(The downstream use is my reading of the data model. P1 itself does not include it.)*

## 2. The assignment (P1 spec in short)

| Req | Requirement |
| --- | --- |
| **FR-1.1** | CRUD for farms and plots |
| **FR-1.2** | Read-only catalogues (crops, soils, emitters). Any other method → **405** |
| **FR-1.3** | Reject a plot if `area_m2` ≤ 0, a spacing ≤ 0, `planting_date` is in the future, crop/soil/emitter is not in the catalogue, `lat` ∉ [-90, 90], or `lon` ∉ [-180, 180] |
| **FR-1.4** | Every error is `application/problem+json` (RFC 9457) with `code` ∈ {`VALIDATION`, `NOT_FOUND`, `CONFLICT`, `UNAVAILABLE`} |
| **NFR-1.1** | `GET` list / by id: **p95 ≤ 100 ms at 10 RPS**. Measure it and report the number |
| Data | Return **only** the listed fields. Plot names are unique within a farm. Lists are JSON arrays, and an empty list is `200 []` |
| Storage | SQLite locally and in tests, PostgreSQL in production, chosen by `DATABASE_URL`. SQLite is one file, `registry.db`, built by the supplied `seed_registry.sh`; PostgreSQL is set up by `seed_registry_pg.py` (15 rows: 2 crops, 3 soils, 4 emitters, 2 farms, 4 plots) |
| Docs | A service README and `docs/judgment-log.md` with at least 2 entries (what the AI agent suggested, what I decided, why) |

## 3. Requirement → implementation map

| Req | Where it lives | Status |
| --- | --- | --- |
| FR-1.1 | `routers/farms.py`, `routers/plots.py`, `repository.py` | Done. 201 / 200 / 204 as specified, PATCH is partial, `?farm_id=` filter |
| FR-1.2 | `routers/catalogues.py` (GET routes only). 405 handling in `errors.py` | Done. 405 includes an `Allow` header |
| FR-1.3 | `schemas.py` (Pydantic types) + `_check_references` in `routers/plots.py` | Done, plus stricter rules (see §6) |
| FR-1.4 | `errors.py`: exception hierarchy + handlers for every error source | Done. Framework errors (404 route, 405, bad JSON) are covered too |
| NFR-1.1 | `scripts/locustfile.py`, results in the service README | **p95 = 20 ms**, 0 failures, 9.65 RPS (5-minute run) |
| Only listed fields | `response_model=` on every route | Tested (`..._returns_201_with_only_spec_fields`) |
| Docs | `services/registry-service/README.md`, `docs/judgment-log.md` (4 entries) | Done |

## 4. Tech stack

- **Python 3.12**, **FastAPI 0.115** + **Pydantic v2**, **uvicorn**
- **SQLite** (default, local and tests) through the standard `sqlite3` module, or **PostgreSQL** (production) through `psycopg`, chosen by `DATABASE_URL`; **no ORM**
- **uv** for environment and dependencies
- **pytest** + FastAPI `TestClient`: **122 tests, all passing**
- **Locust** (run through `uvx`, so it is not a project dependency) for NFR-1.1

## 5. Architecture

```
HTTP request
   │
   ▼
routers/  farms.py · plots.py · catalogues.py   ← HTTP: status codes, transactions, business checks
   ├── schemas.py     ← Pydantic request/response models = validation (FR-1.3) + output shape
   ├── repository.py  ← all SQL; maps database constraint errors to API errors
   ├── db.py          ← per-request connection (FastAPI dependency) + write_transaction()
   └── errors.py      ← RFC 9457 problem documents for every failure (FR-1.4)
main.py               ← creates the app, registers error handlers, includes routers, GET /health
```

Each layer has one job. The routers never write SQL, the repository never knows about HTTP, and every error goes out through one formatter.

### Data model (from the supplied seed)

```
farms(id PK, name)
plots(id PK, farm_id FK→farms, name, area_m2, crop_id FK→crops, planting_date,
      soil_id FK→soils, row_spacing_m, emitter_spacing_m, emitter_id FK→emitters,
      lat, lon, UNIQUE(farm_id, name))
crops(id, name) · soils(id, name, available_water_mm_per_m) · emitters(id, name, flow_lph)
```

The schema was given, and the service **never creates tables**. The `UNIQUE(farm_id, name)` and foreign keys in it are the database-level guarantee for the spec's uniqueness and catalogue rules.

## 6. Key implementation points

### 6.1 Validation (FR-1.3), `schemas.py`

The rules are reusable `Annotated` types:

```python
Name           = Annotated[str,   AfterValidator(_not_blank)]
PositiveNumber = Annotated[float, Field(gt=0, strict=True, allow_inf_nan=False)]
Latitude       = Annotated[float, Field(ge=-90, le=90, strict=True, allow_inf_nan=False)]
Longitude      = Annotated[float, Field(ge=-180, le=180, strict=True, allow_inf_nan=False)]
PlantingDate   = Annotated[date,  AfterValidator(_not_in_future)]      # "today" = UTC
```

These go further than the spec, and each choice is in the judgment log:
- `strict=True`: `"1000"` (a string) is rejected, and `Infinity`/`NaN` are rejected.
- `extra="forbid"`: unknown body fields → 422, so a typo in a PATCH can't return 200 while changing nothing.
- PATCH fields are optional but **cannot be `null`**.
- Plot names can't be blank either (the spec only says this for farms).

Catalogue references (`crop_id`, `soil_id`, `emitter_id`, and `farm_id`) are checked against the database, and all unknown references are reported in one 422.

### 6.2 Errors (FR-1.4), `errors.py`

```json
{"type": "about:blank", "title": "Conflict", "status": 409,
 "detail": "A plot named 'North block' already exists on this farm", "code": "CONFLICT"}
```

- `ApiProblem` subclasses (`ValidationProblem`, `NotFoundProblem`, `ConflictProblem`, `UnavailableProblem`) carry `status` and `code`.
- Handlers also convert **framework** errors: unknown route → 404 `NOT_FOUND`, wrong method → 405 with a correct `Allow` header, malformed or non-UTF-8 JSON → 422 `VALIDATION`.
- **"Database unreachable" → 503 `UNAVAILABLE` + `Retry-After: 5`** when SQLite reports `CANTOPEN` (file missing), `BUSY` or `LOCKED`, and on PostgreSQL when the server is unreachable or busy (connection failures, lock timeouts, deadlocks, serialization failures). The connection opens with `mode=rw`, so a missing file fails instead of SQLite silently creating an empty database.
- Any other database error or unexpected exception is logged and returns 500, still as problem+json.

### 6.3 Uniqueness and race conditions, `db.py` + `repository.py`

Writes follow "check, then write": does the farm exist, is the name free, then INSERT. Two concurrent requests could both pass the check, so:

1. **`BEGIN IMMEDIATE`** takes SQLite's write lock *before* the checks. The check and the write are atomic, and every failure path rolls back.
2. **The database constraints are the backstop.** `SQLITE_CONSTRAINT_UNIQUE` → 409 and `SQLITE_CONSTRAINT_FOREIGNKEY` → 422. The app checks give clear messages, and the constraints guarantee correctness.
3. `PRAGMA foreign_keys = ON` on every connection, because SQLite turns FK enforcement off by default.

This is also why uniqueness is **case-sensitive**: it matches what the `UNIQUE` index enforces, so the app rule and the database never disagree.

### 6.4 Farm delete with plots → 409

`DELETE /v1/farms/{id}` counts the farm's plots inside the transaction and returns **409 CONFLICT** if there are any. The FK constraint backs this up. Nothing is ever cascade-deleted.

### 6.5 How a PATCH flows (`PATCH /v1/plots/{id}`)

1. Route match. Wrong method → 405, unknown route → 404.
2. Path `id` must be a UUID → otherwise 422.
3. Body validated by `PlotUpdate`: decodable JSON, no unknown fields, no nulls, per-field rules → otherwise 422.
4. Open the DB connection. File missing → 503.
5. `model_dump(exclude_unset=True)` keeps **only the fields that were sent** (the spec's "PATCH changes only the fields in the body").
6. `BEGIN IMMEDIATE` (lock busy → 503).
7. Plot exists? → otherwise 404.
8. Referenced farm/crop/soil/emitter exist? → otherwise 422.
9. Name free on the **resulting** farm? The patch is merged with the current row, so rename, move, and rename + move are all handled. The plot itself is excluded, so keeping its own name is fine. Taken → 409.
10. `UPDATE` with a column whitelist (the column names are interpolated into SQL, so they are checked first).
11. Re-read the row, COMMIT, return 200 with the stored plot. Any error → ROLLBACK.

Order: cheap checks with no database first, then database checks under the lock, then the constraints as the final net.

## 7. Spec gaps and my decisions (judgment log)

The spec left several things open. In each case the AI agent suggested options with a recommendation, and I decided:

| Gap in the spec | Decision | Reason |
| --- | --- | --- |
| Is a blank plot name OK? | No, same rule as farms | A blank name is meaningless, and one rule is consistent |
| "Future" according to which clock? | UTC date | Same answer on every server |
| Unknown body fields? | 422 | Catches PATCH typos that would otherwise be a silent no-op |
| Can PATCH move a plot to another farm? | Yes, if the farm exists and the name is free there | "PATCH changes the fields in the body" includes `farm_id` |
| List order? | `name`, then `id` | Stable and predictable |
| Case-sensitive uniqueness? | Yes | Matches the DB index, so it is race-safe |
| Non-UTF-8 body (FastAPI gives 400)? | 422 like malformed JSON | Matches the spec's mapping. A test pins FastAPI's message text |
| Who generates the plot `id`? | Server (UUID4) | The spec says "201 returns that object plus id" |

Two further mappings follow from the spec's four-code limit:
- **405** uses code `VALIDATION`, the closest of the four codes.
- **500** uses code `UNAVAILABLE`, since there is no internal-error code.

An unknown `farm_id` in a **body** is 422, not 404. The URL resource is fine and the body is invalid, consistent with how the spec treats unknown crop, soil and emitter.

## 8. Testing

- **122 tests, all passing.** Each test seeds a **fresh `registry.db` in a temp directory** using the real `seed_registry.sh` and swaps it in through `app.dependency_overrides`. Tests are isolated, and the real DB is never touched.
- **FR coverage:** every CRUD status code, the `?farm_id=` filter, PATCH semantics (partial updates, moves, renames, keeping its own name), 405 on every non-GET catalogue method, and the "only spec fields" responses.
- **FR-1.3 boundaries:** `lat=90` accepted, just above rejected, `area_m2=0` rejected, today (UTC) accepted, tomorrow rejected, numeric strings, infinity, and every failing field reported in one response.
- **FR-1.4 failure modes:** problem+json shape for each code, missing DB → 503 + Retry-After, **locked DB → 503**, DB without schema → 500, unexpected exception → 500.
- **`test_constraints.py`** tests the database directly, proving the safety net holds even if the app checks are bypassed.

## 9. NFR-1.1 measurement

Locust: 10 users × 1 request/s ≈ 10 RPS for 5 minutes, randomly hitting the 5 list endpoints and 5 by-id endpoints. The server runs without `--reload`, and `--reset-stats` drops the ramp-up.

| Requests | Failures | RPS | Median | **p95** | p99 | Max |
| --- | --- | --- | --- | --- | --- | --- |
| 2,970 | 0 | 9.65 | 8 ms | **20 ms** | 42 ms | 93 ms |

That is **5× under the 100 ms budget**. Caveats: it was measured on the seed data on a laptop (i5-1235U) with Locust on the same machine, and `GET /v1/plots` has no pagination, so it will slow down as data grows.

## 10. Trade-offs and what I'd do next

| Current | Why it's fine for P1 | Next step |
| --- | --- | --- |
| SQLite by default, PostgreSQL in production | SQLite is required by the spec and is far above 10 RPS; PostgreSQL is now supported through `DATABASE_URL` | Done: `db.py` picks the backend from `DATABASE_URL` |
| No pagination | Small dataset | Cursor pagination on `(name, id)`, which matches the sort order |
| No auth / tenancy | Not in the spec | JWT, farms scoped to an owner |
| No migrations | The schema is given by the seed | Alembic / versioned SQL |
| 500 uses `UNAVAILABLE` | The spec allows only 4 codes | Propose an `INTERNAL` code |
| No CI / Docker / metrics | Out of scope | GitHub Actions, Dockerfile, OpenTelemetry |

## 11. Likely questions

- **Why no ORM?** Five fixed tables and simple queries. Raw SQL keeps SQLite-specific behaviour visible (error names, `BEGIN IMMEDIATE`), and `repository.py` is the seam to swap later.
- **How do you guarantee unique plot names under concurrency?** The lock is taken before checking, and the `UNIQUE` constraint maps to 409 as a backstop.
- **Why 503 with `Retry-After` and not 500?** A missing or locked DB is a *transient* infrastructure problem, so the client should retry. A 500 means a bug.
- **How do you make sure you return only the spec fields?** `response_model` on every route filters the output, and tests assert the exact key set.
- **What did the AI agent do vs. you?** The agent implemented the code and raised the spec gaps as options with a recommendation. I made the decisions, and they are logged with reasons in `docs/judgment-log.md`. In one case (plot id) I went against the first suggestion.
