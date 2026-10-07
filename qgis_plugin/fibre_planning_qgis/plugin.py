"""The plugin: a toolbar button and a dock panel backed by the API."""

from __future__ import annotations

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsSettings,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import (
    QAction,
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

from .api_client import DEFAULT_API_URL, ApiError, FibreApi

SETTINGS_KEY = "fibre_planning/api_url"
WGS84 = QgsCoordinateReferenceSystem("EPSG:4326")


class FibrePanel(QDockWidget):
    def __init__(self, iface) -> None:
        super().__init__("Fibre planning")
        self.iface = iface
        self.links = []
        body = QWidget()
        layout = QVBoxLayout(body)

        self.api_url = QLineEdit(QgsSettings().value(SETTINGS_KEY, DEFAULT_API_URL))
        self.api_url.editingFinished.connect(
            lambda: QgsSettings().setValue(SETTINGS_KEY, self.api_url.text())
        )
        layout.addWidget(QLabel("API address"))
        layout.addWidget(self.api_url)

        row = QHBoxLayout()
        self.limit = QSpinBox(minimum=5, maximum=200, value=20)
        load = QPushButton("Top road links")
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

    def api(self) -> FibreApi:
        return FibreApi(self.api_url.text() or DEFAULT_API_URL)

    def _to_canvas(self) -> QgsCoordinateTransform:
        canvas_crs = self.iface.mapCanvas().mapSettings().destinationCrs()
        return QgsCoordinateTransform(WGS84, canvas_crs, QgsProject.instance())

    def _show_error(self, error: Exception) -> None:
        self.result.setText(f"<span style='color:#b00'>{error}</span>")

    def load_links(self) -> None:
        try:
            self.links = self.api().top_road_links(self.limit.value())
        except ApiError as error:
            self._show_error(error)
            return
        self.list.clear()
        for link in self.links:
            item = QListWidgetItem(link.label)
            item.setData(Qt.ItemDataRole.UserRole, link)
            self.list.addItem(item)
        self.result.setText(f"{len(self.links)} road links, highest priority first. Click one to zoom.")

    def zoom_to_link(self, item: QListWidgetItem) -> None:
        link = item.data(Qt.ItemDataRole.UserRole)
        line = QgsGeometry.fromPolylineXY([QgsPointXY(x, y) for x, y in link.coordinates])
        line.transform(self._to_canvas())
        canvas = self.iface.mapCanvas()
        canvas.setExtent(line.boundingBox().buffered(150))
        canvas.refresh()
        canvas.flashGeometries([line], canvas.mapSettings().destinationCrs(), QColor("#b30000"))

    def add_links_layer(self) -> None:
        # OGR reads GeoJSON straight from the API URL
        url = self.api().url("/v1/road-links", limit=self.limit.value())
        layer = QgsVectorLayer(url, f"Top {self.limit.value()} road links (API)", "ogr")
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
