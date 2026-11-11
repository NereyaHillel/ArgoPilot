import sqlite3
from typing import Any, NoReturn

from errors import ConflictProblem, ValidationProblem

Row = dict[str, Any]

FARM_COLUMNS = frozenset({"name"})
PLOT_COLUMNS = frozenset(
    {
        "farm_id",
        "name",
        "area_m2",
        "crop_id",
        "planting_date",
        "soil_id",
        "row_spacing_m",
        "emitter_spacing_m",
        "emitter_id",
        "lat",
        "lon",
    }
)
_PLOT_SELECT = (
    "SELECT id, farm_id, name, area_m2, crop_id, planting_date, soil_id, "
    "row_spacing_m, emitter_spacing_m, emitter_id, lat, lon FROM plots"
)


def _rows(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> list[Row]:
    return [dict(row) for row in conn.execute(sql, params)]


def _row(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...]) -> Row | None:
    row = conn.execute(sql, params).fetchone()
    return None if row is None else dict(row)


def _update(
    conn: sqlite3.Connection, table: str, columns: frozenset[str], row_id: str, changes: Row
) -> None:
    if not changes:
        return
    if not set(changes) <= columns:
        raise ValueError(f"unexpected columns for {table}: {sorted(set(changes) - columns)}")
    # Column names are interpolated, so they are checked against the whitelist above.
    assignments = ", ".join(f"{column} = ?" for column in changes)
    conn.execute(f"UPDATE {table} SET {assignments} WHERE id = ?", (*changes.values(), row_id))


def _raise_plot_problem(exc: sqlite3.IntegrityError) -> NoReturn:
    if exc.sqlite_errorname == "SQLITE_CONSTRAINT_UNIQUE":
        raise ConflictProblem("A plot with this name already exists on this farm") from exc
    if exc.sqlite_errorname == "SQLITE_CONSTRAINT_FOREIGNKEY":
        raise ValidationProblem(
            "farm_id, crop_id, soil_id, or emitter_id refers to a record that does not exist"
        ) from exc
    raise exc


def list_farms(conn: sqlite3.Connection) -> list[Row]:
    return _rows(conn, "SELECT id, name FROM farms ORDER BY name, id")


def get_farm(conn: sqlite3.Connection, farm_id: str) -> Row | None:
    return _row(conn, "SELECT id, name FROM farms WHERE id = ?", (farm_id,))


def insert_farm(conn: sqlite3.Connection, farm: Row) -> None:
    conn.execute("INSERT INTO farms (id, name) VALUES (:id, :name)", farm)


def update_farm(conn: sqlite3.Connection, farm_id: str, changes: Row) -> None:
    _update(conn, "farms", FARM_COLUMNS, farm_id, changes)


def count_plots(conn: sqlite3.Connection, farm_id: str) -> int:
    return conn.execute("SELECT COUNT(*) FROM plots WHERE farm_id = ?", (farm_id,)).fetchone()[0]


def delete_farm(conn: sqlite3.Connection, farm_id: str) -> None:
    try:
        conn.execute("DELETE FROM farms WHERE id = ?", (farm_id,))
    except sqlite3.IntegrityError as exc:
        if exc.sqlite_errorname == "SQLITE_CONSTRAINT_FOREIGNKEY":
            raise ConflictProblem("Farm still has plots; delete its plots first") from exc
        raise


def list_plots(conn: sqlite3.Connection, farm_id: str | None) -> list[Row]:
    if farm_id is None:
        return _rows(conn, f"{_PLOT_SELECT} ORDER BY name, id")
    return _rows(conn, f"{_PLOT_SELECT} WHERE farm_id = ? ORDER BY name, id", (farm_id,))


def get_plot(conn: sqlite3.Connection, plot_id: str) -> Row | None:
    return _row(conn, f"{_PLOT_SELECT} WHERE id = ?", (plot_id,))


def plot_name_taken(
    conn: sqlite3.Connection, farm_id: str, name: str, plot_id: str | None
) -> bool:
    # `id IS NOT ?` acts like `!=` for a real id, and matches every row when plot_id is None.
    row = conn.execute(
        "SELECT 1 FROM plots WHERE farm_id = ? AND name = ? AND id IS NOT ?",
        (farm_id, name, plot_id),
    ).fetchone()
    return row is not None


def insert_plot(conn: sqlite3.Connection, plot: Row) -> None:
    try:
        conn.execute(
            "INSERT INTO plots (id, farm_id, name, area_m2, crop_id, planting_date, soil_id, "
            "row_spacing_m, emitter_spacing_m, emitter_id, lat, lon) VALUES "
            "(:id, :farm_id, :name, :area_m2, :crop_id, :planting_date, :soil_id, "
            ":row_spacing_m, :emitter_spacing_m, :emitter_id, :lat, :lon)",
            plot,
        )
    except sqlite3.IntegrityError as exc:
        _raise_plot_problem(exc)


def update_plot(conn: sqlite3.Connection, plot_id: str, changes: Row) -> None:
    try:
        _update(conn, "plots", PLOT_COLUMNS, plot_id, changes)
    except sqlite3.IntegrityError as exc:
        _raise_plot_problem(exc)


def delete_plot(conn: sqlite3.Connection, plot_id: str) -> None:
    conn.execute("DELETE FROM plots WHERE id = ?", (plot_id,))


def list_crops(conn: sqlite3.Connection) -> list[Row]:
    return _rows(conn, "SELECT id, name FROM crops ORDER BY name, id")


def get_crop(conn: sqlite3.Connection, crop_id: str) -> Row | None:
    return _row(conn, "SELECT id, name FROM crops WHERE id = ?", (crop_id,))


def list_soils(conn: sqlite3.Connection) -> list[Row]:
    return _rows(conn, "SELECT id, name, available_water_mm_per_m FROM soils ORDER BY name, id")


def get_soil(conn: sqlite3.Connection, soil_id: str) -> Row | None:
    return _row(
        conn,
        "SELECT id, name, available_water_mm_per_m FROM soils WHERE id = ?",
        (soil_id,),
    )


def list_emitters(conn: sqlite3.Connection) -> list[Row]:
    return _rows(conn, "SELECT id, name, flow_lph FROM emitters ORDER BY name, id")


def get_emitter(conn: sqlite3.Connection, emitter_id: str) -> Row | None:
    return _row(conn, "SELECT id, name, flow_lph FROM emitters WHERE id = ?", (emitter_id,))
