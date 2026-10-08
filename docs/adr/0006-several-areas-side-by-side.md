# 6. Keep several planning areas side by side, keyed by district code

Status: accepted (2026-10-08)

## Context

The pipeline was built for one local authority: each run truncated every
table and reloaded it. Planning a second area (Mid Devon, rural, next to
Exeter) that way would replace Exeter, so the two could never be compared in
the API, GeoServer or QGIS. Neighbouring areas also overlap at their edges:
roads are read 500 m beyond the boundary, so a road link on the border is in
both areas' networks, and a postcode can straddle two districts. The routing
graph numbers its edges and junctions from 1 in every run.

## Decision

- Every table carries `lad_code`, and it leads every key: (`lad_code`,
  `road_link_id`), (`lad_code`, `edge_id`) and so on (migration 0005). A
  border link appears once per area, with that area's premises.
- A run plans one area, chosen with `kedro run --params
  area.lad_code=E07000042` (default in `conf/base/globals.yml`). The same
  value sets the parameter, a folder per area for the intermediate and output
  files, and the area the PostGIS datasets work on.
- The PostGIS dataset is one area's slice of its table: loading reads that
  area's rows and saving replaces them (DELETE + INSERT in one transaction).
  It refuses rows labelled with another area.
- Routing copies the area's graph into a temporary table with its own primary
  key, so pgRouting and the joins after it see one area and keep their index
  use.
- The API takes an optional `area` on every list and adds `/v1/areas`. Ranks
  stay per area; without `area`, results from all areas are ordered by the
  measure the ranks come from (people without gigabit per km), so "where to
  build first in the region" has an answer too. This is additive, so it stays
  in `/v1`.

## Consequences

- Re-running one area never touches another; areas can be run in any order.
- Results for an area depend only on its own data, so a border road ranked in
  both areas is two candidates, not one. Merging areas into a region-wide
  graph would need a different design: one run over the combined boundary.
- Downgrading migration 0005 keeps only the most recently run area.
- Rural Mid Devon exposed a modelling gap that Exeter hid: farms beside the M5
  snapped to it and made a 15.6 km motorway link a "gap street". Motorways are
  now excluded as drop roads (`analysis.no_drop_functions`).
