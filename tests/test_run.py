"""The Kedro project loads and its pipelines are registered (no data needed)."""

from pathlib import Path

from kedro.framework.project import pipelines
from kedro.framework.startup import bootstrap_project


def test_pipelines_registered():
    bootstrap_project(Path.cwd())
    assert {"ingest", "analysis", "routing", "publish", "__default__"} <= set(pipelines)
    assert len(pipelines["__default__"].nodes) == 24
