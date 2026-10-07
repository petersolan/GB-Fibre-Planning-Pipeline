"""Read-only role for the API and GeoServer (least privilege).

The role can SELECT from the fibre schema and nothing else, so a bug or a
compromised service can't change data. Its password comes from .env at
migration time and is never stored in the repository.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-07
"""

import re
from collections.abc import Sequence

from alembic import op

from fibre_planning.db.config import get_settings

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "fibre"


def _literal(value: str) -> str:
    """Quote a string as an SQL literal (CREATE ROLE can't take bind parameters)."""
    return "'" + value.replace("'", "''") + "'"


def _identifier(name: str) -> str:
    """Role and database names go into SQL as identifiers, so allow only plain ones."""
    if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", name):
        raise ValueError(f"Unsafe SQL identifier: {name!r}")
    return name


def upgrade() -> None:
    settings = get_settings()
    role = _identifier(settings.api_db_user)
    password = _literal(settings.api_db_password.get_secret_value())
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{role}') THEN
                CREATE ROLE {role} LOGIN PASSWORD {password};
            ELSE
                ALTER ROLE {role} LOGIN PASSWORD {password};
            END IF;
        END $$;
        """
    )
    op.execute(f"GRANT CONNECT ON DATABASE {_identifier(settings.postgres_db)} TO {role}")
    op.execute(f"GRANT USAGE ON SCHEMA {SCHEMA} TO {role}")
    op.execute(f"GRANT SELECT ON ALL TABLES IN SCHEMA {SCHEMA} TO {role}")
    # Tables added by later migrations are readable too
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA {SCHEMA} GRANT SELECT ON TABLES TO {role}")
    op.execute(f"GRANT SELECT ON public.spatial_ref_sys TO {role}")


def downgrade() -> None:
    role = _identifier(get_settings().api_db_user)
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA {SCHEMA} REVOKE SELECT ON TABLES FROM {role}")
    op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA {SCHEMA} FROM {role}")
    op.execute(f"REVOKE USAGE ON SCHEMA {SCHEMA} FROM {role}")
    op.execute(f"REVOKE CONNECT ON DATABASE {_identifier(get_settings().postgres_db)} FROM {role}")
    op.execute(f"DROP ROLE IF EXISTS {role}")
