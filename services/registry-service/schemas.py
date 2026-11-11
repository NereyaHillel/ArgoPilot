from datetime import UTC, date, datetime
from typing import Annotated, Any
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator
from pydantic_core import PydanticCustomError


def _no_nul(value: str) -> str:
    # PostgreSQL text columns cannot store NUL, so every backend rejects it.
    if "\x00" in value:
        raise PydanticCustomError("nul", "must not contain NUL characters")
    return value


def _not_blank(value: str) -> str:
    if not value.strip():
        raise PydanticCustomError("blank", "must not be blank")
    return _no_nul(value)


def _not_in_future(value: date) -> date:
    # The spec does not name a timezone, so "today" is the UTC date.
    if value > datetime.now(UTC).date():
        raise PydanticCustomError("future_date", "Planting date cannot be in the future")
    return value


Name = Annotated[str, AfterValidator(_not_blank)]
RefId = Annotated[str, AfterValidator(_no_nul)]
PositiveNumber = Annotated[float, Field(gt=0, strict=True, allow_inf_nan=False)]
Latitude = Annotated[float, Field(ge=-90, le=90, strict=True, allow_inf_nan=False)]
Longitude = Annotated[float, Field(ge=-180, le=180, strict=True, allow_inf_nan=False)]
PlantingDate = Annotated[date, AfterValidator(_not_in_future)]


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _PatchRequest(_Request):
    @field_validator("*", mode="before")
    @classmethod
    def _reject_null(cls, value: Any) -> Any:
        # Every PATCH field is optional, but none may be set to null.
        if value is None:
            raise PydanticCustomError("null", "must not be null")
        return value


class FarmCreate(_Request):
    name: Name


class FarmUpdate(_PatchRequest):
    name: Name | None = None


class Farm(BaseModel):
    id: UUID
    name: str


class PlotCreate(_Request):
    farm_id: UUID
    name: Name
    area_m2: PositiveNumber
    crop_id: RefId
    planting_date: PlantingDate
    soil_id: RefId
    row_spacing_m: PositiveNumber
    emitter_spacing_m: PositiveNumber
    emitter_id: RefId
    lat: Latitude
    lon: Longitude


class PlotUpdate(_PatchRequest):
    farm_id: UUID | None = None
    name: Name | None = None
    area_m2: PositiveNumber | None = None
    crop_id: RefId | None = None
    planting_date: PlantingDate | None = None
    soil_id: RefId | None = None
    row_spacing_m: PositiveNumber | None = None
    emitter_spacing_m: PositiveNumber | None = None
    emitter_id: RefId | None = None
    lat: Latitude | None = None
    lon: Longitude | None = None


class Plot(BaseModel):
    id: UUID
    farm_id: UUID
    name: str
    area_m2: float
    crop_id: str
    planting_date: date
    soil_id: str
    row_spacing_m: float
    emitter_spacing_m: float
    emitter_id: str
    lat: float
    lon: float


class Crop(BaseModel):
    id: str
    name: str


class Soil(BaseModel):
    id: str
    name: str
    available_water_mm_per_m: int


class Emitter(BaseModel):
    id: str
    name: str
    flow_lph: float
