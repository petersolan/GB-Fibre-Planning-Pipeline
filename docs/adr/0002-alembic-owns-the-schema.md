# 2. Alembic owns the database schema; the pipeline only loads rows

Status: accepted (2026-10-07)

## Context

`GeoDataFrame.to_postgis(if_exists="replace")` is the quick way to load
PostGIS, but it drops and recreates tables: indexes, constraints and grants
vanish, and every run silently changes the schema.

## Decision

- Tables, GiST indexes, check constraints and roles are created only by
  hand-reviewed Alembic migrations (`migrations/versions/`).
- The pipeline's `PostGISDataset` does `TRUNCATE` + `INSERT` in one
  transaction.
- Tests check that every migration downgrades and upgrades cleanly, and that
  the SQLAlchemy models match the migrated schema (no drift).

## Consequences

- A failed load rolls back and leaves the previous run's data in place.
- Schema changes are reviewed code, and `alembic upgrade head --sql` can hand
  the SQL to a DBA for regulated environments.
- The drift test caught a real mismatch (geometries `NOT NULL` in the schema
  but nullable in the models) and the round-trip test caught a downgrade that
  dropped a cluster-wide role still used by another database.
