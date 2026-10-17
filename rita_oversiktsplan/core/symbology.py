"""Ritar planens lager: gruppens symbol (kant, linje och punktform) i värdets färg, ett värde i ÖP-katalogen per
klass (se :mod:`styles` för grupper, färger och varför bara enkla symboler används).

Symbolerna byggs bara av QGIS enkla symbollager: enkel yta, enkel linje och enkel punkt. Ett överlägg är en enkel yta
(svag fyllning) med en enkel linje som kant, eftersom en enkel ytas egen kant inte kan få egna strecklängder. I SLD
blir det en PolygonSymbolizer och en LineSymbolizer med ``stroke-dasharray``, som GeoServer, QGIS Server och
vektortiler återger likadant."""
from __future__ import annotations

from qgis.core import (QgsCategorizedSymbolRenderer, QgsFillSymbol, QgsLineSymbol, QgsMarkerSymbol,
                       QgsRendererCategory, QgsSimpleFillSymbolLayer, QgsSimpleLineSymbolLayer,
                       QgsSingleSymbolRenderer, QgsVectorLayer, QgsWkbTypes)

from . import model, styles
from .styles import Group, Style

UNASSIGNED_LABEL = "Innehållstyp ej vald"
WITHOUT_COMPLEMENT_LABEL = "Utan kompletterande utvecklingsinriktning"
FALLBACK = Style((120, 120, 120))
SIMPLE_LAYER_TYPES = {"SimpleFill", "SimpleLine", "SimpleMarker"}


def apply(layer: QgsVectorLayer, category: model.Category, lookups: dict[str, list[str]]) -> None:
    """Klassar lagret på innehållstyp (Utvecklingsinriktning på kompletterande utvecklingsinriktning) med gruppens
    symbol i en färg per värde i planens uppslagstabell, plus en klass för objekt som ännu saknar värde."""
    field = styles.field_for(category.key)
    group = styles.group_for(category.key)
    values = lookups.get(category.kompletterande if field != styles.DEFAULT_FIELD else category.lookup, [])
    geometry = layer.geometryType()
    categories = []
    for value in values:
        style = styles.style_for(category.key, value) or FALLBACK
        categories.append(QgsRendererCategory(value, symbol(style, group, geometry), value))
    if field == styles.DEFAULT_FIELD:
        empty = symbol(Style(styles.UNASSIGNED_COLOR, filled=False), group, geometry)
        label = UNASSIGNED_LABEL
    else:  # utvecklingsinriktning utan kompletterande värde är tillåten och inte ofärdig
        empty = symbol(Style((226, 85, 58)), group, geometry)
        label = WITHOUT_COMPLEMENT_LABEL
    # Klassen utan värde fångar tomma fält (NULL). Klassningen sker direkt på fältet, inte på ett uttryck, så att
    # SLD-filtren blir vanliga jämförelser (PropertyIsEqualTo, och ElseFilter för klassen utan värde) som GeoServer
    # förstår.
    categories.append(QgsRendererCategory(None, empty, label))
    layer.setRenderer(QgsCategorizedSymbolRenderer(field, categories))


DRAFT_GROUP = Group("1.5;1", 0.8, "circle", label="orange streckad, orange cirkel")


def apply_draft(layer: QgsVectorLayer) -> None:
    """Otilldelad geometri: orange, som innehåll utan vald innehållstyp, så att man ser vad som återstår."""
    layer.setRenderer(QgsSingleSymbolRenderer(symbol(Style(styles.UNASSIGNED_COLOR), DRAFT_GROUP,
                                                     layer.geometryType())))


def symbol(style: Style, group: Group, geometry):
    if geometry == QgsWkbTypes.GeometryType.PolygonGeometry:
        return _fill(style, group)
    if geometry == QgsWkbTypes.GeometryType.LineGeometry:
        return _line(style, group)
    return _marker(style, group)


def _rgb(color, alpha: int = 255) -> str:
    return ",".join(str(c) for c in color) + f",{alpha}"


def _stroke(color, group: Group, width: float | None = None) -> QgsSimpleLineSymbolLayer:
    props = {"line_color": _rgb(color), "line_width": str(width or group.width), "line_width_unit": "MM",
             "capstyle": "flat", "joinstyle": "miter"}
    if group.dash:
        props.update({"use_custom_dash": "1", "customdash": group.dash, "customdash_unit": "MM"})
    return QgsSimpleLineSymbolLayer.create(props)


def _fill(style: Style, group: Group) -> QgsFillSymbol:
    if style.filled:  # markanvändning: heltäckande färg och tunn, mörkare kant
        fill = QgsSimpleFillSymbolLayer.create({"color": _rgb(style.color), "outline_style": "no"})
        return QgsFillSymbol([fill, _stroke(styles.darker(style.color), group)])
    fill = QgsSimpleFillSymbolLayer.create({"color": "0,0,0,0" if group.hollow else _rgb(style.color,
                                                                                        styles.OVERLAY_ALPHA),
                                            "outline_style": "no"})
    return QgsFillSymbol([fill, _stroke(style.color, group)])


def _line(style: Style, group: Group) -> QgsLineSymbol:
    if style.filled:  # markanvändning: kraftig linje i en mörkare ton (färgerna är ljusa) med gruppens strecktyp
        return QgsLineSymbol([_stroke(styles.darker(style.color, 0.65), group, width=1.2)])
    return QgsLineSymbol([_stroke(style.color, group, width=max(group.width, 0.6))])


def _marker(style: Style, group: Group) -> QgsMarkerSymbol:
    if group.hollow:
        fill, outline, outline_width = "0,0,0,0", _rgb(style.color), "0.6"
    elif group.ring:
        fill, outline, outline_width = _rgb(style.color), "255,255,255,255", "0.9"
    else:
        fill, outline, outline_width = _rgb(style.color), _rgb(styles.darker(style.color)), "0.3"
    if group.shape == "cross":  # korset är bara linjer: färgen sitter i kanten
        outline, outline_width = _rgb(style.color), "0.8"
    return QgsMarkerSymbol.createSimple({
        "name": group.shape, "angle": str(group.angle), "color": fill, "outline_color": outline,
        "outline_width": outline_width, "size": "3.8" if group.shape in ("star", "cross") else "3.2"})
