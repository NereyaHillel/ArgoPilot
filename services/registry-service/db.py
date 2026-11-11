import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, Any

import psycopg
from fastapi import Depends
from psycopg.pq import TransactionStatus
from psycopg.rows import dict_row

import config

DB_PATH = Path(__file__).resolve().parent / "registry.db"

# `?` and `:name` placeholders as written in the SQL; `::` (a Postgres cast) is left alone.
_PLACEHOLDER = re.compile(r"\?|(?<!:):(\w+)")


def connect(path: Path = DB_PATH) -> sqlite3.Connection:
    # mode=rw: a missing file must fail, not be silently created as an empty database.
    # check_same_thread=False: FastAPI may run the dependency and the endpoint on different threads.
    conn = sqlite3.connect(
        f"{path.as_uri()}?mode=rw",
        uri=True,
        isolation_level=None,
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row
    # SQLite does not enforce foreign keys unless this is set on each connection.
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


class PgConnection:
    """A psycopg connection that takes the same SQL and parameters as sqlite3."""

    def __init__(self, url: str) -> None:
        self._conn = psycopg.connect(url, autocommit=True, row_factory=dict_row)

    def execute(self, sql: str, params: tuple[Any, ...] | dict[str, Any] = ()) -> psycopg.Cursor:
        sql = _PLACEHOLDER.sub(lambda m: "%s" if m[0] == "?" else f"%({m[1]})s", sql)
        return self._conn.execute(sql, params or None)

    @property
    def in_transaction(self) -> bool:
        status = self._conn.info.transaction_status
        return status in (TransactionStatus.INTRANS, TransactionStatus.INERROR)

    def close(self) -> None:
        self._conn.close()


Conn = sqlite3.Connection | PgConnection


def connect_url(url: str) -> Conn:
    if url.startswith("sqlite:"):
        if not url.startswith("sqlite:///"):
            raise ValueError(f"SQLite DATABASE_URL must start with sqlite:///, got {url!r}")
        path = Path(url.removeprefix("sqlite:///"))
        return connect(path if path.is_absolute() else config.SERVICE_DIR / path)
    return PgConnection(url)


def get_db() -> Iterator[Conn]:
    conn = connect_url(config.database_url())
    try:
        yield conn
    finally:
        conn.close()


DbConn = Annotated[Conn, Depends(get_db)]


# Any fixed key works; every Postgres writer takes this one lock, like SQLite's single write lock.
PG_WRITE_LOCK_KEY = 0x52454749
# How long a writer waits for that lock before giving up with a 503. Tests shorten it.
PG_LOCK_TIMEOUT = "5s"

# Database states that mean "unreachable or busy, try again". Any other database error is a bug.
UNAVAILABLE_SQLITE_ERRORS = frozenset({"SQLITE_CANTOPEN", "SQLITE_BUSY", "SQLITE_LOCKED"})
# Postgres SQLSTATEs with the same meaning; class 08 (connection exceptions) is matched by prefix.
UNAVAILABLE_PG_SQLSTATES = frozenset(
    {"57P01", "57P02", "57P03", "53300", "55P03", "57014", "40P01", "40001", "3D000"}
)

INTEGRITY_ERRORS: tuple[type[Exception], ...] = (sqlite3.IntegrityError, psycopg.IntegrityError)


@contextmanager
def write_transaction(conn: Conn) -> Iterator[None]:
    # SQLite: BEGIN IMMEDIATE takes the write lock up front, so checks made inside the block
    # cannot be invalidated by another writer before COMMIT. Postgres: an advisory lock held
    # until COMMIT gives the same guarantee.
    conn.execute("BEGIN" if isinstance(conn, PgConnection) else "BEGIN IMMEDIATE")
    try:
        if isinstance(conn, PgConnection):
            conn.execute(f"SET LOCAL lock_timeout = '{PG_LOCK_TIMEOUT}'")
            conn.execute(f"SELECT pg_advisory_xact_lock({PG_WRITE_LOCK_KEY})")
        yield
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def is_unavailable(exc: Exception) -> bool:
    if isinstance(exc, sqlite3.Error):
        return getattr(exc, "sqlite_errorname", None) in UNAVAILABLE_SQLITE_ERRORS
    if not isinstance(exc, psycopg.Error):
        return False
    if exc.sqlstate is None:
        # libpq fails to connect without a SQLSTATE, whether the server is down, the database
        # is missing or the password is wrong. Only the message tells bad credentials apart.
        return isinstance(exc, psycopg.OperationalError) and "authentication failed" not in str(exc)
    return exc.sqlstate.startswith("08") or exc.sqlstate in UNAVAILABLE_PG_SQLSTATES


def is_unique_violation(exc: Exception) -> bool:
    if isinstance(exc, sqlite3.IntegrityError):
        return exc.sqlite_errorname == "SQLITE_CONSTRAINT_UNIQUE"
    return isinstance(exc, psycopg.errors.UniqueViolation)


def is_foreign_key_violation(exc: Exception) -> bool:
    if isinstance(exc, sqlite3.IntegrityError):
        return exc.sqlite_errorname == "SQLITE_CONSTRAINT_FOREIGNKEY"
    return isinstance(exc, psycopg.errors.ForeignKeyViolation)


def order_by_name(conn: Conn) -> str:
    # SQLite compares text byte-wise; Postgres needs the "C" collation to sort the same way.
    if isinstance(conn, PgConnection):
        return 'ORDER BY name COLLATE "C", id COLLATE "C"'
    return "ORDER BY name, id"
