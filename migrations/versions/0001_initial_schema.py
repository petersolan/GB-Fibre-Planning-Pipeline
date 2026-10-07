"""Initial fibre schema: boundary, premises, postcode coverage, road priority, run log.

Revision ID: 0001
Revises:
Create Date: 2026-10-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "fibre"
SRID = 27700


def _geom(kind: str) -> sa.Column:
    return sa.Column("geom", Geometry(kind, srid=SRID, spatial_index=False), nullable=False)


def _gist(table: str) -> None:
    op.create_index(f"ix_{table}_geom", table, ["geom"], schema=SCHEMA, postgresql_using="gist")


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    op.create_table(
        "area_boundary",
        sa.Column("lad_code", sa.String(9), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        _geom("MULTIPOLYGON"),
        schema=SCHEMA,
    )

    op.create_table(
        "premises",
        sa.Column("uprn", sa.BigInteger, primary_key=True),
        sa.Column("postcode", sa.String(8)),
        sa.Column("population", sa.Integer, nullable=False),
        sa.Column("gigabit_pct", sa.Float),
        sa.Column("p_no_gigabit", sa.Float),
        sa.Column("people_no_gigabit", sa.Float),
        sa.Column("road_link_id", sa.String(38)),
        sa.Column("drop_m", sa.Float),
        _geom("POINT"),
        sa.CheckConstraint("population >= 0", name="ck_premises_population"),
        sa.CheckConstraint("gigabit_pct BETWEEN 0 AND 100", name="ck_premises_gigabit_pct"),
        schema=SCHEMA,
    )
    op.create_index("ix_premises_postcode", "premises", ["postcode"], schema=SCHEMA)
    op.create_index("ix_premises_road_link_id", "premises", ["road_link_id"], schema=SCHEMA)
    _gist("premises")

    op.create_table(
        "postcode_coverage",
        sa.Column("postcode", sa.String(8), primary_key=True),
        sa.Column("premises", sa.Integer, nullable=False),
        sa.Column("population", sa.Integer, nullable=False),
        sa.Column("gigabit_pct", sa.Float),
        sa.Column("people_no_gigabit", sa.Float),
        _geom("POINT"),
        schema=SCHEMA,
    )
    _gist("postcode_coverage")

    op.create_table(
        "road_link_priority",
        sa.Column("road_link_id", sa.String(38), primary_key=True),
        sa.Column("road_function", sa.String(40)),
        sa.Column("road_name", sa.String(100)),
        sa.Column("length_m", sa.Float, nullable=False),
        sa.Column("premises", sa.Integer, nullable=False),
        sa.Column("premises_no_gigabit", sa.Float, nullable=False),
        sa.Column("people_no_gigabit", sa.Float, nullable=False),
        sa.Column("people_per_km", sa.Float, nullable=False),
        sa.Column("priority_rank", sa.Integer),
        _geom("LINESTRING"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_road_link_priority_priority_rank", "road_link_priority", ["priority_rank"], schema=SCHEMA
    )
    _gist("road_link_priority")

    op.create_table(
        "pipeline_run",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("run_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("lad_code", sa.String(9), nullable=False),
        sa.Column("summary", JSONB),
        schema=SCHEMA,
    )


def downgrade() -> None:
    for table in ["pipeline_run", "road_link_priority", "postcode_coverage", "premises", "area_boundary"]:
        op.drop_table(table, schema=SCHEMA)
