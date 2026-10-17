"""Skapar ett utkast till planhandling (Word) med en rubrik för allt innehåll i ÖP-katalogen.

    python tools/skapa_planhandling_mall.py              # skriver exempel/Planhandling_mall_ÖP-katalogen_<version>.docx

Utkastet är en mall att skriva i och ett testdokument för Skapa bokmärken i planhandling: rubrikerna (Rubrik 1–3) följer
katalogens kategorier och värden, och under varje rubrik finns katalogens vägledning (grå, kursiv) och en plats för
kommunens text. Kategorier som inte är text (Avsnittstyp, Planhändelse, Sambandsnivå, Plangeometri, Område) får
ingen egen rubrik. Rubriknamnen är valda så att Skapa bokmärken i planhandling föreslår rätt avsnittstyp.

Ingen QGIS och inga extra paket behövs: Word-filen skrivs direkt som Office Open XML. Katalogen läses ur pluginets
medföljande kopia (``rita_oversiktsplan/data/opkatalog.json``, Boverket, CC0).
"""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rita_oversiktsplan.core import opkatalog  # noqa: E402

OUT_DIR = ROOT / "exempel"
GUIDE_LIMIT = 420  # så många tecken av vägledningen tas med

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
WRITE_HERE = "[Skriv kommunens text här.]"


# -- innehållet ---------------------------------------------------------------------------------------------------
def guide(catalog: opkatalog.Catalog, node: dict) -> str:
    """Katalogens vägledning (annars beskrivning) för en kategori eller ett värde, kortad vid en mening."""
    text = opkatalog._attribute(node, "Vägledning") or opkatalog._attribute(node, "Beskrivning")
    text = " ".join(text.split())
    text = text.split(" Finns behov av att specificera")[0]  # samma upplysning under varje markanvändning
    if len(text) <= GUIDE_LIMIT:
        return text
    cut = text[:GUIDE_LIMIT]
    end = cut.rfind(". ")
    return (cut[: end + 1] if end > 100 else cut.rstrip() + " …")


def children(catalog: opkatalog.Catalog, category: str) -> list[dict]:
    return list(catalog.category(category).get("barn") or [])


def outline(catalog: opkatalog.Catalog) -> list[tuple[int, str, str]]:
    """(nivå, rubrik, vägledning) i dokumentets ordning. Vägledningen tom = bara platsen för kommunens text."""
    rows: list[tuple[int, str, str]] = []

    def add(level: int, heading: str, text: str = "") -> None:
        rows.append((level, heading, text))

    def category(name: str, title: str = "", statement: bool = True, sublevel_statement: bool = True) -> None:
        """En kategori som rubrik 1, varje värde som rubrik 2, och "Ställningstaganden" under (eller direkt under
        kategorin om den saknar värden)."""
        node = catalog.category(name)
        add(1, title or name.strip(), guide(catalog, node))
        values = children(catalog, name)
        if not values and statement:
            add(2, "Ställningstaganden")
        for value in values:
            add(2, value["namn"].strip(), guide(catalog, value))
            if statement and sublevel_statement:
                add(3, "Ställningstaganden")

    add(1, "Sammanfattning", "En kort sammanfattning av översiktsplanen: vad kommunen vill och de viktigaste "
                             "ställningstagandena.")
    add(1, "Översiktsplanens syfte", "Varför planen tas fram och vad den ska vägleda.")
    add(1, "Läsanvisning", "Hur planen är uppbyggd och hur den ska läsas. Planens innehåll finns också som digitala "
                           "kartdata; texten är kopplad till kartans innehåll med bokmärken.")

    category("Mål, planer och program", statement=False)
    category("Utvecklingsinriktning")
    category("Mark- och vattenanvändning")
    add(2, "Kompletterande mark- och vattenanvändning", guide(catalog, catalog.category(
        "Kompletterande mark- och vattenanvändning")))
    for value in children(catalog, "Kompletterande mark- och vattenanvändning"):
        add(3, value["namn"].strip(), guide(catalog, value))
    category("Bostadsförsörjning")
    category("LIS", "Landsbygdsutveckling i strandnära lägen (LIS)")
    category("Riksintresse kommunens ställningstagande", "Riksintressen", sublevel_statement=False)
    # riksintressen: kommunens ställningstagande per riksintresse (rubrik 3)
    rows[:] = _riksintressen(rows)
    category("Miljökvalitetsnormer enligt 5 kap. MB")
    category("Särskilt värdefull kulturmiljö")
    category("Klimatrelaterade risker")
    category("Övriga förhållanden av väsentlig betydelse")
    category("Mellankommunala och regionala intressen")
    category("Avvikelse från regionplan")
    category("Konsekvenser", statement=False)
    add(1, "Länsstyrelsens invändningar", guide(catalog, catalog.category(
        "Invändningar i länsstyrelsens granskningsyttrande")))
    for value in children(catalog, "Invändningar i länsstyrelsens granskningsyttrande"):
        add(2, value["namn"].strip(), guide(catalog, value))
        add(3, "Länsstyrelsens invändning")
        add(3, "Kommentar på länsstyrelsens invändning")
    add(1, "Framtagandeprocess", "Hur planen har tagits fram: samråd, granskning, antagande och dialog.")
    for heading in ("Samråd", "Granskning", "Antagande"):
        add(2, heading)
    add(1, "Övrig information", "Till exempel underlag till planen och ordlista.")
    add(2, "Underlag", "Planens underlag, med underlagstyperna i ÖP-katalogen.")
    for value in children(catalog, "Underlagstyp"):
        add(3, value["namn"].strip(), guide(catalog, value))
    return rows


def _riksintressen(rows: list[tuple[int, str, str]]) -> list[tuple[int, str, str]]:
    """Under varje riksintresse (rubrik 2 i kapitlet Riksintressen) läggs "Kommunens ställningstagande"."""
    out: list[tuple[int, str, str]] = []
    inside = False
    for level, heading, text in rows:
        out.append((level, heading, text))
        if level == 1:
            inside = heading == "Riksintressen"
        elif inside and level == 2:
            out.append((3, "Kommunens ställningstagande", ""))
    return out


# -- Word ---------------------------------------------------------------------------------------------------------
def paragraph(text: str, style: str = "") -> str:
    props = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    return f'<w:p>{props}<w:r><w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>'


def document_xml(catalog: opkatalog.Catalog, rows: list[tuple[int, str, str]]) -> str:
    body = [
        paragraph("Översiktsplan [kommunens namn] [år]", "Rubrik"),
        paragraph(f"Utkast till planhandling med en rubrik för allt innehåll i Boverkets ÖP-katalog "
                  f"{catalog.version}. Den grå texten är katalogens vägledning och tas bort. Ta också bort de "
                  "rubriker som planen inte behöver, och lägg till egna underrubriker där det behövs.", "Vagledning"),
    ]
    for level, heading, text in rows:
        body.append(paragraph(heading, f"Rubrik{level}"))
        if text:
            body.append(paragraph(text, "Vagledning"))
        body.append(paragraph(WRITE_HERE))
    section = ('<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1417" w:right="1417" w:bottom="1417" '
               'w:left="1417" w:header="708" w:footer="708" w:gutter="0"/></w:sectPr>')
    return (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<w:document xmlns:w="{W}"><w:body>'
            + "".join(body) + section + "</w:body></w:document>")


def _heading_style(level: int, size: int, before: int) -> str:
    return (f'<w:style w:type="paragraph" w:styleId="Rubrik{level}"><w:name w:val="heading {level}"/>'
            f'<w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:uiPriority w:val="9"/><w:qFormat/>'
            f'<w:pPr><w:keepNext/><w:keepLines/><w:spacing w:before="{before}" w:after="80"/>'
            f'<w:outlineLvl w:val="{level - 1}"/></w:pPr>'
            f'<w:rPr><w:rFonts w:asciiTheme="majorHAnsi" w:hAnsiTheme="majorHAnsi"/><w:b/><w:color w:val="1F3A33"/>'
            f'<w:sz w:val="{size}"/></w:rPr></w:style>')


STYLES = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<w:styles xmlns:w="{W}">'
          '<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:eastAsia="Calibri" '
          'w:cs="Calibri"/><w:sz w:val="22"/><w:lang w:val="sv-SE"/></w:rPr></w:rPrDefault>'
          '<w:pPrDefault><w:pPr><w:spacing w:after="120" w:line="264" w:lineRule="auto"/></w:pPr></w:pPrDefault>'
          '</w:docDefaults>'
          '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/></w:style>'
          '<w:style w:type="paragraph" w:styleId="Rubrik"><w:name w:val="Title"/><w:basedOn w:val="Normal"/>'
          '<w:next w:val="Normal"/><w:qFormat/><w:pPr><w:spacing w:after="240"/></w:pPr>'
          '<w:rPr><w:sz w:val="52"/><w:color w:val="1F3A33"/></w:rPr></w:style>'
          + _heading_style(1, 36, 480) + _heading_style(2, 28, 280) + _heading_style(3, 24, 200) +
          '<w:style w:type="paragraph" w:customStyle="1" w:styleId="Vagledning"><w:name w:val="Vägledning"/>'
          '<w:basedOn w:val="Normal"/><w:qFormat/><w:rPr><w:i/><w:color w:val="6B7672"/><w:sz w:val="20"/></w:rPr>'
          '</w:style></w:styles>')

CONTENT_TYPES = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                 '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                 '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                 '<Default Extension="xml" ContentType="application/xml"/>'
                 '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.'
                 'wordprocessingml.document.main+xml"/>'
                 '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.'
                 'wordprocessingml.styles+xml"/></Types>')
RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/'
        'officeDocument" Target="word/document.xml"/></Relationships>')
DOCUMENT_RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                 '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                 '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/'
                 'styles" Target="styles.xml"/></Relationships>')


def write(destination: Path, catalog: opkatalog.Catalog | None = None) -> Path:
    catalog = catalog or opkatalog.bundled()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", RELS)
        archive.writestr("word/_rels/document.xml.rels", DOCUMENT_RELS)
        archive.writestr("word/document.xml", document_xml(catalog, outline(catalog)))
        archive.writestr("word/styles.xml", STYLES)
    return destination


def main() -> None:
    catalog = opkatalog.bundled()
    path = write(OUT_DIR / f"Planhandling_mall_ÖP-katalogen_{catalog.version}.docx", catalog)
    rows = outline(catalog)
    print(f"Skapade {path} ({len(rows)} rubriker)")


if __name__ == "__main__":
    main()
