from kedro.pipeline import Pipeline, node, pipeline

from .nodes import fetch_boundary, load_ofcom_coverage, load_premises, load_roads, validate_premises


def create_pipeline(**kwargs) -> Pipeline:
    return pipeline(
        [
            node(fetch_boundary, ["params:area", "params:boundary_api"], "boundary", name="fetch_boundary"),
            node(load_premises, ["params:census", "params:area"], "premises_raw", name="load_premises"),
            node(validate_premises, ["premises_raw", "boundary"], "premises_valid", name="validate_premises"),
            node(
                load_ofcom_coverage,
                ["params:ofcom", "premises_valid"],
                "ofcom_coverage",
                name="load_ofcom_coverage",
            ),
            node(load_roads, ["params:roads", "boundary"], "road_links", name="load_roads"),
        ]
    )
