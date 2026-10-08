"""Response models: the API's public contract (shown in the OpenAPI docs)."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class Health(BaseModel):
    status: Literal["ok"]


class Ready(BaseModel):
    status: Literal["ready"]
    database: str
    last_run_at: datetime | None


class Area(BaseModel):
    lad_code: str
    name: str
    run_at: datetime | None = Field(description="Latest pipeline run for the area")
    premises: int | None
    gigabit_coverage_pct: float | None
    people_no_gigabit: float | None
    bbox: list[float] = Field(description="min_lon, min_lat, max_lon, max_lat (WGS84)")


class AreaSummary(BaseModel):
    lad_code: str
    name: str
    run_at: datetime
    premises: int
    population: int
    gigabit_coverage_pct: float = Field(description="Share of premises with gigabit service")
    premises_no_gigabit: float = Field(description="Expected premises without gigabit")
    people_no_gigabit: float = Field(description="Expected residents without gigabit")
    road_links_to_build: int


class PostcodeCoverage(BaseModel):
    postcode: str
    premises: int
    population: int
    gigabit_pct: float | None
    people_no_gigabit: float | None
    lon: float
    lat: float


class Feature(BaseModel):
    type: Literal["Feature"] = "Feature"
    id: str | int
    geometry: dict[str, Any]
    properties: dict[str, Any]


class FeatureCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[Feature]
    count: int = Field(description="Number of features returned")
