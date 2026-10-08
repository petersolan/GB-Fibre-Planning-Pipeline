"""The plugin: a toolbar button and a dock panel backed by the API."""

from __future__ import annotations

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsRectangle,
    QgsSettings,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import (
    QAction,
    QComboBox,
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .api_client import DEFAULT_API_URL, ApiError, Area, FibreApi

SETTINGS_KEY = "fibre_planning/api_url"
# view name -> (API path, label used for layers and messages)
VIEWS = {
    "Build plan (with routes)": ("/v1/build-plan", "build plan steps"),
    "Road links (street only)": ("/v1/road-links", "road links"),
}
WGS84 = QgsCoordinateReferenceSystem("EPSG:4326")
ALL_AREAS = "All areas"


class FibrePanel(QDockWidget):
    def __init__(self, iface) -> None:
        super().__init__("Fibre planning")
        self.iface = iface
        self.links = []
        self.areas: dict[str, Area] = {}
        body = QWidget()
        layout = QVBoxLayout(body)

        self.api_url = QLineEdit(QgsSettings().value(SETTINGS_KEY, DEFAULT_API_URL))
        self.api_url.editingFinished.connect(
            lambda: QgsSettings().setValue(SETTINGS_KEY, self.api_url.text())
        )
        layout.addWidget(QLabel("API address"))
        layout.addWidget(self.api_url)

        # Areas come from the API; picking one zooms to it and filters what follows
        row = QHBoxLayout()
        self.area = QComboBox()
        self.area.addItem(ALL_AREAS, None)
        self.area.activated.connect(self.zoom_to_area)
        refresh = QPushButton("Refresh areas")
        refresh.clicked.connect(self.load_areas)
        row.addWidget(self.area, 1)
        row.addWidget(refresh)
        layout.addWidget(QLabel("Planning area"))
        layout.addLayout(row)

        self.view = QComboBox()
        self.view.addItems(list(VIEWS))
        layout.addWidget(self.view)

        row = QHBoxLayout()
        self.limit = QSpinBox(minimum=5, maximum=200, value=20)
        load = QPushButton("Load")
        load.clicked.connect(self.load_links)
        add_layer = QPushButton("Add as layer")
        add_layer.clicked.connect(self.add_links_layer)
        row.addWidget(self.limit)
        row.addWidget(load)
        row.addWidget(add_layer)
        layout.addLayout(row)

        self.list = QListWidget()
        self.list.itemActivated.connect(self.zoom_to_link)
        self.list.itemClicked.connect(self.zoom_to_link)
        layout.addWidget(self.list)

        row = QHBoxLayout()
        self.postcode = QLineEdit(placeholderText="Postcode, e.g. EX4 4QJ")
        self.postcode.returnPressed.connect(self.lookup_postcode)
        find = QPushButton("Look up")
        find.clicked.connect(self.lookup_postcode)
        row.addWidget(self.postcode)
        row.addWidget(find)
        layout.addLayout(row)

        self.result = QLabel(wordWrap=True)
        layout.addWidget(self.result)
        self.setWidget(body)
        self.load_areas()

    def api(self) -> FibreApi:
        return FibreApi(self.api_url.text() or DEFAULT_API_URL)

    def _to_canvas(self) -> QgsCoordinateTransform:
        canvas_crs = self.iface.mapCanvas().mapSettings().destinationCrs()
        return QgsCoordinateTransform(WGS84, canvas_crs, QgsProject.instance())

    def _show_error(self, error: Exception) -> None:
        self.result.setText(f"<span style='color:#b00'>{error}</span>")

    def selected_area(self) -> str | None:
        """The chosen area's district code, or None for all areas."""
        return self.area.currentData()

    def load_areas(self) -> None:
        try:
            areas = self.api().areas()
        except ApiError as error:
            self._show_error(error)
            return
        current = self.selected_area()
        self.areas = {a.lad_code: a for a in areas}
        self.area.clear()
        self.area.addItem(ALL_AREAS, None)
        for a in areas:
            self.area.addItem(f"{a.name} ({a.lad_code})", a.lad_code)
        self.area.setCurrentIndex(max(self.area.findData(current), 0))

    def zoom_to_area(self) -> None:
        chosen = [self.areas[self.selected_area()]] if self.selected_area() else list(self.areas.values())
        if not chosen:
            return
        box = QgsRectangle(*chosen[0].bbox)
        for a in chosen[1:]:
            box.combineExtentWith(QgsRectangle(*a.bbox))
        canvas = self.iface.mapCanvas()
        canvas.setExtent(self._to_canvas().transformBoundingBox(box))
        canvas.refresh()

    def _label(self, link) -> str:
        # Ranks are per area, so name the area when the list mixes them
        if self.selected_area() or link.lad_code not in self.areas:
            return link.label
        return f"{self.areas[link.lad_code].name} {link.label}"

    def load_links(self) -> None:
        build = self.view.currentText().startswith("Build")
        try:
            api = self.api()
            limit, area = self.limit.value(), self.selected_area()
            self.links = api.build_plan(limit, area) if build else api.top_road_links(limit, area)
        except ApiError as error:
            self._show_error(error)
            return
        self.list.clear()
        for link in self.links:
            item = QListWidgetItem(self._label(link))
            item.setData(Qt.ItemDataRole.UserRole, link)
            self.list.addItem(item)
        what = VIEWS[self.view.currentText()][1]
        where = "across all areas" if self.selected_area() is None else f"in {self.area.currentText()}"
        note = " Costs are indicative civil works only." if build else ""
        self.result.setText(
            f"{len(self.links)} {what} {where}, highest priority first. Click one to zoom.{note}"
        )

    def zoom_to_link(self, item: QListWidgetItem) -> None:
        link = item.data(Qt.ItemDataRole.UserRole)
        # A build step is the street plus its connecting route: several lines
        line = QgsGeometry.fromMultiPolylineXY([[QgsPointXY(x, y) for x, y in part] for part in link.lines])
        line.transform(self._to_canvas())
        canvas = self.iface.mapCanvas()
        canvas.setExtent(line.boundingBox().buffered(150))
        canvas.refresh()
        canvas.flashGeometries([line], canvas.mapSettings().destinationCrs(), QColor("#b30000"))

    def add_links_layer(self) -> None:
        # OGR reads GeoJSON straight from the API URL
        path, what = VIEWS[self.view.currentText()]
        area = self.selected_area()
        url = self.api().url(path, limit=self.limit.value(), area=area)
        where = f", {self.areas[area].name}" if area in self.areas else ""
        layer = QgsVectorLayer(url, f"Top {self.limit.value()} {what}{where} (API)", "ogr")
        if not layer.isValid():
            self._show_error(ApiError(f"Could not load {url}"))
            return
        QgsProject.instance().addMapLayer(layer)

    def lookup_postcode(self) -> None:
        try:
            found = self.api().postcode(self.postcode.text())
        except (ApiError, ValueError) as error:
            self._show_error(error)
            return
        self.result.setText(found.summary)
        point = QgsGeometry.fromPointXY(QgsPointXY(found.lon, found.lat))
        point.transform(self._to_canvas())
        canvas = self.iface.mapCanvas()
        canvas.setCenter(point.asPoint())
        canvas.zoomScale(5000)
        canvas.flashGeometries([point], canvas.mapSettings().destinationCrs())


class FibrePlanningPlugin:
    def __init__(self, iface) -> None:
        self.iface = iface
        self.action = None
        self.panel = None

    def initGui(self) -> None:  # noqa: N802 - QGIS plugin API
        self.action = QAction("Fibre planning", self.iface.mainWindow())
        self.action.setCheckable(True)
        self.action.toggled.connect(self.toggle_panel)
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToWebMenu("Fibre planning", self.action)

    def toggle_panel(self, checked: bool) -> None:
        if self.panel is None:
            self.panel = FibrePanel(self.iface)
            self.iface.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.panel)
            self.panel.visibilityChanged.connect(self.action.setChecked)
        self.panel.setVisible(checked)

    def unload(self) -> None:
        self.iface.removePluginWebMenu("Fibre planning", self.action)
        self.iface.removeToolBarIcon(self.action)
        if self.panel is not None:
            self.iface.removeDockWidget(self.panel)
            self.panel.deleteLater()
        self.panel = None
