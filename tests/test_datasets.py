"""The PostGIS dataset reads and replaces only its own area's rows."""

import geopandas as gpd
import pytest
from kedro.io import DatasetError
from shapely.geometry import MultiPolygon, box
from sqlalchemy import text

from fibre_planning.datasets.postgis import PostGISDataset

pytestmark = pytest.mark.integration

CRS = "EPSG:27700"


def _boundary(name: str, x: float) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame({"name": [name]}, geometry=[MultiPolygon([box(x, 0, x + 100, 100)])], crs=CRS)


@pytest.fixture
def areas(test_database):
    """Two areas' datasets; their rows are removed again afterwards."""
    datasets = [PostGISDataset(table="area_boundary", area_code=code) for code in ("E99000021", "E99000022")]
    yield datasets
    with datasets[0].engine.begin() as conn:
        conn.execute(text("DELETE FROM fibre.area_boundary WHERE lad_code IN ('E99000021', 'E99000022')"))


def test_save_replaces_only_its_own_area(areas):
    north, south = areas
    north.save(_boundary("North", 0))
    south.save(_boundary("South", 200))

    north.save(_boundary("North, again", 0))  # a re-run of one area

    assert list(north.load()["name"]) == ["North, again"]
    assert list(south.load()["name"]) == ["South"]
    assert set(north.load()["lad_code"]) == {"E99000021"}


def test_save_rejects_rows_for_another_area(areas):
    data = _boundary("Elsewhere", 0).assign(lad_code="E99000099")
    with pytest.raises(DatasetError, match="E99000099"):
        areas[0].save(data)
