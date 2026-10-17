"""Byggstenar som stegen delar: etiketter, knappar, kort, kartan och notisen längst ner. De flesta är hämtade från
Tagga planbeskrivning i Rita Detaljplan (``pbapp/widgets.py``); kartan är ny och visar översiktsplanens innehåll."""
from __future__ import annotations

import html
from typing import Optional

from qgis.PyQt.QtCore import QPointF, QRectF, Qt, QTimer, pyqtSignal
from qgis.PyQt.QtGui import QBrush, QColor, QIcon, QPainter, QPainterPath, QPainterPathStroker, QPen, QPixmap
from qgis.PyQt.QtWidgets import (QBoxLayout, QFrame, QGridLayout, QHBoxLayout, QLabel, QLayout, QPushButton,
                                 QScrollArea, QSizePolicy, QVBoxLayout, QWidget)

from . import session as ss
from . import theme


def label(text: str = "", name: str = "", wrap: bool = False, rich: bool = False) -> QLabel:
    widget = QLabel(text)
    if name:
        widget.setObjectName(name)
    widget.setWordWrap(wrap)
    widget.setTextFormat(Qt.TextFormat.RichText if rich else Qt.TextFormat.PlainText)
    if wrap:
        widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
    return widget


def button(text: str, kind: str = "", tip: str = "") -> QPushButton:
    widget = QPushButton(text)
    if kind:
        widget.setProperty("kind", kind)
    if tip:
        widget.setToolTip(tip)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    widget.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
    return widget


def box(direction: str, *items, spacing: int = 8, margins=(0, 0, 0, 0)) -> QBoxLayout:
    layout = QVBoxLayout() if direction == "v" else QHBoxLayout()
    layout.setSpacing(spacing)
    layout.setContentsMargins(*margins)
    for item in items:
        if item is None:
            layout.addStretch(1)
        elif isinstance(item, int):
            layout.addSpacing(item)
        elif isinstance(item, QLayout):
            layout.addLayout(item)
        else:
            layout.addWidget(item)
    return layout


def frame(name: str, layout: QBoxLayout) -> QFrame:
    widget = QFrame()
    widget.setObjectName(name)
    widget.setLayout(layout)
    return widget


def scrolled(widget: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setWidget(widget)
    area.setFrameShape(QFrame.Shape.NoFrame)
    return area


def restyle(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def short(text: str, limit: int) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def dot_icon(color: str, square: bool = False) -> QIcon:
    pixmap = QPixmap(12, 12)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(color))
    if square:
        painter.drawRoundedRect(1, 1, 10, 10, 2, 2)
    else:
        painter.drawEllipse(2, 2, 8, 8)
    painter.end()
    return QIcon(pixmap)


class Facts(QWidget):
    """Några uppgifter i rad: liten grå rubrik och värdet under."""

    def __init__(self):
        super().__init__()
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(24)
        self.grid.setVerticalSpacing(2)

    def set(self, items: list[tuple[str, str]]) -> None:
        while self.grid.count():
            self.grid.takeAt(0).widget().deleteLater()
        for column, (name, value) in enumerate(items):
            self.grid.addWidget(label(name, "hint"), 0, column)
            value_label = label(value, "factValue")
            value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.grid.addWidget(value_label, 1, column)
        self.grid.setColumnStretch(len(items), 1)


class Pill(QLabel):
    """Status som en liten etikett med färgad prick."""

    def __init__(self, status: str = "", text: Optional[str] = None):
        super().__init__()
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.set(status, text)

    def set(self, status: str, text: Optional[str] = None, color: Optional[str] = None) -> None:
        text = ss.STATUS_TEXT.get(status, "") if text is None else text
        self.setVisible(bool(text))
        color = color or theme.status_color(status)
        self.setTextFormat(Qt.TextFormat.RichText)
        self.setText(f'<span style="color:{color}">●</span>&nbsp;{html.escape(text)}')
        self.setStyleSheet(f"QLabel {{ color: {color}; background: transparent; border-radius: 9px; padding: 1px 8px; "
                           "font-size: 9pt; font-weight: 600; }")


class TypeChip(QLabel):
    """Avsnittstypen i typens färg."""

    def __init__(self):
        super().__init__()
        self.setWordWrap(True)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)

    def set(self, type_: str, muted: bool = False) -> None:
        color = theme.C["muted"] if muted else theme.type_color(type_)
        self.setText(type_ or "Ingen avsnittstyp")
        self.setStyleSheet(f"QLabel {{ color: {color}; background: {theme.mix(color, .13)}; border-radius: 6px; "
                           "padding: 3px 9px; font-size: 9pt; font-weight: 600; }")


class ObjectChip(QFrame):
    """Ett kopplat objekt: färgruta, namn och ett kryss som tar bort kopplingen."""
    removed = pyqtSignal(str)
    clicked = pyqtSignal(str)

    def __init__(self, obj: ss.PlanObject):
        super().__init__()
        self.identity = obj.identity
        c = theme.C
        swatch = QLabel()
        swatch.setPixmap(dot_icon(c["accent"] if obj.kind == ss.PLAN_KIND else obj.color, square=True).pixmap(12, 12))
        swatch.setFixedSize(14, 14)
        text = label(obj.long_title(), wrap=True)
        text.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        text.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Minimum)
        remove = button("×", "ghost", "Ta bort kopplingen")
        remove.setFixedWidth(30)
        remove.clicked.connect(lambda: self.removed.emit(self.identity))
        layout = box("h", swatch, text, remove, spacing=8, margins=(10, 4, 4, 4))
        layout.setStretch(1, 1)
        self.setLayout(layout)
        self.setToolTip("Klicka för att visa i kartan.")
        self.setStyleSheet(f"ObjectChip {{ background: {c['accent_soft']}; border: 1px solid {theme.mix(c['accent'], .5)}; "
                           "border-radius: 8px; } QLabel { background: transparent; }")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.identity)
        super().mousePressEvent(event)


class _Grip(QLabel):
    """Handtaget under ett stycke: dra för att se mer eller mindre, dubbelklicka för att visa allt eller korta av."""

    def __init__(self, owner: "ParagraphText"):
        super().__init__()
        self.owner = owner
        self.setObjectName("paragraphGrip")
        self.setCursor(Qt.CursorShape.SizeVerCursor)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setToolTip("Dra för att se mer eller mindre av stycket. Dubbelklicka för att visa hela stycket.")
        self._start: Optional[tuple] = None

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._start = (event.globalPosition().y(), self.owner.shown_height())
        event.accept()  # ett klick på handtaget ska inte välja avsnittet

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._start is not None:
            self.owner.set_height(self._start[1] + int(event.globalPosition().y() - self._start[0]))
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._start = None
        event.accept()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        self.owner.toggle()
        event.accept()


class ParagraphText(QWidget):
    """Text ur planhandlingen. Ett långt stycke visas först med de första raderna; handtaget under visar resten."""

    DEFAULT_LINES = 8
    MIN_LINES = 3

    def __init__(self, text: str, name: str = "docText", lines: int = DEFAULT_LINES):
        super().__init__()
        self.lines = lines
        self.label = label(text, name, wrap=True)
        self.label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Minimum)
        self.grip = _Grip(self)
        self.grip.setVisible(False)
        self.setLayout(box("v", self.label, self.grip, spacing=2))
        self._wanted: Optional[int] = None
        self._clipped = False
        self._busy = False

    def set_text(self, text: str) -> None:
        self.label.setText(text)
        self._wanted = None
        self._relayout()

    def _line(self) -> int:
        return max(self.label.fontMetrics().lineSpacing(), 1)

    def full_height(self) -> int:
        width = max(self.label.width() or self.width(), 80)
        flags = Qt.TextFlag.TextWordWrap.value | Qt.AlignmentFlag.AlignLeft.value
        return self.label.fontMetrics().boundingRect(0, 0, width, 1_000_000, flags, self.label.text()).height() + 2

    def shown_height(self) -> int:
        return self.label.height()

    def is_clipped(self) -> bool:
        return self._clipped

    def set_height(self, pixels: int) -> None:
        self._wanted = pixels
        self._relayout()

    def toggle(self) -> None:
        self.set_height(self._line() * self.lines if not self.is_clipped() else self.full_height())

    def _relayout(self) -> None:
        if self._busy:
            return
        self._busy = True
        try:
            full = self.full_height()
            limit = self._line() * self.lines
            long = full > limit + self._line()
            wanted = limit if self._wanted is None else self._wanted
            show = max(min(wanted, full), self._line() * self.MIN_LINES) if long else full
            self._clipped = long and show < full - 1
            if self._clipped:
                self.label.setFixedHeight(show)
            else:
                self.label.setMinimumHeight(0)
                self.label.setMaximumHeight(16_777_215)
            self.grip.setVisible(long)
            if long:
                self.grip.setText("▾  dra eller dubbelklicka för att se hela stycket" if self._clipped
                                  else "▴  dubbelklicka för att korta av stycket")
        finally:
            self._busy = False

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._relayout()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._relayout()


class Card(QFrame):
    """Ett klickbart kort med färgad kant till vänster och markering när det är valt."""
    clicked = pyqtSignal()

    def __init__(self, accent: str = "", clickable: bool = True):
        super().__init__()
        self._accent, self._selected, self._clickable = accent, False, clickable
        if clickable:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus if clickable else Qt.FocusPolicy.NoFocus)
        self._paint()

    def set_accent(self, color: str) -> None:
        self._accent = color
        self._paint()

    def set_selected(self, selected: bool) -> None:
        if selected != self._selected:
            self._selected = selected
            self._paint()

    def _paint(self) -> None:
        c = theme.C
        border = c["accent"] if self._selected else "transparent"
        background = theme.mix(c["accent"], .06, c["page"]) if self._selected else "transparent"
        left = self._accent or "transparent"
        self.setStyleSheet(
            f"Card {{ border: 1.5px solid {border}; border-left: 4px solid {left}; border-radius: 8px; "
            f"background: {background}; }} Card:hover {{ background: {theme.mix(c['fg'], .04, c['page'])}; }}")

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if self._clickable and event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class MapView(QWidget):
    """Planens innehåll, förenklat: ytor, linjer och punkter i sina färger. Det kopplade lyser upp. Klick på ett objekt
    skickar ``clicked`` med objektets identitet. Rullhjulet zoomar, dra för att panorera, dubbelklick visar allt."""
    clicked = pyqtSignal(str)

    POINT_RADIUS = 5
    HIT_PIXELS = 6

    def __init__(self):
        super().__init__()
        self.objects: list[ss.PlanObject] = []
        self.highlighted: set[str] = set()
        self.zoom = 1.0
        self.center: Optional[tuple[float, float]] = None
        self._press = None
        self._dragged = False
        self.setMinimumHeight(240)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)
        self.setToolTip("Klicka på innehåll för att koppla det till avsnittet, eller klicka igen för att ta bort "
                        "kopplingen. Rullhjulet zoomar, dra för att flytta, dubbelklicka för att se hela planen.")

    def set_objects(self, objects: list[ss.PlanObject]) -> None:
        self.objects = [o for o in objects if o.parts and o.kind in ("polygon", "line", "point")]
        self.reset_view()

    def highlight(self, identities) -> None:
        self.highlighted = set(identities or ())
        self.update()

    def reset_view(self) -> None:
        self.zoom = 1.0
        bounds = self.bounds()
        self.center = ((bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2) if bounds else None
        self.update()

    def zoom_to(self, identities) -> None:
        """Visar objekten (till exempel det som är kopplat till avsnittet)."""
        bounds = self.bounds([o for o in self.objects if o.identity in identities])
        full = self.bounds()
        if not bounds or not full:
            return
        span = max(bounds[2] - bounds[0], bounds[3] - bounds[1], 1.0) * 1.3
        self.zoom = max(1.0, min(200.0, max(full[2] - full[0], full[3] - full[1], 1.0) / span))
        self.center = ((bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2)
        self.update()

    def bounds(self, objects=None):
        xs, ys = [], []
        for obj in self.objects if objects is None else objects:
            for part in obj.parts:
                xs += [p[0] for p in part]
                ys += [p[1] for p in part]
        return (min(xs), min(ys), max(xs), max(ys)) if xs else None

    # -- omräkning mellan planens koordinater och skärmen -----------------------------------------------------------
    def _scale(self) -> float:
        bounds = self.bounds()
        if not bounds:
            return 1.0
        margin = 16
        width, height = max(self.width() - 2 * margin, 10), max(self.height() - 2 * margin, 10)
        base = min(width / max(bounds[2] - bounds[0], 1e-9), height / max(bounds[3] - bounds[1], 1e-9))
        return base * self.zoom

    def _point(self, p, scale: float) -> QPointF:
        cx, cy = self.center
        return QPointF(self.width() / 2 + (p[0] - cx) * scale, self.height() / 2 - (p[1] - cy) * scale)

    def _path(self, obj: ss.PlanObject, scale: float) -> QPainterPath:
        path = QPainterPath()
        path.setFillRule(Qt.FillRule.OddEvenFill)  # hål i ytor
        for part in obj.parts:
            if not part:
                continue
            if obj.kind == "point":
                path.addEllipse(self._point(part[0], scale), self.POINT_RADIUS, self.POINT_RADIUS)
                continue
            path.moveTo(self._point(part[0], scale))
            for p in part[1:]:
                path.lineTo(self._point(p, scale))
            if obj.kind == "polygon":
                path.closeSubpath()
        return path

    def _order(self) -> list[ss.PlanObject]:
        """Ritordning: heltäckande ytor, överlägg, linjer, punkter (det som ligger överst träffas först vid klick)."""
        rank = {"polygon": 1, "line": 2, "point": 3}
        return sorted(self.objects, key=lambda o: (rank[o.kind] if not (o.kind == "polygon" and o.filled) else 0))

    def object_at(self, position: QPointF) -> Optional[str]:
        if self.center is None:
            return None
        scale = self._scale()
        stroker = QPainterPathStroker()
        stroker.setWidth(self.HIT_PIXELS * 2)
        for obj in reversed(self._order()):
            path = self._path(obj, scale)
            if obj.kind == "polygon" and path.contains(position):
                return obj.identity
            if obj.kind in ("line", "point") and stroker.createStroke(path).united(path).contains(position):
                return obj.identity
        return None

    # -- händelser ---------------------------------------------------------------------------------------------------
    def wheelEvent(self, event) -> None:  # noqa: N802
        if self.center is None:
            return
        factor = 1.25 if event.angleDelta().y() > 0 else 0.8
        new_zoom = max(0.5, min(500.0, self.zoom * factor))
        scale_before = self._scale()
        pos = event.position()
        # punkten under muspekaren står kvar
        wx = self.center[0] + (pos.x() - self.width() / 2) / scale_before
        wy = self.center[1] - (pos.y() - self.height() / 2) / scale_before
        self.zoom = new_zoom
        scale_after = self._scale()
        self.center = (wx - (pos.x() - self.width() / 2) / scale_after, wy + (pos.y() - self.height() / 2) / scale_after)
        self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._press = (event.position(), self.center)
            self._dragged = False

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._press is None or self.center is None:
            hit = self.object_at(event.position())
            self.setCursor(Qt.CursorShape.PointingHandCursor if hit else Qt.CursorShape.ArrowCursor)
            return
        start, center = self._press
        delta = event.position() - start
        if abs(delta.x()) + abs(delta.y()) > 4:
            self._dragged = True
        if self._dragged:
            scale = self._scale()
            self.center = (center[0] - delta.x() / scale, center[1] + delta.y() / scale)
            self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._press is not None and not self._dragged:
            hit = self.object_at(event.position())
            if hit:
                self.clicked.emit(hit)
        self._press = None

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if self.object_at(event.position()) is None:
            self.reset_view()

    def paintEvent(self, event) -> None:  # noqa: N802
        c = theme.C
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(c["map_bg"]))
        painter.drawRoundedRect(QRectF(self.rect()), 8, 8)
        if self.center is None:
            painter.setPen(QColor(c["muted"]))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Planen har inget innehåll med geometri än.")
            return
        painter.setClipRect(self.rect().adjusted(1, 1, -1, -1))
        scale = self._scale()
        dim = bool(self.highlighted)
        accent = QColor(c["accent"])
        for obj in self._order():
            lit = obj.identity in self.highlighted
            painter.setOpacity(1.0 if lit or not dim else 0.3)
            color = QColor(obj.color)
            path = self._path(obj, scale)
            if obj.kind == "polygon":
                fill = QColor(color)
                fill.setAlpha(210 if obj.filled else 60)
                painter.setBrush(QBrush(fill))
                painter.setPen(QPen(color.darker(140), 0.8) if obj.filled else QPen(color.darker(120), 1.4))
            elif obj.kind == "line":
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(color, 2.2))
            else:
                painter.setBrush(QBrush(color))
                painter.setPen(QPen(QColor("#ffffff"), 1.2))
            painter.drawPath(path)
            if lit:
                painter.setOpacity(1.0)
                painter.setBrush(Qt.BrushStyle.NoBrush if obj.kind != "polygon" else QBrush(QColor(theme.mix(
                    c["accent"], .35, obj.color if obj.filled else c["map_bg"]))))
                painter.setPen(QPen(accent, 3 if obj.kind != "point" else 2.5))
                painter.drawPath(path)
        painter.setOpacity(1.0)


class Toast(QLabel):
    """En kort notis längst ner i fönstret."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("toast")
        self.setWordWrap(True)
        self.setMaximumWidth(560)
        self.hide()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    def show_text(self, text: str, ms: int = 3500) -> None:
        self.setText(text)
        self.adjustSize()
        parent = self.parentWidget()
        self.move((parent.width() - self.width()) // 2, parent.height() - self.height() - 24)
        self.raise_()
        self.show()
        self._timer.start(ms)
