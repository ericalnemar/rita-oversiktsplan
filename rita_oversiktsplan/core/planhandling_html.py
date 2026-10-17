"""Webbversion av planhandlingen: Word-dokumentet (.docx) som en enkel HTML-sida. Ren Python.

Varje avsnitt blir ett ``<section>`` med avsnittets bokmärke som ``id`` (``<section id="op_3f2a…">``), så att en
webbkarta kan länka från ett objekt till dess text med adressen ``planhandling.html#op_3f2a…``: samma bokmärkesnamn
som står i planens tabell ``dokumentavsnitt``. Avsnittstypen står i ``data-avsnittstyp``.

Rubrikerna flyttas ner ett steg: dokumentets titel (formatmallen Rubrik/Title, annars planens titel) blir ``<h1>``,
Rubrik 1 blir ``<h2>``, Rubrik 2 ``<h3>`` och så vidare, eftersom en webbsida bör ha en enda ``<h1>``. Med kommer
stycken, fet och kursiv stil, länkar, punkt- och numrerade listor och tabeller; Words formatering i övrigt (typsnitt,
färger, marginaler) gör det inte. Bilder ersätts med sin alternativtext. Innehållsförteckningar hoppas över.
"""
from __future__ import annotations

import html
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

from . import planhandling as ph

W = ph.W
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
WP = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"
MC = "{http://schemas.openxmlformats.org/markup-compatibility/2006}"
HYPERLINK = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink"

CSS = """
body { font-family: Georgia, "Cambria", serif; line-height: 1.55; max-width: 46rem; margin: 2rem auto; padding: 0 1rem;
  color: #16201e; background: #ffffff; }
h1, h2, h3, h4, h5, h6 { font-family: "Segoe UI", system-ui, sans-serif; line-height: 1.25; }
nav { font-family: "Segoe UI", system-ui, sans-serif; font-size: .9rem; border: 1px solid #d6dedb; border-radius: 8px;
  padding: .5rem 1rem; }
nav ol { list-style: none; padding-left: 0; } nav li { margin: .15rem 0; }
section:target { background: #dcefe9; outline: .5rem solid #dcefe9; }
table { border-collapse: collapse; margin: 1rem 0; } td, th { border: 1px solid #d6dedb; padding: .3rem .6rem;
  vertical-align: top; text-align: left; }
.bild { color: #5a6b66; font-style: italic; }
@media (prefers-color-scheme: dark) { body { background: #0f1514; color: #e4ebe9; } a { color: #74a8ea; }
  section:target { background: #173a33; outline-color: #173a33; } nav, td, th { border-color: #2f3d3a; } }
"""


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


class _Converter:
    def __init__(self, parts: dict[str, bytes], types: dict[str, str]):
        self.types = types
        styles = parts.get("word/styles.xml", b"").decode("utf-8")
        self.levels = ph.heading_levels(styles) if styles else {}
        self.title_styles = self._title_styles(styles)
        self.links = self._relations(parts.get("word/_rels/document.xml.rels", b""))
        self.list_kinds = self._numbering(parts.get("word/numbering.xml", b""))

    # -- dokumentets delar ---------------------------------------------------------------------------------------
    @staticmethod
    def _title_styles(styles: str) -> set[str]:
        if not styles:
            return set()
        found = set()
        for node in ET.fromstring(styles).findall(W + "style"):
            name = node.find(W + "name")
            if name is not None and name.get(W + "val", "").strip().lower() in ("title", "rubrik"):
                found.add(node.get(W + "styleId"))
        return found

    @staticmethod
    def _relations(data: bytes) -> dict[str, str]:
        if not data:
            return {}
        root = ET.fromstring(data)
        return {rel.get("Id"): rel.get("Target") for rel in root if rel.get("Type") == HYPERLINK}

    @staticmethod
    def _numbering(data: bytes) -> dict[tuple[str, str], str]:
        """(numId, nivå) → "ul" eller "ol"."""
        if not data:
            return {}
        root = ET.fromstring(data)
        abstract = {}
        for node in root.findall(W + "abstractNum"):
            for lvl in node.findall(W + "lvl"):
                fmt = lvl.find(W + "numFmt")
                kind = "ul" if fmt is None or fmt.get(W + "val") in ("bullet", "none") else "ol"
                abstract[(node.get(W + "abstractNumId"), lvl.get(W + "ilvl"))] = kind
        kinds = {}
        for num in root.findall(W + "num"):
            ref = num.find(W + "abstractNumId")
            if ref is None:
                continue
            for (abstract_id, level), kind in abstract.items():
                if abstract_id == ref.get(W + "val"):
                    kinds[(num.get(W + "numId"), level)] = kind
        return kinds

    # -- text i ett stycke ---------------------------------------------------------------------------------------
    def inline(self, node) -> str:
        out = []
        for child in node:
            name = _local(child.tag)
            if name == "r":
                out.append(self.run(child))
            elif name == "hyperlink":
                target = _safe_link(self.links.get(child.get(R + "id")) or (
                    "#" + child.get(W + "anchor") if child.get(W + "anchor") else None))
                text = self.inline(child)
                out.append(f'<a href="{html.escape(target)}">{text}</a>' if target else text)
            elif name in ("ins", "smartTag", "fldSimple", "customXml", "sdt", "sdtContent"):
                out.append(self.inline(child))
            # w:del (borttagen text), w:pPr, bokmärken och kommentarer ger ingen text
        return "".join(out)

    def run(self, run) -> str:
        props = run.find(W + "rPr")
        bold = props is not None and _on(props.find(W + "b"))
        italic = props is not None and _on(props.find(W + "i"))
        parts = []
        for child in run:
            name = _local(child.tag)
            if name == "t":
                parts.append(html.escape(child.text or ""))
            elif name == "tab":
                parts.append(" ")
            elif name in ("br", "cr"):
                parts.append("<br>")
            elif name in ("drawing", "pict") or (name == "AlternateContent" and child.find(f".//{WP}docPr") is not None):
                parts.append(self.image(child))
        text = "".join(parts)
        if text and bold:
            text = f"<strong>{text}</strong>"
        if text and italic:
            text = f"<em>{text}</em>"
        return text

    @staticmethod
    def image(node) -> str:
        doc_pr = node.find(f".//{WP}docPr")
        alt = (doc_pr.get("descr") or doc_pr.get("title") or "").strip() if doc_pr is not None else ""
        return f'<span class="bild">[Bild{": " + html.escape(alt) if alt else ""}]</span>'

    # -- stycken, listor och tabeller ----------------------------------------------------------------------------
    @staticmethod
    def style(paragraph) -> str:
        style = paragraph.find(f"{W}pPr/{W}pStyle")
        return style.get(W + "val") if style is not None else ""

    def heading_level(self, paragraph) -> Optional[int]:
        level = self.levels.get(self.style(paragraph))
        return level if level and _plain(paragraph) else None

    @staticmethod
    def bookmark(paragraph) -> Optional[str]:
        for start in paragraph.iter(W + "bookmarkStart"):
            name = start.get(W + "name", "")
            if name.startswith(ph.BOOKMARK_PREFIX):
                return name
        return None

    def list_item(self, paragraph) -> Optional[tuple[str, int, str]]:
        """(ul/ol, nivå, listans id) för ett stycke i en punkt- eller numrerad lista."""
        num = paragraph.find(f"{W}pPr/{W}numPr")
        if num is None:
            return None
        num_id = num.find(W + "numId")
        level = num.find(W + "ilvl")
        num_id = num_id.get(W + "val") if num_id is not None else None
        level = level.get(W + "val") if level is not None else "0"
        if not num_id or num_id == "0":
            return None
        return self.list_kinds.get((num_id, level), "ul"), int(level), num_id

    def table(self, table) -> str:
        rows = []
        for tr in table.findall(W + "tr"):
            header = tr.find(f"{W}trPr/{W}tblHeader") is not None
            cells = []
            for tc in tr.findall(W + "tc"):
                tag = "th" if header else "td"
                content = "".join(self.blocks(list(tc), in_cell=True))
                cells.append(f"<{tag}>{content}</{tag}>")
            rows.append("<tr>" + "".join(cells) + "</tr>")
        return "<table>\n" + "\n".join(rows) + "\n</table>"

    def blocks(self, nodes, in_cell: bool = False) -> list[str]:
        """Stycken, listor och tabeller (inte rubriker; de sköts av ``convert``)."""
        out: list[str] = []
        lists: list[tuple[str, int, str]] = []  # öppna listor: (ul/ol, nivå, listans id)

        def close(to_level: int = -1) -> None:
            """Stänger listorna djupare än ``to_level`` (alla med -1)."""
            while lists and lists[-1][1] > to_level:
                out.append(f"</li></{lists.pop()[0]}>")

        for node in nodes:
            name = _local(node.tag)
            if name == "p":
                text = self.inline(node).strip()
                item = self.list_item(node)
                if item is None:
                    close()
                    if text:
                        out.append(text if in_cell and len(nodes) == 1 else f"<p>{text}</p>")
                    continue
                kind, level, num_id = item
                if lists and level < lists[-1][1]:
                    close(level)
                if lists and level == lists[-1][1] and (kind, num_id) != lists[-1][::2]:
                    close(level - 1)  # en annan lista på samma nivå
                if not lists or level > lists[-1][1]:
                    out.append(f"<{kind}><li>{text}")  # ny lista, eller en underlista i punkten ovanför
                    lists.append((kind, level, num_id))
                else:
                    out.append(f"</li><li>{text}")
            elif name == "tbl":
                close()
                out.append(self.table(node))
            elif name == "sdt":
                close()
                if not _is_toc(node):
                    content = node.find(W + "sdtContent")
                    if content is not None:
                        out += self.blocks(list(content), in_cell)
        close()
        return out

    # -- hela dokumentet -----------------------------------------------------------------------------------------
    def convert(self, body, fallback_title: str) -> tuple[str, str, list[tuple[Optional[str], str, int]]]:
        """(titel, innehåll, [(bokmärke eller None, rubrik, nivå)])."""
        title = None
        parts: list[str] = []
        toc: list[tuple[Optional[str], str, int]] = []
        pending: list = []  # stycken m.m. som väntar på att skrivas
        open_section = False

        def flush() -> None:
            if pending:
                parts.extend(self.blocks(pending))
                pending.clear()

        nodes = []
        for node in body:  # innehåll i innehållskontroller (utom innehållsförteckningar) räknas som brödtext
            if _local(node.tag) == "sdt" and not _is_toc(node):
                content = node.find(W + "sdtContent")
                nodes += list(content) if content is not None else []
            elif _local(node.tag) != "sectPr" and not (_local(node.tag) == "sdt" and _is_toc(node)):
                nodes.append(node)
        for node in nodes:
            if _local(node.tag) == "p":
                if title is None and not toc and not open_section and self.style(node) in self.title_styles \
                        and _plain(node):
                    flush()
                    title = _plain(node)
                    continue
                level = self.heading_level(node)
                if level:
                    flush()
                    if open_section:
                        parts.append("</section>")
                    elif parts:  # det som står före första rubriken
                        parts[:] = ["<header>", *parts, "</header>"]
                    bookmark = self.bookmark(node)
                    attributes = ""
                    if bookmark:
                        attributes = f' id="{html.escape(bookmark)}"'
                        if self.types.get(bookmark):
                            attributes += f' data-avsnittstyp="{html.escape(self.types[bookmark])}"'
                    toc.append((bookmark, _plain(node), level))
                    tag = f"h{min(level + 1, 6)}"
                    parts.append(f"<section{attributes}>\n<{tag}>{self.inline(node).strip()}</{tag}>")
                    open_section = True
                    continue
            pending.append(node)
        flush()
        if open_section:
            parts.append("</section>")
        return title or fallback_title, "\n".join(parts), toc


SAFE_SCHEMES = ("http://", "https://", "mailto:", "#")


def _safe_link(target: Optional[str]) -> Optional[str]:
    """Bara vanliga webbadresser, e-post och ankare blir länkar på webbsidan. En länk som ``javascript:`` eller en
    lokal fil i Word-dokumentet blir vanlig text, så att den publicerade sidan inte kan köra kod eller peka in på
    någons dator."""
    if not target:
        return None
    return target if target.strip().lower().startswith(SAFE_SCHEMES) else None


def _on(node) -> bool:
    return node is not None and node.get(W + "val", "true") not in ("0", "false", "off")


def _plain(paragraph) -> str:
    return " ".join("".join(t.text or "" for t in paragraph.iter(W + "t")).split())


def _is_toc(sdt) -> bool:
    gallery = sdt.find(f"{W}sdtPr/{W}docPartObj/{W}docPartGallery")
    return gallery is not None and "Contents" in (gallery.get(W + "val") or "")


def to_html(docx: str | Path, types: Optional[dict[str, str]] = None, title: str = "") -> str:
    """HTML-sidan för en planhandling (med bokmärken). ``types``: bokmärke → avsnittstyp."""
    docx = Path(docx)
    parts = ph._read_zip(docx)
    if "word/document.xml" not in parts:
        raise ph.DocxError("Filen är inget Word-dokument (word/document.xml saknas).")
    root = ET.fromstring(parts["word/document.xml"])
    body = root.find(W + "body")
    if body is None:
        raise ph.DocxError("Dokumentet saknar brödtext (w:body).")
    converter = _Converter(parts, types or {})
    page_title, content, toc = converter.convert(body, title or docx.stem)
    nav = ""
    if toc:
        items = "\n".join(  # rubriker utan bokmärke står med, men utan länk
            f'<li style="margin-left:{(level - 1) * 1.2}rem">'
            + (f'<a href="#{html.escape(ident)}">{html.escape(text)}</a>' if ident else html.escape(text)) + "</li>"
            for ident, text, level in toc)
        nav = f'<nav aria-label="Innehåll">\n<ol>\n{items}\n</ol>\n</nav>\n'
    return (f'<!doctype html>\n<html lang="sv">\n<head>\n<meta charset="utf-8">\n'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f"<title>{html.escape(page_title)}</title>\n"
            f'<meta name="generator" content="Rita Översiktsplan">\n<style>{CSS}</style>\n</head>\n<body>\n'
            f"<h1>{html.escape(page_title)}</h1>\n{nav}<main>\n{content}\n</main>\n</body>\n</html>\n")


def write(docx: str | Path, destination: str | Path, types: Optional[dict[str, str]] = None, title: str = "") -> Path:
    destination = Path(destination)
    destination.write_text(to_html(docx, types, title), encoding="utf-8")
    return destination


def html_name(docx: str | Path) -> Path:
    """Webbversionens namn: samma som Word-filen, med .html."""
    return Path(docx).with_suffix(".html")
