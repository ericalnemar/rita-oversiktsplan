"""Datamodell (GeoPackage-schema) för en översiktsplan enligt Boverkets GIS-databasmodell för ÖP-modellen. Ren Python.

Tabell- och kolumnnamnen följer Boverkets GeoPackage ``databasmodell_op_0.3`` (synkad med test 4_1 av Lantmäteriets
nationella specifikation för översiktsplan), så att en plan som pluginet skapar har samma struktur som Boverkets mall.
Varje innehållstyp är ett lager i tre varianter: ``_polygon``, ``_line`` och ``_point`` (utom Område och
Plangeometri, som bara är ytor).

Medvetna avvikelser från Boverkets mall (se ``docs/datamodell.md``):
  * alla tabeller har ``fid`` som nyckel och ``geom`` som geometrikolumn, och alla lager ligger i SWEREF 99 TM
    (mallen har ``OBJECTID``/``Shape`` och Web Mercator i lagret Plangeometri);
  * ``oversiktsplan`` har även ``kommunnamn``, som specifikationen kräver;
  * datum är datum, ja/nej-fält är booleska och ``digitalt_ursprung`` är ett ja/nej-fält;
  * restkolumner i mallen (``dokument_id1``, ``planhandelse_datum1``, ``GlobalID``) och ``anvandningsstatus``, som
    togs bort ur ÖP-katalogen i version 2.0, finns inte med; inte heller ``texttyp_lookup``, som ersatts av
    ``avsnittstyp_varde_lookup``;
  * uppslagstabellerna har samma kolumner överallt och fylls med värden ur den aktuella ÖP-katalogen.

Pluginets egna tabeller har prefixet ``rita_``: metadata och standardvärden (``rita_oversiktsplan_meta``) och
geometri som ritats men ännu inte fått något innehåll (``rita_otilldelad_yta``, ``_linje``, ``_punkt``). De följer
inte med i en leverans.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

DATABASMODELL = "0.3"  # Boverkets GIS-databasmodell som tabellerna följer
SPEC_VERSION = "test 4"  # Lantmäteriets nationella specifikation för översiktsplan
SCHEMA_VERSION = 4  # pluginets egen schemaversion (1: grundtabellerna; 2: + otilldelad geometri, standardvärden;
# 3: + beslut_op; 4: + precisering i plangeometrin och rita_pilar i utvecklingsinriktningens linjer)
EPSG = 3006  # SWEREF 99 TM, som i Boverkets mall; standard för nya planer
# Lantmäteriets geometri 2.0.1 (koordinatsystemPlan) tillåter SWEREF 99 TM och de tolv lokala zonerna
EPSG_CODES = tuple(range(3006, 3019))
META_TABLE = "rita_oversiktsplan_meta"

# Fälttyper
TEXT, INT, REAL, DATE, DATETIME, BOOL = "text", "int", "real", "date", "datetime", "bool"

# Uttryck som QGIS använder för standardvärden.
UUID_EXPR = "lower(uuid('WithoutBraces'))"
NOW_EXPR = "now()"
TRUE_EXPR = "true"
FALSE_EXPR = "false"

AVGRANSNING = ("nedåt", "uppåt")  # vertikal avgränsning, kodlista i specifikationen


@dataclass(frozen=True)
class FieldDef:
    name: str
    type: str
    alias: str
    required: bool = False  # obligatoriskt enligt specifikationen (mjuk begränsning i QGIS)
    lookup: Optional[str] = None  # uppslagstabell med tillåtna värden
    choices: Optional[tuple[str, ...]] = None  # fast lista med tillåtna värden
    default: Optional[str] = None  # QGIS-uttryck
    length: int = 0
    multiline: bool = False
    hidden: bool = False  # sköts av pluginet, visas inte i formuläret


@dataclass(frozen=True)
class LayerDef:
    name: str  # tabellnamn i GeoPackage
    alias: str
    geometry: Optional[str]  # "MultiPolygon" | "MultiLineString" | "Point" | None (attributtabell)
    fields: tuple[FieldDef, ...]
    category: Optional["Category"] = None


@dataclass(frozen=True)
class LookupDef:
    """Uppslagstabell med värden ur ÖP-katalogen."""
    name: str
    value_column: str
    category: str  # kategori i ÖP-katalogen
    group: Optional[str] = None  # annan kategori som grupp (se opkatalog.Catalog.values)
    itself: bool = False  # kategorin själv är värdet, inte värdena under den


@dataclass(frozen=True)
class Category:
    """En innehållstyp i Boverkets modell: ett lager per geometrityp och en uppslagstabell."""
    key: str  # del av tabellnamnet: innehall_op_<key>_<geometri>
    alias: str  # namn i QGIS lagerpanel
    catalog: str  # kategori i ÖP-katalogen
    group: Optional[str] = None
    kompletterande: Optional[str] = None  # uppslagstabell för kompletterande innehållstyp
    extra: tuple[FieldDef, ...] = ()
    polygon_only: bool = False

    @property
    def lookup(self) -> str:
        return f"innehall_op_{self.key}_lookup"


GEOMETRIES = (("polygon", "MultiPolygon", "yta"), ("line", "MultiLineString", "linje"), ("point", "Point", "punkt"))

# -- uppslagstabeller ---------------------------------------------------------------------------------------------------
PLANHANDELSE_LOOKUP = LookupDef("planhandelse_lookup", "planhandelse_varde", "Planhändelse")
SAMBANDSNIVA_LOOKUP = LookupDef("sambandsniva_lookup", "sambandsniva_varde", "Sambandsnivå")
UNDERLAGSTYP_LOOKUP = LookupDef("underlagstyp_lookup", "underlagstyp_varde", "Underlagstyp")
AVSNITTSTYP_LOOKUP = LookupDef("avsnittstyp_varde_lookup", "innehallstyp_varde", "Avsnittstyp")
KOMPLETTERANDE_MVA = LookupDef("innehall_op_kompletterandemarkochvattenanvandning_lookup", "innehallstyp_varde",
                               "Kompletterande mark- och vattenanvändning")
KOMPLETTERANDE_UI = LookupDef("innehall_op_kompletterandeutvecklingsinriktning_lookup", "innehallstyp_varde",
                              "Utvecklingsinriktning")

_UTBYGGNADSORDNING = FieldDef("utbyggnadsordning", TEXT, "Utbyggnadsordning", multiline=True)
_SAMBANDSNIVA = FieldDef("sambandsniva_varde", TEXT, "Sambandsnivå", lookup=SAMBANDSNIVA_LOOKUP.name)
_RI = FieldDef("objektidentitet_ri", TEXT, "Riksintressets objektidentitet", length=38)

CATEGORIES: tuple[Category, ...] = (
    Category("plangeometri", "Plangeometri", "Plangeometri", polygon_only=True),
    Category("omrade", "Område", "Område", polygon_only=True),
    Category("utvecklingsinriktning", "Utvecklingsinriktning", "Utvecklingsinriktning",
             kompletterande=KOMPLETTERANDE_UI.name, extra=(_SAMBANDSNIVA, _UTBYGGNADSORDNING)),
    Category("markochvattenanvandning", "Mark- och vattenanvändning", "Mark- och vattenanvändning",
             kompletterande=KOMPLETTERANDE_MVA.name, extra=(_UTBYGGNADSORDNING,)),
    Category("riksintressenop", "Riksintresse, kommunens ställningstagande", "Riksintresse kommunens ställningstagande",
             extra=(_RI,)),
    Category("riksintressen", "Riksintressen enligt 3 och 4 kap. MB", "Riksintresse kommunens ställningstagande",
             group="Riksintressen enligt 3 och 4 kap. MB",
             extra=(FieldDef("extern_referens_ri_id", TEXT, "Extern referens", length=38),
                    FieldDef("hamtatdatum", DATE, "Hämtat datum"), _RI)),
    Category("miljokvalitetsnormer", "Miljökvalitetsnormer", "Miljökvalitetsnormer enligt 5 kap. MB"),
    Category("ovrigaforhallandeavvasentligbetydelse", "Övriga förhållanden av väsentlig betydelse",
             "Övriga förhållanden av väsentlig betydelse"),
    Category("bostadsforsorjning", "Bostadsförsörjning", "Bostadsförsörjning"),
    Category("malplanprogram", "Mål, planer och program", "Mål, planer och program"),
    Category("lis", "LIS", "LIS"),
    Category("sarskiltvardefullabyggnadsverkallmannaplatserochbebyggelseomraden", "Särskilt värdefull kulturmiljö",
             "Särskilt värdefull kulturmiljö"),
    Category("klimatrelateradrisk", "Klimatrelaterade risker", "Klimatrelaterade risker"),
    Category("avvikelsefranregionplan", "Avvikelse från regionplan", "Avvikelse från regionplan"),
    Category("mellankommunalaochregionalaintressen", "Mellankommunala och regionala intressen",
             "Mellankommunala och regionala intressen", extra=(_SAMBANDSNIVA,)),
    Category("lansstyrelsensinvandning", "Länsstyrelsens invändningar",
             "Invändningar i länsstyrelsens granskningsyttrande"),
    Category("konsekvenser", "Konsekvenser", "Konsekvenser"),
)

LOOKUPS: tuple[LookupDef, ...] = (
    *(LookupDef(c.lookup, "innehallstyp_varde", c.catalog, c.group, itself=c.key == "utvecklingsinriktning")
      for c in CATEGORIES),
    KOMPLETTERANDE_MVA, KOMPLETTERANDE_UI, PLANHANDELSE_LOOKUP, SAMBANDSNIVA_LOOKUP, UNDERLAGSTYP_LOOKUP,
    AVSNITTSTYP_LOOKUP,
)


# -- tabeller -----------------------------------------------------------------------------------------------------------
def _identitet() -> tuple[FieldDef, ...]:
    return (
        FieldDef("objektidentitet", TEXT, "Objektidentitet", required=True, default=UUID_EXPR, length=38, hidden=True),
        FieldDef("versiongiltigfran", DATETIME, "Versionen gäller från", required=True, default=NOW_EXPR, hidden=True),
    )


OVERSIKTSPLAN = LayerDef("oversiktsplan", "Översiktsplan", None, (
    *_identitet(),
    FieldDef("beslut", TEXT, "Beslut", length=38, hidden=True),
    FieldDef("kommunkod", TEXT, "Kommunkod", required=True, length=4),
    FieldDef("kommunnamn", TEXT, "Kommun", required=True),
    FieldDef("planens_titel", TEXT, "Planens titel"),
    FieldDef("planhandelse_varde", TEXT, "Planhändelse", required=True, lookup=PLANHANDELSE_LOOKUP.name),
    FieldDef("planhandelse_datum", DATE, "Datum för planhändelsen", required=True),
    FieldDef("datum_paborjat", DATE, "Datum påbörjad", required=True),
    FieldDef("digitalt_ursprung", BOOL, "Digitalt ursprung", required=True, default=TRUE_EXPR),
    FieldDef("digitaliseringsbeskrivning", TEXT, "Digitaliseringsbeskrivning", multiline=True),
    FieldDef("underlag_id", TEXT, "Underlag", length=38, hidden=True),
    FieldDef("dokument_id", TEXT, "Dokument", length=38, hidden=True),
))


def _innehall(category: Category) -> tuple[FieldDef, ...]:
    """Fälten i ett innehållslager (innehallOP i specifikationen), i samma ordning som i Boverkets mall."""
    fields = [
        *_identitet()[:1],
        FieldDef("vertikal_avgransning", TEXT, "Vertikal avgränsning", choices=AVGRANSNING),
        FieldDef("beror_annat_innehall_id", TEXT, "Berör annat innehåll", hidden=True),
        FieldDef("kompletterandeInnehallstyp", TEXT, "Kompletterande innehållstyp", lookup=category.kompletterande),
        FieldDef("namn", TEXT, "Namn"),
        FieldDef("innehallstyp_varde", TEXT, "Innehållstyp", required=True, lookup=category.lookup),
        FieldDef("precisering", TEXT, "Precisering", multiline=True),
        _identitet()[1],
        FieldDef("beslut", TEXT, "Beslut", length=38, hidden=True),
        FieldDef("planhandelse_varde", TEXT, "Planhändelse", required=True, lookup=PLANHANDELSE_LOOKUP.name),
        FieldDef("under_ersattning", BOOL, "Under ersättning", required=True, default=FALSE_EXPR),
        FieldDef("datum_paborjat", DATE, "Datum påbörjad"),
        FieldDef("illustrativa_granser", BOOL, "Illustrativa gränser", required=True, default=TRUE_EXPR,
                 hidden=True),  # alltid sant enligt specifikationen
        FieldDef("presentationsskala", INT, "Presentationsskala"),
        FieldDef("planhandelse_datum", DATE, "Datum för planhändelsen", required=True),
        FieldDef("dokument_id", TEXT, "Dokument", length=38, hidden=True),
    ]
    # Boverkets mall har inte kompletterande innehållstyp i Plangeometri och Område, och inte precisering i Område
    if category.key == "plangeometri":
        fields = [f for f in fields if f.name != "kompletterandeInnehallstyp"]
    elif category.key == "omrade":
        fields = [f for f in fields if f.name not in ("kompletterandeInnehallstyp", "precisering")]
    return (*fields, *category.extra)


# Pluginets eget fält (inte i Boverkets mall, följer inte med i exporten): pilspetsarna på utvecklingsinriktningens
# linjer. Tomt = temats standard (se styles.ARROWS).
ARROW_FIELD = "rita_pilar"
ARROW_END, ARROW_START, ARROW_BOTH, ARROW_NONE = "slut", "start", "båda", "ingen"
_ARROWS = FieldDef(ARROW_FIELD, TEXT, "Pilspetsar", choices=(ARROW_END, ARROW_START, ARROW_BOTH, ARROW_NONE))


def content_layers() -> tuple[LayerDef, ...]:
    layers = []
    for category in CATEGORIES:
        for suffix, geometry, word in GEOMETRIES:
            if category.polygon_only and suffix != "polygon":
                continue
            name = f"innehall_op_{category.key}" + ("" if category.polygon_only else f"_{suffix}")
            alias = category.alias if category.polygon_only else f"{category.alias} ({word})"
            fields = _innehall(category)
            if category.key == "utvecklingsinriktning" and suffix == "line":
                fields = (*fields, _ARROWS)
            layers.append(LayerDef(name, alias, geometry, fields, category))
    return tuple(layers)


CONTENT_LAYERS = content_layers()

DOCUMENT_TABLES: tuple[LayerDef, ...] = (
    LayerDef("oversiktsplan_underlag", "Underlag", None, (
        FieldDef("underlag_id", TEXT, "Underlag", length=38),
        FieldDef("underlagstyp_varde", TEXT, "Underlagstyp", lookup=UNDERLAGSTYP_LOOKUP.name),
    )),
    LayerDef("oversiktsplan_underlag_underlag", "Underlagets dokument", None, (
        FieldDef("underlag_id", TEXT, "Underlag", length=38),
        FieldDef("dokumentreferens_id", TEXT, "Dokumentreferens", length=38),
    )),
    LayerDef("dokumentreferens_op", "Dokumentreferenser", None, (
        FieldDef("namn", TEXT, "Namn"),
        FieldDef("kortnamn", TEXT, "Kortnamn"),
        FieldDef("datumangivelse", TEXT, "Datumangivelse"),
        FieldDef("specifik_referens", TEXT, "Specifik referens"),
        FieldDef("dokumentreferens_id", TEXT, "Dokumentreferens", length=38),
        FieldDef("referens_id", TEXT, "Referens", length=38),
        FieldDef("lank", TEXT, "Länk"),
        FieldDef("identitet", TEXT, "Identitet"),
        FieldDef("namespace", TEXT, "Namnrymd"),
    )),
    LayerDef("dokumentavsnitt", "Dokumentavsnitt", None, (
        FieldDef("avsnittstyp_varde", TEXT, "Avsnittstyp", lookup=AVSNITTSTYP_LOOKUP.name),
        FieldDef("avsnittsbokmarke_id", TEXT, "Bokmärke"),
        FieldDef("dokumentreferens_id", TEXT, "Dokumentreferens", length=38),
        FieldDef("dokument_id", TEXT, "Dokument", length=38),
        FieldDef("objektidentitet", TEXT, "Objektidentitet", length=38),
    )),
    # Tabellnamnet har å i Boverkets mall; det behålls.
    LayerDef("avsnittsbokmärke", "Avsnittsbokmärken", None, (
        FieldDef("avsnittsbokmarke_id", TEXT, "Bokmärke"),
        FieldDef("avsnittsbokmarke_text", TEXT, "Bokmärkets namn"),
    )),
    # Stavningen beror_annat_innehal_uuid och dokumentreferns_id kommer från Boverkets mall och behålls.
    LayerDef("innehall_op_beror_annat_innehall", "Berör annat innehåll", None, (
        FieldDef("beror_annat_innehall_id", TEXT, "Berör annat innehåll"),
        FieldDef("beror_annat_innehal_uuid", TEXT, "Berört innehåll", length=38),
    )),
    LayerDef("innehall_op_extern_referens_ri", "Externa referenser till riksintressen", None, (
        FieldDef("extern_referens_ri_id", TEXT, "Extern referens"),
        FieldDef("dokumentreferns_id", TEXT, "Dokumentreferens"),
    )),
)

# Geometri som ritats men ännu inte fått innehåll: man ritar först och tilldelar sedan innehållet (som i Rita
# Detaljplan). Ett objekt flyttas till rätt innehållslager när det tilldelas.
DRAFT_LAYERS: dict[str, LayerDef] = {
    suffix: LayerDef(f"rita_otilldelad_{word}", f"Otilldelad {word}", geometry, (
        FieldDef("skapad", DATETIME, "Skapad", default=NOW_EXPR, hidden=True),
    ))
    for suffix, geometry, word in GEOMETRIES
}

# Beslut om planen (beslutOP i Lantmäteriets specifikation). Boverkets mall har ingen tabell för beslut, bara
# kolumnen ``beslut`` i oversiktsplan och innehållet; tabellen är ett tillägg med specifikationens uppgifter.
# Föreskrifterna (BFS 2024:2, 2 kap. 2 §) kräver antagandebeslutets diarienummer och datum när det fick laga kraft.
BESLUT_INSTANS = "kommunfullmäktige"  # den enda beslutande instansen i specifikationens kodlista
BESLUT = LayerDef("beslut_op", "Beslut", None, (
    *_identitet(),
    FieldDef("rubrik", TEXT, "Rubrik"),
    FieldDef("diarienummer", TEXT, "Diarienummer", required=True),
    FieldDef("beslutande_organisation", TEXT, "Beslutande organisation", required=True),
    FieldDef("beslutande_instans", TEXT, "Beslutande instans", choices=(BESLUT_INSTANS,), default=f"'{BESLUT_INSTANS}'"),
    FieldDef("datum_fattat", DATE, "Beslutet fattat"),
    FieldDef("datum_overklagat", DATE, "Beslutet överklagat"),
    FieldDef("datum_laga_kraft", DATE, "Beslutet fick laga kraft"),
    FieldDef("arkividentitet", TEXT, "Arkividentitet"),
))

LAYERS: tuple[LayerDef, ...] = (OVERSIKTSPLAN, *CONTENT_LAYERS, *DOCUMENT_TABLES, BESLUT, *DRAFT_LAYERS.values())
ADDED_TABLES: tuple[LayerDef, ...] = (*DRAFT_LAYERS.values(), BESLUT)  # läggs till i planer från äldre versioner
# kolumner som lagts till i befintliga tabeller (schema 4), läggs till i planer från äldre versioner
ADDED_COLUMNS: dict[str, tuple[str, ...]] = {"innehall_op_plangeometri": ("precisering",),
                                             "innehall_op_utvecklingsinriktning_line": (ARROW_FIELD,)}


def layer(name: str) -> LayerDef:
    return next(layer_def for layer_def in LAYERS if layer_def.name == name)


def geometry_suffix(layer_def: LayerDef) -> str:
    """``polygon``, ``line`` eller ``point`` för ett geometrilager."""
    return next(suffix for suffix, geometry, _ in GEOMETRIES if geometry == layer_def.geometry)


def content_layer(category: Category, suffix: str) -> Optional[LayerDef]:
    """Innehållslagret för en grupp och geometri, eller None om gruppen inte har den geometrin."""
    return next((d for d in CONTENT_LAYERS if d.category == category and geometry_suffix(d) == suffix), None)


NO_GEOMETRY = "none"  # innehåll utan geometri, bara kopplat till planhandlingens text


def categories_for(suffix: str) -> tuple[Category, ...]:
    """Grupperna som kan ha den här geometrin (Plangeometri och Område är bara ytor). Utan geometri: alla utom
    Plangeometri, Område och Mark- och vattenanvändning, som enligt föreskrifterna (BFS 2024:2, 3 kap. 3 §) ska vara
    lägesbestämd."""
    if suffix == NO_GEOMETRY:
        return tuple(c for c in CATEGORIES if not c.polygon_only and c.key != "markochvattenanvandning")
    return tuple(c for c in CATEGORIES if content_layer(c, suffix) is not None)


def storage_layer(category: Category, suffix: str) -> Optional[LayerDef]:
    """Lagret ett innehåll sparas i. Innehåll utan geometri sparas i gruppens ytlager med tom geometri, så att det
    ligger i samma tabell som gruppens övriga innehåll (geometrin är frivillig i specifikationen)."""
    return content_layer(category, "polygon" if suffix == NO_GEOMETRY else suffix)


# -- standardvärden för nytt innehåll --------------------------------------------------------------------------------
# Värden som gäller allt innehåll i planen ställs in under Planens uppgifter och sparas i metadatatabellen. De sätts
# på varje objekt när det tilldelas innehåll, och kan sedan ändras per objekt i attributformuläret.
DEFAULT_KEYS = {
    "vertikal_avgransning": "standard_vertikal_avgransning",  # "", "nedåt" eller "uppåt"
    "under_ersattning": "standard_under_ersattning",  # "0" eller "1"
    "datum_paborjat": "standard_datum_paborjat",  # ÅÅÅÅ-MM-DD eller ""
    "presentationsskala": "standard_presentationsskala",  # heltal eller ""
}
DEFAULT_VALUES = {"standard_vertikal_avgransning": "", "standard_under_ersattning": "0",
                  "standard_datum_paborjat": "", "standard_presentationsskala": ""}
