# 1. Kedro for the data pipeline

Status: accepted (2026-10-07)

## Context

The pipeline reads four sources, joins and analyses them, and loads several
outputs. It must be reproducible, easy to rerun in parts, and readable by
engineers who did not write it.

## Decision

Use Kedro: pure-function nodes, a YAML data catalog for every input and
output, parameters in `conf/`, and three named pipelines (`ingest`,
`analysis`, `publish`).

## Consequences

- Nodes are plain functions on GeoDataFrames, so they are unit-tested without
  any files or database (`tests/pipelines/test_nodes.py`).
- Where data lives is configuration, not code: intermediate results are
  GeoParquet, final ones PostGIS. Switching an output means editing one
  catalog entry.
- Two custom datasets were needed, because kedro-datasets has no PostGIS
  table dataset and its GeoPandas dataset can't write Shapefiles (it writes
  through a single file handle).
- Hooks give per-node observability without touching node code.
