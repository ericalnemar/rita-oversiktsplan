"""Ändring av översiktsplanen: ett eget planärende för en del av planen, med eget beslut och egen planhändelse.

Lantmäteriets specifikation (Översiktsplan 1.0 test 4) har stöd för det:

* ``innehallOP.planhandelse`` är innehållets egen planhändelse, som kan skilja sig från planens;
* ``innehallOP.datumPaborjat`` är "datum för kommunens beslut att påbörja ändring av översiktsplan" (saknas det
  gäller planens datum);
* ``innehallOP.underErsattning`` markerar innehåll i den gällande planen som en påbörjad ändring avser att ersätta;
* ett ``beslutOP`` påverkar antingen översiktsplanen eller innehåll (OP-JSON-005): ändringens beslut påverkar det
  innehåll som ändringen gäller (innehållets ``beslut``).

Så här gör pluginet (en tolkning av specifikationen, eftersom den inte beskriver arbetsgången):

* En ändring är en rad i tabellen ``beslut_op`` (rubrik, diarienummer och, när den antagits, datumen). Den ändring som
  pågår står i planens metadata (``andring_*``), tillsammans med datum påbörjat och ändringens planhändelse.
* Medan ändringen pågår får nytt innehåll ändringens planhändelse, datum påbörjat och beslut. Befintligt innehåll kan
  läggas till i ändringen (det ändras) eller markeras *under ersättning* (det ska ersättas av nytt innehåll).
* Exporten tar inte med beslutet, eller innehållets hänvisning till det, förrän beslutet har ett datum.
* När ändringen antas får dess innehåll planhändelsen *Antagen* och beslutets datum, och innehållet under ersättning
  kan tas bort. Ändringarna läggs i redigeringsbufferten om lagret redigeras, annars sparas de direkt.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Optional

from qgis.core import NULL, QgsGeometry, QgsVectorLayerUtils
from qgis.PyQt.QtCore import QDate

from . import model
from .project import layer_in_group, plan_storage

KEYS = {"beslut": "andring_beslut", "paborjat": "andring_paborjat", "planhandelse": "andring_planhandelse",
        "planhandelse_datum": "andring_planhandelse_datum"}
ADOPTED = "Antagen"


@dataclass
class Andring:
    beslut: str  # beslutets objektidentitet
    namn: str
    paborjat: Optional[datetime.date]
    planhandelse: Optional[str]
    planhandelse_datum: Optional[datetime.date]
    diarienummer: str = ""
    fattat: Optional[datetime.date] = None
    overklagat: Optional[datetime.date] = None
    laga_kraft: Optional[datetime.date] = None


def _plain(value):
    return None if value is None or value == NULL or (hasattr(value, "isNull") and value.isNull()) else value


def _date(value) -> Optional[datetime.date]:
    value = _plain(value)
    if value is None or value == "":
        return None
    if isinstance(value, QDate):
        return value.toPyDate() if value.isValid() else None
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    try:
        return datetime.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _qgis(value):
    if isinstance(value, datetime.date):
        return QDate(value.year, value.month, value.day)
    return NULL if value is None else value


def _decisions(group):
    layer = layer_in_group(group, model.BESLUT.name)
    if layer is None:
        raise ValueError(f"Lagret {model.BESLUT.alias} saknas i planen. Öppna planen på nytt.")
    return layer


def _decision_row(group, identity: str):
    return next((f for f in _decisions(group).getFeatures() if str(_plain(f["objektidentitet"])) == identity), None)


# -- läsa --------------------------------------------------------------------------------------------------------------
def active(group) -> Optional[Andring]:
    """Ändringen som pågår, eller None."""
    meta = plan_storage(group).read_meta()
    identity = meta.get(KEYS["beslut"]) or ""
    if not identity:
        return None
    row = _decision_row(group, identity)
    if row is None:
        return None
    rubrik = str(_plain(row["rubrik"]) or "")
    return Andring(identity, rubrik.removeprefix("Ändring: "), _date(meta.get(KEYS["paborjat"])),
                   meta.get(KEYS["planhandelse"]) or None, _date(meta.get(KEYS["planhandelse_datum"])),
                   str(_plain(row["diarienummer"]) or ""), _date(row["datum_fattat"]), _date(row["datum_overklagat"]),
                   _date(row["datum_laga_kraft"]))


def content_values(group) -> dict[str, object]:
    """Det nytt innehåll får medan en ändring pågår (tomt annars)."""
    change = active(group)
    if change is None:
        return {}
    return {"beslut": change.beslut, "datum_paborjat": change.paborjat, "planhandelse_varde": change.planhandelse,
            "planhandelse_datum": change.planhandelse_datum}


def _content(group):
    for layer_def in model.CONTENT_LAYERS:
        layer = layer_in_group(group, layer_def.name)
        if layer is not None:
            yield layer_def, layer


def members(group, identity: str) -> int:
    """Antal innehåll som hör till ändringen."""
    return sum(1 for _, layer in _content(group) for f in layer.getFeatures()
               if str(_plain(f["beslut"]) or "") == identity)


def replaced(group) -> int:
    """Antal innehåll som är under ersättning."""
    return sum(1 for _, layer in _content(group) for f in layer.getFeatures() if _plain(f["under_ersattning"]))


def selected(group) -> list[tuple]:
    """(lager, fid) för markerat innehåll i planen."""
    return [(layer, fid) for _, layer in _content(group) for fid in layer.selectedFeatureIds()]


# -- ändra -------------------------------------------------------------------------------------------------------------
def _apply(layer, changes: dict[int, dict[str, object]], deletes: tuple = ()) -> None:
    """Ändrar attribut (och tar bort objekt) i redigeringsbufferten; redigerades lagret inte sparas det direkt."""
    if not changes and not deletes:
        return
    started = not layer.isEditable() and layer.startEditing()
    for fid, values in changes.items():
        layer.changeAttributeValues(fid, {layer.fields().indexOf(k): _qgis(v) for k, v in values.items()
                                          if layer.fields().indexOf(k) >= 0})
    if deletes:
        layer.deleteFeatures(list(deletes))
    if started and not layer.commitChanges():
        raise ValueError(f"Kunde inte spara {layer.name()}: " + "; ".join(layer.commitErrors()))


def start(group, namn: str, diarienummer: str, paborjat: datetime.date, planhandelse: Optional[str],
          planhandelse_datum: Optional[datetime.date]) -> Andring:
    """Påbörjar en ändring: ett nytt beslut (utan datum) och ändringens uppgifter i planens metadata."""
    if active(group) is not None:
        raise ValueError("En ändring pågår redan. Anta eller avbryt den först.")
    if not namn.strip():
        raise ValueError("Ge ändringen ett namn.")
    storage = plan_storage(group)
    layer = _decisions(group)
    plan = layer_in_group(group, model.OVERSIKTSPLAN.name)
    plan_row = next(plan.getFeatures(), None) if plan is not None else None
    organisation = str(_plain(plan_row["kommunnamn"]) or "") if plan_row is not None else ""
    values = {"rubrik": f"Ändring: {namn.strip()}", "diarienummer": diarienummer.strip() or None,
              "beslutande_organisation": organisation, "beslutande_instans": model.BESLUT_INSTANS}
    feature = QgsVectorLayerUtils.createFeature(layer, QgsGeometry(), {layer.fields().indexOf(k): _qgis(v)
                                                                       for k, v in values.items()})
    started = not layer.isEditable() and layer.startEditing()
    layer.addFeature(feature)
    identity = str(feature["objektidentitet"])
    if started and not layer.commitChanges():
        raise ValueError("Kunde inte spara ändringens beslut: " + "; ".join(layer.commitErrors()))
    storage.write_meta({KEYS["beslut"]: identity, KEYS["paborjat"]: paborjat.isoformat(),
                        KEYS["planhandelse"]: planhandelse or "",
                        KEYS["planhandelse_datum"]: planhandelse_datum.isoformat() if planhandelse_datum else ""})
    return active(group)


def update(group, planhandelse: Optional[str], planhandelse_datum: Optional[datetime.date], diarienummer: str,
           fattat: Optional[datetime.date], overklagat: Optional[datetime.date],
           laga_kraft: Optional[datetime.date]) -> int:
    """Ändrar den pågående ändringens planhändelse (även på dess innehåll) och beslutets uppgifter. Returnerar antalet
    innehåll som fick den nya planhändelsen."""
    change = active(group)
    if change is None:
        raise ValueError("Ingen ändring pågår.")
    plan_storage(group).write_meta({KEYS["planhandelse"]: planhandelse or "",
                                    KEYS["planhandelse_datum"]: planhandelse_datum.isoformat()
                                    if planhandelse_datum else ""})
    row = _decision_row(group, change.beslut)
    _apply(_decisions(group), {row.id(): {"diarienummer": diarienummer.strip() or None, "datum_fattat": fattat,
                                          "datum_overklagat": overklagat, "datum_laga_kraft": laga_kraft}})
    changed = 0
    for _, layer in _content(group):
        found = {f.id(): {"planhandelse_varde": planhandelse, "planhandelse_datum": planhandelse_datum}
                 for f in layer.getFeatures() if str(_plain(f["beslut"]) or "") == change.beslut}
        _apply(layer, found)
        changed += len(found)
    return changed


def add_selected(group) -> int:
    """Lägger markerat innehåll i ändringen (det ändras): ändringens beslut, planhändelse och datum påbörjat, och
    inte längre under ersättning."""
    values = content_values(group)
    if not values:
        raise ValueError("Ingen ändring pågår.")
    by_layer: dict = {}
    for layer, fid in selected(group):
        by_layer.setdefault(layer, {})[fid] = {**values, "under_ersattning": False}
    for layer, changes in by_layer.items():
        _apply(layer, changes)
    return sum(len(c) for c in by_layer.values())


def mark_replaced(group, on: bool = True) -> int:
    """Markerar markerat innehåll som under ersättning (eller tar bort markeringen). Innehåll som hör till ändringen
    hoppas över: det är det nya, inte det som ersätts."""
    change = active(group)
    own = change.beslut if change else None
    by_layer: dict = {}
    for layer, fid in selected(group):
        feature = layer.getFeature(fid)
        if own and str(_plain(feature["beslut"]) or "") == own:
            continue
        by_layer.setdefault(layer, {})[fid] = {"under_ersattning": on}
    for layer, changes in by_layer.items():
        _apply(layer, changes)
    return sum(len(c) for c in by_layer.values())


def finish(group, remove_replaced: bool) -> tuple[int, int]:
    """Ändringen är antagen: dess innehåll får planhändelsen Antagen och beslutets datum, innehållet under ersättning
    tas bort (om ``remove_replaced``), och ingen ändring pågår längre. Returnerar (antaget, borttaget)."""
    change = active(group)
    if change is None:
        raise ValueError("Ingen ändring pågår.")
    if change.fattat is None or not change.diarienummer:
        raise ValueError("Fyll i beslutets diarienummer och datum då ändringen antogs först.")
    adopted = removed = 0
    for _, layer in _content(group):
        changes, deletes = {}, []
        for f in layer.getFeatures():
            if str(_plain(f["beslut"]) or "") == change.beslut:
                changes[f.id()] = {"planhandelse_varde": ADOPTED, "planhandelse_datum": change.fattat}
            elif remove_replaced and _plain(f["under_ersattning"]):
                deletes.append(f.id())
        _apply(layer, changes, tuple(deletes))
        adopted += len(changes)
        removed += len(deletes)
    plan_storage(group).write_meta({key: "" for key in KEYS.values()})
    return adopted, removed


def cancel(group) -> None:
    """Avbryter den pågående ändringen: ingen ändring pågår längre. Innehållet och beslutet finns kvar och kan rättas
    eller tas bort för hand."""
    plan_storage(group).write_meta({key: "" for key in KEYS.values()})
