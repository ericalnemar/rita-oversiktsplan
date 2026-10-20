"""Rita först, tilldela sedan: hitta geometrin man klickar på, ge den innehåll och flytta den till rätt
innehållslager, och läs och skriv planens uppgifter och standardvärden.

Ändringar i lagren läggs i QGIS redigeringsbuffert och sparas när man avslutar redigeringen (disketten, som i Rita Detaljplan). Undantaget är
Planens uppgifter, som sparas direkt när man klickar OK i dialogen."""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Optional

from qgis.core import (NULL, QgsFeatureRequest, QgsGeometry, QgsPointXY, QgsRectangle, QgsVectorLayer,
                       QgsVectorLayerUtils, QgsWkbTypes)
from qgis.PyQt.QtCore import QDate

from . import geopackage, model
from .project import draft_layers, layer_in_group, plan_storage

# Fält som tilldelningsdialogen fyller i; resten kommer från standardvärdena och planen.
CONTENT_FIELDS = ("innehallstyp_varde", "kompletterandeInnehallstyp", "namn", "precisering", "sambandsniva_varde",
                  "utbyggnadsordning", "objektidentitet_ri", "rita_pilar")


@dataclass(frozen=True)
class Candidate:
    """Ett objekt under ett klick."""
    layer: QgsVectorLayer
    fid: int
    suffix: str  # polygon, line eller point
    category: Optional[model.Category]  # None för otilldelad geometri

    @property
    def assigned(self) -> bool:
        return self.category is not None

    def label(self) -> str:
        if self.category is None:
            return f"Otilldelad {dict((s, w) for s, _, w in model.GEOMETRIES)[self.suffix]}"
        value = self.layer.getFeature(self.fid)["innehallstyp_varde"]
        return f"{self.category.alias}: {value if value not in (None, NULL) else 'innehållstyp ej vald'}"


@dataclass
class Assignment:
    """Det man väljer i tilldelningsdialogen."""
    category: model.Category
    values: dict[str, object] = field(default_factory=dict)  # fältnamn → värde, bara fälten i CONTENT_FIELDS


def candidates_at(group, point: QgsPointXY, tolerance: float) -> list[Candidate]:
    """Objekten under en punkt i planens synliga lager: först otilldelad geometri, sedan innehåll. Punkter och linjer
    före ytor, eftersom de är svårare att träffa."""
    probe = QgsGeometry.fromPointXY(point)
    rect = QgsRectangle(point.x() - tolerance, point.y() - tolerance, point.x() + tolerance, point.y() + tolerance)
    order = ("point", "line", "polygon")
    layers: list[tuple[QgsVectorLayer, str, Optional[model.Category]]] = []
    drafts = draft_layers(group)
    for suffix in order:
        if drafts.get(suffix) is not None:
            layers.append((drafts[suffix], suffix, None))
    for suffix in order:
        for layer_def in model.CONTENT_LAYERS:
            if model.geometry_suffix(layer_def) == suffix:
                layer = layer_in_group(group, layer_def.name)
                if layer is not None:
                    layers.append((layer, suffix, layer_def.category))
    found = []
    for layer, suffix, category in layers:
        node = group.findLayer(layer.id())
        if node is None or not node.isVisible():
            continue
        for feature in layer.getFeatures(QgsFeatureRequest().setFilterRect(rect)):
            geometry = feature.geometry()
            if geometry is None or geometry.isEmpty():
                continue
            if category is not None and category.key == model.PLAN_AREA_KEY:
                # plangeometrin täcker hela planen och ändras sällan: den väljs bara på sin kant, så att den inte
                # kommer i vägen när man klickar på innehåll inne i planen
                hit = QgsGeometry(geometry.constGet().boundary()).distance(probe) <= tolerance
            else:
                hit = (geometry.contains(probe) if geometry.type() == QgsWkbTypes.GeometryType.PolygonGeometry
                       else geometry.distance(probe) <= tolerance)
            if hit:
                found.append(Candidate(layer, feature.id(), suffix, category))
    return found


def assign(group, candidate: Candidate, assignment: Assignment) -> tuple[QgsVectorLayer, int]:
    """Ger objektet innehåll: flyttar det till innehållslagret för vald grupp och geometri med valda värden.
    Otilldelad geometri får dessutom standardvärdena och planens planhändelse; innehåll som byter typ behåller sina
    övriga uppgifter, även objektidentiteten. Returnerar lagret och objektets id (negativt tills det sparats)."""
    target_def = model.content_layer(assignment.category, candidate.suffix)
    if target_def is None:
        raise ValueError(f"{assignment.category.alias} kan inte ritas som {candidate.suffix}")
    target = layer_in_group(group, target_def.name)
    if target is None:
        raise ValueError(f"Lagret {target_def.alias} saknas i planen")
    source = candidate.layer
    feature = source.getFeature(candidate.fid)
    values: dict[str, object] = {}
    if candidate.assigned:  # byter typ: behåll allt utom det som väljs i dialogen
        for name in feature.fields().names():
            if name != "fid" and target.fields().indexOf(name) >= 0:
                values[name] = feature[name]
    else:
        values.update(new_content_values(group))
    values.update(assignment.values)
    attributes = {target.fields().indexOf(name): _to_qgis(value) for name, value in values.items()
                  if target.fields().indexOf(name) >= 0}

    if not target.isEditable():
        target.startEditing()
    if source is target:  # samma lager: ändra på plats
        target.changeAttributeValues(candidate.fid, attributes)
        return target, candidate.fid
    new = QgsVectorLayerUtils.createFeature(target, QgsGeometry(feature.geometry()), attributes)
    if not target.addFeature(new):
        raise ValueError(f"Kunde inte lägga till objektet i {target_def.alias}")
    if not source.isEditable():
        source.startEditing()
    source.deleteFeature(candidate.fid)
    return target, new.id()


def create_without_geometry(group, assignment: Assignment) -> str:
    """Skapar innehåll utan geometri (till exempel bostadsförsörjning som bara beskrivs i text) och returnerar dess
    objektidentitet. Sparas direkt om lagret inte redigerades, annars i redigeringsbufferten."""
    target_def = model.storage_layer(assignment.category, model.NO_GEOMETRY)
    target = layer_in_group(group, target_def.name) if target_def is not None else None
    if target is None:
        raise ValueError(f"{assignment.category.alias} kan inte vara innehåll utan geometri")
    values = {**new_content_values(group), **assignment.values}
    attributes = {target.fields().indexOf(name): _to_qgis(value) for name, value in values.items()
                  if target.fields().indexOf(name) >= 0}
    started = not target.isEditable() and target.startEditing()
    feature = QgsVectorLayerUtils.createFeature(target, QgsGeometry(), attributes)
    if not target.addFeature(feature):
        raise ValueError(f"Kunde inte lägga till innehållet i {target_def.alias}")
    identity = str(feature["objektidentitet"])
    if started and not target.commitChanges():
        raise ValueError(f"Kunde inte spara {target_def.alias}: " + "; ".join(target.commitErrors()))
    return identity


def new_content_values(group) -> dict[str, object]:
    """Värdena nytt innehåll får från början: standardvärdena under Planens uppgifter, och planens planhändelse och
    datum påbörjat. Pågår en ändring av planen får innehållet i stället ändringens planhändelse, datum påbörjat och
    beslut (se :mod:`andring`)."""
    from . import andring
    defaults = plan_storage(group).read_defaults()
    plan = plan_feature(group)
    values = {
        "vertikal_avgransning": defaults["vertikal_avgransning"] or None,
        "under_ersattning": defaults["under_ersattning"] == "1",
        "datum_paborjat": plain(plan["datum_paborjat"]) if plan is not None else None,
        "presentationsskala": int(defaults["presentationsskala"]) if defaults["presentationsskala"] else None,
        "illustrativa_granser": True,
        "planhandelse_varde": plain(plan["planhandelse_varde"]) if plan is not None else None,
        "planhandelse_datum": plain(plan["planhandelse_datum"]) if plan is not None else None,
    }
    values.update(andring.content_values(group))
    return values


# -- planens uppgifter ----------------------------------------------------------------------------------------------
@dataclass
class Decision:
    """Antagandebeslutet (beslutOP i specifikationen). Föreskrifterna kräver diarienummer och datum för laga kraft."""
    diarienummer: str = ""
    fattat: Optional[datetime.date] = None
    overklagat: Optional[datetime.date] = None
    laga_kraft: Optional[datetime.date] = None

    def is_empty(self) -> bool:
        return not (self.diarienummer or self.fattat or self.overklagat or self.laga_kraft)


@dataclass
class PlanInfo:
    kommunnamn: str
    kommunkod: str
    titel: str
    datum_paborjat: Optional[datetime.date]
    digitalt_ursprung: bool
    digitaliseringsbeskrivning: str
    planhandelse: Optional[str]
    planhandelse_datum: Optional[datetime.date]
    defaults: dict[str, str]  # fältnamn → värde som text, se model.DEFAULT_KEYS
    beslut: Decision = field(default_factory=Decision)


def plan_layer(group) -> QgsVectorLayer:
    return layer_in_group(group, model.OVERSIKTSPLAN.name)


def plan_feature(group):
    layer = plan_layer(group)
    return next(iter(layer.getFeatures()), None) if layer is not None else None


def read_plan_info(group) -> PlanInfo:
    feature = plan_feature(group)
    if feature is None:
        raise ValueError("Planens tabell är tom")
    return PlanInfo(
        kommunnamn=_text(feature["kommunnamn"]), kommunkod=_text(feature["kommunkod"]),
        titel=_text(feature["planens_titel"]), datum_paborjat=_py_date(feature["datum_paborjat"]),
        digitalt_ursprung=bool(plain(feature["digitalt_ursprung"])),
        digitaliseringsbeskrivning=_text(feature["digitaliseringsbeskrivning"]),
        planhandelse=plain(feature["planhandelse_varde"]),
        planhandelse_datum=_py_date(feature["planhandelse_datum"]),
        defaults=plan_storage(group).read_defaults(),
        beslut=read_decision(group),
    )


def decision_feature(group):
    """Antagandebeslutets rad i beslut_op: den som planen pekar på, eller None."""
    plan = plan_feature(group)
    layer = layer_in_group(group, model.BESLUT.name)
    identity = plain(plan["beslut"]) if plan is not None else None
    if layer is None or not identity:
        return None
    return next((f for f in layer.getFeatures() if f["objektidentitet"] == identity), None)


def read_decision(group) -> Decision:
    feature = decision_feature(group)
    if feature is None:
        return Decision()
    return Decision(diarienummer=_text(feature["diarienummer"]), fattat=_py_date(feature["datum_fattat"]),
                    overklagat=_py_date(feature["datum_overklagat"]), laga_kraft=_py_date(feature["datum_laga_kraft"]))


def _save_decision(group, decision: Decision, organisation: str) -> Optional[str]:
    """Sparar antagandebeslutet direkt och returnerar dess objektidentitet. Ett tomt beslut som inte finns skapas
    inte."""
    layer = layer_in_group(group, model.BESLUT.name)
    if layer is None:
        raise ValueError(f"Lagret {model.BESLUT.alias} saknas i planen. Öppna planen på nytt.")
    existing = decision_feature(group)
    if existing is None and decision.is_empty():
        return None
    values = {"diarienummer": decision.diarienummer or None, "datum_fattat": decision.fattat,
              "datum_overklagat": decision.overklagat, "datum_laga_kraft": decision.laga_kraft,
              "beslutande_organisation": organisation, "beslutande_instans": model.BESLUT_INSTANS}
    attributes = {layer.fields().indexOf(k): _to_qgis(v) for k, v in values.items()}
    started = not layer.isEditable() and layer.startEditing()
    if existing is None:
        attributes[layer.fields().indexOf("rubrik")] = "Antagande av översiktsplanen"
        feature = QgsVectorLayerUtils.createFeature(layer, QgsGeometry(), attributes)
        layer.addFeature(feature)
        identity = feature["objektidentitet"]
    else:
        layer.changeAttributeValues(existing.id(), attributes)
        identity = existing["objektidentitet"]
    if not layer.commitChanges(started):
        raise ValueError("Kunde inte spara beslutet: " + "; ".join(layer.commitErrors()))
    return str(identity)


def write_plan_info(group, info: PlanInfo, update_content: bool) -> int:
    """Sparar planens uppgifter och standardvärden direkt. Med ``update_content`` får allt innehåll i planen också
    planens planhändelse; de ändringarna läggs i redigeringsbufferten och sparas med Spara (eller direkt, om lagret
    inte redigerades). Returnerar antalet innehållsobjekt som ändrades."""
    layer = plan_layer(group)
    feature = plan_feature(group)
    decision = _save_decision(group, info.beslut, info.kommunnamn)
    values = {"beslut": decision or plain(feature["beslut"]), "planens_titel": info.titel,
              "datum_paborjat": info.datum_paborjat,
              "digitalt_ursprung": info.digitalt_ursprung,
              "digitaliseringsbeskrivning": info.digitaliseringsbeskrivning or None,
              "planhandelse_varde": info.planhandelse, "planhandelse_datum": info.planhandelse_datum}
    attributes = {layer.fields().indexOf(k): _to_qgis(v) for k, v in values.items()}
    started = not layer.isEditable() and layer.startEditing()
    layer.changeAttributeValues(feature.id(), attributes)
    # sparas direkt; slog vi själva på redigeringen stängs den igen, annars fortsätter användarens redigering
    if not layer.commitChanges(started):
        raise ValueError("Kunde inte spara planens uppgifter: " + "; ".join(layer.commitErrors()))
    plan_storage(group).write_defaults(info.defaults)
    if not update_content:
        return 0
    changed = 0
    event = {"planhandelse_varde": info.planhandelse, "planhandelse_datum": info.planhandelse_datum}
    ongoing = plan_storage(group).read_meta().get("andring_beslut") or ""  # en pågående ändrings innehåll rörs inte
    for layer_def in model.CONTENT_LAYERS:
        content = layer_in_group(group, layer_def.name)
        if content is None or content.featureCount() == 0:
            continue
        idx = {content.fields().indexOf(k): _to_qgis(v) for k, v in event.items()}
        started = not content.isEditable() and content.startEditing()
        for f in content.getFeatures():
            if ongoing and str(plain(f["beslut"]) or "") == ongoing:
                continue
            if (plain(f["planhandelse_varde"]), _py_date(f["planhandelse_datum"])) != (
                    info.planhandelse, info.planhandelse_datum):
                content.changeAttributeValues(f.id(), idx)
                changed += 1
        if started and not content.commitChanges():
            raise ValueError(f"Kunde inte spara {layer_def.alias}: " + "; ".join(content.commitErrors()))
    return changed


# -- hjälpare ---------------------------------------------------------------------------------------------------------
def plain(value):
    """Värdet som Python, None för tomt (NULL)."""
    return None if value is None or value == NULL or (hasattr(value, "isNull") and value.isNull()) else value


def _text(value) -> str:
    value = plain(value)
    return "" if value is None else str(value)


def _date(text: str) -> Optional[datetime.date]:
    return datetime.date.fromisoformat(text) if text else None


def _py_date(value) -> Optional[datetime.date]:
    value = plain(value)
    if value is None:
        return None
    if isinstance(value, QDate):
        return datetime.date(value.year(), value.month(), value.day()) if value.isValid() else None
    if isinstance(value, datetime.date):
        return value
    return datetime.date.fromisoformat(str(value)[:10])


def _to_qgis(value):
    if value is None:
        return NULL
    if isinstance(value, datetime.date) and not isinstance(value, datetime.datetime):
        return QDate(value.year, value.month, value.day)
    return value
