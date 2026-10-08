"""Routing: graph building (unit) and the pgRouting query (integration, fibre_test)."""

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import LineString
from sqlalchemy import create_engine, text

from fibre_planning.pipelines.routing.nodes import build_road_network, route_gaps

CRS = "EPSG:27700"
ROUTING = {
    "min_premises_for_existing": 1,
    "cost_multiplier": {"A Road": 3.0, "Local Road": 1.0},
    "default_multiplier": 1.0,
}

#   (1)--100m gigabit--(2)--100m A Road (cost 300)--(3)--50m gap--(5)
#                        \                          /
#                         150m local--(4)--100m local
LINKS = [
    # id, function, start, end, coordinates, premises, premises_no_gigabit, rank, people_no_gigabit
    ("E1", "Local Road", "J1", "J2", [(0, 0), (100, 0)], 10, 0.0, None, 0.0),
    ("E2", "A Road", "J2", "J3", [(100, 0), (200, 0)], 0, 0.0, None, 0.0),
    ("E3", "Local Road", "J2", "J4", [(100, 0), (100, 150)], 0, 0.0, None, 0.0),
    ("E4", "Local Road", "J4", "J3", [(100, 150), (200, 150)], 0, 0.0, None, 0.0),
    ("E5", "Local Road", "J3", "J5", [(200, 0), (250, 0)], 4, 4.0, 1, 10.0),
]


@pytest.fixture
def links() -> gpd.GeoDataFrame:
    rows = [
        {
            "road_link_id": i,
            "road_function": f,
            "start_node": s,
            "end_node": e,
            "premises": p,
            "premises_no_gigabit": nog,
            "priority_rank": pd.NA if r is None else r,
            "people_no_gigabit": ppl,
            "geometry": LineString(c),
        }
        for i, f, s, e, c, p, nog, r, ppl in LINKS
    ]
    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs=CRS)
    gdf["priority_rank"] = gdf["priority_rank"].astype("Int32")
    return gdf


def test_build_road_network(links):
    net = build_road_network(links, ROUTING).set_index("road_link_id")
    assert net["source"].min() >= 1  # vertex 0 is reserved for the super-source
    assert net.loc["E1", "target"] == net.loc["E2", "source"]  # shared junction J2
    assert net.loc["E2", "cost"] == pytest.approx(300)  # A road: 100 m x 3
    assert net.loc["E3", "cost"] == pytest.approx(150)
    assert bool(net.loc["E1", "has_gigabit"]) and not bool(net.loc["E2", "has_gigabit"])
    assert bool(net.loc["E5", "is_gap"]) and net["is_gap"].sum() == 1


@pytest.mark.integration
def test_route_gaps_takes_the_cheaper_detour(links, test_database):
    from fibre_planning.db.config import get_settings

    network = build_road_network(links, ROUTING)
    engine = create_engine(get_settings().owner_url)
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE fibre.road_network"))
        network.rename_geometry("geom").to_postgis("road_network", conn, schema="fibre", if_exists="append")
    engine.dispose()

    gaps, build, summary = route_gaps(network, None, ROUTING)

    (gap,) = gaps.itertuples()
    # Direct A-road route costs 300; the local detour (150 + 100 m) costs 250 and wins.
    # connect_m is real length, not cost: 250 m
    assert gap.road_link_id == "E5"
    assert gap.connect_m == pytest.approx(250)
    assert gap.total_m == pytest.approx(300)
    assert gap.people_per_km_total == pytest.approx(10 / 0.3)
    roles = dict(zip(build["road_link_id"], build["role"], strict=True))
    assert roles == {"E3": "connection", "E4": "connection", "E5": "gap"}
    assert summary["connection_km"] == pytest.approx(0.25)
    assert summary["gap_links_reachable"] == 1
