"""pgRouting: road network graph, gap connections and the proposed build network.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "fibre"
SRID = 27700


def _geom(kind: str) -> sa.Column:
    return sa.Column("geom", Geometry(kind, srid=SRID, spatial_index=False), nullable=False)


def _gist(table: str) -> None:
    op.create_index(f"ix_{table}_geom", table, ["geom"], schema=SCHEMA, postgresql_using="gist")


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgrouting")

    # One edge per OS Open Roads link; junction TOIDs mapped to integer vertex ids (from 1)
    op.create_table(
        "road_network",
        sa.Column("edge_id", sa.Integer, primary_key=True, autoincrement=False),
        sa.Column("road_link_id", sa.String(38), nullable=False, unique=True),
        sa.Column("road_function", sa.String(40)),
        sa.Column("source", sa.Integer, nullable=False),
        sa.Column("target", sa.Integer, nullable=False),
        sa.Column("length_m", sa.Float, nullable=False),
        sa.Column("cost", sa.Float, nullable=False),
        sa.Column("has_gigabit", sa.Boolean, nullable=False),
        sa.Column("is_gap", sa.Boolean, nullable=False),
        sa.Column("people_no_gigabit", sa.Float, nullable=False),
        _geom("LINESTRING"),
        sa.CheckConstraint("source > 0 AND target > 0", name="ck_road_network_vertex_ids"),
        sa.CheckConstraint("cost >= 0", name="ck_road_network_cost"),
        schema=SCHEMA,
    )
    op.create_index("ix_road_network_source", "road_network", ["source"], schema=SCHEMA)
    op.create_index("ix_road_network_target", "road_network", ["target"], schema=SCHEMA)
    _gist("road_network")

    # Each gap street: how far it is, along roads, from the existing gigabit network
    op.create_table(
        "gap_connection",
        sa.Column("road_link_id", sa.String(38), primary_key=True),
        sa.Column("road_name", sa.String(100)),
        sa.Column("people_no_gigabit", sa.Float, nullable=False),
        sa.Column("street_m", sa.Float, nullable=False),
        sa.Column("connect_m", sa.Float, nullable=False),
        sa.Column("total_m", sa.Float, nullable=False),
        sa.Column("people_per_km_total", sa.Float, nullable=False),
        sa.Column("build_rank", sa.Integer, nullable=False, unique=True),
        _geom("MULTILINESTRING"),  # the connecting route plus the street itself
        schema=SCHEMA,
    )
    _gist("gap_connection")

    # The proposed new cable network: every link on a connecting route, or a gap street
    op.create_table(
        "build_route",
        sa.Column("road_link_id", sa.String(38), primary_key=True),
        sa.Column("role", sa.String(10), nullable=False),
        sa.Column("length_m", sa.Float, nullable=False),
        sa.Column("gap_links_served", sa.Integer, nullable=False),
        sa.Column("people_served", sa.Float, nullable=False),
        _geom("LINESTRING"),
        sa.CheckConstraint("role IN ('connection', 'gap')", name="ck_build_route_role"),
        schema=SCHEMA,
    )
    _gist("build_route")


def downgrade() -> None:
    for table in ["build_route", "gap_connection", "road_network"]:
        op.drop_table(table, schema=SCHEMA)
    # The extension may be used by other schemas, so it is left installed
