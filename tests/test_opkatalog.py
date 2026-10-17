"""ÖP-katalogen och datamodellen (ren Python, kräver inte QGIS)."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rita_oversiktsplan.core import model, opkatalog  # noqa: E402

UUID = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.catalog = opkatalog.bundled()

    def test_the_bundled_catalog_is_version_2_2_with_its_source(self):
        self.assertEqual(self.catalog.version, "2.2")
        self.assertIn("CC0", self.catalog.data["kalla"])

    def test_values_carry_name_id_group_and_group_id_like_the_specification(self):
        value = self.catalog.find("Mark- och vattenanvändning", "Bostadsbebyggelse")
        self.assertEqual(value.grupp, "Mark- och vattenanvändning")
        self.assertRegex(value.vardereferens, UUID)
        self.assertRegex(value.gruppreferens, UUID)
        self.assertTrue(value.beskrivning)

    def test_a_category_without_values_below_it_is_its_own_value(self):
        (lis,) = self.catalog.values("LIS")
        self.assertEqual((lis.varde, lis.grupp), ("LIS", "LIS"))

    def test_utvecklingsinriktning_is_itself_the_value_and_its_children_are_the_complementary_ones(self):
        (value,) = self.catalog.values("Utvecklingsinriktning", itself=True)
        self.assertEqual(value.varde, "Utvecklingsinriktning")
        complementary = {v.varde for v in self.catalog.values("Utvecklingsinriktning")}
        self.assertIn("Grön- och blåstruktur", complementary)

    def test_the_national_interests_under_the_environmental_code_get_their_own_group(self):
        value = self.catalog.find("Riksintresse kommunens ställningstagande", "Friluftsliv",
                                  group="Riksintressen enligt 3 och 4 kap. MB")
        own = self.catalog.find("Riksintresse kommunens ställningstagande", "Friluftsliv")
        self.assertEqual(value.vardereferens, own.vardereferens)
        self.assertEqual(value.grupp, "Riksintressen enligt 3 och 4 kap. MB")
        self.assertNotEqual(value.gruppreferens, own.gruppreferens)

    def test_values_have_no_stray_whitespace(self):
        for lookup in model.LOOKUPS:
            for value in self.catalog.values(lookup.category, lookup.group, lookup.itself):
                self.assertEqual(value.varde, value.varde.strip(), lookup.name)

    def test_an_unknown_category_is_named_in_the_error(self):
        with self.assertRaisesRegex(KeyError, "Finns inte"):
            self.catalog.values("Finns inte")


class ModelTests(unittest.TestCase):
    def test_every_content_type_has_three_geometry_layers_except_area_and_plan_geometry(self):
        names = {layer.name for layer in model.CONTENT_LAYERS}
        self.assertIn("innehall_op_markochvattenanvandning_polygon", names)
        self.assertIn("innehall_op_markochvattenanvandning_line", names)
        self.assertIn("innehall_op_markochvattenanvandning_point", names)
        self.assertIn("innehall_op_omrade", names)
        self.assertIn("innehall_op_plangeometri", names)
        self.assertEqual(len(model.CONTENT_LAYERS), 15 * 3 + 2)

    def test_every_lookup_used_by_a_field_exists_and_can_be_filled_from_the_catalog(self):
        lookups = {lookup.name: lookup for lookup in model.LOOKUPS}
        catalog = opkatalog.bundled()
        for layer in model.LAYERS:
            for field in layer.fields:
                if field.lookup:
                    self.assertIn(field.lookup, lookups, f"{layer.name}.{field.name}")
        for lookup in model.LOOKUPS:
            self.assertTrue(catalog.values(lookup.category, lookup.group, lookup.itself), lookup.name)

    def test_content_layers_have_the_columns_of_boverkets_model(self):
        columns = [f.name for f in model.layer("innehall_op_markochvattenanvandning_polygon").fields]
        for name in ("objektidentitet", "innehallstyp_varde", "kompletterandeInnehallstyp", "planhandelse_varde",
                     "illustrativa_granser", "under_ersattning", "utbyggnadsordning"):
            self.assertIn(name, columns)
        self.assertNotIn("anvandningsstatus", columns)  # borttagen ur ÖP-katalogen 2.0

    def test_the_plan_table_also_has_the_municipality_name_the_specification_requires(self):
        self.assertIn("kommunnamn", [f.name for f in model.OVERSIKTSPLAN.fields])

    def test_table_names_are_unique(self):
        names = [layer.name for layer in model.LAYERS] + [lookup.name for lookup in model.LOOKUPS]
        self.assertEqual(len(names), len(set(names)))


if __name__ == "__main__":
    unittest.main()
