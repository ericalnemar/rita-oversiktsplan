"""Översiktsplanens textdokument (planhandlingen, Word .docx): läsa avsnitten och märka dem med bokmärken. Ren Python.

Boverkets "Instruktion för Office Open XML" (ÖP-modellen): ett textavsnitt identifieras med ett vanligt Word-bokmärke,
och bokmärkets namn är det som sparas i planens data (``dokumentavsnitt`` och ``avsnittsbokmärke``). Namnet är
beständigt: ett avsnitt som redan har ett av pluginets bokmärken behåller det när dokumentet får bokmärken igen.

Varje rubrik (formatmall Rubrik 1, 2, 3 … eller en formatmall med dispositionsnivå) inleder ett avsnitt som räcker till
nästa rubrik. Bokmärkena läggs i en kopia av filen; originalet rörs inte.

Funktionerna för att läsa och ändra Words XML är hämtade från Tagga planbeskrivning i Rita Detaljplan
(``planbeskrivning/pbkarna/planbeskrivning_docx.py``). XML:en läses och ändras som text, så att Words namnrymder och
all formatering lämnas exakt som de var: bara bokmärken läggs till eller flyttas.
"""
from __future__ import annotations

import difflib
import html
import re
import uuid
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
BOOKMARK_PREFIX = "op_"  # pluginets bokmärken; andra bokmärken i dokumentet rörs inte
DEFAULT_TYPE = "Beskrivning"

# Ord i en rubrik som pekar på en avsnittstyp i ÖP-katalogen. Ordningen spelar roll: mer specifika först.
TYPE_WORDS: tuple[tuple[str, str], ...] = (
    ("kommentar", "Kommentar på länsstyrelsens invändning"),
    ("invändning", "Länsstyrelsens invändning"),
    ("granskningsyttrande", "Länsstyrelsens invändning"),
    ("syfte", "Översiktsplanens syfte"),
    ("sammanfattning", "Sammanfattning"),
    ("ställningstagande", "Ställningstagande"),
    ("riktlinje", "Ställningstagande"),
    ("konsekvens", "Konsekvens"),
    ("miljökonsekvens", "Konsekvens"),
    ("hållbarhetsbedömning", "Konsekvens"),
    ("framtagande", "Framtagandeprocess"),
    ("process", "Framtagandeprocess"),
    ("samråd", "Framtagandeprocess"),
    ("dialog", "Framtagandeprocess"),
    ("övrig information", "Övrig information"),  # inte "övriga förhållanden"
)


class DocxError(ValueError):
    """Filen går inte att läsa eller få bokmärken. Meddelandet är avsett för användaren."""


@dataclass
class Section:
    """Ett avsnitt: en rubrik och texten fram till nästa rubrik."""
    index: int
    level: int
    heading: str
    path: tuple[str, ...]  # rubrikerna ovanför och rubriken själv
    start: int  # där bokmärket börjar i document.xml (efter rubrikens styckeegenskaper)
    end: int  # där bokmärket slutar (före sista styckets slut)
    text: str = ""
    bookmark: Optional[str] = None  # pluginets befintliga bokmärke, om avsnittet redan har ett
    suggested_type: str = DEFAULT_TYPE
    reason: str = "default"  # varför typen föreslogs (se explain_type)
    reason_word: str = ""


@dataclass
class Document:
    source: Path
    xml: str  # document.xml utan pluginets gamla bokmärken
    sections: list[Section] = field(default_factory=list)


# -- läsa dokumentets XML som text (från Rita Detaljplan) ----------------------------------------------------------
_TAG = re.compile(r"<!--.*?-->|<\?.*?\?>|<(/?)([^\s/>]+)((?:\"[^\"]*\"|'[^']*'|[^>\"'])*?)(/?)>", re.S)


def _spans(xml: str, lo: int, hi: int) -> list[tuple[str, int, int]]:
    """De direkta barnen (namn, start, slut) till ett element vars innehåll ligger i ``xml[lo:hi]``."""
    found, depth, start, name = [], 0, 0, ""
    for m in _TAG.finditer(xml, lo, hi):
        tag = m.group(2)
        if tag is None:
            continue
        if m.group(1):
            depth -= 1
            if depth == 0:
                found.append((name, start, m.end()))
        elif m.group(4):
            if depth == 0:
                found.append((tag, m.start(), m.end()))
        else:
            if depth == 0:
                name, start = tag, m.start()
            depth += 1
    return found


def _inner(xml: str, start: int, end: int) -> tuple[int, int]:
    first = _TAG.match(xml, start)
    if first.group(4):
        return end, end
    return first.end(), xml.rindex("</", start, end)


def _self_closing(xml: str, start: int) -> bool:
    return bool(_TAG.match(xml, start).group(4))


_FALLBACK = re.compile(r"<mc:Fallback>.*?</mc:Fallback>", re.S)
_TEXT_TOKEN = re.compile(r"<w:t(?:\s[^>]*)?>([^<]*)</w:t>|<w:tab\s*/>|<w:br\b[^>]*/>|<w:cr\s*/>|</w:txbxContent>|</w:p>")


def _text(xml: str, start: int, end: int) -> str:
    """Texten i ett stycke eller en tabell (Words reservversion av textrutor, ``mc:Fallback``, hoppas över)."""
    parts = []
    for token in _TEXT_TOKEN.finditer(_FALLBACK.sub("", xml[start:end])):
        parts.append(html.unescape(token.group(1)) if token.group(1) is not None else " ")
    return "".join(parts)


def _style(xml: str, start: int, end: int) -> str:
    m = re.search(r'<w:pStyle\s+w:val="([^"]*)"', xml[start:end])
    return m.group(1) if m else ""


def _paragraph_start(xml: str, start: int) -> int:
    """Där ett bokmärkes start läggs i ett stycke: efter styckets egenskaper (``w:pPr``)."""
    after_open = _TAG.match(xml, start).end()
    if xml.startswith("<w:pPr>", after_open) or xml.startswith("<w:pPr ", after_open):
        return xml.index("</w:pPr>", after_open) + len("</w:pPr>")
    return after_open


def _paragraph_end(xml: str, start: int, end: int) -> int:
    return xml.rindex("</w:p>", start, end)


def _edge_paragraph(xml: str, name: str, start: int, end: int, last: bool) -> Optional[tuple[int, int]]:
    """Första (eller sista) stycket i ett stycke eller en tabell, utan att gå ner i textrutor och liknande."""
    if name == "w:p":
        return None if _self_closing(xml, start) else (start, end)
    lo, hi = _inner(xml, start, end)
    if name == "w:tbl":
        rows = [s for s in _spans(xml, lo, hi) if s[0] == "w:tr"]
        parts = rows[::-1] if last else rows
    elif name in ("w:tr", "w:tc"):
        parts = [s for s in _spans(xml, lo, hi) if s[0] in ("w:tc", "w:p", "w:tbl")]
        parts = parts[::-1] if last else parts
    else:
        return None
    for part in parts:
        found = _edge_paragraph(xml, *part, last)
        if found:
            return found
    return None


def heading_levels(styles_xml: str) -> dict[str, int]:
    """Styckeformatets id → rubriknivå (1 = Rubrik 1), ur formatmallarna (dispositionsnivå eller namnet Rubrik N)."""
    root = ET.fromstring(styles_xml)
    styles = {}
    for node in root.findall(W + "style"):
        if node.get(W + "type") != "paragraph":
            continue
        name = node.find(W + "name")
        outline = node.find(f"{W}pPr/{W}outlineLvl")
        based = node.find(W + "basedOn")
        styles[node.get(W + "styleId")] = (name.get(W + "val") if name is not None else "",
                                            outline.get(W + "val") if outline is not None else None,
                                            based.get(W + "val") if based is not None else None)
    levels = {}
    for style_id in styles:
        seen, current = set(), style_id
        while current in styles and current not in seen:
            seen.add(current)
            name, outline, based = styles[current]
            if outline is not None and outline.isdigit():
                if int(outline) < 9:
                    levels[style_id] = int(outline) + 1
                break  # nivå 9 = brödtext
            m = re.match(r"^(?:heading|rubrik)\s*(\d)$", name.strip(), re.I)
            if m:
                levels[style_id] = int(m.group(1))
                break
            current = based
    return levels


def _read_zip(path: Path) -> dict[str, bytes]:
    try:
        with zipfile.ZipFile(path) as archive:
            return {name: archive.read(name) for name in archive.namelist()}
    except (zipfile.BadZipFile, OSError) as exc:
        raise DocxError(f"Kunde inte öppna filen som ett Word-dokument (.docx): {exc}") from exc


def _write_zip(source: Path, destination: Path, parts: dict[str, bytes]) -> None:
    """Skriver paketet i samma ordning som originalet (``[Content_Types].xml`` först), via en tillfällig fil."""
    with zipfile.ZipFile(source) as original:
        order = [i.filename for i in original.infolist()]
    order += [n for n in parts if n not in order]
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as out:
        for name in order:
            if name in parts:
                out.writestr(name, parts[name])
    temporary.replace(destination)


# -- avsnittstyp --------------------------------------------------------------------------------------------------
def _key(text: str) -> str:
    text = re.sub(r"^\s*\d+(?:\.\d+)*\.?\s+", "", text or "")  # ev. skriven numrering
    return re.sub(r"[^\w]+", " ", text.casefold()).strip()


LIKE, WORD, INHERITED, DEFAULT = "like", "word", "inherited", "default"  # skälen till ett förslag


def explain_type(heading: str, types: list[str], inherited: Optional[str] = None) -> tuple[str, str, str]:
    """(avsnittstyp, skäl, ordet) för en rubrik. Skälen: LIKE (rubriken liknar typens namn), WORD (ett ord i rubriken
    pekar på typen), INHERITED (samma som rubriken ovanför) och DEFAULT (Beskrivning)."""
    key = _key(heading)
    by_key = {_key(t): t for t in types}
    close = difflib.get_close_matches(key, list(by_key), n=1, cutoff=0.85)
    if close:
        return by_key[close[0]], LIKE, ""
    for word, type_ in TYPE_WORDS:
        if word in key and type_ in types:
            return type_, WORD, word
    if inherited and inherited in types:
        return inherited, INHERITED, ""
    return (DEFAULT_TYPE if DEFAULT_TYPE in types else (types[0] if types else DEFAULT_TYPE)), DEFAULT, ""


def suggest_type(heading: str, types: list[str], inherited: Optional[str] = None) -> str:
    """Avsnittstyp för en rubrik: en typ vars namn rubriken liknar, ett ord i rubriken som pekar på en typ, typen från
    rubriken ovanför, eller Beskrivning."""
    return explain_type(heading, types, inherited)[0]


# -- läsa och skapa bokmärken -----------------------------------------------------------------------------------------------
_OWN_START = re.compile(r'<w:bookmarkStart\b[^>]*\bw:name="(' + re.escape(BOOKMARK_PREFIX) + r'[^"]*)"[^>]*/>')


def _strip_own_bookmarks(xml: str) -> tuple[str, list[tuple[int, str]]]:
    """Tar bort pluginets bokmärken och returnerar (xml, [(position där bokmärket började, namn)])."""
    found = []
    while True:
        start = _OWN_START.search(xml)
        if start is None:
            return xml, found
        ident = re.search(r'\bw:id="(\d+)"', start.group(0)).group(1)
        found.append((start.start(), start.group(1)))
        xml = xml[:start.start()] + xml[start.end():]
        xml = re.sub(r'<w:bookmarkEnd\b[^>]*\bw:id="' + ident + r'"[^>]*/>', "", xml, count=1)


def read(path: str | Path, types: list[str]) -> Document:
    """Läser avsnitten i en planhandling och föreslår en avsnittstyp för varje. Skriver ingenting."""
    path = Path(path)
    parts = _read_zip(path)
    if "word/document.xml" not in parts or "word/styles.xml" not in parts:
        raise DocxError("Filen är inget Word-dokument (word/document.xml eller word/styles.xml saknas).")
    xml, old = _strip_own_bookmarks(parts["word/document.xml"].decode("utf-8"))
    levels = heading_levels(parts["word/styles.xml"].decode("utf-8"))
    try:
        body_lo = xml.index("<w:body>") + len("<w:body>")
        body_hi = xml.rindex("</w:body>")
    except ValueError as exc:
        raise DocxError("Dokumentet saknar brödtext (w:body).") from exc
    elements = [e for e in _spans(xml, body_lo, body_hi) if e[0] != "w:sectPr"]
    headings = []  # (index i elements, nivå, text)
    for i, (name, start, end) in enumerate(elements):
        if name == "w:p":
            level = levels.get(_style(xml, start, end))
            text = " ".join(_text(xml, start, end).split())
            if level and text:
                headings.append((i, level, text))
    if not headings:
        raise DocxError("Dokumentet har inga rubriker. Avsnitten känns igen på rubrikformaten (Rubrik 1, 2, 3).")

    sections, stack = [], []  # stack: (nivå, rubrik, föreslagen typ)
    for n, (i, level, text) in enumerate(headings):
        while stack and stack[-1][0] >= level:
            stack.pop()
        inherited = stack[-1][2] if stack else None
        suggested, reason, word = explain_type(text, types, inherited)
        stack.append((level, text, suggested))
        last = headings[n + 1][0] if n + 1 < len(headings) else len(elements)
        first_p = _edge_paragraph(xml, *elements[i], last=False)
        last_p = None
        for j in range(last - 1, i - 1, -1):
            last_p = last_p or _edge_paragraph(xml, *elements[j], last=True)
        if not (first_p and last_p):
            continue
        body = [" ".join(_text(xml, s, e).split()) for name, s, e in elements[i + 1:last]
                if name in ("w:p", "w:tbl")]  # även text i tabeller
        heading_start, heading_end = elements[i][1], elements[i][2]
        bookmark = next((name for position, name in old if heading_start <= position <= heading_end), None)
        sections.append(Section(len(sections), level, text, tuple(t for _, t, _ in stack),
                                _paragraph_start(xml, first_p[0]), _paragraph_end(xml, *last_p),
                                "\n\n".join(b for b in body if b), bookmark, suggested, reason, word))
    return Document(path, xml, sections)


def new_bookmark_name(taken: set[str]) -> str:
    """Ett nytt, unikt bokmärkesnamn (Word: högst 40 tecken, börjar med en bokstav, bara bokstäver, siffror och _)."""
    while True:
        name = BOOKMARK_PREFIX + uuid.uuid4().hex[:12]
        if name not in taken:
            return name


def bookmark_names(document: Document, tagged: set[int]) -> dict[int, str]:
    """Bokmärkesnamnet för varje avsnitt som ska få bokmärke: det befintliga, annars ett nytt."""
    taken = {s.bookmark for s in document.sections if s.bookmark}
    names = {}
    for section in document.sections:
        if section.index in tagged:
            name = section.bookmark or new_bookmark_name(taken)
            taken.add(name)
            names[section.index] = name
    return names


def write(document: Document, destination: str | Path, names: dict[int, str]) -> Path:
    """Skriver en kopia av dokumentet med ett bokmärke per avsnitt i ``names`` (avsnittets index → namn). Avsnitt som
    inte är med får inget bokmärke. Originalet skrivs aldrig över, utom när det själv är en kopia som pluginet har
    skapat (filen har redan pluginets bokmärken), så att man kan arbeta vidare i samma fil."""
    destination = Path(destination)
    source = Path(document.source)
    if destination.resolve() == source.resolve() and not any(s.bookmark for s in document.sections):
        raise DocxError("Spara kopian med bokmärken under ett annat namn än originalet.")
    parts = _read_zip(source)
    xml = document.xml
    next_id = max([int(i) for i in re.findall(r'<w:bookmarkStart\b[^>]*\bw:id="(\d+)"', xml)] + [0]) + 1
    inserts = []
    for n, section in enumerate(s for s in document.sections if s.index in names):
        bid = next_id + n
        inserts.append((section.start, f'<w:bookmarkStart w:id="{bid}" w:name="{names[section.index]}"/>'))
        inserts.append((section.end, f'<w:bookmarkEnd w:id="{bid}"/>'))
    for position, insert in sorted(inserts, key=lambda x: x[0], reverse=True):
        xml = xml[:position] + insert + xml[position:]
    parts["word/document.xml"] = xml.encode("utf-8")
    _write_zip(source, destination, parts)
    return destination


def bookmarked_copy_name(source: str | Path) -> Path:
    """Föreslaget namn på kopian med bokmärken: ``<namn>_bokmarken.docx`` bredvid originalet (eller samma fil om den redan
    är en kopia med bokmärken)."""
    source = Path(source)
    if source.stem.endswith("_bokmarken"):
        return source
    return source.with_name(f"{source.stem}_bokmarken{source.suffix}")
