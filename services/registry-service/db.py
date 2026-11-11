import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends

DB_PATH = Path(__file__).resolve().parent / "registry.db"


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


def get_db() -> Iterator[sqlite3.Connection]:
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


DbConn = Annotated[sqlite3.Connection, Depends(get_db)]


@contextmanager
def write_transaction(conn: sqlite3.Connection) -> Iterator[None]:
    # BEGIN IMMEDIATE takes the write lock up front, so checks made inside the block
    # cannot be invalidated by another writer before COMMIT.
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")
