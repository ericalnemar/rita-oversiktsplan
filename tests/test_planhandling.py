"""Planhandlingen (Word): avsnitt, avsnittstyp och bokmärken i en kopia med bokmärken (ren Python, kräver inte QGIS)."""
import re
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from docx_case import DOCUMENT, TYPES, document_xml, write_docx  # noqa: E402

from rita_oversiktsplan.core import planhandling  # noqa: E402

OWN = re.compile(r'<w:bookmarkStart\b[^>]*w:name="(op_[^"]*)"')


class ReadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.path = write_docx(Path(self.tmp.name) / "op.docx")
        self.document = planhandling.read(self.path, TYPES)

    def headings(self):
        return [(s.level, s.heading) for s in self.document.sections]

    def test_every_heading_becomes_a_section_with_its_level(self):
        self.assertEqual(self.headings(), [(1, "Sammanfattning"), (1, "Översiktsplanens syfte"),
                                           (1, "Ställningstaganden"), (2, "Bostäder"), (3, "Bostadsförsörjning"),
                                           (2, "Klimatrisker"), (1, "Konsekvenser"), (1, "Tom rubrik")])

    def test_the_table_of_contents_heading_is_not_a_section(self):
        self.assertNotIn("Innehåll", [s.heading for s in self.document.sections])

    def test_section_types_are_suggested_from_the_heading_or_the_heading_above(self):
        types = {s.heading: s.suggested_type for s in self.document.sections}
        self.assertEqual(types["Sammanfattning"], "Sammanfattning")
        self.assertEqual(types["Översiktsplanens syfte"], "Översiktsplanens syfte")
        self.assertEqual(types["Ställningstaganden"], "Ställningstagande")
        self.assertEqual(types["Bostäder"], "Ställningstagande")  # ärvs från rubriken ovanför
        self.assertEqual(types["Bostadsförsörjning"], "Ställningstagande")
        self.assertEqual(types["Konsekvenser"], "Konsekvens")

    def test_a_heading_without_a_hint_is_a_description(self):
        self.assertEqual(planhandling.suggest_type("Planeringsförutsättningar", TYPES), "Beskrivning")

    def test_the_text_under_each_heading_is_read(self):
        section = next(s for s in self.document.sections if s.heading == "Bostadsförsörjning")
        self.assertIn("200 nya bostäder", section.text)
        self.assertEqual(next(s for s in self.document.sections if s.heading == "Tom rubrik").text, "")

    def test_text_in_a_table_counts_as_text_under_the_heading(self):
        section = next(s for s in self.document.sections if s.heading == "Klimatrisker")
        self.assertIn("Översvämning vid Ån", section.text)

    def test_a_document_without_headings_is_refused_with_a_clear_message(self):
        path = write_docx(Path(self.tmp.name) / "utan.docx", DOCUMENT.replace("Rubrik", "Normal"))
        with self.assertRaisesRegex(planhandling.DocxError, "inga rubriker"):
            planhandling.read(path, TYPES)

    def test_a_file_that_is_not_word_is_refused(self):
        path = Path(self.tmp.name) / "fel.docx"
        path.write_text("inte en zip")
        with self.assertRaises(planhandling.DocxError):
            planhandling.read(path, TYPES)


class WriteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.path = write_docx(Path(self.tmp.name) / "op.docx")
        self.original = self.path.read_bytes()
        self.document = planhandling.read(self.path, TYPES)
        self.tagged = {s.index for s in self.document.sections}
        self.names = planhandling.bookmark_names(self.document, self.tagged)
        self.copy = planhandling.write(self.document, Path(self.tmp.name) / "op_bokmarken.docx", self.names)

    def test_every_tagged_section_gets_a_bookmark_in_a_copy_and_the_original_is_untouched(self):
        self.assertEqual(self.path.read_bytes(), self.original)
        names = OWN.findall(document_xml(self.copy))
        self.assertEqual(sorted(names), sorted(self.names.values()))

    def test_the_copy_is_valid_xml_and_keeps_other_bookmarks(self):
        xml = document_xml(self.copy)
        ET.fromstring(xml)
        self.assertIn('w:name="_Toc100"', xml)
        starts = re.findall(r'<w:bookmarkStart\b[^>]*w:id="(\d+)"', xml)
        ends = re.findall(r'<w:bookmarkEnd\b[^>]*w:id="(\d+)"', xml)
        self.assertEqual(sorted(starts), sorted(ends))
        self.assertEqual(len(starts), len(set(starts)))

    def test_bookmark_names_follow_words_rules(self):
        for name in self.names.values():
            self.assertRegex(name, r"^[A-Za-z][A-Za-z0-9_]{0,39}$")

    def test_a_tagged_copy_read_again_keeps_its_bookmark_names(self):
        again = planhandling.read(self.copy, TYPES)
        self.assertEqual({s.index: s.bookmark for s in again.sections}, self.names)
        self.assertEqual(planhandling.bookmark_names(again, self.tagged), self.names)

    def test_tagging_the_tagged_copy_again_does_not_duplicate_bookmarks(self):
        again = planhandling.read(self.copy, TYPES)
        planhandling.write(again, self.copy, planhandling.bookmark_names(again, self.tagged))
        self.assertEqual(sorted(OWN.findall(document_xml(self.copy))), sorted(self.names.values()))

    def test_sections_that_are_left_out_get_no_bookmark(self):
        document = planhandling.read(self.path, TYPES)
        names = planhandling.bookmark_names(document, {0})
        copy = planhandling.write(document, Path(self.tmp.name) / "en.docx", names)
        self.assertEqual(OWN.findall(document_xml(copy)), [names[0]])

    def test_the_original_is_never_overwritten(self):
        document = planhandling.read(self.path, TYPES)
        with self.assertRaisesRegex(planhandling.DocxError, "annat namn"):
            planhandling.write(document, self.path, planhandling.bookmark_names(document, {0}))

    def test_the_suggested_copy_name_ends_with_bokmarken(self):
        self.assertEqual(planhandling.bookmarked_copy_name(self.path).name, "op_bokmarken.docx")
        self.assertEqual(planhandling.bookmarked_copy_name(self.copy), self.copy)


if __name__ == "__main__":
    unittest.main()
