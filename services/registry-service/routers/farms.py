import uuid
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Response

import repository
from db import Conn, DbConn, write_transaction
from errors import ConflictProblem, require
from schemas import Farm, FarmCreate, FarmUpdate

router = APIRouter(prefix="/v1/farms", tags=["farms"])


@router.post("", status_code=201, response_model=Farm)
def create_farm(body: FarmCreate, conn: DbConn) -> dict[str, Any]:
    farm = {"id": str(uuid.uuid4()), "name": body.name}
    with write_transaction(conn):
        repository.insert_farm(conn, farm)
    return farm


@router.get("", response_model=list[Farm])
def list_farms(conn: DbConn) -> list[dict[str, Any]]:
    return repository.list_farms(conn)


@router.get("/{farm_id}", response_model=Farm)
def get_farm(farm_id: UUID, conn: DbConn) -> dict[str, Any]:
    return _farm_or_404(conn, farm_id)


@router.patch("/{farm_id}", response_model=Farm)
def update_farm(farm_id: UUID, body: FarmUpdate, conn: DbConn) -> dict[str, Any]:
    with write_transaction(conn):
        _farm_or_404(conn, farm_id)
        repository.update_farm(conn, str(farm_id), body.model_dump(exclude_unset=True))
        return _farm_or_404(conn, farm_id)


@router.delete("/{farm_id}", status_code=204)
def delete_farm(farm_id: UUID, conn: DbConn) -> Response:
    with write_transaction(conn):
        _farm_or_404(conn, farm_id)
        if repository.count_plots(conn, str(farm_id)):
            raise ConflictProblem("Farm still has plots; delete its plots first")
        repository.delete_farm(conn, str(farm_id))
    return Response(status_code=204)


def _farm_or_404(conn: Conn, farm_id: UUID) -> dict[str, Any]:
    return require(repository.get_farm(conn, str(farm_id)), f"Farm {farm_id} not found")
