from typing import Any

from fastapi import APIRouter

import repository
from db import DbConn
from errors import require
from schemas import Crop, Emitter, Soil

router = APIRouter(prefix="/v1", tags=["catalogues"])


@router.get("/crops", response_model=list[Crop])
def list_crops(conn: DbConn) -> list[dict[str, Any]]:
    return repository.list_crops(conn)


@router.get("/crops/{crop_id}", response_model=Crop)
def get_crop(crop_id: str, conn: DbConn) -> dict[str, Any]:
    return require(repository.get_crop(conn, crop_id), f"Crop {crop_id} not found")


@router.get("/soils", response_model=list[Soil])
def list_soils(conn: DbConn) -> list[dict[str, Any]]:
    return repository.list_soils(conn)


@router.get("/soils/{soil_id}", response_model=Soil)
def get_soil(soil_id: str, conn: DbConn) -> dict[str, Any]:
    return require(repository.get_soil(conn, soil_id), f"Soil {soil_id} not found")


@router.get("/emitters", response_model=list[Emitter])
def list_emitters(conn: DbConn) -> list[dict[str, Any]]:
    return repository.list_emitters(conn)


@router.get("/emitters/{emitter_id}", response_model=Emitter)
def get_emitter(emitter_id: str, conn: DbConn) -> dict[str, Any]:
    return require(repository.get_emitter(conn, emitter_id), f"Emitter {emitter_id} not found")
