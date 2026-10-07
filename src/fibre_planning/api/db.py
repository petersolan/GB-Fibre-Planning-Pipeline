"""Database access for the API: one engine per process, read-only role."""

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Connection, Engine

from fibre_planning.db.config import get_settings


@lru_cache
def get_engine() -> Engine:
    return create_engine(
        get_settings().reader_url,
        pool_size=5,
        pool_pre_ping=True,  # survive database restarts
        # Guard rails: no query may run longer than 10 s, and the session is read-only
        connect_args={"options": "-c statement_timeout=10000 -c default_transaction_read_only=on"},
    )


def get_connection() -> Iterator[Connection]:
    """FastAPI dependency: a pooled connection for the duration of a request."""
    with get_engine().connect() as conn:
        yield conn
