from kedro.pipeline import Pipeline, node, pipeline

from .nodes import record_run, to_db_premises, to_db_road_links, to_shapefile


def _identity(data):
    return data


def create_pipeline(**kwargs) -> Pipeline:
    return pipeline(
        [
            node(_identity, "boundary", "db_area_boundary", name="load_db_boundary"),
            node(to_db_premises, "premises", "db_premises", name="load_db_premises"),
            node(_identity, "postcode_coverage", "db_postcode_coverage", name="load_db_postcodes"),
            node(to_db_road_links, "road_link_priority", "db_road_link_priority", name="load_db_road_links"),
            node(to_shapefile, "road_link_priority", "road_priority_shp", name="export_shapefile"),
            node(_identity, "road_link_priority", "road_priority_gpkg", name="export_geopackage"),
            node(
                record_run,
                [
                    "area_summary",
                    "db_area_boundary",
                    "db_premises",
                    "db_postcode_coverage",
                    "db_road_link_priority",
                ],
                "run_summary",
                name="record_run",
            ),
        ]
    )
