"""Kartverktyget "Markera" (som i Rita Detaljplan): klicka eller dra en rektangel för att markera planens innehåll och
det som ska tilldelas, oavsett vilket lager som är valt. Ctrl-klick eller Skift-klick lägger till i markeringen (en
rektangel likaså). Högerklick avmarkerar allt."""
from __future__ import annotations

from typing import Callable

from qgis.core import Qgis, QgsGeometry, QgsPointXY, QgsRectangle
from qgis.gui import QgsMapCanvas, QgsMapTool, QgsRubberBand
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor

CLICK_PIXELS = 5
DRAG_PIXELS = 4  # kortare drag än så räknas som ett klick, inte en rektangel
MIN_TOLERANCE = 0.05  # meter
ADD_MODIFIERS = Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.ControlModifier


class SelectTool(QgsMapTool):
    def __init__(self, canvas: QgsMapCanvas, on_click: Callable[[QgsPointXY, float, bool], None],
                 on_rect: Callable[[QgsRectangle, bool], None], on_clear: Callable[[], None]):
        super().__init__(canvas)
        self.on_click, self.on_rect, self.on_clear = on_click, on_rect, on_clear
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._start = None
        self._frame = QgsRubberBand(canvas, Qgis.GeometryType.Polygon)
        self._frame.setColor(QColor(30, 110, 200, 40))
        self._frame.setStrokeColor(QColor(30, 110, 200))
        self._frame.setWidth(1)

    def tolerance(self) -> float:
        return max(self.canvas().mapUnitsPerPixel() * CLICK_PIXELS, MIN_TOLERANCE)

    def canvasPressEvent(self, event):  # noqa: N802 - namnet krävs av Qt
        if event.button() == Qt.MouseButton.LeftButton:
            self._start = event.mapPoint()

    def canvasMoveEvent(self, event):  # noqa: N802
        if self._start is not None:
            self._frame.setToGeometry(QgsGeometry.fromRect(QgsRectangle(self._start, event.mapPoint())), None)

    def canvasReleaseEvent(self, event):  # noqa: N802
        if event.button() == Qt.MouseButton.RightButton:
            self.on_clear()
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        start, self._start = self._start, None
        self._frame.reset(Qgis.GeometryType.Polygon)
        if start is None:
            return
        point = event.mapPoint()
        add = bool(event.modifiers() & ADD_MODIFIERS)
        if start.distance(point) > self.canvas().mapUnitsPerPixel() * DRAG_PIXELS:
            self.on_rect(QgsRectangle(start, point), add)
        else:
            self.on_click(point, self.tolerance(), add)

    def deactivate(self):
        self._start = None
        self._frame.reset(Qgis.GeometryType.Polygon)
        super().deactivate()
