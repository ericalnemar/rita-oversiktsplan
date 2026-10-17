"""En liten syntetisk planhandling (.docx) för testerna: rubriker på tre nivåer, Words egna namnrymder, ett eget
bokmärke (innehållsförteckningens _Toc) och en tabell. Formatmallarna följer samma mönster som Rita Detaljplans
testdokument (tests/docx_case.py där)."""
import zipfile
from pathlib import Path

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def para(text: str, style: str = "") -> str:
    props = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    return f"<w:p>{props}<w:r><w:t>{text}</w:t></w:r></w:p>"


BODY = "".join([
    para("Innehåll", "Innehllsfrteckningsrubrik"),
    '<w:p><w:pPr><w:pStyle w:val="Rubrik1"/></w:pPr><w:bookmarkStart w:id="0" w:name="_Toc100"/>'
    '<w:r><w:t>Sammanfattning</w:t></w:r><w:bookmarkEnd w:id="0"/></w:p>',
    para("Översiktsplanen visar hur kommunen vill utvecklas till 2040."),
    para("Översiktsplanens syfte", "Rubrik1"),
    para("Planen ska vägleda beslut om mark och vatten."),
    para("Ställningstaganden", "Rubrik1"),
    para("Bostäder", "Rubrik2"),
    para("Nya bostäder placeras nära kollektivtrafik."),
    para("Bostadsförsörjning", "Rubrik3"),
    para("Kommunen behöver 200 nya bostäder per år."),
    para("Klimatrisker", "Rubrik2"),
    '<w:tbl><w:tblPr/><w:tblGrid><w:gridCol/></w:tblGrid><w:tr><w:tc>'
    + para("Översvämning vid Ån.") + "</w:tc></w:tr></w:tbl>",
    para("Konsekvenser", "Rubrik1"),
    para("Planen ger minskade utsläpp."),
    para("Tom rubrik", "Rubrik1"),
])

DOCUMENT = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="{W}" xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml" \
xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" mc:Ignorable="w14"><w:body>{BODY}\
<w:sectPr><w:pgSz w:w="11906" w:h="16838"/></w:sectPr></w:body></w:document>"""

STYLES = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="{W}">
<w:style w:type="paragraph" w:styleId="Normal"><w:name w:val="Normal"/></w:style>
<w:style w:type="paragraph" w:styleId="Rubrik1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:pPr><w:outlineLvl w:val="0"/></w:pPr></w:style>
<w:style w:type="paragraph" w:styleId="Rubrik2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:pPr><w:outlineLvl w:val="1"/></w:pPr></w:style>
<w:style w:type="paragraph" w:styleId="Rubrik3"><w:name w:val="Rubrik 3"/><w:basedOn w:val="Normal"/></w:style>
<w:style w:type="paragraph" w:styleId="Innehllsfrteckningsrubrik"><w:name w:val="TOC Heading"/><w:basedOn w:val="Rubrik1"/><w:pPr><w:outlineLvl w:val="9"/></w:pPr></w:style>
</w:styles>"""

CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>"""

RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>"""

TYPES = ["Beskrivning", "Framtagandeprocess", "Kommentar på länsstyrelsens invändning", "Konsekvens",
         "Länsstyrelsens invändning", "Sammanfattning", "Ställningstagande", "Översiktsplanens syfte",
         "Övrig information"]


def write_docx(path: Path, document: str = DOCUMENT) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", RELS)
        archive.writestr("word/document.xml", document)
        archive.writestr("word/styles.xml", STYLES)
    return path


def document_xml(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        return archive.read("word/document.xml").decode("utf-8")
