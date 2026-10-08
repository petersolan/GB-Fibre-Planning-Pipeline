r"""Plugin tests, run with QGIS's own Python (no QGIS window opens):

    set QT_QPA_PLATFORM=offscreen
    "C:\Program Files\QGIS 3.44.13\bin\python-qgis-ltr.bat" qgis_plugin\tests\test_plugin.py

Parsing tests always run; API and panel tests need the API on 127.0.0.1:8000
(docker compose up -d) with a pipeline run loaded, and are skipped otherwise.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from qgis.core import QgsApplication, QgsCoordinateReferenceSystem, QgsProject  # noqa: E402

APP = QgsApplication([], True)
APP.initQgis()

from fibre_planning_qgis.api_client import (  # noqa: E402
    ApiError,
    FibreApi,
    normalise_postcode,
    parse_areas,
    parse_build_plan,
    parse_road_links,
)

SAMPLE = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "id": "LINK-B",
            "geometry": {"type": "LineString", "coordinates": [[-3.53, 50.72], [-3.52, 50.72]]},
            "properties": {
                "lad_code": "E99000001",
                "priority_rank": 1,
                "road_name": None,
                "road_function": "Local Road",
                "people_no_gigabit": 5.0,
                "people_per_km": 10.0,
                "length_m": 500.0,
            },
        }
    ],
    "count": 1,
}


def api_available() -> bool:
    try:
        return FibreApi().health()
    except ApiError:
        return False


class ParsingTests(unittest.TestCase):
    def test_parse_road_links(self):
        (link,) = parse_road_links(SAMPLE)
        self.assertEqual(link.rank, 1)
        self.assertEqual(link.name, "Local Road")  # falls back when the road has no name
        self.assertIn("5 people without gigabit", link.label)
        self.assertEqual(link.lad_code, "E99000001")

    def test_parse_areas(self):
        (area,) = parse_areas(
            [{"lad_code": "E07000042", "name": "Mid Devon", "bbox": [-3.9, 50.7, -3.1, 51.0]}]
        )
        self.assertEqual((area.name, area.bbox[0]), ("Mid Devon", -3.9))

    def test_url_leaves_out_unset_filters(self):
        api = FibreApi("http://example.test/")
        self.assertEqual(
            api.url("/v1/build-plan", limit=5, area=None), "http://example.test/v1/build-plan?limit=5"
        )
        self.assertIn("area=E07000042", api.url("/v1/build-plan", limit=5, area="E07000042"))

    def test_parse_build_plan(self):
        collection = {
            "features": [
                {
                    "type": "Feature",
                    "id": "LINK-B",
                    "geometry": {
                        "type": "MultiLineString",
                        "coordinates": [[[-3.53, 50.72], [-3.52, 50.72]], [[-3.52, 50.72], [-3.51, 50.72]]],
                    },
                    "properties": {
                        "build_rank": 1,
                        "road_name": "Low Lane",
                        "people_no_gigabit": 5.0,
                        "connect_m": 100.0,
                        "total_m": 600.0,
                        "est_cost_gbp": 60000.0,
                        "cost_per_premises_gbp": 30000.0,
                    },
                }
            ]
        }
        (step,) = parse_build_plan(collection)
        self.assertEqual(len(step.lines), 2)  # street plus connecting route
        self.assertIn("+100 m to reach", step.label)
        self.assertIn("£60,000", step.label)

    def test_normalise_postcode(self):
        self.assertEqual(normalise_postcode(" ex44qj "), "EX4 4QJ")
        self.assertEqual(normalise_postcode("sw1a1aa"), "SW1A 1AA")
        with self.assertRaises(ValueError):
            normalise_postcode("hello")


@unittest.skipUnless(api_available(), "API not running on 127.0.0.1:8000")
class LiveApiTests(unittest.TestCase):
    def test_top_road_links_ranked(self):
        for area in FibreApi().areas():
            links = FibreApi().top_road_links(5, area.lad_code)
            self.assertEqual([link.rank for link in links], [1, 2, 3, 4, 5], area.name)
            self.assertEqual({link.lad_code for link in links}, {area.lad_code})

    def test_postcode_round_trip(self):
        first = FibreApi().top_road_links(1)[0]
        self.assertTrue(first.coordinates)
        with self.assertRaises(ApiError):
            FibreApi().postcode("ZZ9 9ZZ")  # valid format, not in the area -> 404

    def test_unreachable_api_reports_clearly(self):
        with self.assertRaises(ApiError) as caught:
            FibreApi("http://127.0.0.1:9").health()
        self.assertIn("Could not reach", str(caught.exception))


@unittest.skipUnless(api_available(), "API not running on 127.0.0.1:8000")
class PanelTests(unittest.TestCase):
    def test_panel_loads_links_and_looks_up_postcode(self):
        from fibre_planning_qgis.plugin import FibrePanel
        from qgis.gui import QgsMapCanvas

        canvas = QgsMapCanvas()
        canvas.setDestinationCrs(QgsCoordinateReferenceSystem("EPSG:27700"))

        class Iface:
            def mapCanvas(self):
                return canvas

        panel = FibrePanel(Iface())
        self.assertGreaterEqual(panel.area.count(), 2)  # "All areas" plus at least one area
        panel.area.setCurrentIndex(panel.area.findData("E07000041"))  # Exeter
        panel.zoom_to_area()
        self.assertTrue(280_000 < canvas.extent().center().x() < 300_000, canvas.extent().toString())
        panel.limit.setValue(10)
        for view in ("Build plan (with routes)", "Road links (street only)"):
            panel.view.setCurrentText(view)
            panel.load_links()
            self.assertEqual(panel.list.count(), 10, view)
            self.assertEqual({link.lad_code for link in panel.links}, {"E07000041"})
            panel.zoom_to_link(panel.list.item(0))
            extent = canvas.extent()
            self.assertTrue(280_000 < extent.center().x() < 300_000, extent.toString())  # Exeter, BNG

        panel.area.setCurrentIndex(0)  # all areas: items name their area
        panel.load_links()
        self.assertTrue(
            panel.list.item(0).text().startswith(("Exeter", "Mid Devon")), panel.list.item(0).text()
        )

        panel.postcode.setText("ex4 4qj")
        panel.lookup_postcode()
        self.assertIn("EX4 4QJ", panel.result.text())

        panel.area.setCurrentIndex(panel.area.findData("E07000041"))
        panel.add_links_layer()
        layers = QgsProject.instance().mapLayersByName("Top 10 road links, Exeter (API)")
        self.assertEqual(layers[0].featureCount(), 10)


if __name__ == "__main__":
    result = unittest.main(exit=False, verbosity=2).result
    APP.exitQgis()
    sys.exit(0 if result.wasSuccessful() else 1)
