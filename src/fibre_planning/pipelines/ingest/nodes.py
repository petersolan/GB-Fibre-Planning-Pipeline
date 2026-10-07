"""Ingest: raw open data -> clean GeoDataFrames for one local authority.

Each node reads only what the area needs: the boundary from the ONS API,
the area's addresses from the census GeoParquet (filtered on read), Ofcom
postcode files for the postcode areas present, and OS Open Roads Shapefiles
for the 100 km grid squares the area touches (read straight from the zip).
"""

from __future__ import annotations

import logging
import zipfile
from pathlib import Path
from typing import Any

import geopandas as gpd
import httpx
import numpy as np
import pandas as pd
import pyarrow.compute as pc
import pyarrow.dataset as ds
import pyogrio
from shapely.geometry import MultiPolygon

log = logging.getLogger(__name__)

CRS = "EPSG:27700"
# Share of premises allowed outside the boundary (50 m tolerance) before failing
MAX_OUTSIDE_SHARE = 0.01

# Ofcom column -> our name (percent of premises in the postcode)
OFCOM_COLUMNS = {
    "postcode_space": "postcode",
    "Gigabit availability (% premises)": "gigabit_pct",
    "SFBB availability (% premises)": "sfbb_pct",
    "% of premises unable to receive 10Mbit/s": "below_10mbit_pct",
}


def fetch_boundary(area: dict[str, Any], boundary_api: dict[str, Any]) -> gpd.GeoDataFrame:
    """Local authority boundary from the ONS ArcGIS feature service."""
    params = {
        "where": f"{boundary_api['code_field']}='{area['lad_code']}'",
        "outFields": f"{boundary_api['code_field']},{boundary_api['name_field']}",
        "f": "geojson",  # GeoJSON is always WGS84 lon/lat; reprojected below
    }
    transport = httpx.HTTPTransport(retries=3)
    with httpx.Client(transport=transport, timeout=60) as client:
        response = client.get(boundary_api["url"], params=params)
        response.raise_for_status()
    features = response.json().get("features", [])
    if not features:
        raise ValueError(f"No boundary found for {area['lad_code']}")
    gdf = gpd.GeoDataFrame.from_features(features, crs="EPSG:4326").to_crs(CRS)
    gdf = gdf.rename(columns={boundary_api["code_field"]: "lad_code", boundary_api["name_field"]: "name"})
    gdf["geometry"] = gdf.geometry.make_valid()
    gdf = gdf.dissolve(by=["lad_code", "name"], as_index=False)
    gdf["geometry"] = gdf.geometry.apply(_as_multipolygon)
    log.info("Boundary %s (%s): %.1f km2", gdf.at[0, "name"], area["lad_code"], gdf.area.sum() / 1e6)
    return gdf[["lad_code", "name", "geometry"]]


def _as_multipolygon(geom):
    return MultiPolygon([geom]) if geom.geom_type == "Polygon" else geom


def load_premises(census: dict[str, str], area: dict[str, Any]) -> gpd.GeoDataFrame:
    """The area's addresses (UPRNs) with modelled census population.

    Premises are UPRNs inside a building (OS Open Zoomstack, from the census
    project), the closest open stand-in for Ofcom's residential and business
    premises.
    """
    directory = Path(census["directory"])
    onsud = ds.dataset(directory / "onsud_uprn.parquet").to_table(
        filter=pc.field("lad26cd") == area["lad_code"], columns=["uprn", "pcds", "geometry"]
    )
    if onsud.num_rows == 0:
        raise ValueError(f"No UPRNs for {area['lad_code']} in {directory}")
    uprns = onsud["uprn"]
    population = (
        ds.dataset(directory / "uprn_population.parquet")
        .to_table(filter=pc.field("uprn").isin(uprns), columns=["uprn", "population"])
        .to_pandas()
    )
    weights = (
        ds.dataset(directory / "uprn_weights.parquet")
        .to_table(filter=pc.field("uprn").isin(uprns), columns=["uprn", "in_building"])
        .to_pandas()
    )

    geom = onsud["geometry"].combine_chunks()
    df = pd.DataFrame({"uprn": uprns.to_numpy(), "postcode": onsud["pcds"].to_pandas()})
    df = df.merge(population, on="uprn", how="left").merge(weights, on="uprn", how="left")
    gdf = gpd.GeoDataFrame(
        df,
        geometry=gpd.points_from_xy(geom.field("x").to_numpy(), geom.field("y").to_numpy()),
        crs=CRS,
    )
    gdf["population"] = gdf["population"].fillna(0).astype("int32")
    premises = gdf[gdf["in_building"].fillna(False).astype(bool)].drop(columns="in_building")
    log.info(
        "%s UPRNs, %s premises in buildings, %s residents",
        f"{len(gdf):,}",
        f"{len(premises):,}",
        f"{premises['population'].sum():,}",
    )
    return premises.reset_index(drop=True)


def load_ofcom_coverage(ofcom: dict[str, str], premises: gpd.GeoDataFrame) -> pd.DataFrame:
    """Ofcom Connected Nations postcode coverage for the postcode areas in use."""
    areas = sorted(premises["postcode"].dropna().str.extract(r"^([A-Z]{1,2})")[0].unique())
    frames = []
    with zipfile.ZipFile(ofcom["zip_path"]) as z:
        names = {Path(n).stem.rsplit("_", 1)[-1]: n for n in z.namelist() if ofcom["postcode_glob"] in n}
        for code in areas:
            if code not in names:
                log.warning("No Ofcom postcode file for area %s", code)
                continue
            frames.append(pd.read_csv(z.open(names[code]), usecols=list(OFCOM_COLUMNS)))
    coverage = pd.concat(frames, ignore_index=True).rename(columns=OFCOM_COLUMNS)
    coverage["postcode"] = coverage["postcode"].str.strip()
    log.info("Ofcom coverage for %s postcodes in areas %s", f"{len(coverage):,}", ", ".join(areas))
    return coverage.drop_duplicates("postcode")


def osgb_squares(bounds: tuple[float, float, float, float]) -> list[str]:
    """OS 100 km grid square letters (e.g. 'SX') covering a BNG bounding box."""
    letters = "ABCDEFGHJKLMNOPQRSTUVWXYZ"  # no I
    squares = []
    for e in range(int(bounds[0] // 100_000), int(bounds[2] // 100_000) + 1):
        for n in range(int(bounds[1] // 100_000), int(bounds[3] // 100_000) + 1):
            # 500 km square from the false origin (SV = 0, 0), then 100 km within it
            e5, n5 = e // 5 + 2, n // 5 + 1
            first = letters[(4 - n5) * 5 + e5]
            second = letters[(4 - n % 5) * 5 + e % 5]
            squares.append(first + second)
    return squares


def load_roads(roads: dict[str, Any], boundary: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """OS Open Roads links within (a buffer of) the area, read from the zipped Shapefiles."""
    area = boundary.geometry.union_all().buffer(roads["buffer_m"])
    bounds = area.bounds
    frames = []
    for square in osgb_squares(bounds):
        path = f"/vsizip/{Path(roads['zip_path']).as_posix()}/data/{square}_RoadLink.shp"
        frames.append(pyogrio.read_dataframe(path, bbox=bounds, columns=roads["columns"]))
    links = pd.concat(frames, ignore_index=True)
    links = gpd.GeoDataFrame(links, geometry="geometry", crs=CRS)
    links = links[links.intersects(area)]
    links["geometry"] = links.geometry.force_2d()
    links = links.rename(
        columns={"identifier": "road_link_id", "function": "road_function", "name1": "road_name"}
    )
    links = links.drop_duplicates("road_link_id")
    log.info("%s road links, %.0f km", f"{len(links):,}", links.length.sum() / 1000)
    return links[["road_link_id", "road_function", "road_name", "geometry"]].reset_index(drop=True)


def validate_premises(premises: gpd.GeoDataFrame, boundary: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Fail fast on data that would make the outputs wrong."""
    if premises["uprn"].duplicated().any():
        raise ValueError("Duplicate UPRNs in premises")
    if (premises["population"] < 0).any():
        raise ValueError("Negative population")
    outside = ~premises.within(boundary.geometry.union_all().buffer(50))
    if outside.mean() > MAX_OUTSIDE_SHARE:
        raise ValueError(f"{outside.mean():.1%} of premises fall outside the boundary")
    if np.isnan(premises.geometry.x).any():
        raise ValueError("Premises without coordinates")
    return premises
