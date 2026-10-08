r"""Render qgis_project/fibre_planning.qgz to the README images (PyQGIS, no GUI).

"C:\Program Files\QGIS 3.44.13\bin\python-qgis-ltr.bat" qgis_project\render_preview.py
"""

import sys
from pathlib import Path

from PIL import Image
from qgis.core import QgsApplication, QgsMapRendererParallelJob, QgsMapSettings, QgsProject, QgsRectangle
from qgis.PyQt.QtCore import QSize
from qgis.PyQt.QtGui import QColor

ROOT = Path(__file__).resolve().parents[1]
IMAGES = ROOT / "docs" / "images"
# (file, extent in British National Grid, layers to leave out)
VIEWS = [
    # Central Exeter: premises by coverage and road links by priority
    ("qgis_exeter.png", QgsRectangle(290500, 91500, 294500, 94500), {"Proposed cable network"}),
    # Closer in: the proposed cable network from pgRouting
    (
        "qgis_routes.png",
        QgsRectangle(291800, 92200, 293900, 93775),
        {"Premises: gigabit coverage", "Road links: build priority"},
    ),
]


def render(project: QgsProject, extent: QgsRectangle, hidden: set[str], out: Path) -> bool:
    layers = [
        node.layer()
        for node in project.layerTreeRoot().findLayers()
        if node.isVisible() and node.layer() and node.layer().isValid() and node.name() not in hidden
    ]
    settings = QgsMapSettings()
    settings.setLayers(layers)
    settings.setDestinationCrs(project.crs())
    settings.setExtent(extent)
    settings.setOutputSize(QSize(1200, 900))
    settings.setBackgroundColor(QColor("white"))
    job = QgsMapRendererParallelJob(settings)
    job.start()
    job.waitForFinished()
    ok = job.renderedImage().save(str(out), "png")
    if ok:
        # 256-colour median-cut palette (Pillow ships with QGIS): about 3x smaller with no
        # visible change, which keeps README images under the 1 MB pre-commit limit
        palette = (
            Image.open(out).convert("RGB").quantize(256, Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
        )
        palette.save(out, optimize=True)
    print(f"{'Rendered' if ok else 'FAILED'} {len(layers)} layers -> {out}")
    return ok


def main() -> int:
    app = QgsApplication([], False)
    app.initQgis()
    project = QgsProject.instance()
    project.read(str(ROOT / "qgis_project" / "fibre_planning.qgz"))
    IMAGES.mkdir(parents=True, exist_ok=True)
    ok = all(render(project, extent, hidden, IMAGES / name) for name, extent, hidden in VIEWS)
    app.exitQgis()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
