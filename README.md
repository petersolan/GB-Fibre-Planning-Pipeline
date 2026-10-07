# Fibre planning pipeline: who lacks gigabit broadband, and which roads reach them

A geospatial data platform that turns open data into a fibre build plan for a
local authority. It combines **population per address** (from the companion
project [GB-Census-Population-Map](https://github.com/petersolan/GB-Census-Population-Map)),
**Ofcom Connected Nations** broadband coverage by postcode and the **OS Open
Roads** network, ranks road links by people without gigabit service per km of
road, and serves the results through PostGIS, a REST API, GeoServer and QGIS.

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
| Best 20 road links | 1.9 km of road reaching ≈ 4,200 people |
| Full pipeline run | ≈ 15 s |

The top-ranked links are short access roads into dense blocks of flats and
student accommodation: the most people connected per metre of cable.

## How it works

```
ingest  ──►  analysis  ──►  publish  ──►  PostGIS  ──►  FastAPI ──► QGIS plugin
(Kedro)      (Kedro)        (Kedro)       (Alembic)  ├─► GeoServer (WMS/WFS)
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
3. **publish**: loads PostGIS tables whose schema is owned by Alembic
   ([ADR 2](docs/adr/0002-alembic-owns-the-schema.md)), exports a Shapefile
   and a GeoPackage, and records each run with per-node timings.
4. **serve**: a read-only FastAPI service, GeoServer configured through its
   REST API, a QGIS project and a QGIS plugin.

More in [docs/architecture.md](docs/architecture.md), with a diagram.

## Technology map

| Area | Where |
|---|---|
| Python 3.11, Conda | `environment.yml` (conda-forge), env-pinned PROJ/GDAL paths |
| Data pipeline (Kedro: nodes, datasets, orchestration, reproducibility) | `src/fibre_planning/pipelines/`, `conf/base/catalog.yml`, custom datasets in `src/fibre_planning/datasets/` |
| GeoPandas, GDAL, Shapefiles | `/vsizip/` Shapefile reads, Shapefile + GeoPackage exports (10-character field names handled) |
| PostgreSQL / PostGIS, efficient SQL, indexing | GiST indexes, check constraints, bbox queries that keep the index ([0.74 ms vs 364 ms](docs/performance.md)) |
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
  pipelines/{ingest,analysis,publish}/   Kedro nodes and pipelines
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
