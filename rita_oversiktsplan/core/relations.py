"""Berör annat innehåll: att ett innehåll hänger ihop med ett annat (``berorAnnatInnehall`` i Lantmäteriets
*innehallOP*, en lista med objektidentiteter), till exempel en klimatrisk som berör ett område för bostadsbebyggelse.

I Boverkets tabeller har varje innehåll kolumnen ``beror_annat_innehall_id``, som pekar på rader i tabellen
``innehall_op_beror_annat_innehall`` (``beror_annat_innehall_id`` och det berörda innehållets objektidentitet i
``beror_annat_innehal_uuid``, med mallens stavning). Ändringarna läggs i redigeringsbufferten, som när man ritar."""
from __future__ import annotations

import uuid

from qgis.core import QgsGeometry, QgsVectorLayer, QgsVectorLayerUtils

from .content import plain
from .project import layer_in_group

TABLE = "innehall_op_beror_annat_innehall"
LINK = "beror_annat_innehall_id"
TARGET = "beror_annat_innehal_uuid"


def _table(group) -> QgsVectorLayer:
    layer = layer_in_group(group, TABLE)
    if layer is None:
        raise ValueError(f"Tabellen {TABLE} saknas i planen. Öppna planen på nytt.")
    return layer


def links(group) -> dict[str, set[str]]:
    """``beror_annat_innehall_id`` → objektidentiteterna det berör."""
    found: dict[str, set[str]] = {}
    for row in _table(group).getFeatures():
        link, target = plain(row[LINK]), plain(row[TARGET])
        if link and target:
            found.setdefault(str(link), set()).add(str(target))
    return found


def related(group, layer: QgsVectorLayer, fid: int) -> set[str]:
    """Objektidentiteterna som ett innehåll berör."""
    link = plain(layer.getFeature(fid)[LINK])
    return links(group).get(str(link), set()) if link else set()


def toggle(group, layer: QgsVectorLayer, fid: int, target: str) -> bool:
    """Lägger till kopplingen till ``target`` (en objektidentitet), eller tar bort den om den finns. Returnerar True
    om innehållet nu berör ``target``."""
    feature = layer.getFeature(fid)
    if str(plain(feature["objektidentitet"])) == target:
        raise ValueError("Ett innehåll kan inte beröra sig självt.")
    table = _table(group)
    for started_layer in (layer, table):
        if not started_layer.isEditable():
            started_layer.startEditing()
    link = plain(feature[LINK])
    if not link:
        link = str(uuid.uuid4())
        layer.changeAttributeValue(fid, layer.fields().indexOf(LINK), link)
    existing = [row.id() for row in table.getFeatures()
                if str(plain(row[LINK])) == str(link) and str(plain(row[TARGET])) == target]
    if existing:
        table.deleteFeatures(existing)
        return False
    table.addFeature(QgsVectorLayerUtils.createFeature(
        table, QgsGeometry(), {table.fields().indexOf(LINK): str(link), table.fields().indexOf(TARGET): target}))
    return True
