# Fibre planning pipeline: who lacks gigabit broadband, and which roads reach them

A geospatial data platform that turns open data into a fibre build plan for a
local authority. It combines **population per address** (from the companion
project [GB-Census-Population-Map](https://github.com/petersolan/GB-Census-Population-Map)),
**Ofcom Connected Nations** broadband coverage by postcode and the **OS Open
Roads** network, routes new cable from the existing gigabit network to every
gap street with **pgRouting**, ranks streets by people without gigabit per km
of cable needed, and serves the results through PostGIS, a REST API,
GeoServer and QGIS.

![Exeter in QGIS: premises by gigabit coverage and road links by build priority](docs/images/qgis_exeter.png)

*Exeter in the QGIS project: premises green where their postcode has gigabit,
red where it doesn't; road links from pale to dark red by people without
gigabit per km. GeoServer serves the same layers with the same SLD styles.*

## Results: Exeter (Ofcom coverage, January 2026)

| | |
|---|---|
| Premises (addresses in buildings) | 73,646 |
| Residents | 130,371 |
| Gigabit coverage | 86.2% of premises (UK: 89%) |
| People without gigabit (expected) | ≈ 12,000 |
| Road links serving them | 722 of 6,402 |
| Proposed new cable (pgRouting) | ≈ 101 km: 89 km along gap streets + 12 km connecting them |
| Best 20 streets, including their connections | 2.9 km of cable reaching ≈ 4,300 people |
| Full pipeline run (24 nodes) | ≈ 20 s |

The top-ranked streets are short access roads into dense blocks of flats and
student accommodation: the most people connected per metre of cable.

### Routing new cable

A street's own length isn't the whole cost: cable has to reach it. With no
open data on exchanges or cabinets, new cable starts from the **existing
gigabit network** (road links whose premises all have it). A single
pgRouting Dijkstra run from a virtual super-source joined to that network
finds each gap street's cheapest route along the roads, with digging under A
and B roads weighted as dearer ([ADR 5](docs/adr/0005-routing-from-the-existing-network.md)).

- All 722 gap streets are reachable; 380 already touch the existing network.
- Counting the connection changes the plan: 6 of the top 20 streets drop
  out. Hook Drive, for example, ranks 138th on its own length but needs a
  339 m connection to reach 2 people, and falls to 663rd.

![Proposed cable network in central Exeter: gap streets red, connecting routes blue](docs/images/qgis_routes.png)

*Proposed cable network (`fibre.build_route`): gap streets in red, connecting
routes from the existing gigabit network in blue (darker where they serve
100+ people). Most connections are short hops at junctions.*

## How it works

```
ingest ──► analysis ──► routing ──► publish ──► PostGIS ──► FastAPI ──► QGIS plugin
(Kedro)    (Kedro)      (pgRouting) (Kedro)     (Alembic) ├─► GeoServer (WMS/WFS)
                                                          └─► QGIS project
```

1. **ingest**: the boundary from the ONS API; the area's addresses and
   population from GeoParquet (filtered on read); Ofcom postcode CSVs from
   their zip; OS Open Roads **Shapefiles** read straight from the 606 MB zip
   for the 100 km grid squares the area touches; validation that fails fast.
2. **analysis**: each address gets its postcode's chance of having no gigabit
   service ([ADR 4](docs/adr/0004-coverage-per-address-is-a-probability.md));
   addresses snap to their nearest road link (the cable drop, median 16 m);
   links are ranked by people without gigabit per km.
3. **routing**: road links become a graph (junctions as vertices, length ×
   road-type cost as weights) loaded into PostGIS; pgRouting finds each gap
   street's route from the existing gigabit network; the union of routes is
   the proposed build network, and streets are re-ranked by people per km of
   total cable.
4. **publish**: loads PostGIS tables whose schema is owned by Alembic
   ([ADR 2](docs/adr/0002-alembic-owns-the-schema.md)), exports a Shapefile
   and a GeoPackage, and records each run with per-node timings.
5. **serve**: a read-only FastAPI service (`/v1/build-plan` returns streets
   in build order with their routes), GeoServer configured through its
   REST API, a QGIS project and a QGIS plugin.

More in [docs/architecture.md](docs/architecture.md), with a diagram.

## Technology map

| Area | Where |
|---|---|
| Python 3.11, Conda | `environment.yml` (conda-forge), env-pinned PROJ/GDAL paths |
| Data pipeline (Kedro: nodes, datasets, orchestration, reproducibility) | `src/fibre_planning/pipelines/`, `conf/base/catalog.yml`, custom datasets in `src/fibre_planning/datasets/` |
| GeoPandas, GDAL, Shapefiles | `/vsizip/` Shapefile reads, Shapefile + GeoPackage exports (10-character field names handled) |
| PostgreSQL / PostGIS, efficient SQL, indexing | GiST indexes, check constraints, bbox queries that keep the index ([0.74 ms vs 364 ms](docs/performance.md)) |
| Network analysis (pgRouting) | `src/fibre_planning/pipelines/routing/`: graph from OS Open Roads junctions, multi-source Dijkstra via a super-source, shortest-path tree as the build network ([a join rewrite took it from 62 s to 0.01 s](docs/performance.md)) |
| SQLAlchemy + Alembic | `src/fibre_planning/db/models.py`, `migrations/`; round-trip and model-drift tests |
| Service and API design | `src/fibre_planning/api/`: versioned `/v1`, Pydantic contracts, OpenAPI at `/docs`, input limits |
| GeoServer | Docker service; `python -m fibre_planning.geoserver` publishes over REST (idempotent); SLD styles |
| QGIS and plugin development | `qgis_project/build_project.py` (PyQGIS), `qgis_plugin/` dock panel using QGIS's network stack, tested headless |
| Observability | JSON request logs with request IDs, Prometheus `/metrics`, `/health` + `/ready`; Kedro hooks writing `logs/pipeline.jsonl` and run history |
| Testing and quality | pytest (unit + integration on a seeded test database), ruff, mypy, pre-commit |
| CI/CD | `.gitlab-ci.yml` and `.github/workflows/ci.yml`: lint, migrations, tests with PostGIS, image build |
| PowerShell and batch | `scripts/run.ps1` task runner, `run.bat`, `setup_pg_service.ps1`, `package.ps1` |
| Packaging (Artifactory-style) | wheel + QGIS plugin zip, published with twine to a private index (pypiserver in Docker) |
| Security and privacy | read-only role for services, secrets only in `.env`, credential-free QGIS project, localhost-only ports ([ADR 3](docs/adr/0003-least-privilege-and-secrets.md)) |
| Documentation | [architecture](docs/architecture.md), [ADRs](docs/adr/), [runbook](docs/runbook.md), [performance notes](docs/performance.md) |

## Quick start (Windows)

```powershell
.\run.bat setup      # .env with random passwords, conda env, pg_service entry
.\run.bat all        # start containers, migrate, run pipeline, publish, test
.\run.bat status     # container health and latest runs
```

Or step by step with the `fibre` environment active:

```powershell
docker compose up -d --build         # PostGIS :5433, API :8000, GeoServer :8080
alembic upgrade head
kedro run
python -m fibre_planning.geoserver
pytest
```

- API docs: http://127.0.0.1:8000/docs
- GeoServer: http://127.0.0.1:8080/geoserver (layers in workspace `fibre`)
- QGIS: open `qgis_project/fibre_planning.qgz` (3.34+)
- QGIS plugin: `.\scripts\package.ps1 -NoPublish`, then install
  `dist\fibre_planning_qgis-0.1.0.zip` via *Plugins > Install from ZIP*

To plan another area, change `area.lad_code` in `conf/base/parameters.yml`.

## Repository layout

```
src/fibre_planning/
  pipelines/{ingest,analysis,routing,publish}/   Kedro nodes and pipelines
  datasets/          PostGIS table and GDAL vector file datasets
  db/                settings (.env) and SQLAlchemy models
  api/               FastAPI app, routes, schemas, logging and metrics
  geoserver.py       GeoServer REST publisher
  hooks.py           pipeline monitoring
migrations/          Alembic migrations
conf/                Kedro catalog, parameters, logging
geoserver/styles/    SLD styles (also used by QGIS)
qgis_project/        PyQGIS project builder and preview renderer
qgis_plugin/         QGIS plugin and its headless tests
scripts/             PowerShell: task runner, packaging, pg_service setup
tests/               unit, API and migration tests
docs/                architecture, ADRs, runbook, performance notes
```

## Data and licences

Inputs go in `data/01_raw/` (not committed). The census outputs are read from
`../Census-distribution/data/processed`.

| Data | Source | Licence |
|---|---|---|
| Fixed broadband coverage by postcode | [Ofcom Connected Nations](https://www.ofcom.org.uk/phones-and-broadband/coverage-and-speeds/connected-nations-update-spring-2026), January 2026 | OGL v3 |
| Road network | [OS Open Roads](https://www.ordnancesurvey.co.uk/products/os-open-roads) (Shapefile) | OGL v3 |
| Local authority boundary | ONS Open Geography Portal, LAD May 2025 | OGL v3 |
| Population per address | GB-Census-Population-Map (Census 2021/2022, ONSUD, OS Open Zoomstack) | OGL v3 |
| Basemap in the QGIS project | OpenStreetMap | ODbL |
