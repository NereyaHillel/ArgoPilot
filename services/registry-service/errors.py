import logging
import sqlite3
from http import HTTPStatus
from typing import Any, ClassVar

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.routing import Route

logger = logging.getLogger(__name__)

PROBLEM_MEDIA_TYPE = "application/problem+json"
RETRY_AFTER_SECONDS = 5

# Database states that mean "unreachable or busy, try again". Any other SQLite error is a bug.
UNAVAILABLE_SQLITE_ERRORS = frozenset({"SQLITE_CANTOPEN", "SQLITE_BUSY", "SQLITE_LOCKED"})

# The spec's code list has no entry for 405, so it maps to VALIDATION.
FRAMEWORK_CODES = {404: "NOT_FOUND", 405: "VALIDATION"}

# The 400 FastAPI raises when it cannot decode a body, such as non-UTF-8 bytes.
FASTAPI_BODY_READ_ERROR = "There was an error parsing the body"


class ApiProblem(Exception):
    status: ClassVar[int]
    code: ClassVar[str]

    def __init__(self, detail: str, headers: dict[str, str] | None = None) -> None:
        super().__init__(detail)
        self.detail = detail
        self.headers = headers


class ValidationProblem(ApiProblem):
    status = 422
    code = "VALIDATION"


class NotFoundProblem(ApiProblem):
    status = 404
    code = "NOT_FOUND"


class ConflictProblem(ApiProblem):
    status = 409
    code = "CONFLICT"


class UnavailableProblem(ApiProblem):
    status = 503
    code = "UNAVAILABLE"

    def __init__(self, detail: str) -> None:
        super().__init__(detail, headers={"Retry-After": str(RETRY_AFTER_SECONDS)})


def require[T](row: T | None, detail: str) -> T:
    if row is None:
        raise NotFoundProblem(detail)
    return row


def problem_response(
    status: int, code: str, detail: str, headers: dict[str, str] | None = None
) -> JSONResponse:
    return JSONResponse(
        {
            "type": "about:blank",
            "title": HTTPStatus(status).phrase,
            "status": status,
            "detail": detail,
            "code": code,
        },
        status_code=status,
        headers=headers,
        media_type=PROBLEM_MEDIA_TYPE,
    )


def _describe(error: dict[str, Any]) -> str:
    # FastAPI prefixes each location with its source ("body", "path", "query").
    # Malformed JSON has no field name, so the label falls back to the source.
    source, *path = error["loc"]
    label = ".".join(part for part in path if isinstance(part, str)) or source
    return f"{label}: {error['msg']}"


def _internal_error() -> JSONResponse:
    # The spec's four codes have no internal-error entry. UNAVAILABLE is the closest fit.
    return problem_response(500, "UNAVAILABLE", "Internal server error")


async def _handle_problem(request: Request, exc: ApiProblem) -> JSONResponse:
    return problem_response(exc.status, exc.code, exc.detail, exc.headers)


async def _handle_http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    if exc.status_code == 400 and exc.detail == FASTAPI_BODY_READ_ERROR:
        # Malformed JSON already gets 422, so an unreadable body gets the same status.
        return problem_response(422, "VALIDATION", "body: could not be read as JSON")
    headers = exc.headers
    if exc.status_code == 405:
        headers = {"Allow": ", ".join(sorted(_allowed_methods(request)))}
    default = "UNAVAILABLE" if exc.status_code >= 500 else "VALIDATION"
    code = FRAMEWORK_CODES.get(exc.status_code, default)
    return problem_response(exc.status_code, code, str(exc.detail), headers)


def _allowed_methods(request: Request) -> set[str]:
    # Starlette reports only the first route matching the path, so combine every match.
    methods: set[str] = set()
    for route in request.app.routes:
        if isinstance(route, Route) and route.path_regex.match(request.url.path):
            methods |= route.methods
    return methods


async def _handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    detail = "; ".join(_describe(error) for error in exc.errors())
    return problem_response(422, "VALIDATION", detail)


async def _handle_sqlite_error(request: Request, exc: sqlite3.Error) -> JSONResponse:
    if getattr(exc, "sqlite_errorname", None) in UNAVAILABLE_SQLITE_ERRORS:
        logger.warning("registry database unavailable: %s", exc)
        return await _handle_problem(
            request, UnavailableProblem("Registry database is unavailable; retry later")
        )
    logger.error("database error on %s %s", request.method, request.url.path, exc_info=exc)
    return _internal_error()


async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
    return _internal_error()


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiProblem, _handle_problem)
    app.add_exception_handler(StarletteHTTPException, _handle_http_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(sqlite3.Error, _handle_sqlite_error)
    app.add_exception_handler(Exception, _handle_unexpected)
