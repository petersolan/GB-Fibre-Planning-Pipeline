from kedro.pipeline import Pipeline, node, pipeline

from .nodes import attach_coverage, rank_road_links, snap_to_roads, summarise_area, summarise_postcodes


def create_pipeline(**kwargs) -> Pipeline:
    return pipeline(
        [
            node(
                attach_coverage,
                ["premises_valid", "ofcom_coverage"],
                "premises_coverage",
                name="attach_coverage",
            ),
            node(
                snap_to_roads,
                ["premises_coverage", "road_links", "params:analysis"],
                "premises",
                name="snap_to_roads",
            ),
            node(
                rank_road_links,
                ["premises", "road_links", "params:analysis"],
                "road_link_priority",
                name="rank_road_links",
            ),
            node(summarise_postcodes, "premises", "postcode_coverage", name="summarise_postcodes"),
            node(
                summarise_area,
                ["boundary", "premises", "road_link_priority"],
                "area_summary",
                name="summarise_area",
            ),
        ]
    )
