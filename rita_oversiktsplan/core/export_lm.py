"""Export av översiktsplanen till Lantmäteriets format: *Översiktsplan 2.0* (JSON, mediatyp
``application/vnd.lm.oversiktsplan.v2+json``, schemat ``namespace.lantmateriet.se/distribution/geodatakatalog/
oversiktsplan/v2/oversiktsplan-2.0.json``, specifikationen i testversion 4).

Resultatet är en ``FeatureCollection`` med

* ett ``oversiktsplan``-objekt (planens uppgifter, underlag och kopplingar till planhandlingen),
* ett ``beslutOP``-objekt per beslut (antagandebeslutet), och
* ett ``innehallOP``-objekt per innehåll, med geometrin i ``geometri`` (Lantmäteriets geometri 2.0.1).

Alla objekt har ``geometry: null`` på GeoJSON-nivå, som schemat kräver. Värden ur ÖP-katalogen skrivs som
``{varde, vardereferens, grupp, gruppreferens}`` ur planens uppslagstabeller (planens katalogversion). Tomma fält
utelämnas. Koordinater i planens koordinatsystem (SWEREF 99 TM eller en lokal zon), med millimeters precision och ytterringar moturs.

``check`` listar det som saknas för att filen ska följa schemat (fel) och det som är värt att se över (varningar).
Exporten läser planen, med ändringar som inte sparats, och ändrar ingenting.

Tolkningar (schemat säger inte mer): dokumentets ``externReferens`` får dokumentets id som ``identitet``, filnamnet
som ``producentensIdentitet``, datumangivelsen som ``tidsstampel`` och kortnamnet (annars "Planhandling") som
``avser``; en länk tas bara med om den är en webbadress. Beslutet påverkar planen (``paverkar`` = planens id).
"""
from __future__ import annotations

import datetime
import json
from dataclasses import dataclass
from typing import Any, Optional

from qgis.core import NULL, QgsGeometry, QgsWkbTypes
from qgis.PyQt.QtCore import QDate, QDateTime

from . import model
from .project import draft_layers, layer_in_group, plan_storage

MEDIATYP = "application/vnd.lm.oversiktsplan.v2+json"
SCHEMA = "https://namespace.lantmateriet.se/distribution/geodatakatalog/oversiktsplan/v2/oversiktsplan-2.0.json"
DECIMALS = 3
FEL, VARNING = "fel", "varning"
LAND_USE = "markochvattenanvandning"


@dataclass
class Problem:
    level: str  # FEL eller VARNING
    text: str
    layer: Optional[str] = None  # tabellen objektet finns i
    fid: Optional[int] = None


# -- små hjälpare --------------------------------------------------------------------------------------------------------
def _blank(value) -> bool:
    return value is None or value == NULL or (isinstance(value, str) and not value.strip())


def _text(value) -> Optional[str]:
    return None if _blank(value) else str(value).strip()


def _date(value) -> Optional[str]:
    if _blank(value):
        return None
    if isinstance(value, QDate):
        return value.toString("yyyy-MM-dd") if value.isValid() else None
    if isinstance(value, QDateTime):
        return value.date().toString("yyyy-MM-dd") if value.isValid() else None
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.strftime("%Y-%m-%d")
    text = str(value).strip()
    return text[:10] if len(text) >= 10 else None


def _datetime(value) -> Optional[str]:
    """Datum och tid med tidszon (RFC 3339), som schemats ``date-time`` kräver."""
    if _blank(value):
        return None
    if isinstance(value, QDateTime):
        value = value.toPyDateTime() if value.isValid() else None
    elif isinstance(value, QDate):
        value = datetime.datetime.combine(value.toPyDate(), datetime.time()) if value.isValid() else None
    elif isinstance(value, datetime.date) and not isinstance(value, datetime.datetime):
        value = datetime.datetime.combine(value, datetime.time())
    elif isinstance(value, str):
        try:
            value = datetime.datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.astimezone()  # lokal tid (svensk tid i QGIS på en svensk dator)
    return value.replace(microsecond=0).isoformat()


def _bool(value) -> Optional[bool]:
    return None if _blank(value) else bool(value)


def _put(target: dict, key: str, value) -> None:
    if value is not None and value != [] and value != {}:
        target[key] = value


# -- geometri ----------------------------------------------------------------------------------------------------------
def _round(points) -> list[list[float]]:
    result: list[list[float]] = []
    for point in points:
        xy = [round(point.x(), DECIMALS), round(point.y(), DECIMALS)]
        if not result or xy != result[-1]:
            result.append(xy)
    return result


def _area(ring: list[list[float]]) -> float:
    return sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(ring, ring[1:])) / 2


def _polygon(rings) -> Optional[list]:
    """Ytterring moturs och hål medurs (GeoJSON:s högerhandsregel)."""
    coordinates = []
    for index, points in enumerate(rings):
        ring = _round(points)
        if len(ring) < 4:
            if index == 0:
                return None
            continue
        counter_clockwise = _area(ring) > 0
        if counter_clockwise != (index == 0):
            ring.reverse()
        coordinates.append(ring)
    return coordinates


def geometry(value: Optional[QgsGeometry], epsg: int = model.EPSG) -> Optional[dict]:
    """Lantmäteriets ``geometri`` för en geometri: punkt, linje, yta eller multilinje/multiyta."""
    if value is None or value.isNull() or value.isEmpty():
        return None
    value = QgsGeometry(value)
    kind = QgsWkbTypes.geometryType(value.wkbType())
    position: Optional[dict] = None
    typ = ""
    if kind == QgsWkbTypes.GeometryType.PolygonGeometry:
        polygons = [p for p in (_polygon(rings) for rings in (value.asMultiPolygon() if value.isMultipart()
                                                               else [value.asPolygon()])) if p]
        if len(polygons) == 1:
            typ, position = "yta", {"type": "Polygon", "coordinates": polygons[0]}
        elif polygons:
            typ, position = "multiyta", {"type": "MultiPolygon", "coordinates": polygons}
    elif kind == QgsWkbTypes.GeometryType.LineGeometry:
        lines = [line for line in (_round(points) for points in (value.asMultiPolyline() if value.isMultipart()
                                                                  else [value.asPolyline()])) if len(line) >= 2]
        if len(lines) == 1:
            typ, position = "linje", {"type": "LineString", "coordinates": lines[0]}
        elif lines:
            typ, position = "multilinje", {"type": "MultiLineString", "coordinates": lines}
    elif kind == QgsWkbTypes.GeometryType.PointGeometry:
        points = value.asMultiPoint() if value.isMultipart() else [value.asPoint()]
        coordinates = [[round(p.x(), DECIMALS), round(p.y(), DECIMALS)] for p in points]
        if len(coordinates) == 1:
            typ, position = "punkt", {"type": "Point", "coordinates": coordinates[0]}
        elif coordinates:
            typ, position = "multipunkt", {"type": "MultiPoint", "coordinates": coordinates}
    if position is None:
        return None
    return {"typ": typ, "position": position, "koordinatsystemPlan": f"EPSG:{int(epsg)}", "dimension": 2}


# -- planens data --------------------------------------------------------------------------------------------------------
class _Plan:
    def __init__(self, group):
        self.group = group
        storage = plan_storage(group)
        self.epsg = storage.epsg
        self.lookups = {lookup.name: storage.read_lookup_values(lookup) for lookup in model.LOOKUPS}
        self.problems: list[Problem] = []

    def layer(self, name: str):
        return layer_in_group(self.group, name)

    def rows(self, name: str) -> list:
        layer = self.layer(name)
        return list(layer.getFeatures()) if layer is not None else []

    def problem(self, level: str, text: str, layer: Optional[str] = None, fid: Optional[int] = None) -> None:
        self.problems.append(Problem(level, text, layer, fid))

    def value(self, lookup: Optional[str], value, what: str, layer=None, fid=None) -> Optional[dict]:
        """Värdeobjektet för ett värde ur ÖP-katalogen, eller None (med ett fel om värdet inte finns i katalogen)."""
        text = _text(value)
        if text is None or lookup is None:
            return None
        found = self.lookups.get(lookup, {}).get(text)
        if found is None:
            self.problem(FEL, f"{what} \"{text}\" finns inte i planens ÖP-katalog.", layer, fid)
        return dict(found) if found else None


def _documents(plan: _Plan) -> dict[str, dict]:
    """``dokumentreferensOP`` per dokumentreferens_id."""
    result = {}
    for row in plan.rows("dokumentreferens_op"):
        doc_id = _text(row["dokumentreferens_id"])
        if doc_id is None:
            continue
        name = _text(row["namn"]) or "Dokument"
        reference: dict[str, Any] = {"identitet": _text(row["identitet"]) or doc_id,
                                     "producentensIdentitet": name,
                                     "tidsstampel": _datetime(row["datumangivelse"])
                                     or datetime.datetime.now().astimezone().replace(microsecond=0).isoformat(),
                                     "avser": _text(row["kortnamn"]) or "Planhandling"}
        namespace, link = _text(row["namespace"]), _text(row["lank"])
        if namespace and "://" in namespace:
            reference["namnrymd"] = namespace
        if link and link.lower().startswith(("http://", "https://")):
            reference["lank"] = link
        document: dict[str, Any] = {"namn": name}
        _put(document, "kortnamn", _text(row["kortnamn"]))
        document["externReferens"] = reference
        _put(document, "specifikReferens", _text(row["specifik_referens"]))
        result[doc_id] = document
    return result


def _sections(plan: _Plan, documents: dict[str, dict]) -> dict[str, list[dict]]:
    """``dokumentavsnitt`` per objektidentitet: ett avsnitt per (dokument, avsnittstyp) med alla bokmärken."""
    grouped: dict[str, dict[tuple, dict]] = {}
    for row in plan.rows("dokumentavsnitt"):
        identity, doc_id = _text(row["objektidentitet"]), _text(row["dokumentreferens_id"])
        bookmark = _text(row["avsnittsbokmarke_id"])
        if not identity or not doc_id or not bookmark or doc_id not in documents:
            continue
        kind = plan.value(model.AVSNITTSTYP_LOOKUP.name, row["avsnittstyp_varde"], "Avsnittstypen", "dokumentavsnitt",
                          row.id())
        if kind is None:
            plan.problem(FEL, f"Avsnittet {bookmark} saknar avsnittstyp.", "dokumentavsnitt", row.id())
            continue
        key = (doc_id, kind["varde"])
        entry = grouped.setdefault(identity, {}).setdefault(
            key, {"avsnittstyp": kind, "avsnittsbokmarke": [], "dokument": documents[doc_id]})
        if bookmark not in entry["avsnittsbokmarke"]:
            entry["avsnittsbokmarke"].append(bookmark)
    return {identity: list(entries.values()) for identity, entries in grouped.items()}


def _identity(feature) -> dict:
    result = {"objektidentitet": _text(feature["objektidentitet"])}
    _put(result, "versionGiltigFran", _datetime(feature["versiongiltigfran"]))
    return result


def _feature(properties: dict) -> dict:
    return {"type": "Feature", "geometry": None, "properties": properties}


def _plan_feature(plan: _Plan, sections: dict, documents: dict) -> tuple[Optional[dict], Optional[str]]:
    rows = plan.rows(model.OVERSIKTSPLAN.name)
    if not rows:
        plan.problem(FEL, "Planens tabell (oversiktsplan) är tom.")
        return None, None
    row = rows[0]
    table = model.OVERSIKTSPLAN.name
    props: dict[str, Any] = {"feature:typ": "oversiktsplan", **_identity(row)}
    identity = props["objektidentitet"]
    _put(props, "beslut", _text(row["beslut"]))
    for key, field, what in (("kommunkod", "kommunkod", "Kommunkoden"), ("kommunnamn", "kommunnamn", "Kommunen")):
        _put(props, key, _text(row[field]))
        if key not in props:
            plan.problem(FEL, f"{what} saknas i planens uppgifter.", table, row.id())
    _put(props, "planhandelse", plan.value(model.PLANHANDELSE_LOOKUP.name, row["planhandelse_varde"],
                                           "Planhändelsen", table, row.id()))
    _put(props, "datumPlanhandelse", _date(row["planhandelse_datum"]))
    _put(props, "datumPaborjat", _date(row["datum_paborjat"]))
    _put(props, "planensTitel", _text(row["planens_titel"]))
    _put(props, "digitaltUrsprung", _bool(row["digitalt_ursprung"]))
    _put(props, "digitaliseringsbeskrivning", _text(row["digitaliseringsbeskrivning"]))
    for key, text in (("planhandelse", "Planhändelsen"), ("datumPlanhandelse", "Datum för planhändelsen"),
                      ("datumPaborjat", "Datum då planen påbörjades"), ("digitaltUrsprung", "Digitalt ursprung")):
        if key not in props:
            plan.problem(FEL, f"{text} saknas i Planens uppgifter.", table, row.id())
    underlag = _underlag(plan, row, documents)
    if underlag:
        props["underlag"] = underlag
    else:
        plan.problem(FEL, "Planen har inget underlag (minst ett krävs, till exempel planeringsunderlag). Lägg till "
                          "det under Planens uppgifter, fliken Underlag.", table, row.id())
    _put(props, "dokument", sections.get(identity))
    return _feature(props), identity


def _underlag(plan: _Plan, row, documents: dict) -> list[dict]:
    wanted = _text(row["underlag_id"])
    links: dict[str, list[str]] = {}
    for link in plan.rows("oversiktsplan_underlag_underlag"):
        if _text(link["underlag_id"]) and _text(link["dokumentreferens_id"]):
            links.setdefault(_text(link["underlag_id"]), []).append(_text(link["dokumentreferens_id"]))
    result = []
    for item in plan.rows("oversiktsplan_underlag"):
        underlag_id = _text(item["underlag_id"])
        if wanted and underlag_id != wanted:
            continue
        kind = plan.value(model.UNDERLAGSTYP_LOOKUP.name, item["underlagstyp_varde"], "Underlagstypen",
                          "oversiktsplan_underlag", item.id())
        docs = [documents[d] for d in links.get(underlag_id, []) if d in documents]
        if kind and docs:
            result.append({"underlagstyp": kind, "underlag": docs})
        else:
            plan.problem(FEL, "Ett underlag saknar underlagstyp eller dokument.", "oversiktsplan_underlag", item.id())
    return result


def _decision_features(plan: _Plan, plan_identity: Optional[str]) -> list[dict]:
    result = []
    table = model.BESLUT.name
    for row in plan.rows(table):
        props: dict[str, Any] = {"feature:typ": "beslutOP", **_identity(row)}
        organisation = _text(row["beslutande_organisation"])
        props["beslutandeOrganisation"] = {"organisationsnamn": organisation} if organisation else {}
        _put(props, "beslutandeInstans", _text(row["beslutande_instans"]))
        events = [{"handelsetyp": kind, "datum": _date(row[field])}
                  for kind, field in (("fattat", "datum_fattat"), ("överklagat", "datum_overklagat"),
                                      ("laga kraft", "datum_laga_kraft")) if _date(row[field])]
        if events:
            props["handelse"] = events
        else:
            plan.problem(FEL, "Beslutet saknar datum (när det fattades eller fick laga kraft).", table, row.id())
        if plan_identity:
            props["paverkar"] = [{"identitet": plan_identity, "objekttyp": "oversiktsplan"}]
        _put(props, "rubrik", _text(row["rubrik"]))
        _put(props, "diarienummer", _text(row["diarienummer"]))
        if "diarienummer" not in props:
            plan.problem(FEL, "Beslutet saknar diarienummer.", table, row.id())
        _put(props, "arkividentitet", _text(row["arkividentitet"]))
        result.append(_feature(props))
    return result


def _content_features(plan: _Plan, plan_identity: Optional[str], sections: dict) -> list[dict]:
    result = []
    for layer_def in model.CONTENT_LAYERS:
        layer = plan.layer(layer_def.name)
        if layer is None:
            continue
        category = layer_def.category
        names = layer.fields().names()
        for row in layer.getFeatures():
            fid, table = row.id(), layer_def.name
            props: dict[str, Any] = {"feature:typ": "innehallOP", **_identity(row)}
            if plan_identity:
                props["oversiktsplan"] = plan_identity
            _put(props, "beslut", _text(row["beslut"]))
            kind = plan.value(category.lookup, row["innehallstyp_varde"], "Innehållstypen", table, fid)
            if _blank(row["innehallstyp_varde"]):
                plan.problem(FEL, f"{category.alias}: innehållstypen saknas.", table, fid)
            _put(props, "innehallstyp", kind)
            if "kompletterandeInnehallstyp" in names:
                _put(props, "kompletterandeInnehallstyp", plan.value(
                    category.kompletterande, row["kompletterandeInnehallstyp"], "Den kompletterande innehållstypen",
                    table, fid))
            _put(props, "planhandelse", plan.value(model.PLANHANDELSE_LOOKUP.name, row["planhandelse_varde"],
                                                   "Planhändelsen", table, fid))
            _put(props, "datumPlanhandelse", _date(row["planhandelse_datum"]))
            props["underErsattning"] = bool(_bool(row["under_ersattning"]))
            _put(props, "datumPaborjat", _date(row["datum_paborjat"]))
            _put(props, "namn", _text(row["namn"]))
            if "precisering" in names:
                _put(props, "precisering", _text(row["precisering"]))
            shape = geometry(row.geometry(), plan.epsg) if row.hasGeometry() else None
            _put(props, "geometri", shape)
            props["illustrativaGranser"] = True
            _put(props, "vertikalAvgransning", _text(row["vertikal_avgransning"]))
            if "utbyggnadsordning" in names:
                _put(props, "utbyggnadsordning", _text(row["utbyggnadsordning"]))
            if "sambandsniva_varde" in names:
                level = plan.value(model.SAMBANDSNIVA_LOOKUP.name, row["sambandsniva_varde"], "Sambandsnivån",
                                   table, fid)
                _put(props, "sambandsniva", [level] if level else None)
            scale = row["presentationsskala"]
            _put(props, "presentationsskala", int(scale) if not _blank(scale) else None)
            _put(props, "dokument", sections.get(props["objektidentitet"]))
            what = f"{category.alias}: {kind['varde'] if kind else 'innehåll'}"
            for key, text in (("planhandelse", "planhändelse"), ("datumPlanhandelse", "datum för planhändelsen")):
                if key not in props:
                    plan.problem(FEL, f"{what} saknar {text}.", table, fid)
            if not props["objektidentitet"]:
                plan.problem(FEL, f"{what} saknar objektidentitet.", table, fid)
            if category.key == LAND_USE and shape is None:
                plan.problem(FEL, f"{what} saknar geometri: mark- och vattenanvändning ska vara lägesbestämd "
                                  "(BFS 2024:2).", table, fid)
            elif row.hasGeometry() and not row.geometry().isGeosValid():
                plan.problem(VARNING, f"{what}: geometrin är ogiltig (till exempel en yta som korsar sig själv).",
                             table, fid)
            result.append(_feature(props))
    return result


def export(group) -> tuple[dict, list[Problem]]:
    """(FeatureCollection, problem). Läser planen, med osparade ändringar, och ändrar ingenting."""
    plan = _Plan(group)
    documents = _documents(plan)
    sections = _sections(plan, documents)
    plan_feature, plan_identity = _plan_feature(plan, sections, documents)
    features = ([plan_feature] if plan_feature else []) + _decision_features(plan, plan_identity) \
        + _content_features(plan, plan_identity, sections)
    if not any(f["properties"]["feature:typ"] == "innehallOP" for f in features):
        plan.problem(VARNING, "Planen har inget innehåll än.")
    drafts = sum(layer.featureCount() for layer in draft_layers(group).values() if layer is not None)
    if drafts:
        plan.problem(VARNING, f"{drafts} objekt under Att tilldela har inget innehåll och följer inte med.")
    return {"type": "FeatureCollection", "feature:mediatyp": MEDIATYP, "features": features}, plan.problems


def dumps(collection: dict) -> str:
    return json.dumps(collection, ensure_ascii=False, indent=2)


def counts(collection: dict) -> dict[str, int]:
    result: dict[str, int] = {}
    for feature in collection["features"]:
        kind = feature["properties"]["feature:typ"]
        result[kind] = result.get(kind, 0) + 1
    return result
