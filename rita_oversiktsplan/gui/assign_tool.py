"""Kartverktyget "Tilldela innehåll": klicka på ritad geometri för att ge den innehåll (som verktyget
Planbestämmelser i Rita Detaljplan). Verktyget är aktivt tills man väljer ett annat, så att man kan tilldela flera
objekt i rad."""
from __future__ import annotations

from typing import Callable

from qgis.core import Qgis, QgsGeometry, QgsPointXY
from qgis.gui import QgsMapCanvas, QgsMapTool, QgsRubberBand
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor

CLICK_PIXELS = 5  # så nära klicket ska en linje eller punkt ligga för att räknas
MIN_TOLERANCE = 0.05  # meter: golv för klicktoleransen om kartan ännu inte är ritad


class AssignTool(QgsMapTool):
    def __init__(self, canvas: QgsMapCanvas, on_click: Callable[[QgsPointXY, float], None]):
        super().__init__(canvas)
        self.on_click = on_click
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._rubber = QgsRubberBand(canvas, Qgis.GeometryType.Polygon)
        self._rubber.setColor(QColor(30, 110, 200, 50))
        self._rubber.setStrokeColor(QColor(30, 110, 200))
        self._rubber.setWidth(2)

    def canvasReleaseEvent(self, event):  # noqa: N802 - namnet krävs av Qt
        if event.button() == Qt.MouseButton.LeftButton:
            self.click(event.mapPoint())

    def deactivate(self):
        self.clear_highlight()
        super().deactivate()

    def tolerance(self) -> float:
        return max(self.canvas().mapUnitsPerPixel() * CLICK_PIXELS, MIN_TOLERANCE)

    def click(self, point: QgsPointXY) -> None:
        try:
            self.on_click(point, self.tolerance())
        finally:
            self.clear_highlight()

    def highlight(self, layer, fid: int) -> None:
        """Markerar objektet som dialogen gäller."""
        self.clear_highlight()
        feature = layer.getFeature(fid)
        if not feature.isValid():
            return
        self._rubber.reset(layer.geometryType())
        self._rubber.setToGeometry(QgsGeometry(feature.geometry()), layer)

    def clear_highlight(self) -> None:
        self._rubber.reset(Qgis.GeometryType.Polygon)
