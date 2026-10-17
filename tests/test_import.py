"""Importera geometri: från ett annat lager till Att tilldela, utan attribut."""
import datetime
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from qgis_app import get_app  # noqa: E402

get_app()

from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer  # noqa: E402

from rita_oversiktsplan import classFactory  # noqa: E402
from rita_oversiktsplan.core import geopackage, importer  # noqa: E402
from rita_oversiktsplan.core.project import active_plan_group, draft_layers, load_plan  # noqa: E402
from rita_oversiktsplan.gui.import_dialog import ImportDialog  # noqa: E402
from test_plugin import FakeIface  # noqa: E402

PLAN = geopackage.NewPlan("0484", "Eskilstuna", "ÖP 2040", datetime.date(2027, 1, 1))


def memory_layer(kind: str, wkts: list[str], crs: str = "EPSG:3006", name: str = "källa") -> QgsVectorLayer:
    layer = QgsVectorLayer(f"{kind}?crs={crs}&field=namn:string&field=yta:double", name, "memory")
    features = []
    for n, wkt in enumerate(wkts):
        feature = QgsFeature(layer.fields())
        feature.setAttributes([f"objekt {n}", 12.5])
        feature.setGeometry(QgsGeometry.fromWkt(wkt))
        features.append(feature)
    layer.dataProvider().addFeatures(features)
    layer.updateExtents()
    return layer


class ImportCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.path = geopackage.create_geopackage(Path(self.tmp.name) / "op.gpkg", PLAN)
        self.layers = load_plan(self.path, QgsProject.instance())
        self.addCleanup(self._clear)
        self.group = active_plan_group(QgsProject.instance())
        self.targets = draft_layers(self.group)

    def _clear(self):
        for layer in self.layers.values():
            if layer.isEditable():
                layer.rollBack()
        QgsProject.instance().clear()

    def features(self, kind):
        return list(self.targets[kind].getFeatures())


class ImporterTests(ImportCase):
    def test_polygons_lines_and_points_go_to_their_own_layer_without_attributes(self):
        polygons = memory_layer("MultiPolygon", ["MULTIPOLYGON(((0 0, 10 0, 10 10, 0 10, 0 0)))",
                                                 "POLYGON((20 0, 30 0, 30 10, 20 0))"])
        lines = memory_layer("LineString", ["LINESTRING(0 0, 5 5)"])
        points = memory_layer("MultiPoint", ["MULTIPOINT((1 1), (2 2))"])
        for source in (polygons, lines, points):
            importer.import_geometries(source, self.targets)
        self.assertEqual((len(self.features("polygon")), len(self.features("line")), len(self.features("point"))),
                         (2, 1, 2))  # multipunkten blir två punkter
        feature = self.features("polygon")[0]
        self.assertNotIn("namn", feature.fields().names())
        self.assertIsNotNone(feature["skapad"])  # lagrets eget standardvärde
        self.assertEqual(feature.geometry().asWkt(0), "MultiPolygon (((0 0, 10 0, 10 10, 0 10, 0 0)))")
        self.assertTrue(self.targets["polygon"].isEditable())  # i redigeringsbufferten, sparas med Spara

    def test_geometry_is_transformed_to_sweref_99_tm(self):
        source = memory_layer("Point", ["POINT(16.5 59.37)"], "EPSG:4326")  # Eskilstuna
        importer.import_geometries(source, self.targets)
        point = self.features("point")[0].geometry().asPoint()
        self.assertAlmostEqual(point.x(), 584000, delta=5000)
        self.assertAlmostEqual(point.y(), 6582000, delta=5000)

    def test_curves_z_and_m_values_and_collections_are_cleaned(self):
        collection = memory_layer("GeometryCollectionZ", [
            "GEOMETRYCOLLECTION Z (POLYGON Z ((0 0 5, 10 0 5, 10 10 5, 0 0 5)), LINESTRING Z (0 0 1, 4 4 1))"])
        curve = memory_layer("CircularString", ["CIRCULARSTRING(0 0, 1 1, 2 0)"])
        first = importer.import_geometries(collection, self.targets)
        second = importer.import_geometries(curve, self.targets)
        self.assertEqual((first.counts, second.counts["line"]), ({"polygon": 1, "line": 1, "point": 0}, 1))
        self.assertGreater(len(self.features("line")[1].geometry().asMultiPolyline()[0]), 3)  # bågen är uppdelad i segment
        for feature in self.features("polygon") + self.features("line"):
            wkt = feature.geometry().asWkt()
            self.assertNotIn(" Z", wkt)
            self.assertNotIn("Curve", wkt)
            self.assertNotIn("Circular", wkt)

    def test_only_selected_features_and_empty_geometries_are_counted(self):
        source = memory_layer("Polygon", ["POLYGON((0 0, 1 0, 1 1, 0 0))", "POLYGON((5 5, 6 5, 6 6, 5 5))", ""])
        ids = [f.id() for f in source.getFeatures()]
        source.selectByIds(ids[1:])
        result = importer.import_geometries(source, self.targets, selected_only=True)
        self.assertEqual((result.counts["polygon"], result.skipped), (1, 1))
        self.assertIn("1 yta", result.text())

    def test_invalid_geometries_are_imported_but_reported(self):
        source = memory_layer("Polygon", ["POLYGON((0 0, 10 10, 10 0, 0 10, 0 0))"])  # rosett
        result = importer.import_geometries(source, self.targets)
        self.assertEqual((result.counts["polygon"], result.invalid), (1, 1))
        self.assertIn("ogiltiga", result.text())

    def test_import_can_be_undone(self):
        importer.import_geometries(memory_layer("Point", ["POINT(1 1)", "POINT(2 2)"]), self.targets)
        self.targets["point"].undoStack().undo()
        self.assertEqual(self.features("point"), [])


class DialogAndPluginTests(ImportCase):
    def setUp(self):
        super().setUp()
        self.iface = FakeIface()
        self.plugin = classFactory(self.iface)
        self.plugin.initGui()
        self.addCleanup(self.plugin.unload)
        self.source = memory_layer("Polygon", ["POLYGON((0 0, 1 0, 1 1, 0 0))"], "EPSG:4326", "Gamla ÖP")
        QgsProject.instance().addMapLayer(self.source)

    def test_the_dialog_lists_other_layers_and_explains_the_transformation(self):
        own = [node.layer() for node in self.group.findLayers()]
        dialog = ImportDialog(self.iface, own)
        self.addCleanup(dialog.release)
        dialog.layer.setLayer(self.source)
        self.assertIn("1 objekt (ytor)", dialog.summary.text())
        self.assertIn("EPSG:3006", dialog.summary.text())
        self.assertFalse(dialog.selected_only.isEnabled())  # inget markerat
        layers = [dialog.layer.layer(n) for n in range(dialog.layer.count())]
        self.assertIn(self.source, layers)
        self.assertNotIn(self.targets["polygon"], layers)  # planens egna lager kan inte väljas

    def test_a_layer_added_while_the_dialog_is_open_is_chosen(self):
        dialog = ImportDialog(self.iface, [])
        self.addCleanup(dialog.release)
        added = memory_layer("Point", ["POINT(1 1)"], name="Ny källa")
        QgsProject.instance().addMapLayer(added)
        self.assertIs(dialog.source(), added)

    def test_the_toolbar_button_imports_into_att_tilldela(self):
        def choose(dialog):
            dialog.layer.setLayer(self.source)
            return True

        with mock.patch.object(ImportDialog, "exec", new=choose):
            result = self.plugin.import_geometry()
        self.assertEqual(result.counts["polygon"], 1)
        self.assertEqual(len(self.features("polygon")), 1)
        self.assertIn("1 yta importerades", self.iface.bar.pushMessage.call_args[0][1])

    def test_cancel_imports_nothing(self):
        with mock.patch.object(ImportDialog, "exec", return_value=False):
            self.assertIsNone(self.plugin.import_geometry())
        self.assertEqual(self.features("polygon"), [])


if __name__ == "__main__":
    unittest.main()
