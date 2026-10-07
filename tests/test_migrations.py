"""Migrations are reversible and the schema matches the SQLAlchemy models."""

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect

pytestmark = pytest.mark.integration


def _engine():
    from fibre_planning.db.config import get_settings

    return create_engine(get_settings().owner_url)


def test_downgrade_and_upgrade_round_trip(test_database):
    config = Config("alembic.ini")
    command.downgrade(config, "base")
    assert "premises" not in inspect(_engine()).get_table_names(schema="fibre")
    command.upgrade(config, "head")
    tables = set(inspect(_engine()).get_table_names(schema="fibre"))
    assert {"area_boundary", "premises", "postcode_coverage", "road_link_priority", "pipeline_run"} <= tables


def test_models_match_migrations(test_database):
    """No drift: autogenerate would produce an empty migration."""
    from fibre_planning.db.models import SCHEMA, Base

    def include(obj, name, type_, reflected, compare_to):
        if type_ == "table":
            return obj.schema == SCHEMA and name != "alembic_version"
        # Spatial and constraint details are managed in the migrations by hand
        return type_ not in ("index", "unique_constraint", "foreign_key_constraint")

    with _engine().connect() as conn:
        context = MigrationContext.configure(
            conn, opts={"include_schemas": True, "include_object": include, "compare_type": False}
        )
        diff = compare_metadata(context, Base.metadata)
    assert diff == [], diff
