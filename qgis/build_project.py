"""Build qgis/fibre_planning.qgz: the pipeline outputs ready to inspect in QGIS.

Run with QGIS's Python (PyQGIS), e.g. on Windows:
    "C:\\Program Files\\QGIS 3.44.13\\bin\\python-qgis-ltr.bat" qgis\\build_project.py

The project holds no passwords. PostGIS layers connect through the PostgreSQL
service "fibre" (see scripts/setup_pg_service.ps1, which writes your
pg_service.conf from .env), and GeoServer layers through its public WMS.
Styles come from the same SLD files GeoServer uses, so both look the same.
"""

import sys
from pathlib import Path

from qgis.core import (
    Qgis,
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsDataSourceUri,
    QgsProject,
    QgsRasterLayer,
    QgsReferencedRectangle,
    QgsVectorLayer,
)

ROOT = Path(__file__).resolve().parents[1]
STYLES = ROOT / "geoserver" / "styles"
OUT = ROOT / "qgis" / "fibre_planning.qgz"
SERVICE = "fibre"
GEOSERVER_WMS = "http://127.0.0.1:8080/geoserver/fibre/wms"

# (table, geometry type, layer name, SLD style or None)
POSTGIS_LAYERS = [
    ("area_boundary", "MultiPolygon", "Planning area", "area_boundary"),
    ("road_link_priority", "LineString", "Road links: build priority", "road_link_priority"),
    ("premises", "Point", "Premises: gigabit coverage", "premises_coverage"),
    ("postcode_coverage", "Point", "Postcodes", None),
]


def postgis_layer(table: str, geom_type: str, name: str, key: str) -> QgsVectorLayer:
    uri = QgsDataSourceUri()
    uri.setConnection(SERVICE, "", "", "")  # service only: credentials stay in pg_service.conf
    uri.setDataSource("fibre", table, "geom", "", key)
    uri.setWkbType(getattr(Qgis.WkbType, geom_type))
    uri.setSrid("27700")
    return QgsVectorLayer(uri.uri(False), name, "postgres")


def main() -> int:
    app = QgsApplication([], False)
    app.initQgis()
    project = QgsProject.instance()
    project.setTitle("Fibre planning: Exeter")
    project.setCrs(QgsCoordinateReferenceSystem("EPSG:27700"))
    root = project.layerTreeRoot()

    basemap = QgsRasterLayer(
        "type=xyz&url=https://tile.openstreetmap.org/{z}/{x}/{y}.png&zmax=19&zmin=0", "OpenStreetMap", "wms"
    )
    project.addMapLayer(basemap, False)
    root.addLayer(basemap)

    db_group = root.insertGroup(0, "PostGIS (service=fibre)")
    keys = {
        "area_boundary": "lad_code",
        "road_link_priority": "road_link_id",
        "premises": "uprn",
        "postcode_coverage": "postcode",
    }
    for table, geom_type, name, style in POSTGIS_LAYERS:
        layer = postgis_layer(table, geom_type, name, keys[table])
        if not layer.isValid():
            print(f"Could not open {table}: is PostGIS up and pg_service.conf set?", file=sys.stderr)
            return 1
        if style:
            message, ok = layer.loadSldStyle(str(STYLES / f"{style}.sld"))
            if not ok:
                print(f"Style {style}: {message}", file=sys.stderr)
        project.addMapLayer(layer, False)
        node = db_group.insertLayer(0, layer)
        if style is None:
            node.setItemVisibilityChecked(False)  # unstyled: off by default

    wms_group = root.insertGroup(1, "GeoServer WMS (same data, served)")
    wms_group.setItemVisibilityChecked(False)
    wms = QgsRasterLayer(
        f"contextualWMSLegend=0&crs=EPSG:27700&format=image/png&layers=fibre:road_link_priority"
        f"&styles=&url={GEOSERVER_WMS}",
        "Road priority (WMS)",
        "wms",
    )
    project.addMapLayer(wms, False)
    wms_group.addLayer(wms)

    extent = project.mapLayersByName("Planning area")[0].extent()
    extent.scale(1.05)
    project.viewSettings().setDefaultViewExtent(QgsReferencedRectangle(extent, project.crs()))
    ok = project.write(str(OUT))
    print(f"{'Wrote' if ok else 'FAILED to write'} {OUT}")
    app.exitQgis()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
