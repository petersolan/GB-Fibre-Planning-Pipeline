"""Kedro dataset for a PostGIS table whose schema is owned by Alembic.

Saving replaces the table's rows (TRUNCATE + INSERT in one transaction), so
column types, constraints and indexes from the migrations stay in place and a
failed load leaves the previous data untouched. Loading reads it back as a
GeoDataFrame.
"""

from __future__ import annotations

from typing import Any

import geopandas as gpd
from kedro.io import AbstractDataset
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from fibre_planning.db.config import get_settings


class PostGISDataset(AbstractDataset[gpd.GeoDataFrame, gpd.GeoDataFrame]):
    def __init__(self, table: str, schema: str = "fibre", geometry_column: str = "geom") -> None:
        self._table = table
        self._schema = schema
        self._geom = geometry_column
        self._engine: Engine | None = None

    @property
    def engine(self) -> Engine:
        # Created lazily, so building the catalog needs no database
        if self._engine is None:
            self._engine = create_engine(get_settings().owner_url)
        return self._engine

    def _qualified(self) -> str:
        return f'"{self._schema}"."{self._table}"'

    def load(self) -> gpd.GeoDataFrame:
        return gpd.read_postgis(text(f"SELECT * FROM {self._qualified()}"), self.engine, geom_col=self._geom)

    def save(self, data: gpd.GeoDataFrame) -> None:
        data = data.rename_geometry(self._geom) if data.geometry.name != self._geom else data
        with self.engine.begin() as conn:
            conn.execute(text(f"TRUNCATE {self._qualified()}"))
            data.to_postgis(self._table, conn, schema=self._schema, if_exists="append", index=False)

    def _exists(self) -> bool:
        with self.engine.connect() as conn:
            return bool(conn.execute(text(f"SELECT EXISTS (SELECT 1 FROM {self._qualified()})")).scalar())

    def _describe(self) -> dict[str, Any]:
        return {"table": self._table, "schema": self._schema}
