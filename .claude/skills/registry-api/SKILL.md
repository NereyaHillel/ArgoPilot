---
name: registry-api
description: API conventions for services/registry-service. Use this skill whenever you add, change, fix or review an endpoint, route, router, request/response schema, error response or status code in registry-service (farms, plots, catalogues, anything under /v1), and whenever you write or change tests for those endpoints, even if the user never mentions "conventions". Covers /v1 prefixing, list and PATCH behavior, response fields, RFC 9457 problem+json errors with stable codes, required tests, running pytest, and asking instead of inventing behavior.
---

# registry-service API conventions

These rules apply to every endpoint you add or change in `services/registry-service`. Other services will build on this API and handle its errors by `code`, so an unplanned field, status or error shape breaks them silently. Follow the rules even when the task doesn't mention them.

## Rules

**Routes.** Every route lives under `/v1` (routers use `prefix="/v1/<resource>"`). The version prefix leaves room to ship a breaking change later as `/v2` without breaking existing callers. The one exception is the existing `/health` probe in `main.py`.

**Lists.** A list endpoint returns a JSON array, never an object wrapper. No rows means `200` with `[]`, not 404. An empty list is a valid answer, not a missing resource, and clients can then loop over every list response without special cases.

**Response fields.** Return exactly the fields the spec lists for that resource. Don't add convenience fields, timestamps, counts or computed values on your own, because consumers can't tell which extra fields are safe to depend on. Enforce this with `response_model=` on every route, and assert it in tests with `set(body) == {...}`.

**PATCH.** Change only the fields present in the request body. Use `body.model_dump(exclude_unset=True)`, so a field that wasn't sent is never touched or reset to a default. A client that sends one field must not wipe the others by accident.

**Errors.** Every error response is `application/problem+json` (RFC 9457) with a stable `code`:

| Code | Status | Notes |
|---|---|---|
| `VALIDATION` | 422 | bad body, query or path parameter |
| `NOT_FOUND` | 404 | |
| `CONFLICT` | 409 | |
| `UNAVAILABLE` | 503 | must carry a `Retry-After` header |

Never let FastAPI's default error body (`{"detail": ...}`) reach a client. Callers can only rely on one error shape if there is exactly one, and `code` is what they match on, so it has to stay stable. A response looks like this (from `problem_response()` in `errors.py`):

```
HTTP/1.1 404 Not Found
Content-Type: application/problem+json

{"type": "about:blank", "title": "Not Found", "status": 404,
 "detail": "Farm 00000000-0000-4000-8000-000000000000 not found", "code": "NOT_FOUND"}
```

A 503 has the same body with `"code": "UNAVAILABLE"` plus a `Retry-After: 5` header. `errors.py` already does the work. Raise its exceptions from route code (`NotFoundProblem`, `ConflictProblem`, `ValidationProblem`, `UnavailableProblem`, or `require(row, detail)` for "missing row means 404"). Don't build `JSONResponse` errors or raise `HTTPException` yourself. If a new kind of failure doesn't fit one of the four codes, that is a spec gap, so ask (see below) instead of adding a code.

**Tests.** Every endpoint gets tests for the success case and for every failure case it can return. Work out that list from the code, not from memory:

- `404`: unknown id, and any referenced id in the body that must exist.
- `422`: each constrained field, a malformed path id, unknown fields, and `null` in a PATCH.
- `409`: every uniqueness or still-referenced rule the endpoint can hit.
- `503`: the database being unavailable (see `tests/test_errors.py` for how to simulate it).

Failure tests should check the status, the `application/problem+json` content type and the `code` (the `assert_problem` helper in `tests/test_errors.py` does this). A test that checks only the status code can pass while the body is still FastAPI's default. Success tests should check the exact field set. Follow the style of `tests/test_farms.py` and `tests/test_plots.py`, and reuse `tests/support.py` and the `client` fixture.

**Verify before you finish.** Run `uv run pytest` from `services/registry-service` and read the result. Passing tests are the only evidence that the new endpoint works and that nothing existing broke, and a claim of "done" from memory is how broken code gets handed over. If something fails, say so and show the output. Don't report success on a run you didn't see.

**When the spec is silent, ask.** If the spec doesn't say what to do in some case (a status code, a field rule, a sort order, whether a field is editable, how two rules interact), stop and ask the user, with the options and your recommendation. Don't pick a behavior and carry on, because a quietly invented rule becomes API behavior other services rely on. Once the user answers, record the decision in `docs/judgment-log.md` in the existing format (Problem, My answer, Reason).

## Checklist for a new or changed endpoint

1. Route is under `/v1` and has `response_model=` with only spec fields.
2. Lists return `[]` with 200 when empty. PATCH uses `exclude_unset=True`.
3. All failures go through `errors.py` exceptions, and no default FastAPI body is reachable.
4. Tests cover success plus every failure the endpoint can return.
5. `uv run pytest` passes, and you have seen the output.
6. Anything the spec didn't cover was asked about, not guessed.
