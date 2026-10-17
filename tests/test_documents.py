"""Planhandlingen i en riktig plan: kopplingarna i dokumenttabellerna och innehåll utan geometri. Programmet Skapa
bokmärken i planhandling testas i test_bookmarks.py."""
import datetime
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from qgis_app import get_app  # noqa: E402

get_app()

from docx_case import write_docx  # noqa: E402
from qgis.core import QgsFeature, QgsGeometry, QgsProject  # noqa: E402

from rita_oversiktsplan.core import content, documents, geopackage, model, planhandling  # noqa: E402
from rita_oversiktsplan.core.project import active_plan_group, load_plan  # noqa: E402

PLAN = geopackage.NewPlan("0484", "Eskilstuna", "ÖP 2040", datetime.date(2027, 1, 1))


class DocumentCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.path = geopackage.create_geopackage(Path(self.tmp.name) / "op.gpkg", PLAN)
        self.layers = load_plan(self.path, QgsProject.instance())
        self.addCleanup(self._clear)
        self.group = active_plan_group(QgsProject.instance())
        self.docx = write_docx(Path(self.tmp.name) / "planhandling.docx")
        self.messages = []

    def _clear(self):
        for layer in self.layers.values():
            if layer.isEditable():
                layer.rollBack()
        QgsProject.instance().clear()

    def add_content(self, table="innehall_op_klimatrelateradrisk_polygon", value="Risk för översvämning"):
        layer = self.layers[table]
        layer.startEditing()
        feature = QgsFeature(layer.fields())
        feature.setGeometry(QgsGeometry.fromWkt("MULTIPOLYGON(((0 0, 10 0, 10 10, 0 10, 0 0)))"))
        feature["objektidentitet"] = "11111111-2222-3333-4444-555555555555"
        feature["innehallstyp_varde"] = value
        layer.addFeature(feature)
        self.assertTrue(layer.commitChanges())
        return layer


class LinkTests(DocumentCase):
    def test_links_are_saved_in_boverkets_tables_and_read_back(self):
        self.add_content()
        plan = documents.plan_identity(self.group)
        sections = [documents.SectionLinks("op_a", "Klimatrisker", "Ställningstagande",
                                           {"11111111-2222-3333-4444-555555555555"}),
                    documents.SectionLinks("op_b", "Sammanfattning", "Sammanfattning", {plan})]
        doc_id = documents.save(self.group, self.docx, sections)
        self.assertEqual(self.layers["dokumentreferens_op"].featureCount(), 1)
        self.assertEqual(self.layers["dokumentavsnitt"].featureCount(), 2)
        self.assertEqual(self.layers["avsnittsbokmärke"].featureCount(), 2)
        row = next(f for f in self.layers["dokumentavsnitt"].getFeatures() if f["avsnittsbokmarke_id"] == "op_a")
        self.assertEqual((row["avsnittstyp_varde"], row["dokumentreferens_id"], row["objektidentitet"]),
                         ("Ställningstagande", doc_id, "11111111-2222-3333-4444-555555555555"))
        risk = next(self.layers["innehall_op_klimatrelateradrisk_polygon"].getFeatures())
        self.assertEqual(risk["dokument_id"], "11111111-2222-3333-4444-555555555555")
        links = documents.read_links(self.group, self.docx)
        self.assertEqual(links["op_b"].identities, {plan})
        self.assertEqual(links["op_a"].type, "Ställningstagande")

    def test_saving_again_replaces_the_links_for_the_document(self):
        documents.save(self.group, self.docx, [documents.SectionLinks("op_a", "A", "Beskrivning",
                                                                     {documents.plan_identity(self.group)})])
        documents.save(self.group, self.docx, [documents.SectionLinks("op_b", "B", "Beskrivning",
                                                                     {documents.plan_identity(self.group)})])
        self.assertEqual(self.layers["dokumentreferens_op"].featureCount(), 1)
        self.assertEqual([f["avsnittsbokmarke_id"] for f in self.layers["dokumentavsnitt"].getFeatures()], ["op_b"])

    def test_objects_are_described_for_the_list(self):
        self.add_content()
        self.assertEqual(documents.describe(self.group, "11111111-2222-3333-4444-555555555555"),
                         "Klimatrelaterade risker: Risk för översvämning")
        self.assertEqual(documents.describe(self.group, documents.plan_identity(self.group)), "Hela planen")

    def test_content_without_geometry_is_stored_in_the_groups_area_layer(self):
        category = next(c for c in model.CATEGORIES if c.key == "bostadsforsorjning")
        identity = content.create_without_geometry(
            self.group, content.Assignment(category, {"innehallstyp_varde": "Bostadsförsörjning"}))
        layer = self.layers["innehall_op_bostadsforsorjning_polygon"]
        feature = next(layer.getFeatures())
        self.assertEqual(str(feature["objektidentitet"]), identity)
        self.assertFalse(feature.hasGeometry())
        self.assertTrue(feature["illustrativa_granser"])
        self.assertIn("(utan geometri)", documents.describe(self.group, identity))

    def test_land_use_cannot_be_content_without_geometry(self):
        keys = [c.key for c in model.categories_for(model.NO_GEOMETRY)]
        self.assertNotIn("markochvattenanvandning", keys)
        self.assertNotIn("plangeometri", keys)
        self.assertIn("bostadsforsorjning", keys)


if __name__ == "__main__":
    unittest.main()
