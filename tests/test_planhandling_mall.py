"""Utkastet till planhandling med hela ÖP-katalogen (tools/skapa_planhandling_mall.py). Ren Python."""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import skapa_planhandling_mall as mall  # noqa: E402

from rita_oversiktsplan.core import opkatalog, planhandling  # noqa: E402

CONTENT = ("Utvecklingsinriktning", "Mark- och vattenanvändning", "Kompletterande mark- och vattenanvändning",
           "Riksintresse kommunens ställningstagande", "Miljökvalitetsnormer enligt 5 kap. MB", "Klimatrelaterade risker",
           "Mål, planer och program", "Konsekvenser", "Invändningar i länsstyrelsens granskningsyttrande",
           "Underlagstyp")


class TemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.catalog = opkatalog.bundled()
        cls.types = [v.varde for v in cls.catalog.values("Avsnittstyp")]
        cls.path = mall.write(Path(cls.tmp.name) / "mall.docx", cls.catalog)
        cls.document = planhandling.read(cls.path, cls.types)
        cls.headings = {s.heading for s in cls.document.sections}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_every_value_in_the_catalogs_content_categories_has_a_heading(self):
        for category in CONTENT:
            for value in self.catalog.values(category):
                self.assertIn(value.varde, self.headings, category)

    def test_the_text_parts_without_values_have_a_chapter(self):
        for heading in ("Sammanfattning", "Översiktsplanens syfte", "Bostadsförsörjning", "Särskilt värdefull kulturmiljö",
                        "Övriga förhållanden av väsentlig betydelse", "Mellankommunala och regionala intressen",
                        "Avvikelse från regionplan", "Framtagandeprocess", "Övrig information"):
            self.assertIn(heading, self.headings)

    def test_tagga_planhandling_suggests_the_intended_section_types(self):
        by_heading = {}
        for section in self.document.sections:
            by_heading.setdefault(section.heading, section.suggested_type)
        self.assertEqual(by_heading["Sammanfattning"], "Sammanfattning")
        self.assertEqual(by_heading["Ställningstaganden"], "Ställningstagande")
        self.assertEqual(by_heading["Övriga förhållanden av väsentlig betydelse"], "Beskrivning")
        self.assertEqual(by_heading["Kommentar på länsstyrelsens invändning"], "Kommentar på länsstyrelsens invändning")
        self.assertEqual(by_heading["Miljökonsekvenser"], "Konsekvens")
        every_type = {s.suggested_type for s in self.document.sections}
        self.assertEqual(every_type, set(self.types))  # alla avsnittstyper förekommer

    def test_headings_use_three_levels(self):
        self.assertEqual({s.level for s in self.document.sections}, {1, 2, 3})


if __name__ == "__main__":
    unittest.main()
