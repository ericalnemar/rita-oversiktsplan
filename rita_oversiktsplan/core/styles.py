"""Symboler per grupp (innehållstyp i Boverkets modell) och färg per värde i ÖP-katalogen. Ren Python: bara data,
ritas av :mod:`symbology`.

Boverkets föreskrifter, ÖP-modellen och Lantmäteriets specifikation anger inte hur en översiktsplan ska visas; det är
upp till kommunen. Det här är pluginets eget förslag, gjort för att fungera **i webbkartor** (GeoServer, QGIS
Server, vektortiler, ArcGIS Online) lika väl som i QGIS. Därför används bara enkla symboler som alla klienter kan
rita och som finns i SLD: enfärgade ytor, genomskinlighet, linjer med strecktyp (``stroke-dasharray``) och
punktformerna cirkel, kvadrat, triangel, stjärna och kors (romb, nedåtvänd triangel och x är vridna former). Inga
mönsterfyllningar, SVG-bilder eller typsnittssymboler.

**Gruppen avgör symbolen, värdet avgör färgen.** Varje grupp, till exempel *Klimatrelaterade risker*, har en egen
kantlinje (strecktyp och tjocklek) som också används för linjer, och en egen punktform. Då ser man vilken grupp ett
objekt hör till. Värdena inom gruppen har samma symbol och skiljs åt med färgen (översvämning blå, ras röd …).

  * **Mark- och vattenanvändning** är grunden: heltäckande färg och tunn streckad kant (gränserna är illustrativa).
    Färgerna utgår från Boverkets färger för detaljplanens användningsområden (samma färgkoder som i Rita
    Detaljplan): Bostadsbebyggelse som B (gul), Verksamheter som Z (beige), Vatten som W (blå) osv. Där detaljplanens
    färger ligger för nära varandra, eller detaljplanen saknar motsvarighet, har värdet fått en egen färg i samma
    färgfamilj. Värdena skiljs åt med färgen (ΔE00 minst 8,5, se :mod:`colors`).
  * **Övrigt innehåll** ligger ovanpå som överlägg: gruppens kant i värdets färg och en svag, genomskinlig fyllning.
  * **Underlag** som kommunen redovisar men inte själv ställer sig bakom (riksintressen enligt miljöbalken) ritas
    utan fyllning och med ihålig punkt.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

RGB = tuple[int, int, int]

# Boverkets färgnamn för detaljplanens användningsområden (samma värden som FARGER i Rita Detaljplan, hämtade ur
# stilbiblioteket "Detaljplaner (Bfs 2020:6)").
FARGER: dict[str, RGB] = {
    "Gul": (255, 255, 206),
    "Brun": (218, 191, 140),
    "Beige": (255, 203, 131),
    "Orange": (255, 128, 64),
    "Röd": (250, 75, 60),
    "Rosa": (255, 188, 225),
    "Lila": (209, 182, 225),
    "Blå": (165, 218, 251),
    "Blågrå": (182, 204, 225),
    "Grön": (178, 236, 64),
    "Ljusgrön": (222, 255, 206),
    "Grå": (217, 217, 217),
    "Ljusgrå": (233, 233, 233),
}

OVERLAY_ALPHA = 46  # fyllningens täckning för överlägg, av 255 (ca 18 %)
UNASSIGNED_COLOR: RGB = (230, 81, 0)
MIN_DELTA_E_LAND_USE = 8.5

# Punktformer i SLD-standarden (WellKnownName); övriga former görs genom vridning.
SLD_SHAPES = ("circle", "square", "triangle", "star", "cross")


@dataclass(frozen=True)
class Group:
    """Gruppens symbol: kantens och linjens strecktyp och tjocklek, punktens form och om gruppen är underlag."""
    dash: str  # strecklängder i mm, "streck;mellanrum;…", tom för heldragen
    width: float  # kantens och linjens tjocklek i mm
    shape: str  # punktform i QGIS (en av SLD_SHAPES)
    angle: int = 0  # vridning av punktformen i grader
    hollow: bool = False  # ingen fyllning och ihålig punkt (underlag, planens avgränsning)
    ring: bool = False  # punkten får en kraftig vit kant, som en ring runt färgen
    label: str = ""  # gruppens symbol i ord, för dokumentationen


@dataclass(frozen=True)
class Style:
    """Ett värdes färg. ``filled`` för markanvändningen, som är heltäckande."""
    color: RGB
    filled: bool = False
    detaljplan: str = ""  # användningen i en detaljplan vars färg är lånad oförändrad


GROUPS: dict[str, Group] = {
    "markochvattenanvandning": Group("2;1", 0.26, "circle", label="tunn streckad kant, fylld cirkel"),
    "plangeometri": Group("8;2;1;2", 1.0, "square", hollow=True, label="kraftig streck-prick, ingen fyllning"),
    "omrade": Group("0.5;1", 0.4, "square", hollow=True, label="tät prickad, ingen fyllning"),
    "utvecklingsinriktning": Group("4;1.5", 1.0, "star", label="kraftig streckad, stjärna"),
    "riksintressenop": Group("", 0.8, "triangle", label="heldragen, triangel"),
    "riksintressen": Group("2;1.5", 0.5, "triangle", hollow=True,
                           label="tunn streckad, ingen fyllning, ihålig triangel"),
    "miljokvalitetsnormer": Group("1;1", 0.6, "square", 45, label="tät prickad, romb"),
    "ovrigaforhallandeavvasentligbetydelse": Group("6;1.5;1;1.5;1;1.5", 0.6, "square", 45, hollow=True,
                                                   label="streck-prick-prick, ihålig romb"),
    "bostadsforsorjning": Group("3;1;1;1", 0.7, "square", label="streck-prick, kvadrat"),
    "malplanprogram": Group("6;3", 0.5, "square", hollow=True, label="glesa långa streck, ihålig kvadrat"),
    "lis": Group("0.6;1.6", 0.9, "cross", 45, label="kraftig gles prick, x"),
    "sarskiltvardefullabyggnadsverkallmannaplatserochbebyggelseomraden": Group(
        "4;1;4;1;1;1", 0.7, "circle", hollow=True, label="dubbelstreck-prick, ihålig cirkel"),
    "klimatrelateradrisk": Group("2;1", 0.9, "triangle", 180, label="kraftig kort streckad, nedåtvänd triangel"),
    "konsekvenser": Group("1.5;1.5", 0.6, "triangle", 180, hollow=True,
                          label="jämn kort streckad, ihålig nedåtvänd triangel"),
    "avvikelsefranregionplan": Group("8;1.5", 0.7, "star", hollow=True, label="långa streck, ihålig stjärna"),
    "mellankommunalaochregionalaintressen": Group("1;1;1;1;5;1.5", 0.7, "cross",
                                                  label="prick-prick-streck, kors"),
    "lansstyrelsensinvandning": Group("3;1.5;0.6;1.5;0.6;1.5", 0.9, "circle", ring=True,
                                      label="kraftig streck-prick-prick, cirkel med vit ring"),
}


def _mva(color: RGB | str, detaljplan: str = "") -> Style:
    return Style(FARGER[color] if isinstance(color, str) else color, filled=True, detaljplan=detaljplan)


MARK_OCH_VATTEN: dict[str, Style] = {
    "Bostadsbebyggelse": _mva("Gul", "B"),
    "Funktionsblandad bebyggelse": _mva((200, 160, 112)),  # C är brun men för nära Z: här mörkare brun
    "Service": _mva("Röd", "S, D"),
    "Verksamheter": _mva("Beige", "Z"),
    "Teknisk infrastruktur": _mva((158, 172, 194)),  # E är blågrå men för nära W: här gråare
    "Energiproduktion": _mva((124, 112, 178)),  # blåviolett
    "Vägtrafik": _mva("Ljusgrå", "GATA, VÄG"),
    "Järnväg": _mva((150, 150, 150)),  # T är grå men för nära GATA: här mörkare grå
    "Luftfart": _mva((204, 178, 240)),  # ljuslila
    "Sjöfart": _mva((52, 84, 140)),  # marinblå
    "Vatten": _mva("Blå", "W"),
    "Fiske": _mva((40, 146, 214)),  # klarblå
    "Vattenbruk": _mva((110, 206, 196)),  # blågrön
    "Grönområde": _mva("Ljusgrön", "PARK"),
    "Natur- och kulturlandskap": _mva((160, 210, 140)),  # NATUR är ljusgrön som PARK: här mellangrön
    "Landsbygd": _mva((206, 196, 176)),  # gråbeige
    "Friluftsliv och rekreation": _mva("Grön", "N"),
    "Jordbruk": _mva((246, 232, 96)),  # sädesgul (L är grön som N)
    "Skogsbruk": _mva((64, 136, 72)),  # mörkgrön
    "Renskötsel": _mva((150, 160, 112)),  # grågrön
    "Annan mark- och vattenanvändning": _mva("Rosa"),
}

# Riksintressen: färgfamilj efter tema (grönt natur, brunt kultur, orange friluftsliv, blått kust och vatten,
# gråblått fjäll, oliv näringar, lila/grått/rött anläggningar).
RIKSINTRESSEN: dict[str, RGB] = {
    "Naturvård": (46, 125, 50),
    "Natura 2000, vilda djur och växter": (20, 90, 40),
    "Natura 2000, vilda fåglar": (110, 170, 40),
    "Nationalstadspark": (0, 150, 110),
    "Kulturmiljövård": (141, 85, 36),
    "Friluftsliv": (230, 126, 34),
    "Turism och rörligt friluftsliv": (200, 80, 0),
    "Obruten kust": (21, 101, 192),
    "Högexploaterad kust": (90, 170, 235),
    "Skyddat vattendrag": (0, 131, 143),
    "Obrutet fjäll": (100, 110, 150),
    "Rennäring": (150, 120, 20),
    "Yrkesfiske": (0, 110, 100),
    "Fyndighet av ämnen och material": (175, 160, 40),
    "Anläggning för avfallshantering": (110, 70, 50),
    "Anläggning för energidistribution": (123, 31, 162),
    "Anläggning för energiproduktion": (170, 80, 190),
    "Anläggning för industriell produktion": (90, 90, 90),
    "Anläggning för kommunikation, elektronisk": (63, 81, 181),
    "Anläggning för kommunikation, trafikslagen": (140, 140, 140),
    "Anläggning för slutlig förvaring av använt kärnbränsle och kärnavfall": (190, 30, 30),
    "Anläggning för totalförsvaret": (25, 25, 25),
    "Anläggning för vattenförsörjning": (2, 136, 209),
}


def _colors(values: dict[str, RGB]) -> dict[str, Style]:
    return {name: Style(color) for name, color in values.items()}


STYLES: dict[str, dict[str, Style]] = {
    "plangeometri": _colors({"Plangeometri": (22, 24, 26)}),
    "omrade": _colors({"Område": (107, 111, 117)}),
    # Utvecklingsinriktningen skiljs åt med den kompletterande utvecklingsinriktningen (se FIELD nedan).
    "utvecklingsinriktning": _colors({
        "Bebyggelsestruktur": (226, 85, 58),
        "Grön- och blåstruktur": (46, 139, 87),
        "Kommunikation": (70, 90, 110),
        "Annan utvecklingsinriktning": (142, 68, 173),
    }),
    "markochvattenanvandning": MARK_OCH_VATTEN,
    "riksintressenop": _colors(RIKSINTRESSEN),
    "riksintressen": _colors(RIKSINTRESSEN),
    "miljokvalitetsnormer": _colors({
        "Fisk- och musselvatten": (0, 137, 123),
        "Havsmiljö": (13, 71, 161),
        "Omgivningsbuller": (156, 39, 176),
        "Utomhusluft": (120, 120, 120),
        "Vattenkvalitet": (30, 136, 229),
    }),
    "ovrigaforhallandeavvasentligbetydelse": _colors({"Övriga förhållanden av väsentlig betydelse": (143, 107, 179)}),
    "bostadsforsorjning": _colors({"Bostadsförsörjning": (196, 150, 0)}),
    "malplanprogram": _colors({
        "Internationella mål, planer och program": (40, 53, 147),
        "Nationella mål, planer och program": (0, 110, 170),
        "Regionala mål, planer och program": (110, 70, 170),
        "Kommunala mål, planer och program": (70, 140, 100),
    }),
    "lis": _colors({"LIS": (47, 156, 149)}),
    "sarskiltvardefullabyggnadsverkallmannaplatserochbebyggelseomraden": _colors(
        {"Särskilt värdefull kulturmiljö": (160, 82, 45)}),
    "klimatrelateradrisk": _colors({
        "Risk för översvämning": (21, 101, 192),
        "Risk för ras": (198, 40, 40),
        "Risk för skred": (230, 120, 0),
        "Risk för erosion": (121, 85, 72),
    }),
    "avvikelsefranregionplan": _colors({"Avvikelse från regionplan": (127, 140, 141)}),
    "mellankommunalaochregionalaintressen": _colors({"Mellankommunala och regionala intressen": (44, 110, 73)}),
    "lansstyrelsensinvandning": _colors({
        "Invändning hälsa och säkerhet": (190, 30, 30),
        "Invändning LIS": (0, 121, 107),
        "Invändning mellankommunala frågor": (80, 140, 40),
        "Invändning miljökvalitetsnorm": (106, 27, 154),
        "Invändning riksintresse": (200, 150, 0),
    }),
    "konsekvenser": _colors({
        "Miljökonsekvenser": (85, 139, 47),
        "Planens väsentliga konsekvenser": (70, 90, 120),
    }),
}

# Fältet som klassar objekten. Utvecklingsinriktning har bara ett värde för innehållstyp; det som skiljer
# utvecklingsinriktningarna åt är den kompletterande utvecklingsinriktningen (nivån under i ÖP-katalogen).
FIELD: dict[str, str] = {"utvecklingsinriktning": "kompletterandeInnehallstyp"}
DEFAULT_FIELD = "innehallstyp_varde"


def field_for(category_key: str) -> str:
    return FIELD.get(category_key, DEFAULT_FIELD)


def style_for(category_key: str, value: str) -> Optional[Style]:
    return STYLES.get(category_key, {}).get(value)


def group_for(category_key: str) -> Group:
    return GROUPS[category_key]


def darker(color: RGB, factor: float = 0.55) -> RGB:
    """En mörkare ton av färgen, till kanter och linjer på en ljus yta."""
    return tuple(round(c * factor) for c in color)  # type: ignore[return-value]
