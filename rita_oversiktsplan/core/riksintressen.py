"""Hämta riksintressen: riksintressena enligt 3 och 4 kap. miljöbalken ur Boverkets samlade karttjänst, som underlag i
planen (gruppen *Riksintressen enligt 3 och 4 kap. MB*), med myndighetens id som riksintressets id.

Källa: Boverket, karttjänsten *Riksintressen* (ArcGIS REST, ``gis2.boverket.se/arcgis/rest/services/
Riksintressen___Februari_2025_WMS/MapServer``, uppdaterad februari 2026 enligt Boverket). Boverket sammanställer
myndigheternas underlag och kan inte garantera att det är aktuellt; det är länsstyrelsen som ansvarar för
planeringsunderlaget. Tjänstens lager och fält lästes 2026-10-19.

Den här modulen är ren Python utom :func:`import_records`. Hämtningen tar en funktion ``get(url) -> text``, så att
nätverket (QGIS ``QgsBlockingNetworkRequest`` i pluginet) kan bytas ut i tester.

Urval (pluginets tolkning): riksintressenas egna områden, linjer och punkter. Påverkansområden, buller- och
hinderytor (luftfart, totalförsvar) tas inte med, eftersom de beskriver hänsyn kring riksintresset snarare än
riksintresset självt; de finns i tjänsten om man vill lägga till dem för hand.
"""
from __future__ import annotations

import json
import urllib.parse
from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional

SERVICE = "https://gis2.boverket.se/arcgis/rest/services/Riksintressen___Februari_2025_WMS/MapServer"
PAGE = 1000  # objekt per fråga (tjänsten tillåter 2000)
CATEGORY = "riksintressen"  # pluginets grupp för underlaget
POSITION = "riksintressenop"  # Riksintresse, kommunens ställningstagande
# fält med myndighetens id och namn, i den ordning de prövas (olika lager har olika fält)
ID_FIELDS = ("RIKSID", "ORIGINALID", "ORGINALID", "RI_beteckning", "RI_Beteckning", "Identifieringskod", "SITE_CODE",
             "OMRADESNR", "OMRÅDESNR", "IDNR", "OBJID", "OMR_NR", "GlobalID")
NAME_FIELDS = ("NAMN", "Geonamn", "OBJNAMN", "F_Specifikt_namn_", "F_Generellt_namn_", "SpecNamn", "Specnamn",
               "GenNamn", "Namn", "VNAMN", "SAMEBY")
# platshållare som vissa lager har i namnfälten i stället för ett namn
PLACEHOLDERS = {"Generellt namn", "Specifikt namn"}


@dataclass(frozen=True)
class Source:
    """Ett lager i tjänsten och värdet i ÖP-katalogen det motsvarar."""
    layers: tuple[int, ...]  # lagrens id i tjänsten
    varde: str  # värdet i ÖP-katalogen (Riksintressen enligt 3 och 4 kap. MB)
    title: str  # i dialogen
    chapter: int  # 3 eller 4 kap. miljöbalken


SOURCES: tuple[Source, ...] = (
    Source((11,), "Friluftsliv", "Friluftsliv (3 kap. 6 §)", 3),
    Source((12,), "Naturvård", "Naturvård (3 kap. 6 §)", 3),
    Source((13,), "Kulturmiljövård", "Kulturmiljövård (3 kap. 6 §)", 3),
    Source((18, 3, 4, 5, 6, 7), "Yrkesfiske", "Yrkesfiske (3 kap. 5 §)", 3),
    Source((9, 10), "Rennäring", "Rennäring (3 kap. 5 §)", 3),
    Source((15, 16), "Fyndighet av ämnen och material", "Värdefulla ämnen och material (3 kap. 7 §)", 3),
    Source((19,), "Anläggning för energiproduktion", "Energiproduktion, vindbruk (3 kap. 8 §)", 3),
    Source((150, 153, 152, 154, 142, 145, 144, 146, 147, 148, 149, 132, 135, 134, 137, 138, 140, 141, 129, 128, 131),
           "Anläggning för kommunikation, trafikslagen",
           "Kommunikationer: väg, järnväg, sjöfart, luftfart (3 kap. 8 §)", 3),
    Source((55,), "Anläggning för slutlig förvaring av använt kärnbränsle och kärnavfall",
           "Slutförvaring av kärnbränsle och kärnavfall (3 kap. 8 §)", 3),
    Source((162,), "Anläggning för industriell produktion", "Industriell produktion (3 kap. 8 §)", 3),
    Source((92, 91, 126), "Anläggning för totalförsvaret", "Totalförsvaret (3 kap. 9 §)", 3),
    Source((169,), "Turism och rörligt friluftsliv", "Turism och rörligt friluftsliv (4 kap. 2 §)", 4),
    Source((165,), "Obruten kust", "Obruten kust (4 kap. 3 §)", 4),
    Source((164,), "Högexploaterad kust", "Högexploaterad kust (4 kap. 4 §)", 4),
    Source((170,), "Obrutet fjäll", "Obrutet fjäll (4 kap. 5 §)", 4),
    Source((171,), "Skyddat vattendrag", "Skyddade vattendrag (4 kap. 6 §)", 4),
    Source((172,), "Nationalstadspark", "Nationalstadspark (4 kap. 7 §)", 4),
    Source((83,), "Natura 2000, vilda fåglar", "Natura 2000, fågeldirektivet (4 kap. 8 §)", 4),
    Source((85, 87, 86), "Natura 2000, vilda djur och växter", "Natura 2000, art- och habitatdirektivet (4 kap. 8 §)",
           4),
)


@dataclass
class Record:
    """Ett riksintresseobjekt ur tjänsten."""
    varde: str
    geometry: dict  # GeoJSON-geometri i planens koordinatsystem
    ri_id: Optional[str] = None
    namn: Optional[str] = None
    layer: int = 0
    properties: dict = field(default_factory=dict)


class FetchError(RuntimeError):
    pass


def query_url(layer: int, bbox: Optional[tuple[float, float, float, float]], epsg: int, offset: int = 0,
              service: str = SERVICE, where: str = "1=1") -> str:
    """Frågan för ett lager inom ett utsnitt (xmin, ymin, xmax, ymax) i planens koordinatsystem, som GeoJSON. Utan
    utsnitt (``bbox`` None) gäller bara ``where``."""
    params = {"where": where}
    if bbox is not None:
        params.update({"geometry": ",".join(f"{v:.3f}" for v in bbox), "geometryType": "esriGeometryEnvelope",
                       "inSR": str(epsg), "spatialRel": "esriSpatialRelIntersects"})
    params.update({"outFields": "*", "returnGeometry": "true", "outSR": str(epsg), "resultOffset": str(offset),
                   "resultRecordCount": str(PAGE), "f": "geojson"})
    return f"{service}/{layer}/query?" + urllib.parse.urlencode(params)


def fetch_layer(get: Callable[[str], str], service: str, layer: int, bbox, epsg: int, title: str,
                progress: Optional[Callable[[str], None]] = None, where: str = "1=1",
                owner: str = "Boverkets tjänst") -> list[tuple[dict, dict]]:
    """(egenskaper, GeoJSON-geometri) för alla objekt i ett lager i en ArcGIS-tjänst, sida för sida."""
    found: list[tuple[dict, dict]] = []
    offset = 0
    while True:
        if progress:
            progress(f"Hämtar {title} …")
        try:
            data = json.loads(get(query_url(layer, bbox, epsg, offset, service, where)))
        except (ValueError, OSError) as exc:
            raise FetchError(f"Kunde inte läsa svaret från {owner}: {exc}") from exc
        if "error" in data:
            message = (data.get("error") or {}).get("message", "okänt fel")
            raise FetchError(f"{owner[0].upper()}{owner[1:]} svarade med ett fel för {title}: {message}")
        features = data.get("features") or []
        found += [(f.get("properties") or {}, f["geometry"]) for f in features if f.get("geometry")]
        more = data.get("exceededTransferLimit") or (data.get("properties") or {}).get("exceededTransferLimit")
        if not more or not features:
            return found
        offset += len(features)


def _first(properties: dict, names: Iterable[str]) -> Optional[str]:
    for name in names:
        value = properties.get(name)
        if value not in (None, "") and str(value).strip() and str(value).strip() not in PLACEHOLDERS:
            return str(value).strip()
    return None


def fetch(get: Callable[[str], str], source: Source, bbox: tuple[float, float, float, float], epsg: int,
          service: str = SERVICE, progress: Optional[Callable[[str], None]] = None) -> list[Record]:
    """Alla objekt i en källa inom utsnittet, sida för sida."""
    records: list[Record] = []
    for layer in source.layers:
        for properties, geometry in fetch_layer(get, service, layer, bbox, epsg, source.title, progress):
            records.append(Record(source.varde, geometry, _first(properties, ID_FIELDS),
                                  _first(properties, NAME_FIELDS), layer, properties))
    return records


def unique(records: list[Record]) -> list[Record]:
    """Samma riksintresse kan finnas i flera delar eller lager; dubbletter (samma värde, id och geometri) tas bort."""
    seen, result = set(), []
    for record in records:
        key = (record.varde, record.ri_id, json.dumps(record.geometry, sort_keys=True))
        if key not in seen:
            seen.add(key)
            result.append(record)
    return result


# -- in i planen (QGIS) --------------------------------------------------------------------------------------------------
def _shape(geometry) -> str:
    """Geometrin som text avrundad till centimeter, för att känna igen objekt utan id vid en ny hämtning."""
    if geometry is None or geometry.isNull():
        return ""
    copy = type(geometry)(geometry)
    copy.convertToMultiType()
    return copy.asWkt(2)


SIMPLIFY = 5.0  # m: hämtade ytor och linjer förenklas så mycket (gränserna i en översiktsplan är illustrativa)
MIN_HOLE = 1000.0  # m²: mindre hål i hämtade ytor tas bort


def generalize(geometry):
    """Förenklar en hämtad yta eller linje: myndigheternas ytor kan vara framtagna ur rutnät med trappstegskanter
    (Klarälvens översvämningsyta i Munkfors: 26 000 hörn och 165 hål). Bården och namnet längs kanten tog då 12 s
    respektive minuter att rita; förenklat med 5 m: 2 500 hörn, 0,3 s, ytan ändrad 0,1 %."""
    from qgis.core import QgsWkbTypes
    kind = QgsWkbTypes.geometryType(geometry.wkbType())
    if kind == QgsWkbTypes.GeometryType.PointGeometry:
        return geometry
    simple = geometry.simplify(SIMPLIFY)
    if simple is None or simple.isNull() or simple.isEmpty():
        return geometry
    if kind == QgsWkbTypes.GeometryType.PolygonGeometry:
        simple = simple.removeInteriorRings(MIN_HOLE)
        if not simple.isGeosValid():
            simple = simple.makeValid()
            if QgsWkbTypes.geometryType(simple.wkbType()) != kind:
                simple = simple.convertToType(kind, True)
    return simple if simple is not None and not simple.isEmpty() else geometry


def clip_geometry(geometry, clip):
    """Geometrin klippt mot ``clip`` (planens avgränsning), eller None om inget blir kvar. Punkter klipps inte, bara
    sorteras bort utanför. Ogiltiga ytor lagas först, och ett blandat resultat (till exempel en yta som bara nuddar
    gränsen) behåller bara delarna av den ursprungliga geometritypen."""
    from qgis.core import QgsWkbTypes
    if clip is None or clip.isEmpty():
        return geometry
    if not geometry.intersects(clip):
        return None
    kind = QgsWkbTypes.geometryType(geometry.wkbType())
    if kind == QgsWkbTypes.GeometryType.PointGeometry:
        return geometry
    # Först ett snabbt klipp mot planens rektangel: en hel älvs översvämningskartering kan ha hundratusentals
    # brytpunkter, och att laga och skära den hela tog minuter (Klarälven: 745 000 hörn, 138 s mot under 1 s).
    geometry = geometry.clipped(clip.boundingBox())
    if geometry.isEmpty():
        return None
    if not geometry.isGeosValid():
        geometry = geometry.makeValid()
    clipped = geometry.intersection(clip)
    if clipped.isEmpty():
        return None
    if QgsWkbTypes.geometryType(clipped.wkbType()) != kind:
        clipped = clipped.convertToType(kind, True)
        if clipped is None or clipped.isNull() or clipped.isEmpty():
            return None
    return clipped


def _layers(group, key: str) -> dict:
    from .project import layer_in_group
    return {suffix: layer_in_group(group, f"innehall_op_{key}_{suffix}") for suffix in ("polygon", "line", "point")}


def _suffix(geometry) -> str:
    from qgis.core import QgsWkbTypes
    return {QgsWkbTypes.GeometryType.PolygonGeometry: "polygon",
            QgsWkbTypes.GeometryType.LineGeometry: "line"}.get(QgsWkbTypes.geometryType(geometry.wkbType()), "point")


def _add(layer, geometry, values: dict):
    """Lägger ett objekt i lagrets redigeringsbuffert och returnerar det (med objektidentiteten från standardvärdet)."""
    import uuid

    from qgis.core import QgsGeometry, QgsVectorLayerUtils, QgsWkbTypes

    from . import content
    if not layer.isEditable():
        layer.startEditing()
    attributes = {layer.fields().indexOf(k): content._to_qgis(v) for k, v in values.items()
                  if layer.fields().indexOf(k) >= 0}
    feature = QgsVectorLayerUtils.createFeature(layer, geometry, attributes)
    if layer.fields().indexOf("objektidentitet") >= 0 and not content.plain(feature["objektidentitet"]):
        feature["objektidentitet"] = str(uuid.uuid4())
    # Geometrin måste ha lagrets typ: Lantmäteriets data har höjdvärden (Z) och kan ha bågar, och planens lager är
    # plana multiytor/-linjer. Annars läggs objektet i bufferten men vägras när man sparar ("geometritypen stämmer
    # inte överens med det aktuella lagret"), och inget i lagret går att spara.
    if feature.hasGeometry():
        fixed = QgsGeometry(feature.geometry())
        if QgsWkbTypes.isCurvedType(fixed.wkbType()):
            fixed = QgsGeometry(fixed.constGet().segmentize())
        fixed.get().dropZValue()
        fixed.get().dropMValue()
        if QgsWkbTypes.isMultiType(layer.wkbType()):
            fixed.convertToMultiType()
        else:
            fixed.convertToSingleType()
        if QgsWkbTypes.flatType(fixed.wkbType()) != QgsWkbTypes.flatType(layer.wkbType()):
            raise ValueError(f"En geometri av typen {QgsWkbTypes.displayString(fixed.wkbType())} passar inte i "
                             f"lagret {layer.name()}.")
        feature.setGeometry(fixed)
    layer.addFeature(feature)
    return feature


def _positions_by_target(group) -> set[str]:
    """Objektidentiteterna för de riksintressen som redan har ett ställningstagande som berör dem."""
    from . import content, relations
    links = relations.links(group)
    found: set[str] = set()
    for layer in _layers(group, POSITION).values():
        for f in layer.getFeatures() if layer is not None else ():
            link = content.plain(f[relations.LINK])
            found |= links.get(str(link), set()) if link else set()
    return found


def _add_position(group, source, base: dict, table, done: set[str]) -> Optional[str]:
    """Kopierar ett hämtat riksintresse (QgsFeature) till kommunens ställningstagande, med samma värde, namn,
    riksintressets id och geometri, och kopplar kopian till riksintresset med *berör annat innehåll*. Returnerar
    lagrets namn, eller None om riksintresset redan har ett ställningstagande."""
    import uuid

    from qgis.core import QgsGeometry

    from . import content, relations
    target = str(content.plain(source["objektidentitet"]) or "")
    if not target or target in done or not source.hasGeometry():
        return None
    layer = _layers(group, POSITION)[_suffix(source.geometry())]
    if layer is None:
        return None
    link = str(uuid.uuid4())
    values = {**base, "innehallstyp_varde": content.plain(source["innehallstyp_varde"]),
              "namn": content.plain(source["namn"]), "objektidentitet_ri": content.plain(source["objektidentitet_ri"]),
              relations.LINK: link}
    _add(layer, QgsGeometry(source.geometry()), values)
    if not table.isEditable():
        table.startEditing()
    _add(table, QgsGeometry(), {relations.LINK: link, relations.TARGET: target})
    done.add(target)
    return layer.name()


def create_positions(group, sources: list) -> dict[str, int]:
    """Skapa kommunens ställningstagande för hämtade riksintressen (QgsFeature ur gruppen *Riksintressen enligt 3 och
    4 kap. MB*). Riksintressen som redan har ett ställningstagande hoppas över. Allt läggs i redigeringsbufferten.
    Returnerar antal per lager."""
    from . import content, relations
    table = relations._table(group)
    base = content.new_content_values(group)  # kommunens eget innehåll: hör till en pågående ändring
    done = _positions_by_target(group)
    added: dict[str, int] = {}
    for source in sources:
        name = _add_position(group, source, base, table, done)
        if name:
            added[name] = added.get(name, 0) + 1
    return added


def is_position_layer(name: str) -> bool:
    """Om ett lagernamn (som i det :func:`import_records` returnerar) hör till kommunens ställningstagande."""
    from . import model
    title = next(c.alias for c in model.CATEGORIES if c.key == POSITION)
    return name.startswith(title)


def selected_sources(group) -> list:
    """De markerade objekten i gruppen *Riksintressen enligt 3 och 4 kap. MB*."""
    return [f for layer in _layers(group, CATEGORY).values() if layer is not None
            for f in layer.getSelectedFeatures()]


def import_records(group, records: list[Record], clip=None, today=None, positions: bool = False) -> dict[str, int]:
    """Lägger objekten som underlag i planen, i redigeringsbufferten (sparas med Avsluta redigering). ``clip`` är en
    QgsGeometry (planens avgränsning) som objekten klipps mot; objekt utanför tas inte med. Objekt som fanns före
    hämtningen (samma värde och riksintressets id, eller för objekt utan id samma värde och geometri) hoppas över, så att en ny hämtning inte ger dubbletter; ett
    riksintresse i flera delar får alla sina delar. Underlaget hör inte till en pågående ändring. Med ``positions``
    får varje nytt riksintresse också en kopia i kommunens ställningstagande (se :func:`create_positions`).
    Returnerar antal per lager."""
    import datetime

    from qgis.core import QgsGeometry, QgsJsonUtils
    from qgis.PyQt.QtCore import QDate

    from . import content, relations

    today = today or datetime.date.today()
    added: dict[str, int] = {}
    layers = _layers(group, CATEGORY)
    position_base = content.new_content_values(group) if positions else {}
    table = relations._table(group) if positions else None
    done = _positions_by_target(group) if positions else set()
    existing, shapes = set(), set()
    for layer in layers.values():
        for f in layer.getFeatures() if layer is not None else ():
            existing.add((str(f["innehallstyp_varde"]), str(f["objektidentitet_ri"])))
            shapes.add((str(f["innehallstyp_varde"]), _shape(f.geometry())))
    base = content.new_content_values(group)
    base.pop("beslut", None)  # underlaget hör inte till en pågående ändring
    for record in records:
        if record.ri_id and (record.varde, record.ri_id) in existing:
            continue
        geometry = QgsJsonUtils.geometryFromGeoJson(json.dumps(record.geometry))
        if geometry is None or geometry.isNull() or geometry.isEmpty():
            continue
        geometry = clip_geometry(geometry, clip)
        if geometry is None:
            continue
        geometry = generalize(geometry)
        suffix = _suffix(geometry)
        layer = layers[suffix]
        if layer is None:
            continue
        parts = [QgsGeometry.fromPointXY(p) for p in geometry.asMultiPoint()] if suffix == "point" and \
            geometry.isMultipart() else [geometry]
        values = {**base, "innehallstyp_varde": record.varde, "namn": record.namn, "objektidentitet_ri": record.ri_id,
                  "hamtatdatum": QDate(today.year, today.month, today.day)}
        for part in parts:
            if suffix != "point":
                part.convertToMultiType()
            if not record.ri_id:  # utan id: samma värde och samma geometri som förut räknas som samma objekt
                if (record.varde, _shape(part)) in shapes:
                    continue
            feature = _add(layer, part, values)
            added[layer.name()] = added.get(layer.name(), 0) + 1
            if positions:
                name = _add_position(group, feature, position_base, table, done)
                if name:
                    added[name] = added.get(name, 0) + 1
    return added
