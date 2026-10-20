"""Befintlig mark- och vattenanvändning ur Lantmäteriets Topografi 10 (eller Marktäcke): objekttyperna i markytorna,
anläggningsområdena, vägarna, järnvägarna, vattendragen, ledningarna och vissa punkter omklassas till ÖP-katalogens
värden för mark- och vattenanvändning och läggs in i planens lager för yta, linje och punkt.

Källor: Lantmäteriet, *Topografi 10 Nedladdning, vektor* (en GeoPackage per tema, t.ex. ``mark.gpkg``,
``kommunikation.gpkg``, ``hydro.gpkg``, ``anlaggningsomrade.gpkg``, ofta i en zip-fil) och *Marktäcke Nedladdning,
vektor* (en GeoPackage per kommun). Användaren laddar ner filerna själv från Geotorget (kräver inloggning).
Objekttyper och ändamål enligt Lantmäteriets dokumentation av Topografi 10 (läst 2026-10-20). Skikten hittas på fältet
``objekttyp``, inte på namnen; anläggningsområden har också ``andamal``.

Behandling (pluginets val):

* **Ytor:** sammanslagna per värde och klippta mot planens avgränsning. Anläggningsområden, flygplatser och
  transformatorområden ligger ovanpå markytorna i Topografi 10 och går före dem: markytorna får hål där.
* **Linjer:** sammanslagna per värde till sammanhängande linjer, klippta.
* **Punkter:** var för sig, inom planen.
* Alla ytor och linjer förenklas med 5 m (``riksintressen.generalize``). Allt tas med, oavsett storlek.

Omklassningen (``DEFAULT_TYPES``, ``DEFAULT_ANDAMAL``) är pluginets förslag och går att ändra i dialogen. Topografi 10
visar vad marken täcks av och vad som finns där, inte alltid vad den används till: resultatet är ett underlag att
rätta för hand.

Ren Python utom :func:`read_keys`, :func:`build` och :func:`add_to_plan`.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

FIELD = "objekttyp"
PURPOSE = "andamal"
MARK = "Från Lantmäteriet"  # början på preciseringen; känns igen när man kör igen
LAYERS = {"polygon": "innehall_op_markochvattenanvandning_polygon",
          "line": "innehall_op_markochvattenanvandning_line",
          "point": "innehall_op_markochvattenanvandning_point"}
KIND_WORDS = {"polygon": "yta", "line": "linje", "point": "punkt"}

# Markytorna (tema Mark i Topografi 10, och Marktäcke): det som anläggningsområden och liknande ritas ovanpå.
BASE_TYPES = {
    "Sluten bebyggelse", "Hög bebyggelse", "Låg bebyggelse", "Industri- och handelsbebyggelse", "Öppen mark",
    "Torg", "Åker", "Fruktodling", "Kalfjäll", "Barr- och blandskog", "Lövskog", "Fjällbjörkskog",
    "Ej karterat område", "Hav", "Sjö", "Vattendragsyta", "Anlagt vatten", "Glaciär", "Sankmark, fast",
    "Sankmark, våt"}

# Skikten med byggnader (tema Byggnadsverk): föreslås aldrig, eftersom flera objekttyper där heter som
# anläggningsområdenas (t.ex. Samhällsfunktion).
BUILDING_LAYERS = ("byggnad",)

# Förslaget per objekttyp (None = tas inte med). Punkter och byggnader föreslås inte alls, se default_value.
DEFAULT_TYPES: dict[str, Optional[str]] = {
    # tema Mark / Marktäcke
    "Sluten bebyggelse": "Funktionsblandad bebyggelse",
    "Hög bebyggelse": "Bostadsbebyggelse",
    "Låg bebyggelse": "Bostadsbebyggelse",
    "Industri- och handelsbebyggelse": "Verksamheter",
    "Torg": "Funktionsblandad bebyggelse",
    "Öppen mark": "Landsbygd",
    "Åker": "Landsbygd",
    "Fruktodling": "Jordbruk",
    "Kalfjäll": "Natur- och kulturlandskap",
    "Barr- och blandskog": "Landsbygd",
    "Lövskog": "Landsbygd",
    "Fjällbjörkskog": "Natur- och kulturlandskap",
    "Glaciär": "Natur- och kulturlandskap",
    "Hav": "Vatten",
    "Sjö": "Vatten",
    "Vattendragsyta": "Vatten",
    "Anlagt vatten": "Vatten",
    "Ej karterat område": None,
    "Sankmark, fast": None,  # eget skikt ovanpå markytorna
    "Sankmark, våt": None,
    # tema Anläggningsområde (ändamålet avgör, se DEFAULT_ANDAMAL)
    "Industriområde": "Verksamheter",
    "Samhällsfunktion": "Service",
    "Rekreation": "Friluftsliv och rekreation",
    "Idrottsplan": "Friluftsliv och rekreation",
    "Civilt skjutfält": None,
    "Industriområde, punkt": "Verksamheter",
    "Samhällsfunktion, punkt": "Service",
    "Rekreation, punkt": "Friluftsliv och rekreation",
    "Idrottsplan, punkt": "Friluftsliv och rekreation",
    "Flygplatsområde": "Luftfart",
    "Start- och landningsbana": None,  # ligger inom flygplatsområdet
    "Helikopterplats": "Luftfart",
    # tema Ledningar
    "Transformatorområde": "Teknisk infrastruktur",
    "Kraftledning stam": "Teknisk infrastruktur",
    "Kraftledning region": "Teknisk infrastruktur",
    "Kraftledning fördelning": None,
    "Rörledning": None,
    "Telefonledning": None,
    # tema Kommunikation: de större vägarna och spårtrafiken
    "Motorväg": "Vägtrafik",
    "Motortrafikled": "Vägtrafik",
    "Mötesfri väg": "Vägtrafik",
    "Landsväg": "Vägtrafik",
    "Landsväg liten": "Vägtrafik",
    "Övergripande länk": "Vägtrafik",
    "Huvudgata": "Vägtrafik",
    "Småväg": None,
    "Småväg enkel standard": None,
    "Lokalgata stor": None,
    "Lokalgata liten": None,
    "Kvartersväg": None,
    "Parkeringsområdesväg": None,
    "Infartsväg/Utfartsväg": None,
    "Leveransväg": None,
    "Oklassificerad": None,
    "Färjeled": "Sjöfart",
    "Järnväg": "Järnväg",
    "Spårväg": "Järnväg",
    "Tunnelbana": "Järnväg",
    "Museijärnväg": None,
    "Järnvägsstation": "Järnväg",
    "Tunnelbanestation": None,
    "Spårvagnshållplats": None,
    # tema Hydrografi
    "Vattendrag": "Vatten",
    # tema Byggnadsverk
    "Vindkraftverk": "Energiproduktion",
}

# Anläggningsområden efter ändamål (går före objekttypen).
DEFAULT_ANDAMAL: dict[tuple[str, str], Optional[str]] = {
    ("Industriområde", "Energiproduktion"): "Energiproduktion",
    ("Industriområde", "Gruvområde"): "Verksamheter",
    ("Industriområde", "Täkt"): "Verksamheter",
    ("Industriområde", "Rengärde"): "Renskötsel",
    ("Samhällsfunktion", "Avfallsanläggning"): "Teknisk infrastruktur",
    ("Samhällsfunktion", "Begravningsplats"): "Grönområde",
    ("Samhällsfunktion", "Civilt övningsfält"): "Annan mark- och vattenanvändning",
    ("Samhällsfunktion", "Trafikövningsplats"): "Annan mark- och vattenanvändning",
    ("Rekreation", "Parkområde"): "Grönområde",
    ("Rekreation", "Koloniområde"): "Grönområde",
}


@dataclass(frozen=True)
class Key:
    """Det som omklassas: ett skikt, en objekttyp och (för anläggningsområden) ett ändamål."""
    layer: str
    objekttyp: str
    andamal: str = ""
    kind: str = "polygon"  # polygon, line eller point

    @property
    def id(self) -> str:
        return f"{self.layer}|{self.objekttyp}|{self.andamal}"

    @property
    def label(self) -> str:
        return f"{self.objekttyp} – {self.andamal}" if self.andamal else self.objekttyp


def default_value(key: Key) -> Optional[str]:
    """Pluginets förslag. Byggnader och punkter föreslås aldrig (användarens önskan): de går att välja i tabellen."""
    if key.kind == "point" or key.layer.startswith(BUILDING_LAYERS):
        return None
    if key.andamal:
        base = key.objekttyp.replace(", punkt", "")
        if (base, key.andamal) in DEFAULT_ANDAMAL:
            return DEFAULT_ANDAMAL[(base, key.andamal)]
    return DEFAULT_TYPES.get(key.objekttyp)


def mapping_for(keys: list[Key], saved: Optional[dict[str, Optional[str]]] = None) -> dict[str, Optional[str]]:
    """Omklassningen per ``Key.id``: sparad, annars förslaget, annars tas inte med."""
    saved = saved or {}
    return {k.id: saved[k.id] if k.id in saved else default_value(k) for k in keys}


def precisering(sources: list[str]) -> str:
    return f"{MARK} ({', '.join(sorted(sources))})"


def sources(path: str | Path) -> list[str]:
    """GDAL-sökvägarna till filens GeoPackage(r): en GeoPackage direkt, eller alla i en zip-fil."""
    path = Path(path)
    if path.suffix.lower() != ".zip":
        return [str(path)]
    import zipfile
    with zipfile.ZipFile(path) as archive:
        inner = [n for n in archive.namelist() if n.lower().endswith(".gpkg")]
    if not inner:
        raise ValueError(f"Zip-filen {path.name} innehåller ingen GeoPackage (.gpkg).")
    return [f"/vsizip/{path.as_posix()}/{name}" for name in inner]


def sort_key(key: Key) -> tuple:
    order = list(DEFAULT_TYPES)
    kinds = ("polygon", "line", "point")
    return (kinds.index(key.kind), order.index(key.objekttyp) if key.objekttyp in order else len(order),
            key.objekttyp, key.andamal)


# -- QGIS -----------------------------------------------------------------------------------------------------------
def _kind(layer) -> Optional[str]:
    from qgis.core import QgsWkbTypes
    return {QgsWkbTypes.GeometryType.PolygonGeometry: "polygon", QgsWkbTypes.GeometryType.LineGeometry: "line",
            QgsWkbTypes.GeometryType.PointGeometry: "point"}.get(QgsWkbTypes.geometryType(layer.wkbType()))


def _layers(path: str | Path):
    """Skikten i filen som har fältet objekttyp och en geometri."""
    from osgeo import ogr
    from qgis.core import QgsVectorLayer
    found = []
    for source in sources(path):
        ds = ogr.Open(source)
        if ds is None:
            raise ValueError(f"Kunde inte öppna {source}.")
        names = [ds.GetLayer(i).GetName() for i in range(ds.GetLayerCount())]
        ds = None
        for name in names:
            layer = QgsVectorLayer(f"{source}|layername={name}", name, "ogr")
            if layer.isValid() and layer.fields().indexOf(FIELD) >= 0 and _kind(layer):
                found.append(layer)
    if not found:
        raise ValueError("Filen har inga skikt med fältet objekttyp. Är det Lantmäteriets Topografi 10 eller "
                         "Marktäcke (GeoPackage, eller zip-filen som den laddades ner)?")
    return found


def _key(layer, feature) -> Key:
    purpose = ""
    if layer.fields().indexOf(PURPOSE) >= 0:
        value = feature[PURPOSE]
        purpose = str(value) if value not in (None, "") and str(value) != "NULL" else ""
    return Key(layer.name(), str(feature[FIELD]), purpose, _kind(layer))


def read_keys(path: str | Path) -> list[Key]:
    """Allt i filen som kan omklassas (skikt, objekttyp, ändamål), sorterat som förslaget."""
    from qgis.core import QgsFeatureRequest
    keys: set[Key] = set()
    for layer in _layers(path):
        fields = [FIELD] + ([PURPOSE] if layer.fields().indexOf(PURPOSE) >= 0 else [])
        request = QgsFeatureRequest().setFlags(QgsFeatureRequest.Flag.NoGeometry).setSubsetOfAttributes(
            fields, layer.fields())
        for feature in layer.getFeatures(request):
            if feature[FIELD] not in (None, ""):
                keys.add(_key(layer, feature))
    return sorted(keys, key=sort_key)


def build(path: str | Path, mapping: dict[str, Optional[str]], clip=None, crs=None,
          progress: Optional[Callable[[str], None]] = None) -> dict[tuple[str, str], tuple[list, list[str]]]:
    """Geometrierna per (geometri, värde): ``{("polygon", "Skogsbruk"): ([QgsGeometry …], [objekttyper])}``,
    sammanslagna, klippta mot ``clip`` (planens avgränsning, i planens koordinatsystem ``crs``) och förenklade.
    Anläggningsområden och andra ytor ovanpå markytorna går före dem."""
    from qgis.core import QgsCoordinateTransform, QgsFeatureRequest, QgsGeometry, QgsProject

    from .riksintressen import generalize
    collected: dict[tuple[str, str, bool], list] = {}  # (geometri, värde, markyta) → geometrier
    labels: dict[tuple[str, str], set[str]] = {}
    for layer in _layers(path):
        if progress:
            progress(f"Läser {layer.name()} …")
        transform = QgsCoordinateTransform(layer.crs(), crs, QgsProject.instance()) if crs is not None and \
            layer.crs() != crs else None
        request = QgsFeatureRequest()
        if clip is not None:
            rect = clip.boundingBox()
            if transform is not None:
                rect = transform.transformBoundingBox(rect, QgsCoordinateTransform.TransformDirection.ReverseTransform)
            request.setFilterRect(rect)
        for feature in layer.getFeatures(request):
            if not feature.hasGeometry() or feature[FIELD] in (None, ""):
                continue
            key = _key(layer, feature)
            value = mapping.get(key.id)
            if not value:
                continue
            geometry = QgsGeometry(feature.geometry())
            if transform is not None:
                geometry.transform(transform)
            base = key.kind == "polygon" and key.objekttyp in BASE_TYPES
            collected.setdefault((key.kind, value, base), []).append(geometry)
            labels.setdefault((key.kind, value), set()).add(key.label)

    # ytorna ovanpå markytorna (anläggningsområden m.m.) slås ihop först; markytorna får hål där
    overlay = [g for (kind, _, base), shapes in collected.items() if kind == "polygon" and not base for g in shapes]
    on_top = QgsGeometry.unaryUnion(overlay) if overlay else None
    if on_top is not None and not on_top.isGeosValid():
        on_top = on_top.makeValid()

    result: dict[tuple[str, str], tuple[list, list[str]]] = {}
    for kind, value in sorted({(k, v) for k, v, _ in collected}):
        if progress:
            progress(f"Slår ihop {value} ({KIND_WORDS[kind]}) …")
        parts: list = []
        for base in (False, True):
            shapes = collected.get((kind, value, base))
            if not shapes:
                continue
            if kind == "point":
                parts += [p for g in shapes for p in (g.asGeometryCollection() if g.isMultipart() else [g])
                          if clip is None or clip.contains(p)]
                continue
            merged = QgsGeometry.unaryUnion(shapes)
            if not merged.isGeosValid():
                merged = merged.makeValid()
            if base and on_top is not None:
                merged = merged.difference(on_top)
            if kind == "line":
                merged = merged.mergeLines()
            if clip is not None:
                merged = merged.intersection(clip)
            for part in merged.asGeometryCollection():
                if part.isEmpty() or _kind_of(part) != kind:
                    continue
                part = generalize(part)
                if not part.isEmpty():
                    parts.append(part)
        if kind == "polygon" and len(parts) > 1:  # en yta per sammanhängande område, även över skikten
            union = QgsGeometry.unaryUnion(parts)
            parts = [p for p in union.asGeometryCollection() if not p.isEmpty()]
        for part in parts:
            if kind != "point":
                part.convertToMultiType()
        if parts:
            result[(kind, value)] = (parts, sorted(labels[(kind, value)]))
    return result


def _kind_of(geometry) -> str:
    from qgis.core import QgsWkbTypes
    return {QgsWkbTypes.GeometryType.PolygonGeometry: "polygon", QgsWkbTypes.GeometryType.LineGeometry: "line"}.get(
        QgsWkbTypes.geometryType(geometry.wkbType()), "point")


def add_to_plan(group, built: dict, replace: bool = True) -> tuple[dict[str, int], int]:
    """Lägger geometrierna i planens mark- och vattenanvändning (yta, linje, punkt; i redigeringsbufferten). Med
    ``replace`` tas det som tidigare kommit från Lantmäteriet bort först, så att en ny körning inte ger dubbletter;
    ritade objekt rörs inte. Returnerar antal per värde och geometri (``"Skogsbruk (yta)"``) och antal borttagna."""
    from . import content
    from .project import layer_in_group
    from .riksintressen import _add
    layers = {kind: layer_in_group(group, name) for kind, name in LAYERS.items()}
    if any(layer is None for layer in layers.values()):
        raise ValueError("Lagren för mark- och vattenanvändning saknas i planen. Öppna planen på nytt.")
    removed = 0
    for layer in layers.values():
        if not layer.isEditable():
            layer.startEditing()
        if replace:
            old = [f.id() for f in layer.getFeatures()
                   if str(content.plain(f["precisering"]) or "").startswith(MARK)]
            layer.deleteFeatures(old)
            removed += len(old)
    base = content.new_content_values(group)
    base.pop("beslut", None)  # befintlig användning hör inte till en pågående ändring
    added: dict[str, int] = {}
    for (kind, value), (parts, labels) in built.items():
        values = {**base, "innehallstyp_varde": value, "precisering": precisering(labels),
                  "utbyggnadsordning": None}
        for part in parts:
            _add(layers[kind], part, values)
        name = f"{value} ({KIND_WORDS[kind]})"
        added[name] = added.get(name, 0) + len(parts)
    return added, removed
