# Runbook

All commands from the repository root in PowerShell, with the `fibre` conda
environment. `.\run.bat <task>` works from cmd.exe too (use the `.\`:
this environment doesn't run programs from the current folder by name).

## Everyday tasks

| Goal | Command |
|---|---|
| First-time setup (`.env` with random passwords, conda env, pg_service) | `.\run.bat setup` |
| Start PostGIS, API, GeoServer and wait until healthy | `.\run.bat up` |
| Apply migrations | `.\run.bat migrate` |
| Run the pipeline | `.\run.bat pipeline` |
| Publish to GeoServer and rebuild the QGIS project | `.\run.bat publish` |
| Lint, type-check, test | `.\run.bat test` |
| Everything above in order | `.\run.bat all` |
| Health and latest runs | `.\run.bat status` |
| Build wheel + plugin zip, publish to the package index | `.\scripts\package.ps1` |

## Checking a run

- `.\run.bat status` lists recent runs with their duration.
- `logs/pipeline.jsonl` has one JSON line per node: duration, rows per
  output, memory. A node that suddenly takes longer or returns far fewer rows
  than usual is the first thing to look at.
- `SELECT summary FROM fibre.pipeline_run ORDER BY id DESC LIMIT 1;` holds the
  headline figures and per-node timings.
- API: `GET /ready` returns 503 if the database is down; `GET /metrics` has
  request counts and latencies per route.

## Known problems

| Symptom | Cause | Fix |
|---|---|---|
| Every database step takes ~2 minutes | `localhost` resolves to IPv6 `::1` first; Docker listens on IPv4 only | Use `POSTGRES_HOST=127.0.0.1` (the default) |
| `pyproj unable to set PROJ database path` | A system-wide `PROJ_LIB` (PostgreSQL/PostGIS installer) points at an older PROJ | The `fibre` env sets its own `PROJ_LIB`/`PROJ_DATA`/`GDAL_DATA`; run Python through the activated env or `conda run`, not `envs\fibre\python.exe` directly |
| `validate_premises` fails: "% of premises fall outside the boundary" | Wrong `area.lad_code`, or census data from another boundary vintage | Check `conf/base/parameters.yml` and the census outputs |
| QGIS layers won't open | No `fibre` service entry, or PostGIS is down | `.\scripts\setup_pg_service.ps1`, `.\run.bat up` |
| GeoServer layers out of date after a new area | Bounding boxes cached | `python -m fibre_planning.geoserver` recalculates them |
| VS Code offers to enable `python.terminal.useEnvFile` | It found `.env` | Decline: it would put the database passwords in every terminal |

## Changing the database

1. Edit `src/fibre_planning/db/models.py`.
2. `alembic revision -m "describe the change"` and write `upgrade()` and
   `downgrade()` by hand (spatial indexes and grants are explicit).
3. `pytest tests/test_migrations.py`: the round trip and the no-drift check
   must pass.
4. For review by a DBA: `alembic upgrade head --sql > change.sql`.

## Planning a different area

Set `area.lad_code` in `conf/base/parameters.yml` (any GB local authority
code), then `.\run.bat pipeline` and `.\run.bat publish`. The Ofcom files and
OS Open Roads squares needed are chosen automatically.
