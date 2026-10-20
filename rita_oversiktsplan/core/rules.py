"""Lantmäteriets regler för en leverans av översiktsplan, kontrollerade på den färdiga exportfilen. Ren Python.

Källa: Lantmäteriet, *Nationell dataproduktspecifikation för översiktsplan* 1.0 test 4 (kapitel 6, kvalitetskraven
ÖP-X01–X07) och *Objekttypskatalog, informationsutbytesmodell Översiktsplan* 1.0 test 4 (reglerna OP-JSON-001–044),
lästa 2026-10-19. Specifikationen är i testversion och reglerna kan ändras. Det här är pluginets tolkning av texten;
Lantmäteriets egen validering i NGP är det som gäller.

Varje fynd har regelns id, så att det går att slå upp i specifikationen. ``check`` tar emot FeatureCollection från
:mod:`export_lm` och returnerar en lista med :class:`Finding`. Det som :mod:`export_lm` redan kontrollerar när filen
byggs (obligatoriska fält, värden som saknas i planens katalog, underlag) upprepas inte här.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Iterable, Optional

FEL, VARNING = "fel", "varning"
FEATURE_TYPES = ("oversiktsplan", "innehallOP", "beslutOP")  # OP-JSON-002
KOMMUNKOD = re.compile(r"^[0-9]{4}$")  # OP-JSON-004
BOOKMARK = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,39}$")  # OP-JSON-003
# planhändelser som enligt OP-JSON-042/044 kräver granskningsyttrande, MKB och beslut (katalogen skriver
# "inaktuellt", reglerna "inaktuell": båda godtas)
DECIDED = {"Antagen", "Fastställd som aktuell", "Fastställd som inaktuell", "Fastställd som inaktuellt",
           "Angivet innehåll fastställt som inaktuell", "Angivet innehåll fastställt som inaktuellt",
           "Ersatt av ny plan"}
REQUIRED_UNDERLAG = ("Länsstyrelsens granskningsyttrande", "Miljökonsekvensbeskrivning")
GEOMETRY_REQUIRED = ("Plangeometri", "Område")  # OP-JSON-034, OP-JSON-038
SPIKE_DEGREES = 12.0  # ÖP-X05
OOXML = (".docx", ".docm", ".dotx")  # ÖP-X07: Office Open XML (ISO/IEC 29500)


@dataclass(frozen=True)
class Finding:
    level: str
    rule: str  # regelns id i specifikationen
    text: str
    identity: Optional[str] = None  # objektidentiteten för objektet det gäller, om det gäller ett objekt


def _features(collection: dict, kind: str) -> list[dict]:
    return [f["properties"] for f in collection.get("features", []) if f.get("properties", {}).get("feature:typ") == kind]


def _name(props: dict) -> str:
    kind = props.get("innehallstyp") or {}
    name = props.get("namn")
    return f"{kind.get('varde', 'innehåll')}" + (f" ({name})" if name else "")


# -- katalogen -----------------------------------------------------------------------------------------------------------
def catalog_index(catalog) -> dict[str, str]:
    """id → namn för alla begrepp i ÖP-katalogen (kategorier och värden)."""
    index: dict[str, str] = {}

    def walk(nodes: Iterable[dict]) -> None:
        for node in nodes:
            if node.get("id"):
                index[str(node["id"])] = str(node.get("namn", "")).strip()
            walk(node.get("barn") or [])

    walk(catalog.data["katalog"]["data"])
    return index


def _catalog_values(props: dict) -> Iterable[tuple[str, dict]]:
    """(attribut, värdeobjekt) för alla värden ur ÖP-katalogen i ett objekt, även i listor och dokumentavsnitt."""
    for key, value in props.items():
        items = value if isinstance(value, list) else [value]
        for item in items:
            if isinstance(item, dict) and "vardereferens" in item:
                yield key, item
            elif isinstance(item, dict):
                yield from ((f"{key}.{k}", v) for k, v in _catalog_values(item))


# -- geometri ------------------------------------------------------------------------------------------------------------
def _parts(geometri: dict) -> list[tuple[list, bool]]:
    """(koordinatlista, sluten) för varje linje och ring i en geometri."""
    position = (geometri or {}).get("position") or {}
    kind, coordinates = position.get("type"), position.get("coordinates") or []
    if kind == "LineString":
        return [(coordinates, False)]
    if kind == "MultiLineString":
        return [(line, False) for line in coordinates]
    if kind == "Polygon":
        return [(ring, True) for ring in coordinates]
    if kind == "MultiPolygon":
        return [(ring, True) for polygon in coordinates for ring in polygon]
    return []


def _angle(a, b, c) -> Optional[float]:
    """Vinkeln vid b mellan segmenten b–a och b–c, i grader (None om ett segment saknar längd)."""
    ux, uy, vx, vy = a[0] - b[0], a[1] - b[1], c[0] - b[0], c[1] - b[1]
    lu, lv = math.hypot(ux, uy), math.hypot(vx, vy)
    if lu == 0 or lv == 0:
        return None
    cosine = max(-1.0, min(1.0, (ux * vx + uy * vy) / (lu * lv)))
    return math.degrees(math.acos(cosine))


def spikes(points: list, closed: bool) -> int:
    """Antal spikar: hörn där vinkeln mellan två linjesegment är högst 12 grader (ÖP-X05)."""
    pts = [p for i, p in enumerate(points) if i == 0 or p != points[i - 1]]
    if closed and len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    if len(pts) < 3:
        return 0
    corners = range(len(pts)) if closed else range(1, len(pts) - 1)
    found = 0
    for i in corners:
        angle = _angle(pts[i - 1], pts[i], pts[(i + 1) % len(pts)])
        if angle is not None and angle <= SPIKE_DEGREES:
            found += 1
    return found


def _crosses(p1, p2, p3, p4) -> bool:
    def orient(a, b, c):
        value = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        return 0 if abs(value) < 1e-12 else (1 if value > 0 else -1)

    def on(a, b, c):
        return min(a[0], b[0]) <= c[0] <= max(a[0], b[0]) and min(a[1], b[1]) <= c[1] <= max(a[1], b[1])

    o1, o2, o3, o4 = orient(p1, p2, p3), orient(p1, p2, p4), orient(p3, p4, p1), orient(p3, p4, p2)
    if o1 != o2 and o3 != o4:
        return True
    return (o1 == 0 and on(p1, p2, p3)) or (o2 == 0 and on(p1, p2, p4)) or \
        (o3 == 0 and on(p3, p4, p1)) or (o4 == 0 and on(p3, p4, p2))


def self_crossings(points: list) -> int:
    """Antal ställen där en linje korsar eller berör sig själv (ÖP-X04). Segment som delar en brytpunkt räknas inte;
    en linje som slutar där den börjar (en sluten linje) är tillåten."""
    segments = [(points[i], points[i + 1]) for i in range(len(points) - 1) if points[i] != points[i + 1]]
    closed = len(points) > 2 and points[0] == points[-1]
    last = len(segments) - 1
    # svep i x-led: bara segment vars x-intervall överlappar jämförs (snabbt även för långa linjer)
    order = sorted(range(len(segments)), key=lambda k: min(segments[k][0][0], segments[k][1][0]))
    active: list[int] = []
    found = 0
    for i in order:
        a, b = segments[i]
        xmin = min(a[0], b[0])
        active = [j for j in active if max(segments[j][0][0], segments[j][1][0]) >= xmin]
        for j in active:
            lo, hi = min(i, j), max(i, j)
            if hi - lo < 2 or (closed and lo == 0 and hi == last):
                continue  # grannsegment delar en brytpunkt
            if _crosses(a, b, *segments[j]):
                found += 1
        active.append(i)
    return found


# -- reglerna ------------------------------------------------------------------------------------------------------------
def check(collection: dict, catalog=None) -> list[Finding]:
    """Lantmäteriets regler. ``catalog`` är ÖP-katalogen (:class:`opkatalog.Catalog`) för OP-JSON-006."""
    found: list[Finding] = []
    add = lambda level, rule, text, identity=None: found.append(Finding(level, rule, text, identity))  # noqa: E731
    features = collection.get("features", [])

    # OP-JSON-001, 002: en och endast en översiktsplan, och bara de tre objekttyperna
    plans = _features(collection, "oversiktsplan")
    if len(plans) != 1:
        add(FEL, "OP-JSON-001", f"Filen ska innehålla en och endast en översiktsplan (den har {len(plans)}).")
    for feature in features:
        kind = feature.get("properties", {}).get("feature:typ")
        if kind not in FEATURE_TYPES:
            add(FEL, "OP-JSON-002", f"Objekttypen {kind!r} får inte förekomma i en leverans av översiktsplan.")
    plan = plans[0] if plans else {}
    decisions = _features(collection, "beslutOP")
    contents = _features(collection, "innehallOP")
    content_ids = {c.get("objektidentitet") for c in contents}

    # OP-JSON-004: kommunkoden
    kod = plan.get("kommunkod")
    if kod is not None and not KOMMUNKOD.match(str(kod)):
        add(FEL, "OP-JSON-004", f"Kommunkoden {kod!r} ska vara fyra siffror.", plan.get("objektidentitet"))

    # OP-JSON-005: ett beslut påverkar antingen översiktsplanen eller innehåll, aldrig båda
    for decision in decisions:
        affected = decision.get("paverkar") or []
        kinds = {a.get("objekttyp") for a in affected}
        label = decision.get("rubrik") or decision.get("diarienummer") or "Ett beslut"
        if not affected:
            add(FEL, "OP-JSON-005", f"{label}: beslutet påverkar varken planen eller något innehåll (paverkar "
                                    "krävs).", decision.get("objektidentitet"))
        elif len(kinds) > 1:
            add(FEL, "OP-JSON-005", f"{label}: beslutet får påverka antingen översiktsplanen eller innehåll, inte "
                                    "båda.", decision.get("objektidentitet"))
        elif kinds == {"oversiktsplan"} and len(affected) > 1:
            add(FEL, "OP-JSON-005", f"{label}: beslutet får bara påverka en översiktsplan.",
                decision.get("objektidentitet"))
        for item in affected:
            if item.get("objekttyp") == "innehallOP" and item.get("identitet") not in content_ids:
                add(FEL, "OP-JSON-005", f"{label}: beslutet påverkar innehåll som inte finns i filen.",
                    decision.get("objektidentitet"))

    # OP-JSON-032, 036: en plan utan digitalt ursprung (pluginet gör sådana bara om fältet ändrats för hand)
    if plan.get("digitaltUrsprung") is False:
        kinds = {(u.get("underlagstyp") or {}).get("varde") for u in plan.get("underlag") or []}
        if "Översiktsplan" not in kinds:
            add(FEL, "OP-JSON-032", "En plan utan digitalt ursprung ska ha ett underlag av typen Översiktsplan.")
        geometries = [c for c in contents if (c.get("innehallstyp") or {}).get("grupp") == "Plangeometri"]
        if len(geometries) != 1:
            add(FEL, "OP-JSON-032", "En plan utan digitalt ursprung ska ha exakt ett innehåll i Plangeometri.")
        if plan.get("dokument") or decisions:
            add(FEL, "OP-JSON-036", "En plan utan digitalt ursprung får inte ha dokument eller beslut.")

    # OP-JSON-042, 044: en antagen eller fastställd plan
    event = (plan.get("planhandelse") or {}).get("varde")
    if event in DECIDED:
        kinds = {(u.get("underlagstyp") or {}).get("varde") for u in plan.get("underlag") or []}
        for wanted in REQUIRED_UNDERLAG:
            if wanted not in kinds:
                add(FEL, "OP-JSON-042", f"En plan med planhändelsen {event} ska ha ett underlag av typen {wanted}. "
                                        "Lägg till det under Planens uppgifter, fliken Underlag.",
                    plan.get("objektidentitet"))
        if plan.get("digitaltUrsprung") is not False and not decisions:
            add(FEL, "OP-JSON-044", f"En plan med planhändelsen {event} ska ha minst ett beslut. Fyll i "
                                    "antagandebeslutet under Planens uppgifter, fliken Beslut.",
                plan.get("objektidentitet"))

    # OP-JSON-034, 038: plangeometri och område ska ha geometri
    for content in contents:
        group = (content.get("innehallstyp") or {}).get("grupp")
        if group in GEOMETRY_REQUIRED and not content.get("geometri"):
            rule = "OP-JSON-034" if group == "Plangeometri" else "OP-JSON-038"
            add(FEL, rule, f"{group} ska ha geometri.", content.get("objektidentitet"))

    # OP-JSON-003: bokmärkenas namn; ÖP-X07: planhandlingen i Office Open XML
    for props in [plan, *contents]:
        for section in props.get("dokument") or []:
            for bookmark in section.get("avsnittsbokmarke") or []:
                if not BOOKMARK.match(str(bookmark)):
                    add(FEL, "OP-JSON-003", f"Bokmärket {bookmark!r} ska börja med en bokstav och bara innehålla "
                                            "bokstäver a–z, siffror och understreck (högst 40 tecken).",
                        props.get("objektidentitet"))
            name = str(((section.get("dokument") or {}).get("namn")) or "")
            if name and not name.lower().endswith(OOXML):
                add(FEL, "ÖP-X07", f"Planhandlingen {name} ska vara ett Word-dokument (Office Open XML, .docx).",
                    props.get("objektidentitet"))

    # ÖP-X04, X05: linjer som korsar sig själva och spikar
    for content in contents:
        for points, closed in _parts(content.get("geometri")):
            if not closed and self_crossings(points):
                add(FEL, "ÖP-X04", f"{_name(content)}: linjen korsar sig själv.", content.get("objektidentitet"))
            count = spikes(points, closed)
            if count:
                add(FEL, "ÖP-X05", f"{_name(content)}: {count} spik{'ar' if count > 1 else ''} (en vinkel på högst "
                                   f"{SPIKE_DEGREES:g} grader mellan två linjesegment).",
                    content.get("objektidentitet"))

    # OP-JSON-006: värdena ur ÖP-katalogen stämmer med katalogens id:n
    if catalog is not None:
        index = catalog_index(catalog)
        for props in [plan, *contents]:
            for key, value in _catalog_values(props):
                for name_key, id_key in (("varde", "vardereferens"), ("grupp", "gruppreferens")):
                    reference, name = value.get(id_key), value.get(name_key)
                    if reference is None:
                        continue
                    known = index.get(str(reference))
                    if known is None:
                        add(VARNING, "OP-JSON-006", f"{key}: {name!r} finns inte i ÖP-katalogen {catalog.version} "
                                                    "(planen kan ha en äldre katalogversion).",
                            props.get("objektidentitet"))
                    elif known != str(name).strip():
                        add(FEL, "OP-JSON-006", f"{key}: {name!r} stämmer inte med ÖP-katalogens namn {known!r} "
                                                f"för samma id.", props.get("objektidentitet"))
    return found
