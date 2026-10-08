"""Shared fixtures. Integration tests run against a separate ``fibre_test``
database, created and migrated with Alembic and seeded with a tiny synthetic
area, so they never touch real data and run the same locally and in CI.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError

TEST_DB = "fibre_test"
TEST_LAD = "E99000001"  # not real local authority codes
TEST_LAD_2 = "E99000002"


def _settings():
    from fibre_planning.db.config import get_settings

    return get_settings()


def _admin_engine() -> Engine | None:
    """Owner connection to the server's default database, or None if it's down."""
    try:
        settings = _settings()
        url = settings.owner_url.set(database="postgres")
        engine = create_engine(url, isolation_level="AUTOCOMMIT", connect_args={"connect_timeout": 3})
        with engine.connect():
            pass
        return engine
    except (OperationalError, ValueError):
        return None


def _alembic(*args: str) -> None:
    from alembic import command
    from alembic.config import Config

    config = Config("alembic.ini")
    getattr(command, args[0])(config, *args[1:])


@pytest.fixture(scope="session")
def test_database() -> Iterator[str]:
    """Create fibre_test from scratch, point the settings at it, migrate to head."""
    admin = _admin_engine()
    if admin is None:
        pytest.skip("PostGIS not reachable (docker compose up -d postgis)")
    with admin.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)"))
        conn.execute(text(f"CREATE DATABASE {TEST_DB}"))

    os.environ["POSTGRES_DB"] = TEST_DB
    from fibre_planning.api.db import get_engine
    from fibre_planning.db.config import get_settings

    get_settings.cache_clear()
    get_engine.cache_clear()
    _alembic("upgrade", "head")
    yield TEST_DB

    get_engine().dispose()
    with admin.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)"))


@pytest.fixture(scope="session")
def seeded_database(test_database: str) -> str:
    """Two neighbouring 1 km squares. Testville: 4 premises in 2 postcodes, 2 road
    links. Testshire, east of it, shares road link LINK-B and postcode EX2 2BB
    with Testville (as real areas do at their edges) and adds LINK-C.
    """
    engine = create_engine(_settings().owner_url)
    with engine.begin() as conn:
        statements = [
            """INSERT INTO fibre.area_boundary (lad_code, name, geom) VALUES
               (:lad, 'Testville', ST_Multi(ST_MakeEnvelope(291000, 92000, 292000, 93000, 27700))),
               (:lad2, 'Testshire', ST_Multi(ST_MakeEnvelope(292000, 92000, 293000, 93000, 27700)))""",
            """INSERT INTO fibre.premises
                 (lad_code, uprn, postcode, population, gigabit_pct, p_no_gigabit, people_no_gigabit,
                  road_link_id, drop_m, geom) VALUES
               (:lad, 1, 'EX1 1AA', 2, 100, 0, 0, 'LINK-A', 5,  ST_SetSRID(ST_MakePoint(291100, 92105), 27700)),
               (:lad, 2, 'EX1 1AA', 3, 100, 0, 0, 'LINK-A', 5,  ST_SetSRID(ST_MakePoint(291200, 92105), 27700)),
               (:lad, 3, 'EX2 2BB', 4, 0,   1, 4, 'LINK-B', 10, ST_SetSRID(ST_MakePoint(291500, 92510), 27700)),
               (:lad, 4, 'EX2 2BB', 1, 0,   1, 1, 'LINK-B', 10, ST_SetSRID(ST_MakePoint(291600, 92510), 27700)),
               (:lad2, 5, 'EX2 2BB', 3, 0,  1, 3, 'LINK-B', 10, ST_SetSRID(ST_MakePoint(292600, 92510), 27700)),
               (:lad2, 6, 'EX3 3CC', 4, 0,  1, 4, 'LINK-C', 8,  ST_SetSRID(ST_MakePoint(292700, 92808), 27700))""",
            """INSERT INTO fibre.postcode_coverage
                 (lad_code, postcode, premises, population, gigabit_pct, people_no_gigabit, geom) VALUES
               (:lad, 'EX1 1AA', 2, 5, 100, 0, ST_SetSRID(ST_MakePoint(291150, 92105), 27700)),
               (:lad, 'EX2 2BB', 2, 5, 0,   5, ST_SetSRID(ST_MakePoint(291550, 92510), 27700)),
               (:lad2, 'EX2 2BB', 1, 3, 0,  3, ST_SetSRID(ST_MakePoint(292600, 92510), 27700)),
               (:lad2, 'EX3 3CC', 1, 4, 0,  4, ST_SetSRID(ST_MakePoint(292700, 92808), 27700))""",
            """INSERT INTO fibre.road_link_priority
                 (lad_code, road_link_id, road_function, road_name, length_m, premises,
                  premises_no_gigabit, people_no_gigabit, people_per_km, priority_rank, geom) VALUES
               (:lad, 'LINK-A', 'Local Road', 'High Street', 200, 2, 0, 0, 0, NULL,
                ST_SetSRID(ST_MakeLine(ST_MakePoint(291000, 92100), ST_MakePoint(291200, 92100)), 27700)),
               (:lad, 'LINK-B', 'Local Road', 'Low Lane', 500, 2, 2, 5, 10, 1,
                ST_SetSRID(ST_MakeLine(ST_MakePoint(291300, 92500), ST_MakePoint(291800, 92500)), 27700)),
               (:lad2, 'LINK-B', 'Local Road', 'Low Lane', 500, 1, 1, 3, 6, 2,
                ST_SetSRID(ST_MakeLine(ST_MakePoint(291300, 92500), ST_MakePoint(291800, 92500)), 27700)),
               (:lad2, 'LINK-C', 'Local Road', 'Far Close', 100, 1, 1, 4, 40, 1,
                ST_SetSRID(ST_MakeLine(ST_MakePoint(292650, 92800), ST_MakePoint(292750, 92800)), 27700))""",
            """INSERT INTO fibre.gap_connection
                 (lad_code, road_link_id, road_name, people_no_gigabit, street_m, connect_m, total_m,
                  people_per_km_total, build_rank, premises_no_gigabit, est_cost_gbp,
                  cost_per_premises_gbp, geom) VALUES
               (:lad, 'LINK-B', 'Low Lane', 5, 500, 100, 600, 8.33, 1, 2, 60000, 30000,
                ST_Multi(ST_SetSRID(ST_MakeLine(ST_MakePoint(291200, 92500), ST_MakePoint(291800, 92500)), 27700))),
               (:lad2, 'LINK-C', 'Far Close', 4, 100, 100, 200, 20, 1, 1, 20000, 20000,
                ST_Multi(ST_SetSRID(ST_MakeLine(ST_MakePoint(292550, 92800), ST_MakePoint(292750, 92800)), 27700)))""",
            """INSERT INTO fibre.pipeline_run (lad_code, summary) VALUES
               (:lad, CAST(:summary AS jsonb)), (:lad2, CAST(:summary2 AS jsonb))""",
        ]
        params = {
            "lad": TEST_LAD,
            "lad2": TEST_LAD_2,
            "summary": (
                '{"lad_code": "E99000001", "name": "Testville", "premises": 4, "population": 10,'
                ' "premises_no_gigabit": 2, "people_no_gigabit": 5, "gigabit_coverage_pct": 50,'
                ' "road_links_to_build": 1}'
            ),
            "summary2": (
                '{"lad_code": "E99000002", "name": "Testshire", "premises": 2, "population": 7,'
                ' "premises_no_gigabit": 2, "people_no_gigabit": 7, "gigabit_coverage_pct": 0,'
                ' "road_links_to_build": 2}'
            ),
        }
        for sql in statements:
            conn.execute(text(sql), {k: v for k, v in params.items() if f":{k}" in sql})
    engine.dispose()
    return test_database
