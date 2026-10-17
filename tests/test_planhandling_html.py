"""Webbversionen av planhandlingen (core/planhandling_html.py). Ren Python."""
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from docx_case import CONTENT_TYPES, RELS, STYLES, TYPES, W, para, write_docx  # noqa: E402

from rita_oversiktsplan.core import planhandling, planhandling_html  # noqa: E402

TITLE_STYLE = STYLES.replace("</w:styles>", '<w:style w:type="paragraph" w:styleId="Rubrik"><w:name w:val="Title"/>'
                                            "</w:style></w:styles>")
NUMBERING = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:numbering xmlns:w="{W}">
<w:abstractNum w:abstractNumId="0"><w:lvl w:ilvl="0"><w:numFmt w:val="bullet"/></w:lvl>
<w:lvl w:ilvl="1"><w:numFmt w:val="bullet"/></w:lvl></w:abstractNum>
<w:abstractNum w:abstractNumId="1"><w:lvl w:ilvl="0"><w:numFmt w:val="decimal"/></w:lvl></w:abstractNum>
<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num><w:num w:numId="2"><w:abstractNumId w:val="1"/></w:num>
</w:numbering>"""
DOC_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId9" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink"
 Target="https://www.boverket.se/" TargetMode="External"/></Relationships>"""


def item(text: str, num: int, level: int = 0) -> str:
    return (f'<w:p><w:pPr><w:numPr><w:ilvl w:val="{level}"/><w:numId w:val="{num}"/></w:numPr></w:pPr>'
            f"<w:r><w:t>{text}</w:t></w:r></w:p>")


BODY = "".join([
    para("Översiktsplan Eskilstuna 2040", "Rubrik"),
    '<w:sdt><w:sdtPr><w:docPartObj><w:docPartGallery w:val="Table of Contents"/></w:docPartObj></w:sdtPr>'
    "<w:sdtContent>" + para("Innehållsförteckning") + "</w:sdtContent></w:sdt>",
    para("Ställningstaganden", "Rubrik1"),
    '<w:p><w:r><w:t xml:space="preserve">Kommunen </w:t></w:r><w:r><w:rPr><w:b/></w:rPr><w:t>ska</w:t></w:r>'
    '<w:r><w:t xml:space="preserve"> bygga </w:t></w:r><w:hyperlink r:id="rId9" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><w:r><w:t>enligt Boverket</w:t>'
    "</w:r></w:hyperlink><w:r><w:t>.</w:t></w:r></w:p>",
    item("Ett", 1), item("Ett och ett", 1, 1), item("Två", 1),
    item("Första", 2), item("Andra", 2),
    para("Klimatrisker", "Rubrik2"),
    '<w:tbl><w:tr><w:trPr><w:tblHeader/></w:trPr><w:tc>' + para("Risk") + "</w:tc><w:tc>" + para("Åtgärd")
    + '</w:tc></w:tr><w:tr><w:tc>' + para("Översvämning") + "</w:tc><w:tc>" + para("Vallar &amp; pumpar") + "</w:tc></w:tr></w:tbl>",
    '<w:p><w:r><w:drawing><wp:inline xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing">'
    '<wp:docPr id="1" name="Bild 1" descr="Karta över Ån"/></wp:inline></w:drawing></w:r></w:p>',
])
DOCUMENT = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="{W}"><w:body>{BODY}<w:sectPr/></w:body></w:document>"""


def write_rich(path: Path) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", RELS)
        archive.writestr("word/_rels/document.xml.rels", DOC_RELS)
        archive.writestr("word/document.xml", DOCUMENT)
        archive.writestr("word/styles.xml", TITLE_STYLE)
        archive.writestr("word/numbering.xml", NUMBERING)
    return path


def tag(source: Path, destination: Path) -> tuple[Path, dict[int, str]]:
    document = planhandling.read(source, TYPES)
    names = planhandling.bookmark_names(document, {s.index for s in document.sections})
    return planhandling.write(document, destination, names), names


class HtmlTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def test_every_tagged_section_gets_its_bookmark_as_id_and_its_type(self):
        tagged, names = tag(write_docx(self.dir / "p.docx"), self.dir / "p_bokmarken.docx")
        page = planhandling_html.to_html(tagged, {names[0]: "Sammanfattning"}, "ÖP 2040")
        for name in names.values():
            self.assertIn(f'<section id="{name}"', page)
            self.assertIn(f'href="#{name}"', page)  # innehållsförteckningen länkar dit
        self.assertIn(f'<section id="{names[0]}" data-avsnittstyp="Sammanfattning">', page)

    def test_headings_move_down_one_level_under_the_title(self):
        tagged, _ = tag(write_docx(self.dir / "p.docx"), self.dir / "p_bokmarken.docx")
        page = planhandling_html.to_html(tagged, title="ÖP 2040")
        self.assertEqual(page.count("<h1>"), 1)
        self.assertIn("<h1>ÖP 2040</h1>", page)
        self.assertIn("<h2>Sammanfattning</h2>", page)
        self.assertIn("<h3>Bostäder</h3>", page)
        self.assertIn("<h4>Bostadsförsörjning</h4>", page)

    def test_the_documents_own_title_becomes_h1(self):
        tagged, _ = tag(write_rich(self.dir / "r.docx"), self.dir / "r_bokmarken.docx")
        page = planhandling_html.to_html(tagged, title="Annan titel")
        self.assertIn("<h1>Översiktsplan Eskilstuna 2040</h1>", page)
        self.assertIn("<title>Översiktsplan Eskilstuna 2040</title>", page)
        self.assertNotIn("Innehållsförteckning", page)  # Words innehållsförteckning hoppas över

    def test_bold_links_lists_tables_and_images_are_kept_simply(self):
        tagged, _ = tag(write_rich(self.dir / "r.docx"), self.dir / "r_bokmarken.docx")
        page = planhandling_html.to_html(tagged)
        self.assertIn('<p>Kommunen <strong>ska</strong> bygga <a href="https://www.boverket.se/">enligt Boverket</a>.</p>',
                      page)
        self.assertIn("<ul><li>Ett<ul><li>Ett och ett</li></ul></li><li>Två</li></ul>", page.replace("\n", ""))
        self.assertIn("<ol><li>Första</li><li>Andra</li></ol>", page.replace("\n", ""))
        self.assertIn("<tr><th>Risk</th><th>Åtgärd</th></tr>", page)
        self.assertIn("<td>Vallar &amp; pumpar</td>", page)
        self.assertIn("[Bild: Karta över Ån]", page)

    def test_only_web_mail_and_anchor_links_become_links(self):
        from rita_oversiktsplan.core.planhandling_html import _safe_link
        self.assertEqual(_safe_link("https://www.boverket.se/"), "https://www.boverket.se/")
        self.assertEqual(_safe_link("#op_abc"), "#op_abc")
        self.assertEqual(_safe_link("mailto:plan@kommun.se"), "mailto:plan@kommun.se")
        self.assertIsNone(_safe_link("javascript:alert(1)"))
        self.assertIsNone(_safe_link(" JavaScript:alert(1)"))
        self.assertIsNone(_safe_link("file:///C:/hemligt.docx"))
        self.assertIsNone(_safe_link(r"C:\planer\underlag.pdf"))

    def test_an_untagged_document_still_becomes_a_page_without_ids(self):
        page = planhandling_html.to_html(write_docx(self.dir / "p.docx"))
        self.assertIn("<h2>Sammanfattning</h2>", page)
        self.assertNotIn("<section id=", page)

    def test_the_web_version_is_named_after_the_document(self):
        self.assertEqual(planhandling_html.html_name(Path("a/Plan_bokmarken.docx")), Path("a/Plan_bokmarken.html"))


if __name__ == "__main__":
    unittest.main()
