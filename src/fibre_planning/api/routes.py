"""Version 1 of the API. New fields may be added; anything breaking goes to /v2.

Geometries are returned as GeoJSON in WGS84 (EPSG:4326), as the GeoJSON spec
requires; bounding boxes are taken in WGS84 too. PostGIS does the spatial
filtering (using the GiST indexes) and the GeoJSON encoding.
"""

import json
import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import text
from sqlalchemy.engine import Connection

from .db import get_connection
from .schemas import AreaSummary, Feature, FeatureCollection, PostcodeCoverage

router = APIRouter(prefix="/v1", tags=["v1"])

Conn = Annotated[Connection, Depends(get_connection)]
LadCode = Annotated[str, Path(pattern=r"^[EWS]\d{8}$", examples=["E07000041"])]

MAX_BBOX_DEGREES = 0.05  # about 5 x 3.5 km in GB: keeps premises responses small
POSTCODE = re.compile(r"^([A-Z]{1,2}\d[A-Z\d]?) ?(\d[A-Z]{2})$")


def _features(rows, id_column: str) -> FeatureCollection:
    features = [
        Feature(
            id=row[id_column],
            geometry=json.loads(row["geojson"]),
            properties={k: v for k, v in row.items() if k not in ("geojson", id_column)},
        )
        for row in rows
    ]
    return FeatureCollection(features=features, count=len(features))


@router.get("/areas/{lad_code}/summary", response_model=AreaSummary)
def area_summary(lad_code: LadCode, conn: Conn) -> AreaSummary:
    """Headline figures from the latest pipeline run for the area."""
    row = (
        conn.execute(
            text("""
                SELECT r.run_at, r.summary
                FROM fibre.pipeline_run r
                WHERE r.lad_code = :lad
                ORDER BY r.run_at DESC
                LIMIT 1
            """),
            {"lad": lad_code},
        )
        .mappings()
        .first()
    )
    if row is None:
        raise HTTPException(404, f"No pipeline run for {lad_code}")
    return AreaSummary(run_at=row["run_at"], **row["summary"])


@router.get("/road-links", response_model=FeatureCollection)
def priority_road_links(
    conn: Conn,
    limit: Annotated[int, Query(ge=1, le=1000)] = 50,
    min_people: Annotated[float, Query(ge=0)] = 0,
) -> FeatureCollection:
    """Road links in build-priority order (most people without gigabit per km first)."""
    rows = (
        conn.execute(
            text("""
                SELECT road_link_id, priority_rank, road_name, road_function,
                       round(length_m::numeric, 1)::float AS length_m, premises,
                       round(people_no_gigabit::numeric, 1)::float AS people_no_gigabit,
                       round(people_per_km::numeric, 1)::float AS people_per_km,
                       ST_AsGeoJSON(ST_Transform(geom, 4326), 6) AS geojson
                FROM fibre.road_link_priority
                WHERE priority_rank IS NOT NULL AND people_no_gigabit >= :min_people
                ORDER BY priority_rank
                LIMIT :limit
            """),
            {"limit": limit, "min_people": min_people},
        )
        .mappings()
        .all()
    )
    return _features(rows, "road_link_id")


@router.get("/premises", response_model=FeatureCollection)
def premises_in_bbox(
    conn: Conn,
    bbox: Annotated[
        str,
        Query(
            description="min_lon,min_lat,max_lon,max_lat (WGS84)",
            examples=["-3.535,50.720,-3.525,50.727"],
        ),
    ],
    limit: Annotated[int, Query(ge=1, le=5000)] = 1000,
) -> FeatureCollection:
    """Premises in a small bounding box, with population and gigabit coverage."""
    try:
        min_lon, min_lat, max_lon, max_lat = (float(v) for v in bbox.split(","))
    except ValueError:
        raise HTTPException(422, "bbox must be four numbers: min_lon,min_lat,max_lon,max_lat") from None
    if not (min_lon < max_lon and min_lat < max_lat):
        raise HTTPException(422, "bbox minimums must be below maximums")
    if max_lon - min_lon > MAX_BBOX_DEGREES or max_lat - min_lat > MAX_BBOX_DEGREES:
        raise HTTPException(422, f"bbox may span at most {MAX_BBOX_DEGREES} degrees each way")
    rows = (
        conn.execute(
            text("""
                SELECT uprn, postcode, population, gigabit_pct,
                       round(people_no_gigabit::numeric, 2)::float AS people_no_gigabit,
                       road_link_id, round(drop_m::numeric, 1)::float AS drop_m,
                       ST_AsGeoJSON(ST_Transform(geom, 4326), 6) AS geojson
                FROM fibre.premises
                -- Transform the box (not every row) so the GiST index on geom is used
                WHERE geom && ST_Transform(ST_MakeEnvelope(:x0, :y0, :x1, :y1, 4326), 27700)
                ORDER BY uprn
                LIMIT :limit
            """),
            {"x0": min_lon, "y0": min_lat, "x1": max_lon, "y1": max_lat, "limit": limit},
        )
        .mappings()
        .all()
    )
    return _features(rows, "uprn")


@router.get("/postcodes/{postcode}", response_model=PostcodeCoverage)
def postcode_coverage(postcode: str, conn: Conn) -> PostcodeCoverage:
    """Coverage, premises and people for one postcode (any spacing or case)."""
    match = POSTCODE.match(postcode.upper().strip())
    if not match:
        raise HTTPException(422, "Not a valid UK postcode")
    normalised = f"{match.group(1)} {match.group(2)}"
    row = (
        conn.execute(
            text("""
                SELECT postcode, premises, population, gigabit_pct, people_no_gigabit,
                       ST_X(ST_Transform(geom, 4326)) AS lon, ST_Y(ST_Transform(geom, 4326)) AS lat
                FROM fibre.postcode_coverage
                WHERE postcode = :postcode
            """),
            {"postcode": normalised},
        )
        .mappings()
        .first()
    )
    if row is None:
        raise HTTPException(404, f"Postcode {normalised} not in the planning area")
    return PostcodeCoverage(**row)
