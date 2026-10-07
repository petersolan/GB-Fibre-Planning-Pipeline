"""Unit tests for pipeline nodes, on small hand-made data."""

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import LineString, Point, box

from fibre_planning.pipelines.analysis.nodes import attach_coverage, rank_road_links, snap_to_roads
from fibre_planning.pipelines.ingest.nodes import osgb_squares, validate_premises
from fibre_planning.pipelines.publish.nodes import to_shapefile

CRS = "EPSG:27700"


@pytest.mark.parametrize(
    ("x", "y", "square"),
    [(290_000, 90_000, "SX"), (530_000, 180_000, "TQ"), (260_000, 665_000, "NS"), (440_000, 1_150_000, "HU")],
)
def test_osgb_squares(x, y, square):
    assert osgb_squares((x, y, x, y)) == [square]


def test_osgb_squares_spanning_two():
    assert sorted(osgb_squares((295_000, 90_000, 305_000, 90_000))) == ["SX", "SY"]


@pytest.fixture
def premises():
    return gpd.GeoDataFrame(
        {"uprn": [1, 2, 3], "postcode": ["EX1 1AA", "EX1 1AA", "EX2 2BB"], "population": [2, 4, 3]},
        geometry=[Point(0, 10), Point(100, 10), Point(0, 500)],
        crs=CRS,
    )


@pytest.fixture
def roads():
    return gpd.GeoDataFrame(
        {"road_link_id": ["A", "B"], "road_function": ["Local Road"] * 2, "road_name": ["High St", None]},
        geometry=[LineString([(0, 0), (200, 0)]), LineString([(0, 490), (1000, 490)])],
        crs=CRS,
    )


def test_attach_coverage(premises):
    coverage = pd.DataFrame({"postcode": ["EX1 1AA"], "gigabit_pct": [75.0]})
    out = attach_coverage(premises, coverage)
    assert out.loc[0, "p_no_gigabit"] == pytest.approx(0.25)
    assert out.loc[1, "people_no_gigabit"] == pytest.approx(1.0)  # 4 people x 25%
    assert pd.isna(out.loc[2, "gigabit_pct"])  # postcode without Ofcom data


def test_snap_and_rank(premises, roads):
    coverage = pd.DataFrame({"postcode": ["EX1 1AA", "EX2 2BB"], "gigabit_pct": [50.0, 0.0]})
    snapped = snap_to_roads(attach_coverage(premises, coverage), roads, {"max_drop_m": 150})
    assert snapped["road_link_id"].tolist() == ["A", "A", "B"]
    assert snapped["drop_m"].tolist() == pytest.approx([10, 10, 10])

    links = rank_road_links(snapped, roads, {"min_people_to_rank": 1}).set_index("road_link_id")
    # A: 200 m, (2 + 4) x 50% = 3 people -> 15 per km; B: 1000 m, 3 people -> 3 per km
    assert links.loc["A", "people_per_km"] == pytest.approx(15)
    assert links.loc["A", "priority_rank"] == 1
    assert links.loc["B", "priority_rank"] == 2


def test_validate_premises_rejects_duplicates(premises):
    boundary = gpd.GeoDataFrame({"lad_code": ["X"]}, geometry=[box(-10, -10, 200, 600)], crs=CRS)
    with pytest.raises(ValueError, match="Duplicate UPRNs"):
        validate_premises(pd.concat([premises, premises]), boundary)


def test_shapefile_field_names_fit(premises, roads):
    coverage = pd.DataFrame({"postcode": ["EX1 1AA", "EX2 2BB"], "gigabit_pct": [50.0, 0.0]})
    snapped = snap_to_roads(attach_coverage(premises, coverage), roads, {"max_drop_m": 150})
    out = to_shapefile(rank_road_links(snapped, roads, {"min_people_to_rank": 1}))
    assert all(len(c) <= 10 for c in out.columns)
