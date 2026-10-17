"""Kartverktyget "Kopiera innehåll" (som Kopiera bestämmelser i Rita Detaljplan): klicka på ett objekt med innehåll och
sedan på de objekt som ska få samma innehåll (grupp, innehållstyp, kompletterande innehållstyp, sambandsnivå,
precisering och utbyggnadsordning; inte namnet). Målet kan vara otilldelad geometri eller annat innehåll. Verktyget
ligger kvar efter en kopiering så att man kan fortsätta till fler objekt; högerklick eller Esc väljer en ny källa."""
from __future__ import annotations

from typing import Callable, Optional

from qgis.core import Qgis, QgsGeometry, QgsPointXY
from qgis.gui import QgsMapCanvas, QgsMapTool, QgsRubberBand
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor

CLICK_PIXELS = 5
MIN_TOLERANCE = 0.05  # meter


class CopyTool(QgsMapTool):
    def __init__(self, canvas: QgsMapCanvas, on_click: Callable[[QgsPointXY, float], None],
                 on_reset: Callable[[], None]):
        super().__init__(canvas)
        self.on_click, self.on_reset = on_click, on_reset
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._rubber = QgsRubberBand(canvas, Qgis.GeometryType.Polygon)
        self._rubber.setColor(QColor(40, 160, 90, 60))
        self._rubber.setStrokeColor(QColor(40, 160, 90))
        self._rubber.setWidth(2)
        self._targets: list[QgsRubberBand] = []  # det som källan är kopplad till (Berör annat innehåll)

    def tolerance(self) -> float:
        return max(self.canvas().mapUnitsPerPixel() * CLICK_PIXELS, MIN_TOLERANCE)

    def canvasReleaseEvent(self, event):  # noqa: N802 - namnet krävs av Qt
        if event.button() == Qt.MouseButton.LeftButton:
            self.on_click(event.mapPoint(), self.tolerance())
        elif event.button() == Qt.MouseButton.RightButton:
            self.on_reset()

    def keyPressEvent(self, event):  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.on_reset()
            event.accept()
        else:
            super().keyPressEvent(event)

    def deactivate(self):
        self.show_source(None)
        self.show_targets([])
        super().deactivate()

    def show_source(self, geometry: Optional[QgsGeometry], layer=None) -> None:
        """Visar källan i grönt (eller tar bort visningen)."""
        self._rubber.reset(layer.geometryType() if layer is not None else Qgis.GeometryType.Polygon)
        if geometry is not None:
            self._rubber.setToGeometry(QgsGeometry(geometry), layer)

    def show_targets(self, items: list) -> None:
        """Visar objekten källan är kopplad till i blått: ``items`` är (geometri, lager)."""
        canvas = self.canvas()
        for band in self._targets:
            canvas.scene().removeItem(band)
        self._targets = []
        for geometry, layer in items:
            band = QgsRubberBand(canvas, layer.geometryType())
            band.setColor(QColor(30, 110, 200, 50))
            band.setStrokeColor(QColor(30, 110, 200))
            band.setWidth(2)
            band.setToGeometry(QgsGeometry(geometry), layer)
            self._targets.append(band)
