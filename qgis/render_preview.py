r"""Render qgis/fibre_planning.qgz to docs/images/qgis_exeter.png (PyQGIS, no GUI).

"C:\Program Files\QGIS 3.44.13\bin\python-qgis-ltr.bat" qgis\render_preview.py
"""

import sys
from pathlib import Path

from qgis.core import QgsApplication, QgsMapRendererParallelJob, QgsMapSettings, QgsProject, QgsRectangle
from qgis.PyQt.QtCore import QSize
from qgis.PyQt.QtGui import QColor

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "images" / "qgis_exeter.png"
VIEW = QgsRectangle(290500, 91500, 294500, 94500)  # central Exeter, British National Grid


def main() -> int:
    app = QgsApplication([], False)
    app.initQgis()
    project = QgsProject.instance()
    project.read(str(ROOT / "qgis" / "fibre_planning.qgz"))
    visible = [
        node.layer()
        for node in project.layerTreeRoot().findLayers()
        if node.isVisible() and node.layer() and node.layer().isValid()
    ]
    settings = QgsMapSettings()
    settings.setLayers(visible)
    settings.setDestinationCrs(project.crs())
    settings.setExtent(VIEW)
    settings.setOutputSize(QSize(1200, 900))
    settings.setBackgroundColor(QColor("white"))
    job = QgsMapRendererParallelJob(settings)
    job.start()
    job.waitForFinished()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    ok = job.renderedImage().save(str(OUT), "png")
    print(f"{'Rendered' if ok else 'FAILED'} {len(visible)} layers -> {OUT}")
    app.exitQgis()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
