"""Märket och identiteten: ikonen är giltig SVG, bannrarna har texten som konturer och README pekar på riktiga bilder.
Rena filkontroller, kräver inte QGIS."""
import re
import struct
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SVG = "{http://www.w3.org/2000/svg}"
IMAGES = ROOT / "docs" / "images"


class BrandFilesTests(unittest.TestCase):
    def test_the_plugin_icon_is_valid_svg_with_the_mark(self):
        root = ET.parse(ROOT / "rita_oversiktsplan" / "icon.svg").getroot()
        self.assertEqual(root.tag, SVG + "svg")
        self.assertIsNotNone(root.find(f".//{SVG}polyline"))  # märkets linje
        self.assertEqual(root.get("aria-label"), "Rita Översiktsplan")

    def test_the_icon_is_the_suites_o_mark(self):
        self.assertEqual((ROOT / "rita_oversiktsplan" / "icon.svg").read_bytes(),
                         (IMAGES / "marken" / "rita-oversiktsplan.svg").read_bytes())

    def test_the_suites_three_marks_are_valid_svg(self):
        for name in ("rita.svg", "rita-detaljplan.svg", "rita-oversiktsplan.svg"):
            self.assertEqual(ET.parse(IMAGES / "marken" / name).getroot().tag, SVG + "svg", name)

    def test_the_banners_have_their_text_as_outlines_so_no_font_is_needed(self):
        for name in ("banner-mork.svg", "banner-ljus.svg"):
            root = ET.parse(IMAGES / name).getroot()
            self.assertEqual(root.get("viewBox"), "0 0 1280 640", name)
            self.assertIsNone(root.find(f".//{SVG}text"), name)
            self.assertGreaterEqual(len(root.findall(f".//{SVG}path")), 2, name)

    def test_the_social_preview_is_a_1280_by_640_png(self):
        data = (IMAGES / "social-preview.png").read_bytes()
        self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(struct.unpack(">II", data[16:24]), (1280, 640))

    def test_the_readme_shows_images_that_exist(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        shown = re.findall(r'(?:src|srcset)="(docs/images/[^"]+)"', readme)
        self.assertTrue(shown, "README ska visa bannern")
        for name in shown:
            self.assertTrue((ROOT / name).exists(), name)


if __name__ == "__main__":
    unittest.main()
