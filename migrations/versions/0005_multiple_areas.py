"""Several planning areas side by side: lad_code on every table and in every key.

Areas share data at their edges: roads are read 500 m beyond the boundary,
and a postcode can straddle two districts. So the same road link or postcode
can appear once per area, and keys become (lad_code, ...). The routing graph
numbers its edges from 1 in every run, so its key and the gap ranking are per
area too. Existing rows belong to the single area in area_boundary.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "fibre"

# table -> its key before this migration (lad_code goes in front)
KEYS = {
    "premises": ["uprn"],
    "postcode_coverage": ["postcode"],
    "road_link_priority": ["road_link_id"],
    "road_network": ["edge_id"],
    "gap_connection": ["road_link_id"],
    "build_route": ["road_link_id"],
}
# (table, columns) unique within an area; Postgres names the old ones <table>_<column>_key
UNIQUE = [("road_network", ["road_link_id"]), ("gap_connection", ["build_rank"])]


def _set_key(table: str, columns: list[str]) -> None:
    op.drop_constraint(f"{table}_pkey", table, schema=SCHEMA, type_="primary")
    op.create_primary_key(f"{table}_pkey", table, columns, schema=SCHEMA)


def upgrade() -> None:
    for table, key in KEYS.items():
        op.add_column(table, sa.Column("lad_code", sa.String(9)), schema=SCHEMA)
        op.execute(
            f"UPDATE {SCHEMA}.{table} SET lad_code = (SELECT min(lad_code) FROM {SCHEMA}.area_boundary)"
        )
        # Rows from before any boundary was loaded can't be placed in an area
        op.execute(f"DELETE FROM {SCHEMA}.{table} WHERE lad_code IS NULL")
        op.alter_column(table, "lad_code", nullable=False, schema=SCHEMA)
        _set_key(table, ["lad_code", *key])
    for table, columns in UNIQUE:
        op.drop_constraint(f"{table}_{columns[0]}_key", table, schema=SCHEMA, type_="unique")
        op.create_unique_constraint(
            f"uq_{table}_lad_code_{columns[0]}", table, ["lad_code", *columns], schema=SCHEMA
        )
    op.create_index("ix_pipeline_run_lad_code_run_at", "pipeline_run", ["lad_code", "run_at"], schema=SCHEMA)


def downgrade() -> None:
    # One area per table again: keep the most recently run area and drop the others
    keep = f"""(SELECT coalesce(
                   (SELECT lad_code FROM {SCHEMA}.pipeline_run ORDER BY id DESC LIMIT 1),
                   (SELECT min(lad_code) FROM {SCHEMA}.area_boundary)))"""
    op.drop_index("ix_pipeline_run_lad_code_run_at", "pipeline_run", schema=SCHEMA)
    for table, columns in UNIQUE:
        op.drop_constraint(f"uq_{table}_lad_code_{columns[0]}", table, schema=SCHEMA, type_="unique")
    for table in [*KEYS, "area_boundary"]:
        op.execute(f"DELETE FROM {SCHEMA}.{table} WHERE lad_code IS DISTINCT FROM {keep}")
    for table, columns in UNIQUE:
        op.create_unique_constraint(f"{table}_{columns[0]}_key", table, columns, schema=SCHEMA)
    for table, key in KEYS.items():
        _set_key(table, key)
        op.drop_column(table, "lad_code", schema=SCHEMA)
