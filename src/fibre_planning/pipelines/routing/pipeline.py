from kedro.pipeline import Pipeline, node, pipeline

from .nodes import build_road_network, route_gaps


def _identity(data):
    return data


def create_pipeline(**kwargs) -> Pipeline:
    return pipeline(
        [
            node(
                build_road_network,
                ["road_link_priority", "params:routing"],
                "road_network",
                name="build_road_network",
            ),
            node(_identity, "road_network", "db_road_network", name="load_db_road_network"),
            node(
                route_gaps,
                ["db_road_network", "db_road_link_priority", "params:routing", "params:area"],
                ["gap_connection", "build_route", "routing_summary"],
                name="route_gaps",
            ),
            node(_identity, "gap_connection", "db_gap_connection", name="load_db_gap_connection"),
            node(_identity, "build_route", "db_build_route", name="load_db_build_route"),
            node(_identity, "build_route", "build_route_gpkg", name="export_build_route"),
            node(_identity, "gap_connection", "gap_connection_gpkg", name="export_gap_connection"),
        ]
    )
