"""Kopplingen mellan planhandlingens avsnitt och planens innehåll, i Boverkets tabeller för dokument.

``dokumentreferens_op``: planhandlingen (ett Word-dokument), med ett unikt ``dokumentreferens_id``.
``avsnittsbokmärke``: bokmärkena i dokumentet, med rubriken som text.
``dokumentavsnitt``: en rad per koppling mellan ett avsnitt och ett objekt: avsnittstyp, bokmärke, dokumentet och
objektets ``objektidentitet``. Ett avsnitt kan gälla flera objekt och ett objekt flera avsnitt (många-till-många,
som i Boverkets instruktion). Objektets ``dokument_id`` sätts till dess objektidentitet, och samma värde står i
``dokumentavsnitt.dokument_id``, så att raderna för ett objekt går att hitta från båda håll (en tolkning av mallen,
som inte beskriver kolumnen närmare).

Kopplingarna till hela planen gäller raden i ``oversiktsplan`` (specifikationens ``oversiktsplan.dokument``).
Sparas direkt."""
from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from qgis.core import NULL, QgsFeatureRequest, QgsGeometry, QgsVectorLayer, QgsVectorLayerUtils

from . import model
from .content import plain
from .project import layer_in_group

DOCUMENT_TABLE = "dokumentreferens_op"
BOOKMARK_TABLE = "avsnittsbokmärke"
SECTION_TABLE = "dokumentavsnitt"


@dataclass
class SectionLinks:
    bookmark: str
    heading: str
    type: str
    identities: set[str] = field(default_factory=set)


def _layers_with_identity(group) -> list[QgsVectorLayer]:
    names = [model.OVERSIKTSPLAN.name, *(d.name for d in model.CONTENT_LAYERS)]
    return [layer for layer in (layer_in_group(group, name) for name in names) if layer is not None]


def find_object(group, identity: str):
    """(lager, objekt) med en viss objektidentitet, eller None."""
    request = QgsFeatureRequest().setFilterExpression(f"\"objektidentitet\" = '{identity}'")
    for layer in _layers_with_identity(group):
        feature = next(layer.getFeatures(request), None)
        if feature is not None:
            return layer, feature
    return None


def describe(group, identity: str) -> str:
    """Kort text om ett objekt, för listor: "Klimatrelaterade risker: Risk för ras (Branten)"."""
    found = find_object(group, identity)
    if found is None:
        return f"saknas i planen ({identity[:8]}…)"
    layer, feature = found
    table = layer.customProperty("rita_oversiktsplan/table")
    if table == model.OVERSIKTSPLAN.name:
        return "Hela planen"
    layer_def = model.layer(table)
    value = plain(feature["innehallstyp_varde"]) or "innehållstyp ej vald"
    name = plain(feature["namn"])
    where = " (utan geometri)" if not feature.hasGeometry() else ""
    return f"{layer_def.category.alias}: {value}" + (f" ({name})" if name else "") + where


def plan_identity(group) -> Optional[str]:
    layer = layer_in_group(group, model.OVERSIKTSPLAN.name)
    feature = next(layer.getFeatures(), None) if layer is not None else None
    return plain(feature["objektidentitet"]) if feature is not None else None


def selected_identities(group) -> list[str]:
    """Objektidentiteten för de objekt i planens innehållslager som är markerade i kartan."""
    found = []
    for layer_def in model.CONTENT_LAYERS:
        layer = layer_in_group(group, layer_def.name)
        if layer is not None:
            found += [str(f["objektidentitet"]) for f in layer.selectedFeatures() if plain(f["objektidentitet"])]
    return found


def select_in_map(group, identities: set[str]) -> int:
    """Markerar objekten i kartan (och tar bort annan markering i planens innehållslager). Returnerar antalet."""
    count = 0
    for layer_def in model.CONTENT_LAYERS:
        layer = layer_in_group(group, layer_def.name)
        if layer is None:
            continue
        ids = [f.id() for f in layer.getFeatures() if str(f["objektidentitet"]) in identities]
        layer.selectByIds(ids)
        count += len(ids)
    return count


# -- läsa och spara -----------------------------------------------------------------------------------------------
def _table(group, name: str) -> QgsVectorLayer:
    layer = layer_in_group(group, name)
    if layer is None:
        raise ValueError(f"Tabellen {name} saknas i planen. Öppna planen på nytt.")
    return layer


def find_document(group, path: str | Path):
    """Dokumentets rad i dokumentreferens_op: samma fil (länken), annars samma filnamn."""
    path = Path(path)
    layer = _table(group, DOCUMENT_TABLE)
    rows = list(layer.getFeatures())
    for f in rows:
        if plain(f["lank"]) and Path(str(f["lank"])) == path:
            return f
    return next((f for f in rows if plain(f["namn"]) == path.name), None)


def linked_documents(group) -> list[Path]:
    """Dokumenten (länken i dokumentreferens_op) som planen har kopplingar till, senast sparade först."""
    with_rows = {str(f["dokumentreferens_id"]) for f in _table(group, SECTION_TABLE).getFeatures()}
    def date(value) -> str:
        return value.toString("yyyy-MM-dd") if hasattr(value, "toString") else str(plain(value) or "")

    found = [(date(f["datumangivelse"]), Path(str(f["lank"]))) for f in _table(group, DOCUMENT_TABLE).getFeatures()
             if plain(f["lank"]) and str(f["dokumentreferens_id"]) in with_rows]
    return [path for _, path in sorted(found, key=lambda item: item[0], reverse=True)]


def read_links(group, path: str | Path) -> dict[str, SectionLinks]:
    """Kopplingarna som redan finns för dokumentet, per bokmärke."""
    document = find_document(group, path)
    if document is None:
        return {}
    doc_id = str(document["dokumentreferens_id"])
    headings = {str(f["avsnittsbokmarke_id"]): plain(f["avsnittsbokmarke_text"]) or ""
                for f in _table(group, BOOKMARK_TABLE).getFeatures()}
    links: dict[str, SectionLinks] = {}
    for f in _table(group, SECTION_TABLE).getFeatures():
        if str(f["dokumentreferens_id"]) != doc_id:
            continue
        bookmark = str(f["avsnittsbokmarke_id"])
        entry = links.setdefault(bookmark, SectionLinks(bookmark, headings.get(bookmark, ""),
                                                        plain(f["avsnittstyp_varde"]) or ""))
        if plain(f["objektidentitet"]):
            entry.identities.add(str(f["objektidentitet"]))
    return links


def _commit(layer: QgsVectorLayer, started: bool, what: str) -> None:
    if not layer.commitChanges(started):
        raise ValueError(f"Kunde inte spara {what}: " + "; ".join(layer.commitErrors()))


def save(group, path: str | Path, sections: list[SectionLinks]) -> str:
    """Sparar dokumentet och alla kopplingar för det (de tidigare kopplingarna för dokumentet ersätts). Returnerar
    dokumentets dokumentreferens_id."""
    path = Path(path)
    documents = _table(group, DOCUMENT_TABLE)
    bookmarks = _table(group, BOOKMARK_TABLE)
    rows = _table(group, SECTION_TABLE)
    today = datetime.date.today().isoformat()

    existing = find_document(group, path)
    started = not documents.isEditable() and documents.startEditing()
    values = {"namn": path.name, "kortnamn": "Planhandling", "datumangivelse": today, "lank": str(path)}
    if existing is None:
        doc_id = str(uuid.uuid4())
        values.update({"dokumentreferens_id": doc_id, "identitet": doc_id})
        documents.addFeature(QgsVectorLayerUtils.createFeature(
            documents, QgsGeometry(), {documents.fields().indexOf(k): v for k, v in values.items()}))
    else:
        doc_id = str(existing["dokumentreferens_id"])
        documents.changeAttributeValues(existing.id(), {documents.fields().indexOf(k): v for k, v in values.items()})
    _commit(documents, started, "dokumentet")

    old_rows = [f for f in rows.getFeatures() if str(f["dokumentreferens_id"]) == doc_id]
    names = {str(f["avsnittsbokmarke_id"]) for f in old_rows} | {s.bookmark for s in sections}
    started = not rows.isEditable() and rows.startEditing()
    rows.deleteFeatures([f.id() for f in old_rows])
    for section in sections:
        for identity in sorted(section.identities):
            values = {"avsnittstyp_varde": section.type, "avsnittsbokmarke_id": section.bookmark,
                      "dokumentreferens_id": doc_id, "dokument_id": identity, "objektidentitet": identity}
            rows.addFeature(QgsVectorLayerUtils.createFeature(
                rows, QgsGeometry(), {rows.fields().indexOf(k): v for k, v in values.items()}))
    _commit(rows, started, "dokumentavsnitten")

    started = not bookmarks.isEditable() and bookmarks.startEditing()
    bookmarks.deleteFeatures([f.id() for f in bookmarks.getFeatures() if str(f["avsnittsbokmarke_id"]) in names])
    for section in sections:
        values = {"avsnittsbokmarke_id": section.bookmark, "avsnittsbokmarke_text": section.heading}
        bookmarks.addFeature(QgsVectorLayerUtils.createFeature(
            bookmarks, QgsGeometry(), {bookmarks.fields().indexOf(k): v for k, v in values.items()}))
    _commit(bookmarks, started, "bokmärkena")

    _set_document_ids(group, {i for s in sections for i in s.identities})
    return doc_id


def _set_document_ids(group, identities: set[str]) -> None:
    """Ger objekten med kopplingar ett dokument_id (deras objektidentitet), om de saknar ett."""
    for layer in _layers_with_identity(group):
        changes = {f.id(): str(f["objektidentitet"]) for f in layer.getFeatures()
                   if str(f["objektidentitet"]) in identities and f["dokument_id"] in (None, NULL, "")}
        if not changes:
            continue
        idx = layer.fields().indexOf("dokument_id")
        started = not layer.isEditable() and layer.startEditing()
        for fid, value in changes.items():
            layer.changeAttributeValue(fid, idx, value)
        if started:
            _commit(layer, True, layer.name())
