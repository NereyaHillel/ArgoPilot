import sqlite3
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from db import connect

FARM_DEMO = "b7e2c0a0-3c1d-4f0a-9a11-0c5d2e6f1001"
FARM_EAST = "a9c1e4b2-6f70-4d8e-a144-3f8b5c904004"
PLOT_NORTH = "c8f3d1b0-4d2e-5a1b-8b22-1d6e3f702002"
PLOT_EAST = "d9a4e2c1-5e3f-4b6a-9c33-2e7f4a803003"
PLOT_WEST = "e0b5f3d2-6f40-4c7b-8d44-3f8a5b914004"
PLOT_GREENHOUSE = "f1c6a4e3-7051-4d8c-9e55-4a9b6c025005"
UNKNOWN_ID = "00000000-0000-4000-8000-000000000000"


def plot_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "farm_id": FARM_DEMO,
        "name": "Test block",
        "area_m2": 500,
        "crop_id": "tomato",
        "planting_date": "2026-03-01",
        "soil_id": "loam",
        "row_spacing_m": 1.5,
        "emitter_spacing_m": 0.4,
        "emitter_id": "dripnet-pc-1.0",
        "lat": 31.25,
        "lon": 34.79,
    }
    payload.update(overrides)
    return payload


def database_from(path: Path) -> Callable[[], Iterator[sqlite3.Connection]]:
    """Stand-in for get_db that opens the database at path."""

    def dependency() -> Iterator[sqlite3.Connection]:
        conn = connect(path)
        try:
            yield conn
        finally:
            conn.close()

    return dependency
