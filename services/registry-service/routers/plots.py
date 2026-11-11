import uuid
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Response

import repository
from db import Conn, DbConn, write_transaction
from errors import ConflictProblem, ValidationProblem, require
from schemas import Plot, PlotCreate, PlotUpdate

router = APIRouter(prefix="/v1/plots", tags=["plots"])

# Reference field -> (noun for messages, lookup that proves the referenced record exists).
_REFERENCES = {
    "farm_id": ("farm", repository.get_farm),
    "crop_id": ("crop", repository.get_crop),
    "soil_id": ("soil", repository.get_soil),
    "emitter_id": ("emitter", repository.get_emitter),
}


@router.post("", status_code=201, response_model=Plot)
def create_plot(body: PlotCreate, conn: DbConn) -> dict[str, Any]:
    plot = {"id": str(uuid.uuid4()), **body.model_dump(mode="json")}
    with write_transaction(conn):
        _check_references(conn, plot)
        _check_name_free(conn, plot["farm_id"], plot["name"], plot_id=None)
        repository.insert_plot(conn, plot)
    return plot


@router.get("", response_model=list[Plot])
def list_plots(conn: DbConn, farm_id: UUID | None = None) -> list[dict[str, Any]]:
    return repository.list_plots(conn, None if farm_id is None else str(farm_id))


@router.get("/{plot_id}", response_model=Plot)
def get_plot(plot_id: UUID, conn: DbConn) -> dict[str, Any]:
    return _plot_or_404(conn, plot_id)


@router.patch("/{plot_id}", response_model=Plot)
def update_plot(plot_id: UUID, body: PlotUpdate, conn: DbConn) -> dict[str, Any]:
    changes = body.model_dump(mode="json", exclude_unset=True)
    with write_transaction(conn):
        current = _plot_or_404(conn, plot_id)
        _check_references(conn, changes)
        _check_name_free(
            conn,
            changes.get("farm_id", current["farm_id"]),
            changes.get("name", current["name"]),
            plot_id=str(plot_id),
        )
        repository.update_plot(conn, str(plot_id), changes)
        return _plot_or_404(conn, plot_id)


@router.delete("/{plot_id}", status_code=204)
def delete_plot(plot_id: UUID, conn: DbConn) -> Response:
    with write_transaction(conn):
        _plot_or_404(conn, plot_id)
        repository.delete_plot(conn, str(plot_id))
    return Response(status_code=204)


def _plot_or_404(conn: Conn, plot_id: UUID) -> dict[str, Any]:
    return require(repository.get_plot(conn, str(plot_id)), f"Plot {plot_id} not found")


def _check_references(conn: Conn, values: dict[str, Any]) -> None:
    problems = [
        f"{field}: unknown {noun} {values[field]!r}"
        for field, (noun, lookup) in _REFERENCES.items()
        if field in values and lookup(conn, values[field]) is None
    ]
    if problems:
        raise ValidationProblem("; ".join(problems))


def _check_name_free(conn: Conn, farm_id: str, name: str, plot_id: str | None) -> None:
    if repository.plot_name_taken(conn, farm_id, name, plot_id):
        raise ConflictProblem(f"A plot named {name!r} already exists on this farm")
