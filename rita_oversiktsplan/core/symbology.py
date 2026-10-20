"""Ritar planens lager: gruppens symbol (kant, linje och punktform) i värdets färg, ett värde i ÖP-katalogen per
klass (se :mod:`styles` för grupper, färger och varför bara enkla symboler används).

Symbolerna byggs av QGIS enkla symbollager: enkel yta, enkel linje och enkel punkt. Ett överlägg är en enkel yta
(svag fyllning) med en enkel linje som kant, eftersom en enkel ytas egen kant inte kan få egna strecklängder. I SLD
blir det en PolygonSymbolizer och en LineSymbolizer med ``stroke-dasharray``, som GeoServer, QGIS Server och
vektortiler återger likadant.

Undantaget är utvecklingsinriktningens pilspetsar: en punkt (triangel) i linjens ände, som QGIS ritar med en
punktlinje. QGIS skriver den i SLD med en egen inställning som GeoServer inte förstår; :mod:`sld` gör om den till
GeoServers sätt (``endPoint``/``endAngle``).

Utvecklingsinriktningen klassas med regler i två steg: tema (kompletterande utvecklingsinriktning) och storlek
(sambandsnivå). Filtren är vanliga jämförelser, så att SLD-filen bara innehåller standardfilter."""
from __future__ import annotations

from typing import Optional

from qgis.core import (Qgis, QgsCategorizedSymbolRenderer, QgsEditorWidgetSetup, QgsExpression, QgsFillSymbol, QgsLineSymbol,
                       QgsMarkerLineSymbolLayer, QgsMarkerSymbol, QgsPalLayerSettings, QgsRendererCategory,
                       QgsRuleBasedRenderer, QgsSimpleFillSymbolLayer, QgsSimpleLineSymbolLayer,
                       QgsSimpleMarkerSymbolLayer, QgsSingleSymbolRenderer, QgsTextBufferSettings, QgsTextFormat,
                       QgsVectorLayer, QgsVectorLayerSimpleLabeling, QgsWkbTypes)
from qgis.PyQt.QtGui import QColor

from . import model, styles
from .styles import Group, Level, Style

UNASSIGNED_LABEL = "Innehållstyp ej vald"
WITHOUT_COMPLEMENT_LABEL = "Utan kompletterande utvecklingsinriktning"
FALLBACK = Style((120, 120, 120))
SIMPLE_LAYER_TYPES = {"SimpleFill", "SimpleLine", "SimpleMarker"}
ARROW_LAYER_TYPE = "MarkerLine"  # bara för utvecklingsinriktningens pilspetsar
DEVELOPMENT = "utvecklingsinriktning"
LAND_USE = "markochvattenanvandning"
STAGE_FIELD = "utbyggnadsordning"
NAME_FIELD = "namn"


def apply(layer: QgsVectorLayer, category: model.Category, lookups: dict[str, list[str]], stages=()) -> None:
    """Sätter lagrets symboler, namnetiketter och skalgräns. ``stages`` är planens etapper i utbyggnadsordningen
    (``utbyggnad.Stage``), som syns på mark- och vattenanvändningens ytor."""
    if category.key == DEVELOPMENT:
        apply_development(layer, lookups.get(category.kompletterande, []))
    elif stages and category.key == LAND_USE and layer.geometryType() == QgsWkbTypes.GeometryType.PolygonGeometry:
        apply_stages(layer, category, lookups, stages)
    else:
        _apply_categorized(layer, category, lookups)
    apply_labels(layer, category, stages)
    apply_scale(layer, category)


def set_stage_widget(layer: QgsVectorLayer, stages) -> None:
    """Fältet utbyggnadsordning blir en lista med planens etapper (och tomt = ingen etapp) i formulär och tabell.
    Utan etapper är det fritext."""
    index = layer.fields().indexOf(STAGE_FIELD)
    if index < 0:
        return
    if not stages:
        layer.setEditorWidgetSetup(index, QgsEditorWidgetSetup("TextEdit", {"IsMultiline": True}))
        return
    choices = [{"Ingen etapp (befintligt)": "{2839923C-8B7D-419E-B84B-CA2FE9B80EC7}"}]  # QGIS tecken för NULL
    choices += [{stage.label: stage.label} for stage in stages]
    layer.setEditorWidgetSetup(index, QgsEditorWidgetSetup("ValueMap", {"map": choices}))


def apply_stages(layer: QgsVectorLayer, category: model.Category, lookups: dict[str, list[str]], stages) -> None:
    """Mark- och vattenanvändning med utbyggnadsordning: en regel per värde, med en underregel för ytor utan etapp
    (som förut) och en per etapp, där färgen går från mörk (första etappen) till ljus (sista) och kanten är kraftig och
    streckad. Bara vanliga jämförelser i filtren, så att stilen fungerar i GeoServer."""
    field = styles.field_for(category.key)
    group = styles.group_for(category.key)
    stage_field = QgsExpression.quotedColumnRef(STAGE_FIELD)
    labels = [stage.label for stage in stages]
    listed = ", ".join(QgsExpression.quotedValue(label) for label in labels)
    without = f"({stage_field} IS NULL OR NOT ({stage_field} IN ({listed})))"
    root = QgsRuleBasedRenderer.Rule(None)
    for value in [*lookups.get(category.lookup, []), None]:
        style = (styles.style_for(category.key, value) or FALLBACK) if value else Style(styles.UNASSIGNED_COLOR)
        rule = QgsRuleBasedRenderer.Rule(None, 0, 0, _equals(field, value), value or UNASSIGNED_LABEL)
        rule.appendChild(QgsRuleBasedRenderer.Rule(symbol(style, group, layer.geometryType()), 0, 0, without,
                                                   "Ingen etapp (befintligt)"))
        for index, label in enumerate(labels):
            color = styles.stage_color(style.color, index, len(labels))
            fill = QgsSimpleFillSymbolLayer.create({"color": _rgb(color, styles.LAND_USE_ALPHA),
                                                    "outline_style": "no"})
            edge = _stroke(styles.darker(style.color), Group(styles.STAGE_DASH, styles.STAGE_EDGE, group.shape))
            rule.appendChild(QgsRuleBasedRenderer.Rule(QgsFillSymbol([fill, edge]), 0, 0,
                                                       _equals(STAGE_FIELD, label), label))
        root.appendChild(rule)
    layer.setRenderer(QgsRuleBasedRenderer(root))


def _apply_categorized(layer: QgsVectorLayer, category: model.Category, lookups: dict[str, list[str]]) -> None:
    """Klassar lagret på innehållstyp med gruppens symbol i en färg per värde i planens uppslagstabell, plus en klass
    för objekt som ännu saknar värde."""
    field = styles.field_for(category.key)
    group = styles.group_for(category.key)
    values = lookups.get(category.lookup, [])
    geometry = layer.geometryType()
    if group.band and geometry == QgsWkbTypes.GeometryType.PolygonGeometry:
        _apply_band_steps(layer, field, group, category.key, values)
        return
    categories = []
    for value in values:
        style = styles.style_for(category.key, value) or FALLBACK
        categories.append(QgsRendererCategory(value, symbol(style, group, geometry), value))
    empty = symbol(Style(styles.UNASSIGNED_COLOR, filled=False), group, geometry)
    # Klassen utan värde fångar tomma fält (NULL). Klassningen sker direkt på fältet, inte på ett uttryck, så att
    # SLD-filtren blir vanliga jämförelser (PropertyIsEqualTo, och ElseFilter för klassen utan värde) som GeoServer
    # förstår.
    categories.append(QgsRendererCategory(None, empty, UNASSIGNED_LABEL))
    layer.setRenderer(QgsCategorizedSymbolRenderer(field, categories))


def _apply_band_steps(layer: QgsVectorLayer, field: str, group: Group, key: str, values: list[str]) -> None:
    """Ytor med bård (kommunens ställningstagande till riksintressena): en regel per värde, med en underregel per
    skalsteg (``styles.BAND_STEPS``) där bården blir smalare ju längre man zoomar ut, plus en regel för objekt utan
    värde."""
    root = QgsRuleBasedRenderer.Rule(None)
    for value in [*values, None]:
        style = (styles.style_for(key, value) or FALLBACK) if value else Style(styles.UNASSIGNED_COLOR)
        rule = QgsRuleBasedRenderer.Rule(None, 0, 0, _equals(field, value), value or UNASSIGNED_LABEL)
        for inner, outer, band, edge in styles.BAND_STEPS:
            # Rule(symbol, mest inzoomade skala, mest utzoomade skala, …)
            label = f"bård {band:g} mm"
            rule.appendChild(QgsRuleBasedRenderer.Rule(band_symbol(style, group, band, group.width * edge), inner,
                                                       outer, "", label))
        root.appendChild(rule)
    layer.setRenderer(QgsRuleBasedRenderer(root))


# -- utvecklingsinriktningen ------------------------------------------------------------------------------------------
def _equals(field: str, value: Optional[str]) -> str:
    quoted = QgsExpression.quotedColumnRef(field)
    return f"{quoted} IS NULL" if value is None else f"{quoted} = {QgsExpression.quotedValue(value)}"


def level_filter(level: Level) -> str:
    parts = [_equals(styles.LEVEL_FIELD, value) for value in level.values]
    if level.include_empty:
        parts.append(_equals(styles.LEVEL_FIELD, None))
    # parenteser: QGIS sätter ihop temats och nivåns filter med AND utan parenteser när stilen skrivs till SLD
    return "(" + " OR ".join(parts) + ")"


def apply_development(layer: QgsVectorLayer, themes: list[str]) -> None:
    """Ett schema för hela kommunen: en regel per tema (kompletterande utvecklingsinriktning, och en för objekt utan)
    med en underregel per storlek (sambandsnivå), som i sin tur har en symbol för kommunkartan och en mindre för
    inzoomad karta (från 1:50 000). Skalgränserna följer med till SLD (Min-/MaxScaleDenominator).

    Linjernas pilspetsar är egna underregler som läser fältet ``rita_pilar`` (tomt = temats standard), så att valet i
    Tilldela innehåll styr dem med vanliga filter."""
    root = QgsRuleBasedRenderer.Rule(None)
    geometry = layer.geometryType()
    field = styles.field_for(DEVELOPMENT)
    for value in [*themes, None]:
        style = (styles.style_for(DEVELOPMENT, value) or FALLBACK) if value else styles.DEVELOPMENT_NONE
        theme = QgsRuleBasedRenderer.Rule(None, 0, 0, _equals(field, value), value or WITHOUT_COMPLEMENT_LABEL)
        arrows = styles.arrows_for(value)
        for level in styles.DEVELOPMENT_LEVELS:
            sized = QgsRuleBasedRenderer.Rule(None, 0, 0, level_filter(level),
                                              f"{value or 'Utan tema'}, {level.label.lower()}")
            zoom = styles.DEVELOPMENT_ZOOM_SCALE
            # Rule(symbol, mest inzoomade skala, mest utzoomade skala, …): kommunkartan syns bortom 1:50 000,
            # den mindre symbolen när man zoomat in förbi 1:50 000
            for factor, maximum, minimum, label in ((1.0, zoom, 0, "kommunkarta"),
                                                    (styles.DEVELOPMENT_ZOOM_FACTOR, 0, zoom, "inzoomad")):
                scaled = QgsRuleBasedRenderer.Rule(development_symbol(style, level, geometry, factor=factor),
                                                   maximum, minimum, "", label)
                if geometry == QgsWkbTypes.GeometryType.LineGeometry:
                    width = band_width(level, factor)
                    for placement, angle, text, wanted in (
                            (Qgis.MarkerLinePlacement.LastVertex, 90, "pil där linjen slutar", arrow_filter(True, arrows)),
                            (Qgis.MarkerLinePlacement.FirstVertex, 270, "pil där linjen börjar",
                             arrow_filter(False, arrows))):
                        scaled.appendChild(QgsRuleBasedRenderer.Rule(
                            QgsLineSymbol([_arrowhead(style.color, width, placement, angle)]), 0, 0, wanted, text))
                sized.appendChild(scaled)
            theme.appendChild(sized)
        root.appendChild(theme)
    layer.setRenderer(QgsRuleBasedRenderer(root))


def arrow_filter(end: bool, theme_arrows: str) -> str:
    """Filtret för pilen i linjens slut (``end``) eller början, utifrån fältet ``rita_pilar`` och temats standard
    (``theme_arrows``) när fältet är tomt. Parenteser, eftersom QGIS sätter ihop filtren med AND i SLD."""
    own = (model.ARROW_END, model.ARROW_BOTH) if end else (model.ARROW_START, model.ARROW_BOTH)
    parts = [_equals(model.ARROW_FIELD, value) for value in own]
    if end or theme_arrows == styles.BOTH:  # tomt fält: alla teman har pil i slutet, vissa även i början
        parts.append(_equals(model.ARROW_FIELD, None))
    return "(" + " OR ".join(parts) + ")"


def band_width(level: Level, factor: float = 1.0) -> float:
    return _mm(max(level.line_width * factor, styles.MIN_BAND))


def development_symbol(style: Style, level: Level, geometry, factor: float = 1.0):
    """Symbolen för ett tema och en nivå (för linjer bara bandet; pilspetsarna är egna regler). ``factor`` krymper
    den för inzoomad karta."""
    color = style.color
    group = styles.group_for(DEVELOPMENT)
    if geometry == QgsWkbTypes.GeometryType.PolygonGeometry:
        fill = QgsSimpleFillSymbolLayer.create({"color": _rgb(color, styles.DEVELOPMENT_AREA_ALPHA),
                                                "outline_style": "no"})
        edge = level.edge_width * max(factor, 0.6)
        soft = [QgsSimpleLineSymbolLayer.create({
            "line_color": _rgb(color, alpha), "line_width": str(_mm(edge * width)), "line_width_unit": "MM",
            "capstyle": "round", "joinstyle": "round"}) for width, alpha in styles.SOFT_EDGE]
        return QgsFillSymbol([fill, *soft])
    if geometry == QgsWkbTypes.GeometryType.LineGeometry:
        band = QgsSimpleLineSymbolLayer.create({
            "line_color": _rgb(color, styles.DEVELOPMENT_ALPHA), "line_width": str(band_width(level, factor)),
            "line_width_unit": "MM", "capstyle": "flat", "joinstyle": "round"})
        return QgsLineSymbol([band])
    # nod: en ring kring en prick
    size = _mm(max(level.node_size * factor, styles.MIN_NODE))
    ring = QgsSimpleMarkerSymbolLayer.create({
        "name": "circle", "color": "0,0,0,0", "outline_color": _rgb(color, styles.DEVELOPMENT_ALPHA + 60),
        "outline_width": str(_mm(size * 0.12)), "size": str(size)})
    dot = QgsSimpleMarkerSymbolLayer.create({
        "name": "circle", "color": _rgb(color), "outline_color": "255,255,255,255", "outline_width": "0.4",
        "size": str(_mm(max(size * 0.38, 1.6)))})
    return QgsMarkerSymbol([ring, dot])


def _mm(value: float) -> float:
    return round(value, 2)


def _arrowhead(color, band_width: float, placement, angle: int) -> QgsMarkerLineSymbolLayer:
    """En fylld triangel i linjens ände, vriden längs linjen (90° pekar framåt, 270° bakåt)."""
    head = QgsMarkerLineSymbolLayer(True)
    head.setPlacements(placement)
    head.setSubSymbol(QgsMarkerSymbol.createSimple({
        "name": "triangle", "angle": str(angle), "color": _rgb(styles.darker(color, 0.85)), "outline_style": "no",
        "size": str(_mm(max(band_width * styles.ARROW_FACTOR, styles.MIN_ARROW)))}))
    return head


# -- etiketter och skala ----------------------------------------------------------------------------------------------
def apply_labels(layer: QgsVectorLayer, category: model.Category, stages=()) -> None:
    """Innehållets namn i kartan (som områdesbeteckningar i en tryckt översiktsplan): mörk text med vit kant.
    Utvecklingsinriktningens namn syns alltid, övriga från 1:100 000."""
    if layer.fields().indexOf(NAME_FIELD) < 0:
        return
    group = styles.group_for(category.key) if category.key != DEVELOPMENT else None
    if group is not None and group.names == "none":  # plangeometrin: bara en gräns, namnet behövs inte i kartan
        layer.setLabelsEnabled(False)
        return
    text = QgsTextFormat()
    text.setSize(10 if category.key == DEVELOPMENT else 8.5)
    text.setColor(QColor(40, 40, 40))
    buffer = QgsTextBufferSettings()
    buffer.setEnabled(True)
    buffer.setSize(0.8)
    buffer.setColor(QColor(255, 255, 255))
    text.setBuffer(buffer)
    settings = QgsPalLayerSettings()
    if stages and category.key == LAND_USE and layer.fields().indexOf(STAGE_FIELD) >= 0:
        # namnet och etappen på var sin rad, så att utbyggnadsordningen går att läsa i kartan
        name, stage = QgsExpression.quotedColumnRef(NAME_FIELD), QgsExpression.quotedColumnRef(STAGE_FIELD)
        settings.fieldName = f"trim(coalesce({name}, '') || if({stage} IS NULL, '', '\n' || {stage}))"
        settings.isExpression = True
    elif group is not None and group.value_in_label:  # "Vänern – Turism och rörligt friluftsliv", eller bara värdet
        field = QgsExpression.quotedColumnRef(styles.field_for(category.key))
        settings.fieldName = f"coalesce({QgsExpression.quotedColumnRef(NAME_FIELD)} || ' – ', '') || {field}"
        settings.isExpression = True
    else:
        settings.fieldName = NAME_FIELD
    settings.setFormat(text)
    geometry = layer.geometryType()
    if geometry == QgsWkbTypes.GeometryType.PolygonGeometry and group is not None and group.names == "perimeter":
        settings.placement = Qgis.LabelPlacement.PerimeterCurved  # längs kanten, i bården
    elif geometry == QgsWkbTypes.GeometryType.PolygonGeometry:
        settings.placement = Qgis.LabelPlacement.Horizontal
    elif geometry == QgsWkbTypes.GeometryType.LineGeometry:
        settings.placement = Qgis.LabelPlacement.Curved
    else:
        settings.placement = Qgis.LabelPlacement.OrderedPositionsAroundPoint
    if category.key != DEVELOPMENT:
        settings.scaleVisibility = True
        settings.minimumScale = styles.LABEL_SCALE  # QGIS: den mest utzoomade skalan där etiketten syns
        settings.maximumScale = 0
    layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
    layer.setLabelsEnabled(True)


def apply_scale(layer: QgsVectorLayer, category: model.Category) -> None:
    """Punkter och linjer är detaljer och syns först från 1:25 000, så att kommunkartan inte blir grötig.
    Utvecklingsinriktningen är gjord för kommunkartan och syns i alla skalor, liksom alla ytor."""
    detail = layer.geometryType() != QgsWkbTypes.GeometryType.PolygonGeometry and category.key != DEVELOPMENT
    layer.setScaleBasedVisibility(detail)
    if detail:
        layer.setMinimumScale(styles.DETAIL_SCALE)  # den mest utzoomade skalan där lagret syns
        layer.setMaximumScale(0)


# -- att tilldela -----------------------------------------------------------------------------------------------------
DRAFT_GROUP = Group("1.5;1", 0.8, "circle", label="orange streckad, orange cirkel")


def apply_draft(layer: QgsVectorLayer) -> None:
    """Otilldelad geometri: orange, som innehåll utan vald innehållstyp, så att man ser vad som återstår."""
    layer.setRenderer(QgsSingleSymbolRenderer(symbol(Style(styles.UNASSIGNED_COLOR), DRAFT_GROUP,
                                                     layer.geometryType())))


# -- symboler ---------------------------------------------------------------------------------------------------------
def symbol(style: Style, group: Group, geometry):
    if geometry == QgsWkbTypes.GeometryType.PolygonGeometry:
        return _fill(style, group)
    if geometry == QgsWkbTypes.GeometryType.LineGeometry:
        return _line(style, group)
    return _marker(style, group)


def _rgb(color, alpha: int = 255) -> str:
    return ",".join(str(c) for c in color) + f",{min(alpha, 255)}"


def _stroke(color, group: Group, width: float | None = None) -> QgsSimpleLineSymbolLayer:
    props = {"line_color": _rgb(color), "line_width": str(width or group.width), "line_width_unit": "MM",
             "capstyle": "flat", "joinstyle": "miter"}
    if group.dash:
        props.update({"use_custom_dash": "1", "customdash": group.dash, "customdash_unit": "MM"})
    return QgsSimpleLineSymbolLayer.create(props)


def _fill(style: Style, group: Group) -> QgsFillSymbol:
    if style.filled:  # befintlig markanvändning: bara färg som täcker till 80 procent, ingen kant (användarens önskan)
        fill = QgsSimpleFillSymbolLayer.create({"color": _rgb(style.color, styles.LAND_USE_ALPHA),
                                                "outline_style": "no"})
        return QgsFillSymbol([fill])
    if group.band:
        return band_symbol(style, group, group.band, group.width)
    fill = QgsSimpleFillSymbolLayer.create({"color": "0,0,0,0" if group.hollow else _rgb(style.color,
                                                                                        styles.OVERLAY_ALPHA),
                                            "outline_style": "no"})
    return QgsFillSymbol([fill, _stroke(style.color, group)])


def band_symbol(style: Style, group: Group, band: float, edge: float) -> QgsFillSymbol:
    """En mycket svag fyllning, en bred halvgenomskinlig bård innanför kanten (positiv förskjutning = inåt) och en tunn
    kant."""
    fill = QgsSimpleFillSymbolLayer.create({"color": _rgb(style.color, styles.BAND_FILL_ALPHA), "outline_style": "no"})
    inner = QgsSimpleLineSymbolLayer.create({
        "line_color": _rgb(style.color, styles.BAND_ALPHA), "line_width": str(band), "line_width_unit": "MM",
        "offset": str(band / 2), "offset_unit": "MM", "capstyle": "flat", "joinstyle": "miter"})
    return QgsFillSymbol([fill, inner, _stroke(style.color, group, width=edge)])


def _line(style: Style, group: Group) -> QgsLineSymbol:
    if style.filled:  # markanvändning: kraftig linje i en mörkare ton (färgerna är ljusa) med gruppens strecktyp
        return QgsLineSymbol([_stroke(style.line or styles.darker(style.color, 0.65), group, width=1.2)])
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
