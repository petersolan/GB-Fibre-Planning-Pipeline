"""Routing: how much new cable connects each gap street to the existing network.

There is no open data on exchanges or cabinets, so new cable is assumed to
start from the existing gigabit network: road links whose premises all have
gigabit service. A virtual super-source (vertex 0) is joined to every one of
their junctions at zero cost, so a single pgRouting Dijkstra run from it gives
each gap street's cheapest route from the nearest point of that network.

Costs are road length weighted by road type (digging under an A road costs
more than under a cul-de-sac). The union of the chosen routes approximates the
new cable network: a shortest-path tree, in which shared routes count once.
Gap streets are then ranked by people without gigabit per km of total build
(connection plus the street itself).
"""

from __future__ import annotations

import logging
from typing import Any

import geopandas as gpd
import pandas as pd
from sqlalchemy import create_engine, text

from fibre_planning.db.config import get_settings

log = logging.getLogger(__name__)

SUPER_SOURCE = 0  # virtual vertex; real vertex ids start at 1
# Expected premises without gigabit below this count as none (float sums)
NO_GAP_TOLERANCE = 1e-9


def build_road_network(links: gpd.GeoDataFrame, routing: dict[str, Any]) -> gpd.GeoDataFrame:
    """Road links as a routable graph: integer vertices, weighted cost, network flags."""
    # OS junction TOIDs -> integer vertex ids from 1 (0 is the super-source)
    vertex_ids, _ = pd.factorize(pd.concat([links["start_node"], links["end_node"]]))
    n = len(links)
    multipliers = links["road_function"].map(routing["cost_multiplier"]).fillna(routing["default_multiplier"])
    length = links.geometry.length
    network = gpd.GeoDataFrame(
        {
            "edge_id": range(1, n + 1),
            "road_link_id": links["road_link_id"].to_numpy(),
            "road_function": links["road_function"].to_numpy(),
            "source": vertex_ids[:n] + 1,
            "target": vertex_ids[n:] + 1,
            "length_m": length.to_numpy(),
            "cost": (length * multipliers).to_numpy(),
            # Existing network: the link serves premises and none of them lacks gigabit
            "has_gigabit": (
                (links["premises"] >= routing["min_premises_for_existing"])
                & (links["premises_no_gigabit"] < NO_GAP_TOLERANCE)
            ).to_numpy(),
            "is_gap": links["priority_rank"].notna().to_numpy(),
            "people_no_gigabit": links["people_no_gigabit"].to_numpy(),
        },
        geometry=links.geometry.to_numpy(),
        crs=links.crs,
    )
    log.info(
        "Road graph: %s edges, %s vertices; %s links already have gigabit, %s are gaps",
        f"{n:,}",
        f"{vertex_ids.max() + 1:,}",
        f"{network['has_gigabit'].sum():,}",
        f"{network['is_gap'].sum():,}",
    )
    return network


ROUTING_SQL = [
    # Start points: every junction of a link that already has gigabit
    """CREATE TEMP TABLE sources ON COMMIT DROP AS
       SELECT DISTINCT v AS vid FROM fibre.road_network, unnest(ARRAY[source, target]) AS v
       WHERE has_gigabit""",
    # Destinations: both junctions of every gap street
    """CREATE TEMP TABLE gap_vertices ON COMMIT DROP AS
       SELECT DISTINCT v AS vid FROM fibre.road_network, unnest(ARRAY[source, target]) AS v
       WHERE is_gap""",
    # One Dijkstra run from the super-source, which reaches every start point at zero cost
    f"""CREATE TEMP TABLE paths ON COMMIT DROP AS
       SELECT * FROM pgr_dijkstra(
           'SELECT edge_id AS id, source, target, cost, cost AS reverse_cost FROM fibre.road_network
            UNION ALL
            SELECT -vid AS id, {SUPER_SOURCE} AS source, vid AS target, 0 AS cost, 0 AS reverse_cost
            FROM sources',
           {SUPER_SOURCE}, ARRAY(SELECT vid FROM gap_vertices), directed => false)""",
    # Each gap street connects at its cheaper junction; the route excludes the street itself
    """CREATE TEMP TABLE gap_choice ON COMMIT DROP AS
       SELECT DISTINCT ON (g.edge_id)
              g.edge_id, g.road_link_id, g.length_m AS street_m, g.people_no_gigabit, p.end_vid AS vid,
              p.route_cost
       FROM fibre.road_network g
       JOIN (SELECT end_vid, max(agg_cost) AS route_cost FROM paths GROUP BY end_vid) p
         ON p.end_vid IN (g.source, g.target)
       WHERE g.is_gap
       ORDER BY g.edge_id, p.route_cost""",
    """CREATE TEMP TABLE gap_route_edges ON COMMIT DROP AS
       SELECT c.edge_id AS gap_edge, p.edge AS route_edge
       FROM gap_choice c JOIN paths p ON p.end_vid = c.vid
       WHERE p.edge > 0 AND p.edge <> c.edge_id""",
]

GAP_CONNECTION_SQL = """
    WITH lengths AS (
        SELECT c.edge_id, coalesce(sum(n.length_m), 0) AS connect_m
        FROM gap_choice c
        LEFT JOIN gap_route_edges r ON r.gap_edge = c.edge_id
        LEFT JOIN fibre.road_network n ON n.edge_id = r.route_edge
        GROUP BY c.edge_id
    ), shapes AS (
        -- The street itself plus its route edges, as (gap, edge) pairs joined on the
        -- primary key (an OR/IN join condition here took a minute: no index use)
        SELECT u.gap_edge AS edge_id, ST_Multi(ST_Collect(n.geom)) AS geom
        FROM (
            SELECT gap_edge, route_edge AS edge FROM gap_route_edges
            UNION ALL
            SELECT edge_id, edge_id FROM gap_choice
        ) u
        JOIN fibre.road_network n ON n.edge_id = u.edge
        GROUP BY u.gap_edge
    )
    SELECT c.road_link_id, rp.road_name, c.people_no_gigabit, c.street_m, l.connect_m,
           c.street_m + l.connect_m AS total_m,
           c.people_no_gigabit / (greatest(c.street_m + l.connect_m, 1) / 1000) AS people_per_km_total,
           row_number() OVER (
               ORDER BY c.people_no_gigabit / greatest(c.street_m + l.connect_m, 1) DESC, c.road_link_id
           )::int AS build_rank,
           s.geom
    FROM gap_choice c
    JOIN lengths l USING (edge_id)
    JOIN shapes s USING (edge_id)
    LEFT JOIN fibre.road_link_priority rp ON rp.road_link_id = c.road_link_id
"""

BUILD_ROUTE_SQL = """
    WITH used AS (
        SELECT route_edge AS edge_id, gap_edge FROM gap_route_edges
        UNION
        SELECT edge_id, edge_id FROM gap_choice
    )
    SELECT n.road_link_id,
           CASE WHEN n.is_gap THEN 'gap' ELSE 'connection' END AS role,
           n.length_m,
           count(DISTINCT u.gap_edge)::int AS gap_links_served,
           sum(g.people_no_gigabit) AS people_served,
           n.geom
    FROM used u
    JOIN fibre.road_network n ON n.edge_id = u.edge_id
    JOIN fibre.road_network g ON g.edge_id = u.gap_edge
    GROUP BY n.edge_id
"""


def route_gaps(
    network: gpd.GeoDataFrame, _ranked_links: gpd.GeoDataFrame, routing: dict[str, Any]
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame, dict[str, Any]]:
    """Run the routing in PostGIS on fibre.road_network.

    Both inputs are the loaded database tables: taking them makes Kedro run this
    after the graph and the ranked links (used for street names) are saved.
    """
    engine = create_engine(get_settings().owner_url)
    with engine.begin() as conn:
        for sql in ROUTING_SQL:
            conn.execute(text(sql))
        gaps = gpd.read_postgis(text(GAP_CONNECTION_SQL), conn, geom_col="geom")
        build = gpd.read_postgis(text(BUILD_ROUTE_SQL), conn, geom_col="geom")
    engine.dispose()

    gap_total = int(network["is_gap"].sum())
    connection = build[build["role"] == "connection"]
    summary = {
        "gap_links": gap_total,
        "gap_links_reachable": len(gaps),
        "gap_links_touching_network": int((gaps["connect_m"] == 0).sum()),
        "build_network_km": round(float(build["length_m"].sum()) / 1000, 2),
        "connection_km": round(float(connection["length_m"].sum()) / 1000, 2),
        "gap_street_km": round(float(gaps["street_m"].sum()) / 1000, 2),
        "median_connect_m": round(float(gaps["connect_m"].median()), 1),
        "people_reached": round(float(gaps["people_no_gigabit"].sum()), 1),
    }
    log.info("Routing: %s", summary)
    return gaps, build, summary
