"""Analysis: who lacks gigabit broadband, and which roads would reach them.

Ofcom publishes coverage as a share of premises per postcode, not per
address. So each address gets that postcode's chance of having no gigabit
service, and counts below are expected values (sums of those chances).

Cable routes are approximated by OS Open Roads: each address is linked to its
nearest road link (the "drop" distance), and road links are ranked by people
without gigabit per km of road, a simple cost-effectiveness measure for where
to build next.
"""

from __future__ import annotations

import logging
from typing import Any

import geopandas as gpd
import pandas as pd

log = logging.getLogger(__name__)


def attach_coverage(premises: gpd.GeoDataFrame, coverage: pd.DataFrame) -> gpd.GeoDataFrame:
    """Postcode coverage on every address, plus expected people without gigabit."""
    out = premises.merge(coverage[["postcode", "gigabit_pct"]], on="postcode", how="left")
    out["p_no_gigabit"] = 1 - out["gigabit_pct"] / 100
    out["people_no_gigabit"] = out["population"] * out["p_no_gigabit"]
    missing = out["gigabit_pct"].isna()
    log.info(
        "Coverage matched for %.1f%% of premises; %s premises (%.1f%% of people) have no Ofcom postcode",
        100 * (1 - missing.mean()),
        f"{missing.sum():,}",
        100 * out.loc[missing, "population"].sum() / max(out["population"].sum(), 1),
    )
    return gpd.GeoDataFrame(out, geometry="geometry", crs=premises.crs)


def snap_to_roads(
    premises: gpd.GeoDataFrame, roads: gpd.GeoDataFrame, analysis: dict[str, Any]
) -> gpd.GeoDataFrame:
    """Nearest road link for each address and the drop distance to it."""
    joined = gpd.sjoin_nearest(
        premises,
        roads[["road_link_id", "geometry"]],
        how="left",
        max_distance=analysis["max_drop_m"],
        distance_col="drop_m",
    )
    # Ties (equidistant links) give duplicate rows: keep one per address
    joined = joined[~joined.index.duplicated()].drop(columns="index_right")
    unreached = joined["road_link_id"].isna()
    log.info(
        "Median drop %.0f m; %s premises are more than %s m from a road",
        joined["drop_m"].median(),
        f"{unreached.sum():,}",
        analysis["max_drop_m"],
    )
    return joined


def rank_road_links(
    premises: gpd.GeoDataFrame, roads: gpd.GeoDataFrame, analysis: dict[str, Any]
) -> gpd.GeoDataFrame:
    """Premises and people without gigabit per road link, ranked by people per km."""
    per_link = premises.groupby("road_link_id").agg(
        premises=("uprn", "size"),
        premises_no_gigabit=("p_no_gigabit", "sum"),
        people_no_gigabit=("people_no_gigabit", "sum"),
    )
    links = roads.merge(per_link, left_on="road_link_id", right_index=True, how="left")
    links[["premises", "premises_no_gigabit", "people_no_gigabit"]] = links[
        ["premises", "premises_no_gigabit", "people_no_gigabit"]
    ].fillna(0)
    links["premises"] = links["premises"].astype("int32")
    links["length_m"] = links.length
    links["people_per_km"] = links["people_no_gigabit"] / (links["length_m"].clip(lower=1) / 1000)
    worth = links["people_no_gigabit"] >= analysis["min_people_to_rank"]
    links["priority_rank"] = (
        links["people_per_km"].where(worth).rank(ascending=False, method="first").astype("Int32")
    )
    log.info(
        "%s of %s road links serve premises without gigabit (>= %s people)",
        f"{worth.sum():,}",
        f"{len(links):,}",
        analysis["min_people_to_rank"],
    )
    return links


def summarise_postcodes(premises: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """One point per postcode (mean address position) with premises, people and coverage."""
    grouped = premises.assign(x=premises.geometry.x, y=premises.geometry.y).groupby("postcode")
    summary = grouped.agg(
        premises=("uprn", "size"),
        population=("population", "sum"),
        gigabit_pct=("gigabit_pct", "first"),
        people_no_gigabit=("people_no_gigabit", "sum"),
        x=("x", "mean"),
        y=("y", "mean"),
    ).reset_index()
    return gpd.GeoDataFrame(
        summary.drop(columns=["x", "y"]),
        geometry=gpd.points_from_xy(summary["x"], summary["y"]),
        crs=premises.crs,
    )


def summarise_area(
    boundary: gpd.GeoDataFrame, premises: gpd.GeoDataFrame, links: gpd.GeoDataFrame
) -> dict[str, Any]:
    """Headline figures for the area (saved as JSON and to the run log)."""
    ranked = links.dropna(subset=["priority_rank"]).sort_values("priority_rank")
    top = ranked.head(20)
    return {
        "lad_code": boundary.at[0, "lad_code"],
        "name": boundary.at[0, "name"],
        "premises": int(len(premises)),
        "population": int(premises["population"].sum()),
        "premises_no_gigabit": round(float(premises["p_no_gigabit"].sum()), 1),
        "people_no_gigabit": round(float(premises["people_no_gigabit"].sum()), 1),
        "gigabit_coverage_pct": round(100 * (1 - premises["p_no_gigabit"].mean()), 2),
        "road_links": int(len(links)),
        "road_links_to_build": int(len(ranked)),
        "top20_links_km": round(float(top["length_m"].sum() / 1000), 2),
        "top20_links_people": round(float(top["people_no_gigabit"].sum()), 1),
    }
