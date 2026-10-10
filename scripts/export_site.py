"""Export the build plans for the web demo (site/).

Reads data/07_model_output/<LAD>/fibre_planning.gpkg for each area and writes WGS84 GeoJSON
to site/data/:

  gap_streets.geojson  one feature per gap street (its route included) with rank, people,
                       premises and indicative cost: what a click shows
  cable.geojson        the proposed cable, one feature per road link, with `first_rank`: the
                       best rank of the gap streets it serves
  plan.json            per area and rank N: people reached and the km and cost of the cable
                       needed for the top N streets

Connecting routes are shared between gap streets, so summing per-street costs counts shared
cable more than once. Here each link is counted once, at the first rank that needs it.
"""

import json
import logging
from pathlib import Path

import geopandas as gpd
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site" / "data"
log = logging.getLogger("export_site")
AREAS = {"E07000041": "Exeter", "E07000042": "Mid Devon"}
GAP_COLUMNS = [
    "road_name",
    "build_rank",
    "people_no_gigabit",
    "premises_no_gigabit",
    "street_m",
    "connect_m",
    "est_cost_gbp",
    "cost_per_premises_gbp",
]


def first_rank(cable: gpd.GeoDataFrame, gaps: gpd.GeoDataFrame) -> np.ndarray:
    """Best (lowest) build_rank of the gap streets whose route covers each cable link."""
    probe = cable.copy()
    probe["geometry"] = cable.geometry.interpolate(0.5, normalized=True)  # link midpoint
    hits = gpd.sjoin(
        probe, gaps[["build_rank", "geometry"]].assign(geometry=gaps.geometry.buffer(0.5)), predicate="within"
    )
    best = hits.groupby(level=0)["build_rank"].min()
    missing = cable.index.difference(best.index)
    if len(missing):
        raise ValueError(f"{len(missing)} cable links are on no gap street's route")
    return best.reindex(cable.index).to_numpy()


def write(gdf: gpd.GeoDataFrame, name: str) -> None:
    path = OUT / f"{name}.geojson"
    path.unlink(missing_ok=True)
    gdf.to_crs("EPSG:4326").to_file(
        path, driver="GeoJSON", engine="pyogrio", layer_options={"COORDINATE_PRECISION": 6, "RFC7946": "YES"}
    )
    log.info(f"{len(gdf):>6,} {name:<12} {path.stat().st_size / 1e6:.1f} MB")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    OUT.mkdir(parents=True, exist_ok=True)
    all_gaps, all_cable, plan = [], [], {}
    for lad, name in AREAS.items():
        src = ROOT / "data" / "07_model_output" / lad / "fibre_planning.gpkg"
        gaps = gpd.read_file(src, layer="gap_connection")[[*GAP_COLUMNS, "geometry"]]
        cable = gpd.read_file(src, layer="build_route")[["role", "length_m", "est_cost_gbp", "geometry"]]
        cable["first_rank"] = first_rank(cable, gaps)

        # cumulative plan by rank: people from the streets, km and cost from unique links
        n = int(gaps["build_rank"].max())
        people = np.bincount(gaps["build_rank"], weights=gaps["people_no_gigabit"], minlength=n + 1)
        km = np.bincount(cable["first_rank"], weights=cable["length_m"] / 1000, minlength=n + 1)
        cost = np.bincount(cable["first_rank"], weights=cable["est_cost_gbp"], minlength=n + 1)
        plan[lad] = {
            "name": name,
            "streets": n,
            "bounds": [round(v, 4) for v in gaps.to_crs("EPSG:4326").total_bounds],
            "people": np.cumsum(people)[1:].round().astype(int).tolist(),
            "km": np.cumsum(km)[1:].round(2).tolist(),
            "cost": np.cumsum(cost)[1:].round(-3).astype(int).tolist(),
        }
        log.info(
            f"{name}: top 20 = {plan[lad]['km'][19]} km, {plan[lad]['people'][19]:,} people; "
            f"all {n} = {plan[lad]['km'][-1]:.0f} km, £{plan[lad]['cost'][-1] / 1e6:.1f} m"
        )

        for col in ["street_m", "connect_m", "est_cost_gbp", "cost_per_premises_gbp"]:
            gaps[col] = gaps[col].round()
        gaps["people_no_gigabit"] = gaps["people_no_gigabit"].round(1)
        all_gaps.append(gaps.assign(lad=lad))
        all_cable.append(cable[["role", "first_rank", "geometry"]].assign(lad=lad))

    write(gpd.pd.concat(all_gaps, ignore_index=True), "gap_streets")
    write(gpd.pd.concat(all_cable, ignore_index=True), "cable")
    (OUT / "plan.json").write_text(json.dumps(plan, separators=(",", ":")), encoding="utf-8")


if __name__ == "__main__":
    main()
