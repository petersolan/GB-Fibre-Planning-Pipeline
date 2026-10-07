"""Database connection settings, read from environment variables or ``.env``.

One source of truth for the pipeline, Alembic and the API. Passwords never
live in code or in committed config: copy ``.env.example`` to ``.env``.
"""

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # 127.0.0.1, not "localhost": on Windows localhost resolves to IPv6 ::1 first,
    # and Docker publishes the port on IPv4 only, so each connection hung ~2 min
    postgres_host: str = "127.0.0.1"
    postgres_port: int = 5433
    postgres_db: str = "fibre"
    postgres_user: str = "fibre_owner"
    postgres_password: SecretStr
    # Read-only role for the API and GeoServer
    api_db_user: str = "fibre_reader"
    api_db_password: SecretStr

    def _url(self, user: str, password: SecretStr) -> URL:
        return URL.create(
            "postgresql+psycopg",
            username=user,
            password=password.get_secret_value(),
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )

    @property
    def owner_url(self) -> URL:
        """Owner role: runs migrations and loads data."""
        return self._url(self.postgres_user, self.postgres_password)

    @property
    def reader_url(self) -> URL:
        """Read-only role: used by services that only query."""
        return self._url(self.api_db_user, self.api_db_password)


@lru_cache
def get_settings() -> DatabaseSettings:
    return DatabaseSettings()  # type: ignore[call-arg]
