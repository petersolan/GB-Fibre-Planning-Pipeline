"""Publish: shape the analysis outputs for PostGIS, Shapefile and the run log."""

from __future__ import annotations

import logging
from typing import Any

import geopandas as gpd
from sqlalchemy import create_engine, insert

from fibre_planning.db.config import get_settings
from fibre_planning.db.models import PipelineRun

log = logging.getLogger(__name__)

PREMISES_COLUMNS = [
    "uprn",
    "postcode",
    "population",
    "gigabit_pct",
    "p_no_gigabit",
    "people_no_gigabit",
    "road_link_id",
    "drop_m",
    "geometry",
]
ROAD_COLUMNS = [
    "road_link_id",
    "road_function",
    "road_name",
    "length_m",
    "premises",
    "premises_no_gigabit",
    "people_no_gigabit",
    "people_per_km",
    "priority_rank",
    "geometry",
]

# Shapefile field names are limited to 10 characters
SHAPEFILE_NAMES = {
    "road_link_id": "link_id",
    "road_function": "function",
    "road_name": "name",
    "length_m": "length_m",
    "premises": "premises",
    "premises_no_gigabit": "prem_nogig",
    "people_no_gigabit": "ppl_nogig",
    "people_per_km": "ppl_per_km",
    "priority_rank": "priority",
}


def to_db_premises(premises: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    return premises[PREMISES_COLUMNS]


def to_db_road_links(links: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    return links[ROAD_COLUMNS]


def to_shapefile(links: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Road links that serve people without gigabit, with Shapefile-safe field names."""
    ranked = links.dropna(subset=["priority_rank"]).sort_values("priority_rank")
    out = ranked[ROAD_COLUMNS].rename(columns=SHAPEFILE_NAMES)
    out["priority"] = out["priority"].astype("int32")
    return out


def record_run(summary: dict[str, Any], routing: dict[str, Any], *_published: Any) -> dict[str, Any]:
    """Write the run summary (with the routing figures) to fibre.pipeline_run.

    The extra arguments are the loaded tables: they only make Kedro run this
    node last.
    """
    summary = {**summary, "routing": routing}
    engine = create_engine(get_settings().owner_url)
    with engine.begin() as conn:
        conn.execute(insert(PipelineRun).values(lad_code=summary["lad_code"], summary=summary))
    log.info("Run recorded: %s", summary)
    return summary
