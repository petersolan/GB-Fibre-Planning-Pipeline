"""Kedro dataset for one area's rows in a PostGIS table whose schema is owned by Alembic.

Every table holds several planning areas, keyed by ``lad_code``. The dataset
sees only its own area: loading reads that area's rows, and saving replaces
them (DELETE + INSERT in one transaction), so other areas are untouched,
column types, constraints and indexes from the migrations stay in place and a
failed load leaves the previous data untouched.
"""

from __future__ import annotations

from typing import Any

import geopandas as gpd
from kedro.io import AbstractDataset
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from fibre_planning.db.config import get_settings


class PostGISDataset(AbstractDataset[gpd.GeoDataFrame, gpd.GeoDataFrame]):
    def __init__(
        self,
        table: str,
        area_code: str,
        schema: str = "fibre",
        geometry_column: str = "geom",
        area_column: str = "lad_code",
    ) -> None:
        self._table = table
        self._area = area_code
        self._schema = schema
        self._geom = geometry_column
        self._area_column = area_column
        self._engine: Engine | None = None

    @property
    def engine(self) -> Engine:
        # Created lazily, so building the catalog needs no database
        if self._engine is None:
            self._engine = create_engine(get_settings().owner_url)
        return self._engine

    def _qualified(self) -> str:
        return f'"{self._schema}"."{self._table}"'

    def _where(self) -> str:
        return f'WHERE "{self._area_column}" = :area'

    def load(self) -> gpd.GeoDataFrame:
        sql = text(f"SELECT * FROM {self._qualified()} {self._where()}")
        return gpd.read_postgis(sql, self.engine, geom_col=self._geom, params={"area": self._area})

    def save(self, data: gpd.GeoDataFrame) -> None:
        data = data.rename_geometry(self._geom) if data.geometry.name != self._geom else data
        other = set(data.get(self._area_column, [])) - {self._area}
        if other:
            raise ValueError(f"{self._table}: rows for {sorted(other)} in a save for {self._area}")
        data = data.assign(**{self._area_column: self._area})
        with self.engine.begin() as conn:
            conn.execute(text(f"DELETE FROM {self._qualified()} {self._where()}"), {"area": self._area})
            data.to_postgis(self._table, conn, schema=self._schema, if_exists="append", index=False)

    def _exists(self) -> bool:
        with self.engine.connect() as conn:
            sql = text(f"SELECT EXISTS (SELECT 1 FROM {self._qualified()} {self._where()})")
            return bool(conn.execute(sql, {"area": self._area}).scalar())

    def _describe(self) -> dict[str, Any]:
        return {"table": self._table, "schema": self._schema, "area_code": self._area}
