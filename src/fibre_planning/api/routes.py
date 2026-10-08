"""Version 1 of the API. New fields may be added; anything breaking goes to /v2.

Geometries are returned as GeoJSON in WGS84 (EPSG:4326), as the GeoJSON spec
requires; bounding boxes are taken in WGS84 too. PostGIS does the spatial
filtering (using the GiST indexes) and the GeoJSON encoding.

The database holds several planning areas. Every list takes an optional
``area`` (ONS district code); without it, results cover all areas, ordered by
the same measure each area's ranks use, and each feature says its
``lad_code``. Neighbouring areas share road links at their edges, so a road
link can appear once per area.
"""

import json
import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import text
from sqlalchemy.engine import Connection

from .db import get_connection
from .schemas import Area, AreaSummary, Feature, FeatureCollection, PostcodeCoverage

router = APIRouter(prefix="/v1", tags=["v1"])

Conn = Annotated[Connection, Depends(get_connection)]
LAD_CODE = r"^[EWS]\d{8}$"
LadCode = Annotated[str, Path(pattern=LAD_CODE, examples=["E07000041"])]
AreaFilter = Annotated[
    str | None,
    Query(pattern=LAD_CODE, description="ONS district code (see /v1/areas); all areas if omitted"),
]
# One area, or all when :area is NULL (cast so Postgres knows the parameter's type)
AREA_SQL = "(CAST(:area AS varchar) IS NULL OR lad_code = :area)"

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


@router.get("/areas", response_model=list[Area])
def areas(conn: Conn) -> list[Area]:
    """Planning areas in the database, with their latest run's headline figures."""
    rows = (
        conn.execute(
            text("""
                SELECT b.lad_code, b.name, r.run_at,
                       (r.summary->>'premises')::int AS premises,
                       (r.summary->>'gigabit_coverage_pct')::float AS gigabit_coverage_pct,
                       (r.summary->>'people_no_gigabit')::float AS people_no_gigabit,
                       ST_XMin(e.box) AS min_lon, ST_YMin(e.box) AS min_lat,
                       ST_XMax(e.box) AS max_lon, ST_YMax(e.box) AS max_lat
                FROM fibre.area_boundary b
                CROSS JOIN LATERAL (SELECT ST_Transform(b.geom, 4326)::box2d AS box) e
                LEFT JOIN LATERAL (
                    SELECT run_at, summary FROM fibre.pipeline_run
                    WHERE lad_code = b.lad_code ORDER BY run_at DESC LIMIT 1
                ) r ON true
                ORDER BY b.name
            """)
        )
        .mappings()
        .all()
    )
    return [
        Area(
            **{k: v for k, v in row.items() if not k.startswith(("min_", "max_"))},
            bbox=[row["min_lon"], row["min_lat"], row["max_lon"], row["max_lat"]],
        )
        for row in rows
    ]


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
    area: AreaFilter = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 50,
    min_people: Annotated[float, Query(ge=0)] = 0,
) -> FeatureCollection:
    """Road links in build-priority order (most people without gigabit per km first).

    ``priority_rank`` is the link's rank within its own area.
    """
    rows = (
        conn.execute(
            text(f"""
                SELECT road_link_id, lad_code, priority_rank, road_name, road_function,
                       round(length_m::numeric, 1)::float AS length_m, premises,
                       round(people_no_gigabit::numeric, 1)::float AS people_no_gigabit,
                       round(people_per_km::numeric, 1)::float AS people_per_km,
                       ST_AsGeoJSON(ST_Transform(geom, 4326), 6) AS geojson
                FROM fibre.road_link_priority
                WHERE priority_rank IS NOT NULL AND people_no_gigabit >= :min_people AND {AREA_SQL}
                -- The measure priority_rank ranks by, so the order holds across areas too
                ORDER BY people_per_km DESC, priority_rank, lad_code
                LIMIT :limit
            """),
            {"limit": limit, "min_people": min_people, "area": area},
        )
        .mappings()
        .all()
    )
    return _features(rows, "road_link_id")


@router.get("/build-plan", response_model=FeatureCollection)
def build_plan(
    conn: Conn,
    area: AreaFilter = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 50,
) -> FeatureCollection:
    """Gap streets in build order, counting the cable needed to reach them.

    Each feature is the street plus its route from the existing gigabit network
    along the road network (pgRouting); ``connect_m`` is that route's length.
    ``est_cost_gbp`` is an indicative civil-works cost (road-type-weighted length
    x a per-metre rate), excluding equipment, drops and existing ducts.
    ``build_rank`` is the street's rank within its own area.
    """
    rows = (
        conn.execute(
            text(f"""
                SELECT road_link_id, lad_code, build_rank, road_name,
                       round(people_no_gigabit::numeric, 1)::float AS people_no_gigabit,
                       round(street_m::numeric, 1)::float AS street_m,
                       round(connect_m::numeric, 1)::float AS connect_m,
                       round(total_m::numeric, 1)::float AS total_m,
                       round(people_per_km_total::numeric, 1)::float AS people_per_km_total,
                       round(premises_no_gigabit::numeric, 1)::float AS premises_no_gigabit,
                       round(est_cost_gbp::numeric, -2)::float AS est_cost_gbp,
                       round(cost_per_premises_gbp::numeric)::float AS cost_per_premises_gbp,
                       ST_AsGeoJSON(ST_Transform(geom, 4326), 6) AS geojson
                FROM fibre.gap_connection
                WHERE {AREA_SQL}
                -- The measure build_rank ranks by, so the order holds across areas too
                ORDER BY people_no_gigabit / greatest(total_m, 1) DESC, build_rank, lad_code
                LIMIT :limit
            """),
            {"limit": limit, "area": area},
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
    area: AreaFilter = None,
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
            text(f"""
                SELECT uprn, lad_code, postcode, population, gigabit_pct,
                       round(people_no_gigabit::numeric, 2)::float AS people_no_gigabit,
                       road_link_id, round(drop_m::numeric, 1)::float AS drop_m,
                       ST_AsGeoJSON(ST_Transform(geom, 4326), 6) AS geojson
                FROM fibre.premises
                -- Transform the box (not every row) so the GiST index on geom is used
                WHERE geom && ST_Transform(ST_MakeEnvelope(:x0, :y0, :x1, :y1, 4326), 27700)
                  AND {AREA_SQL}
                ORDER BY uprn
                LIMIT :limit
            """),
            {"x0": min_lon, "y0": min_lat, "x1": max_lon, "y1": max_lat, "limit": limit, "area": area},
        )
        .mappings()
        .all()
    )
    return _features(rows, "uprn")


@router.get("/postcodes/{postcode}", response_model=PostcodeCoverage)
def postcode_coverage(postcode: str, conn: Conn, area: AreaFilter = None) -> PostcodeCoverage:
    """Coverage, premises and people for one postcode (any spacing or case).

    A postcode can straddle two areas; without ``area`` its parts are added up.
    """
    match = POSTCODE.match(postcode.upper().strip())
    if not match:
        raise HTTPException(422, "Not a valid UK postcode")
    normalised = f"{match.group(1)} {match.group(2)}"
    row = (
        conn.execute(
            text(f"""
                SELECT postcode, sum(premises)::int AS premises, sum(population)::int AS population,
                       -- Ofcom's figure is per postcode, so every part has the same one
                       max(gigabit_pct) AS gigabit_pct, sum(people_no_gigabit) AS people_no_gigabit,
                       ST_X(ST_Transform(ST_Centroid(ST_Collect(geom)), 4326)) AS lon,
                       ST_Y(ST_Transform(ST_Centroid(ST_Collect(geom)), 4326)) AS lat
                FROM fibre.postcode_coverage
                WHERE postcode = :postcode AND {AREA_SQL}
                GROUP BY postcode
            """),
            {"postcode": normalised, "area": area},
        )
        .mappings()
        .first()
    )
    if row is None:
        raise HTTPException(404, f"Postcode {normalised} not in a planning area")
    return PostcodeCoverage(**row)
