"""Alembic environment: connects with the owner role from ``.env``."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

from fibre_planning.db.config import get_settings
from fibre_planning.db.models import SCHEMA, Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def include_object(obj, name, type_, reflected, compare_to):
    # Leave PostGIS's own tables (spatial_ref_sys, topology...) alone
    return getattr(obj, "schema", SCHEMA) == SCHEMA if type_ == "table" else True


def run_migrations_offline() -> None:
    """Emit SQL to stdout (``alembic upgrade head --sql``) for review or DBAs."""
    context.configure(
        url=get_settings().owner_url.render_as_string(hide_password=True),
        target_metadata=target_metadata,
        literal_binds=True,
        version_table_schema=SCHEMA,
        include_schemas=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(get_settings().owner_url)
    with engine.connect() as connection:
        # The version table lives in the app schema, which must exist first
        connection.exec_driver_sql(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
        connection.commit()
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table_schema=SCHEMA,
            include_schemas=True,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
