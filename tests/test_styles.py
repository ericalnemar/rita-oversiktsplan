"""Symboltabellen: varje värde i ÖP-katalogen har en egen symbol som går att skilja från de andra i lagret och att
rita i en webbkarta (ren Python, kräver inte QGIS)."""
import itertools
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rita_oversiktsplan.core import model, opkatalog, styles  # noqa: E402
from rita_oversiktsplan.core.colors import delta_e, delta_e_lab  # noqa: E402


def classified_values(category):
    """Värdena som lagret klassas på: innehållstypen, eller den kompletterande för Utvecklingsinriktning."""
    catalog = opkatalog.bundled()
    if styles.field_for(category.key) == "kompletterandeInnehallstyp":
        lookup = next(lookup for lookup in model.LOOKUPS if lookup.name == category.kompletterande)
    else:
        lookup = next(lookup for lookup in model.LOOKUPS if lookup.name == category.lookup)
    return [v.varde for v in catalog.values(lookup.category, lookup.group, lookup.itself)]


class ColourDifferenceTests(unittest.TestCase):
    def test_identical_colours_have_no_difference(self):
        self.assertAlmostEqual(delta_e((10, 20, 30), (10, 20, 30)), 0.0)

    def test_it_matches_the_ciede2000_reference_data(self):
        # Sharma, Wu & Dalal (2005), "The CIEDE2000 color-difference formula", testdata par 1, 7, 17 och 25.
        reference = [
            ((50.0, 2.6772, -79.7751), (50.0, 0.0, -82.7485), 2.0425),
            ((50.0, 0.0, 0.0), (50.0, -1.0, 2.0), 2.3669),
            ((50.0, 2.5, 0.0), (73.0, 25.0, -18.0), 27.1492),
            ((60.2574, -34.0099, 36.2677), (60.4626, -34.1751, 39.4387), 1.2644),
        ]
        for lab1, lab2, expected in reference:
            self.assertAlmostEqual(delta_e_lab(lab1, lab2), expected, places=4)

    def test_rgb_colours_are_compared_as_seen(self):
        self.assertLess(delta_e((0, 0, 255), (5, 5, 250)), 3)
        self.assertGreater(delta_e((255, 255, 0), (0, 0, 255)), 50)

    def test_it_is_symmetric(self):
        self.assertAlmostEqual(delta_e((200, 30, 40), (30, 200, 40)), delta_e((30, 200, 40), (200, 30, 40)))


class StyleTableTests(unittest.TestCase):
    def test_every_value_in_the_catalog_has_its_own_style(self):
        for category in model.CATEGORIES:
            for value in classified_values(category):
                self.assertIsNotNone(styles.style_for(category.key, value), f"{category.key}: {value}")

    def test_the_table_has_no_values_the_catalog_lacks(self):
        for category in model.CATEGORIES:
            self.assertEqual(set(styles.STYLES[category.key]), set(classified_values(category)), category.key)

    def test_land_uses_are_told_apart_by_colour(self):
        for (x, a), (y, b) in itertools.combinations(styles.MARK_OCH_VATTEN.items(), 2):
            self.assertGreaterEqual(delta_e(a.color, b.color), styles.MIN_DELTA_E_LAND_USE, f"{x} / {y}")

    def test_every_group_has_a_symbol(self):
        self.assertEqual(set(styles.GROUPS), {c.key for c in model.CATEGORIES})

    def test_every_group_has_its_own_edge_and_line(self):
        edges = [(g.dash, g.width, g.hollow) for g in styles.GROUPS.values()]
        self.assertEqual(len(edges), len(set(edges)))
        dashes = [g.dash for g in styles.GROUPS.values()]
        repeated = {d for d in dashes if dashes.count(d) > 1}
        self.assertEqual(repeated, {""}, "bara markanvändningen och riksintressena (kommunens) har heldragen kant")

    def test_every_group_with_points_has_its_own_point_symbol(self):
        with_points = [c.key for c in model.CATEGORIES if not c.polygon_only]
        points = [(styles.GROUPS[k].shape, styles.GROUPS[k].angle, styles.GROUPS[k].hollow, styles.GROUPS[k].ring)
                  for k in with_points]
        self.assertEqual(len(points), len(set(points)))

    def test_values_in_a_group_share_the_symbol_and_differ_only_in_colour(self):
        # symbolen sitter på gruppen; värdet har bara en färg
        self.assertNotIn("pattern", styles.Style.__dataclass_fields__)
        self.assertNotIn("shape", styles.Style.__dataclass_fields__)

    def test_land_and_water_use_borrows_the_detailed_plan_colours_where_they_are_distinct(self):
        for value, style in styles.MARK_OCH_VATTEN.items():
            self.assertTrue(style.filled, value)
            if style.detaljplan:
                self.assertIn(style.color, styles.FARGER.values(), value)
        self.assertEqual(styles.MARK_OCH_VATTEN["Bostadsbebyggelse"].color, styles.FARGER["Gul"])
        self.assertEqual(styles.MARK_OCH_VATTEN["Vatten"].color, styles.FARGER["Blå"])
        self.assertEqual(styles.MARK_OCH_VATTEN["Verksamheter"].color, styles.FARGER["Beige"])

    def test_everything_else_is_an_overlay_without_solid_fill(self):
        for key, table in styles.STYLES.items():
            if key != "markochvattenanvandning":
                for value, style in table.items():
                    self.assertFalse(style.filled, f"{key}: {value}")
        self.assertLess(styles.OVERLAY_ALPHA, 64)  # svag fyllning, markanvändningen syns igenom

    def test_a_national_interest_has_the_same_colour_in_both_layers_but_the_background_one_is_hollow(self):
        self.assertEqual(styles.style_for("riksintressenop", "Naturvård").color,
                         styles.style_for("riksintressen", "Naturvård").color)
        self.assertEqual((styles.GROUPS["riksintressenop"].hollow, styles.GROUPS["riksintressen"].hollow),
                         (False, True))
        self.assertEqual(styles.GROUPS["riksintressenop"].shape, styles.GROUPS["riksintressen"].shape)

    def test_development_direction_is_told_apart_by_its_complementary_value(self):
        self.assertEqual(styles.field_for("utvecklingsinriktning"), "kompletterandeInnehallstyp")
        self.assertEqual(styles.field_for("markochvattenanvandning"), "innehallstyp_varde")

    def test_point_shapes_come_from_the_sld_standard(self):
        for key, group in styles.GROUPS.items():
            self.assertIn(group.shape, ("circle", "square", "triangle", "star", "cross"), key)
            self.assertIn(group.angle, (0, 45, 180), key)

    def test_dash_patterns_are_valid_lengths(self):
        for key, group in styles.GROUPS.items():
            if group.dash:
                parts = [float(p) for p in group.dash.split(";")]
                self.assertEqual(len(parts) % 2, 0, key)
                self.assertTrue(all(p > 0 for p in parts), key)

    def test_every_group_symbol_is_described_for_the_documentation(self):
        for key, group in styles.GROUPS.items():
            self.assertTrue(group.label, key)


if __name__ == "__main__":
    unittest.main()
