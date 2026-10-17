"""Planens underlag (``underlag`` i Lantmäteriets *oversiktsplan*: minst ett krävs), i Boverkets tabeller.

Varje underlag är ett dokument med en underlagstyp ur ÖP-katalogen (Planeringsunderlag, Miljökonsekvensbeskrivning
…). I tabellerna:

* ``oversiktsplan_underlag``: en rad per underlagstyp, med ett eget ``underlag_id``,
* ``oversiktsplan_underlag_underlag``: kopplar underlaget (``underlag_id``) till dess dokument (``dokumentreferens_id``),
* ``dokumentreferens_op``: dokumentet (namn, länk, datum). Kortnamnet är underlagstypen, så att exporten kan säga vad
  dokumentet avser.

Flera dokument med samma underlagstyp hamnar under samma underlag, som i specifikationen (``underlagstyp`` och en
lista med dokument). Planens kolumn ``underlag_id`` lämnas tom: den kan bara peka på ett underlag, och exporten tar då
med alla (en tolkning av Boverkets mall). Sparas direkt, som resten av Planens uppgifter."""
from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass
from typing import Optional

from qgis.core import QgsGeometry, QgsVectorLayerUtils

from .content import _py_date, plain
from .project import layer_in_group

UNDERLAG_TABLE = "oversiktsplan_underlag"
LINK_TABLE = "oversiktsplan_underlag_underlag"
DOCUMENT_TABLE = "dokumentreferens_op"


@dataclass
class Underlag:
    typ: str  # underlagstyp ur ÖP-katalogen
    namn: str  # dokumentets namn
    lank: str = ""  # webbadress eller sökväg till dokumentet
    datum: Optional[datetime.date] = None


def _date(value) -> Optional[datetime.date]:
    try:
        return _py_date(value)
    except ValueError:  # datumangivelsen är fri text i mallen
        return None


def _table(group, name: str):
    layer = layer_in_group(group, name)
    if layer is None:
        raise ValueError(f"Tabellen {name} saknas i planen. Öppna planen på nytt.")
    return layer


def read_underlag(group) -> list[Underlag]:
    """Planens underlag, ett per dokument, i underlagstypernas ordning."""
    types = {plain(f["underlag_id"]): plain(f["underlagstyp_varde"]) or ""
             for f in _table(group, UNDERLAG_TABLE).getFeatures() if plain(f["underlag_id"])}
    documents = {plain(f["dokumentreferens_id"]): f for f in _table(group, DOCUMENT_TABLE).getFeatures()
                 if plain(f["dokumentreferens_id"])}
    result = []
    for link in _table(group, LINK_TABLE).getFeatures():
        typ = types.get(plain(link["underlag_id"]))
        document = documents.get(plain(link["dokumentreferens_id"]))
        if typ is None or document is None:
            continue
        result.append(Underlag(typ, plain(document["namn"]) or "", plain(document["lank"]) or "",
                               _date(document["datumangivelse"])))
    return result


def _commit(layer, started: bool) -> None:
    if not layer.commitChanges(started):
        raise ValueError(f"Kunde inte spara {layer.name()}: " + "; ".join(layer.commitErrors()))


def _add(layer, values: dict) -> None:
    layer.addFeature(QgsVectorLayerUtils.createFeature(
        layer, QgsGeometry(), {layer.fields().indexOf(k): v for k, v in values.items()}))


def save_underlag(group, items: list[Underlag]) -> int:
    """Ersätter planens underlag med ``items`` (tomma rader hoppas över). Returnerar antalet dokument."""
    items = [i for i in items if i.typ and i.namn.strip()]
    underlag, links, documents = (_table(group, UNDERLAG_TABLE), _table(group, LINK_TABLE),
                                  _table(group, DOCUMENT_TABLE))
    old_links = list(links.getFeatures())
    old_documents = {plain(f["dokumentreferens_id"]) for f in old_links}
    started = [not layer.isEditable() and layer.startEditing() for layer in (underlag, links, documents)]
    underlag.deleteFeatures([f.id() for f in underlag.getFeatures()])
    links.deleteFeatures([f.id() for f in old_links])
    documents.deleteFeatures([f.id() for f in documents.getFeatures()
                              if plain(f["dokumentreferens_id"]) in old_documents])
    ids: dict[str, str] = {}
    for item in items:
        if item.typ not in ids:
            ids[item.typ] = str(uuid.uuid4())
            _add(underlag, {"underlag_id": ids[item.typ], "underlagstyp_varde": item.typ})
        doc_id = str(uuid.uuid4())
        _add(documents, {"dokumentreferens_id": doc_id, "identitet": doc_id, "namn": item.namn.strip(),
                         "kortnamn": item.typ, "lank": item.lank.strip() or None,
                         "datumangivelse": item.datum.isoformat() if item.datum else None})
        _add(links, {"underlag_id": ids[item.typ], "dokumentreferens_id": doc_id})
    for layer, was_started in zip((underlag, links, documents), started):
        _commit(layer, was_started)
    return len(items)
