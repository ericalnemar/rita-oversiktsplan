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

  * **Mark- och vattenanvändning** är grunden: färg som täcker till 80 procent (bakgrundskartan anas), utan kant.
    Färgerna utgår från Boverkets färger för detaljplanens användningsområden (samma färgkoder som i Rita
    Detaljplan): Bostadsbebyggelse som B (gul), Verksamheter som Z (beige), Vatten som W (blå) osv. Där detaljplanens
    färger ligger för nära varandra, eller detaljplanen saknar motsvarighet, har värdet fått en egen färg i samma
    färgfamilj. Värdena skiljs åt med färgen (ΔE00 minst 8,5, se :mod:`colors`).
  * **Utvecklingsinriktningen** är ett schema för hela kommunen, som i flera kommuners digitala översiktsplaner
    (Hudiksvall, Bromölla, Danderyd): en färg per tema (den kompletterande utvecklingsinriktningen), breda
    halvgenomskinliga band med pilspets, noder som ringar, och storleken efter sambandsnivån (se
    ``DEVELOPMENT_LEVELS``). Det är byggt för att läsas i skala 1:100 000–1:400 000.
  * **Övrigt innehåll** ligger ovanpå som överlägg: gruppens kant i värdets färg, en bred bård på insidan av kanten,
    en mycket svag fyllning och namnet längs kanten (se ``NO_BAND`` för undantagen).
  * **Underlag** som kommunen redovisar men inte själv ställer sig bakom (riksintressen enligt miljöbalken) ritas
    som överläggen men med tunn streckad kant och ihålig punkt; namnet säger vilket riksintresse det är.
  * **Kommunens ställningstagande till riksintressena** har, som alla överlägg, en mycket svag fyllning och en bred bård på insidan av kanten
    och namnet längs kanten, som i tryckta översiktsplaner. Där riksintressen överlappar (de är ofta stora och många)
    blir kartan då inte grumlig av starka fyllningar ovanpå varandra, och markanvändningen syns inuti.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
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
BAND_ALPHA = 110  # bården innanför kanten (ca 43 %), se Group.band
BAND_FILL_ALPHA = 20  # mycket svag fyllning innanför bården (ca 8 %): man ser var riksintresset gäller, och tre
# överlappande ger ändå bara ca 22 % täckning
# Bården i skalsteg: (mest inzoomad skala, mest utzoomad skala, bårdens bredd i mm, kantens bredd som andel av
# gruppens), 0 = ingen gräns. Utzoomad blir bården smalare, så att den inte kladdar ihop längs flikiga kuster och sjöar.
# Steg i stället för en referensskala, eftersom stegen följer med till SLD (Min-/MaxScaleDenominator) och GeoServer.
BAND_STEPS: tuple[tuple[int, int, float, float], ...] = (
    (0, 50_000, 2.4, 1.0),  # inzoomad: tätorter och detaljer
    (50_000, 150_000, 1.2, 0.8),  # kommunkartan
    (150_000, 0, 0.6, 0.6),  # länet och regionen
)
BAND_WIDTH = BAND_STEPS[0][2]
# Grupper vars ytor inte får bård: markanvändningen (heltäckande, egen stil), utvecklingsinriktningen (eget schema),
# och planens och områdens avgränsning (bara en gräns).
NO_BAND = ("markochvattenanvandning", "utvecklingsinriktning", "plangeometri", "omrade")
LAND_USE_ALPHA = 204  # markanvändningens täckning (80 %), så att bakgrundskartan anas
DETAIL_SCALE = 25_000  # punkter och linjer utom utvecklingsinriktningen syns först från 1:25 000
LABEL_SCALE = 100_000  # namnen syns från 1:100 000 (utvecklingsinriktningens namn alltid)
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
    band: float = 0.0  # ytor: bred halvgenomskinlig bård innanför kanten (mm) och mycket svag fyllning
    names: str = "center"  # namnen på ytor: "center" (mitt i ytan), "perimeter" (längs kanten) eller "none"
    value_in_label: bool = False  # etiketten säger också värdet, t.ex. "Vänern – Turism och rörligt friluftsliv"


@dataclass(frozen=True)
class Style:
    """Ett värdes färg. ``filled`` för markanvändningen, som är heltäckande."""
    color: RGB
    filled: bool = False
    detaljplan: str = ""  # användningen i en detaljplan vars färg är lånad oförändrad
    line: Optional[RGB] = None  # linjens färg, om den inte ska vara en mörkare ton av ytans (se LINE_COLORS)


GROUPS: dict[str, Group] = {
    "markochvattenanvandning": Group("", 0.2, "circle", label="ingen kant, fylld cirkel"),
    "plangeometri": Group("8;2;1;2", 1.0, "square", hollow=True, names="none",
                          label="kraftig streck-prick, ingen fyllning, inget namn"),
    "omrade": Group("0.5;1", 0.4, "square", hollow=True, label="tät prickad, ingen fyllning"),
    "utvecklingsinriktning": Group("", 1.0, "circle", hollow=True, ring=True,
                                   label="mjuk kant, breda band med pilspets, nod som ring kring en prick"),
    "riksintressenop": Group("", 0.5, "triangle", value_in_label=True, label="heldragen, triangel"),
    "riksintressen": Group("2;1.5", 0.5, "triangle", hollow=True, value_in_label=True,
                           label="tunn streckad, ihålig triangel"),
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
# Alla överlägg utom NO_BAND: ytan får en bred bård innanför kanten och en mycket svag fyllning, och namnet står längs
# kanten (gruppens strecktyp och punktform är kvar). Gjordes först för kommunens ställningstagande till riksintressena
# och användes sedan på alla överlägg (användarens önskan 2026-10-20).
GROUPS = {key: group if key in NO_BAND else replace(group, band=BAND_WIDTH, names="perimeter")
          for key, group in GROUPS.items()}


def _mva(color: RGB | str, detaljplan: str = "") -> Style:
    return Style(FARGER[color] if isinstance(color, str) else color, filled=True, detaljplan=detaljplan)


# Topografi 10: Lantmäteriets färger för markytorna (stilfilen Topografi10_vektor_220825.qlr, läst 2026-10-20).
# Mark- och vattenanvändning som motsvarar ett markslag får markslagets färg, så att befintlig användning ser ut som
# Lantmäteriets karta (användarens önskan); övriga värden behåller färgerna nedan.
TOPOGRAFI10: dict[str, tuple[RGB, str]] = {
    "Bostadsbebyggelse": ((242, 207, 155), "Låg bebyggelse"),
    "Funktionsblandad bebyggelse": ((217, 148, 97), "Sluten bebyggelse"),
    "Verksamheter": ((240, 240, 240), "Industri- och handelsbebyggelse"),
    "Jordbruk": ((255, 247, 166), "Åker"),
    "Skogsbruk": ((212, 238, 183), "Barr- och blandskog"),
    "Natur- och kulturlandskap": ((255, 255, 234), "Öppen mark"),
    "Vatten": ((191, 230, 255), "Sjö, hav och vattendrag"),
    "Grönområde": ((196, 236, 214), "idrottsplanens gröna, något blågrönare för att skiljas från skogen"),
}


def _topo(value: str) -> Style:
    color, source = TOPOGRAFI10[value]
    return Style(color, filled=True, detaljplan=f"Topografi 10: {source}")


MARK_OCH_VATTEN: dict[str, Style] = {
    "Bostadsbebyggelse": _topo("Bostadsbebyggelse"),
    "Funktionsblandad bebyggelse": _topo("Funktionsblandad bebyggelse"),
    "Service": _mva("Röd", "S, D"),
    "Verksamheter": _topo("Verksamheter"),
    "Teknisk infrastruktur": _mva((158, 172, 194)),  # E är blågrå men för nära W: här gråare
    "Energiproduktion": _mva((124, 112, 178)),  # blåviolett
    "Vägtrafik": _mva((195, 195, 195)),  # mellangrå: GATA:s ljusgrå var för nära Topografi 10:s industrigrå
    "Järnväg": _mva((150, 150, 150)),  # T är grå men för nära GATA: här mörkare grå
    "Luftfart": _mva((204, 178, 240)),  # ljuslila
    "Sjöfart": _mva((52, 84, 140)),  # marinblå
    "Vatten": _topo("Vatten"),
    "Fiske": _mva((40, 146, 214)),  # klarblå
    "Vattenbruk": _mva((110, 206, 196)),  # blågrön
    "Grönområde": _topo("Grönområde"),
    "Natur- och kulturlandskap": _topo("Natur- och kulturlandskap"),
    "Landsbygd": _mva((206, 196, 176)),  # gråbeige
    "Friluftsliv och rekreation": _mva("Grön", "N"),
    "Jordbruk": _topo("Jordbruk"),
    "Skogsbruk": _topo("Skogsbruk"),
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
        "Bebyggelsestruktur": (232, 118, 22),  # orange, som bebyggelsen i kommunernas scheman
        "Grön- och blåstruktur": (46, 139, 87),
        "Kommunikation": (84, 90, 102),  # mörkgrå
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


# Utvecklingsinriktningens storlek efter sambandsnivå (ÖP-katalogen): tre steg, eftersom skillnaden mellan
# internationell, nationell och regional nivå inte syns i en kommunkarta. Utan sambandsnivå räknas som lokal.
LEVEL_FIELD = "sambandsniva_varde"
DEVELOPMENT_ALPHA = 150  # banden och ytorna (ca 60 %), så att markanvändningen syns under
DEVELOPMENT_AREA_ALPHA = 90  # ytorna (ca 35 %)
DEVELOPMENT_NONE: Style = Style((120, 120, 120))  # utan kompletterande utvecklingsinriktning
# Schemat är gjort för kommunkartan. Inzoomat (från 1:50 000) blir band, pilar, ringar och kanter mindre, annars tar
# en pil på en kort linje över tätortskartan.
DEVELOPMENT_ZOOM_SCALE = 50_000
DEVELOPMENT_ZOOM_FACTOR = 0.45
ARROW_FACTOR = 1.8  # pilspetsens storlek i förhållande till bandets bredd
# Utvecklingsinriktningens ytor har en mjuk kant: fyra linjer i temats färg ovanpå varandra, från bred och svag till
# smal och tydligare (bredd i förhållande till nivåns kant, täckning av 255). Enkla linjer, så det fungerar i SLD.
SOFT_EDGE: tuple[tuple[float, int], ...] = ((4.0, 22), (2.6, 34), (1.5, 55), (0.6, 110))
MIN_BAND, MIN_ARROW, MIN_NODE = 1.2, 3.0, 4.0  # mm, så att den lokala nivån syns även inzoomad


@dataclass(frozen=True)
class Level:
    label: str
    values: tuple[str, ...]
    line_width: float  # bandets bredd i mm
    node_size: float  # ringens diameter i mm
    edge_width: float  # ytans kant i mm
    include_empty: bool = False  # objekt utan sambandsnivå


DEVELOPMENT_LEVELS: tuple[Level, ...] = (
    Level("Internationell, nationell eller regional", ("Internationell", "Nationell", "Regional"), 5.0, 12.0, 1.6),
    Level("Kommunal", ("Kommunal",), 3.4, 8.5, 1.1),
    Level("Lokal eller ingen sambandsnivå", ("Lokal",), 2.0, 6.0, 0.7, include_empty=True),
)

# Pilspetsar på utvecklingsinriktningens linjer, efter tema: en riktning (utbyggnad, stråk, förbindelse) får en pil där man
# slutade rita; samband i grön- och blåstrukturen går åt båda hållen.
END, BOTH = "end", "both"
ARROWS: dict[Optional[str], str] = {
    "Bebyggelsestruktur": END,
    "Grön- och blåstruktur": BOTH,
    "Kommunikation": END,  # stråk ritas från orten och utåt; en pil i orten skulle täcka noden
    "Annan utvecklingsinriktning": END,
    None: END,
}


def arrows_for(value: Optional[str]) -> str:
    return ARROWS.get(value, END)


def default_arrows(theme: Optional[str]) -> tuple[bool, bool]:
    """Temats standard: (pil där linjen slutar, pil där den börjar)."""
    return True, arrows_for(theme) == BOTH


def field_for(category_key: str) -> str:
    return FIELD.get(category_key, DEFAULT_FIELD)


def style_for(category_key: str, value: str) -> Optional[Style]:
    return STYLES.get(category_key, {}).get(value)


def group_for(category_key: str) -> Group:
    return GROUPS[category_key]


# Utbyggnadsordning (se utbyggnad): mark- och vattenanvändning i en etapp får gruppens färg i en ton från mörk (första
# etappen) till ljus (sista), och en kraftig streckad kant i en mörk ton. Utan etapp: som förut (befintligt/bevarat).
STAGE_SATURATION = 0.5  # första etappen: så här mycket av vägen mot full färgmättnad (samma färgton)
STAGE_VALUE = 0.92  # första etappen: något mörkare
STAGE_LIGHT = 0.6  # sista etappen: så här mycket av vägen mot vitt
STAGE_GREY = 0.08  # färgmättnad under detta räknas som grått
STAGE_GREY_VALUE = 0.72  # första etappen för grått: så här mycket av ljusheten
STAGE_DASH = "3;1.5"
STAGE_EDGE = 0.7


# Linjer för mark- och vattenanvändning ritas i en mörkare ton av ytans färg; några värden har en egen linjefärg.
LINE_COLORS: dict[str, RGB] = {
    "Vägtrafik": (178, 178, 178),  # ljusare grå (användarens önskan), som vägarna i en översiktskarta
}
for _value, _color in LINE_COLORS.items():
    MARK_OCH_VATTEN[_value] = replace(MARK_OCH_VATTEN[_value], line=_color)


def stage_color(color: RGB, index: int, count: int) -> RGB:
    """Färgen för etapp nummer ``index`` (0 = första) av ``count``: från mättad och mörkare till ljus, i samma
    färgton. (Att bara göra färgen mörkare gjorde gult till oliv, som såg ut som en annan användning.)"""
    import colorsys
    t = index / (count - 1) if count > 1 else 0.0
    h, s, v = colorsys.rgb_to_hsv(*(c / 255 for c in color))
    if s < STAGE_GREY:  # grått (t.ex. Topografi 10:s industrigrå) har ingen färgton att mätta: gör det mörkare
        dark = colorsys.hsv_to_rgb(h, s, v * STAGE_GREY_VALUE)
    else:
        dark = colorsys.hsv_to_rgb(h, s + (1 - s) * STAGE_SATURATION, v * STAGE_VALUE)
    light = tuple(c / 255 + (1 - c / 255) * STAGE_LIGHT for c in color)
    return tuple(round(255 * (d + (l - d) * t)) for d, l in zip(dark, light))  # type: ignore[return-value]


def darker(color: RGB, factor: float = 0.55) -> RGB:
    """En mörkare ton av färgen, till kanter och linjer på en ljus yta."""
    return tuple(round(c * factor) for c in color)  # type: ignore[return-value]
