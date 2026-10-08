"""Indicative civil-works cost estimates on gap connections and the build network.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "fibre"

GAP_COLUMNS = ["premises_no_gigabit", "est_cost_gbp", "cost_per_premises_gbp"]


def _add(table: str, column: str) -> None:
    # NOT NULL needs a value for existing rows; the default is dropped again because
    # the pipeline always supplies the column
    op.add_column(table, sa.Column(column, sa.Float, nullable=False, server_default="0"), schema=SCHEMA)
    op.alter_column(table, column, server_default=None, schema=SCHEMA)


def upgrade() -> None:
    for column in GAP_COLUMNS:
        _add("gap_connection", column)
    _add("build_route", "est_cost_gbp")


def downgrade() -> None:
    op.drop_column("build_route", "est_cost_gbp", schema=SCHEMA)
    for column in reversed(GAP_COLUMNS):
        op.drop_column("gap_connection", column, schema=SCHEMA)
