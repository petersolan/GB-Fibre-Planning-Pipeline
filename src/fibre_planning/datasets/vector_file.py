"""Kedro dataset for local vector files written by GDAL (Shapefile, GeoPackage...).

kedro-datasets' GeoPandas dataset writes through a single file handle, which
can't produce a Shapefile (several files) or a GeoPackage. This one hands the
path to GeoPandas/pyogrio directly.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import geopandas as gpd
from kedro.io import AbstractDataset


class VectorFileDataset(AbstractDataset[gpd.GeoDataFrame, gpd.GeoDataFrame]):
    def __init__(self, filepath: str, driver: str = "GPKG", layer: str | None = None) -> None:
        self._path = Path(filepath)
        self._driver = driver
        self._layer = layer

    def load(self) -> gpd.GeoDataFrame:
        return gpd.read_file(self._path, layer=self._layer, engine="pyogrio")

    def save(self, data: gpd.GeoDataFrame) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        kwargs: dict[str, Any] = {"driver": self._driver, "engine": "pyogrio"}
        if self._layer:
            kwargs["layer"] = self._layer
        if self._driver == "ESRI Shapefile":
            kwargs["encoding"] = "UTF-8"  # writes a .cpg so QGIS reads names correctly
        data.to_file(self._path, **kwargs)

    def _exists(self) -> bool:
        return self._path.exists()

    def _describe(self) -> dict[str, Any]:
        return {"filepath": str(self._path), "driver": self._driver, "layer": self._layer}
