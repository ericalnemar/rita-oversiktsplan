"""Pennan, Markera, Avmarkera alla, Kopiera innehåll och Leverans och export, med en riktig plan i kartan."""
import datetime
import json
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

from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsProject, QgsRectangle  # noqa: E402
from qgis.PyQt.QtCore import QDate  # noqa: E402
from qgis.PyQt.QtWidgets import QMessageBox  # noqa: E402

from rita_oversiktsplan import classFactory  # noqa: E402
from rita_oversiktsplan.core import content, documents, editing, export_lm, geopackage, model  # noqa: E402
from rita_oversiktsplan.core.project import active_plan_group, draft_layers, load_plan  # noqa: E402
from rita_oversiktsplan.gui.export_dialog import ExportDialog  # noqa: E402
from test_plugin import FakeIface  # noqa: E402

PLAN = geopackage.NewPlan("0484", "Eskilstuna", "ÖP 2040", datetime.date(2027, 1, 1))
SQUARE = "MULTIPOLYGON(((0 0, 100 0, 100 100, 0 100, 0 0)))"
OTHER = "MULTIPOLYGON(((200 0, 300 0, 300 100, 200 100, 200 0)))"
LAND_USE = next(c for c in model.CATEGORIES if c.key == "markochvattenanvandning")
RISK = next(c for c in model.CATEGORIES if c.key == "klimatrelateradrisk")


class ToolCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.iface = FakeIface()
        self.plugin = classFactory(self.iface)
        self.plugin.initGui()
        self.addCleanup(self.plugin.unload)
        self.path = geopackage.create_geopackage(Path(self.tmp.name) / "op.gpkg", PLAN)
        self.layers = load_plan(self.path, QgsProject.instance())
        self.addCleanup(self._clear)
        self.group = active_plan_group(QgsProject.instance())

    def _clear(self):
        for layer in self.layers.values():
            if layer.isEditable():
                layer.rollBack()
        QgsProject.instance().clear()

    def draft(self, wkt=SQUARE, suffix="polygon"):
        layer = draft_layers(self.group)[suffix]
        layer.startEditing()
        feature = QgsFeature(layer.fields())
        feature.setGeometry(QgsGeometry.fromWkt(wkt))
        layer.addFeature(feature)
        self.assertTrue(layer.commitChanges())
        return content.Candidate(layer, next(layer.getFeatures()).id() if layer.featureCount() == 1 else
                                 max(f.id() for f in layer.getFeatures()), suffix, None)

    def assigned(self, wkt=SQUARE, category=LAND_USE, values=None):
        candidate = self.draft(wkt)
        layer, fid = content.assign(self.group, candidate, content.Assignment(
            category, values or {"innehallstyp_varde": "Bostadsbebyggelse", "namn": "Norr"}))
        return content.Candidate(layer, fid, "polygon", category)


class PenTests(ToolCase):
    def test_the_pen_opens_all_plan_layers_and_stopping_saves(self):
        self.assertTrue(self.plugin.start_editing())
        self.assertTrue(all(layer.isEditable() for layer in editing.plan_layers(self.group)))
        candidate = self.draft()
        candidate.layer.startEditing()
        candidate.layer.changeGeometry(candidate.fid, QgsGeometry.fromWkt(OTHER))
        with mock.patch.object(type(self.plugin), "_ask_save", return_value=QMessageBox.StandardButton.Save):
            self.assertTrue(self.plugin.stop_editing())
        self.assertFalse(editing.is_editing(self.group))
        self.assertEqual(next(candidate.layer.getFeatures()).geometry().boundingBox().xMinimum(), 200)

    def test_stopping_can_discard_or_be_cancelled(self):
        self.plugin.start_editing()
        layer = draft_layers(self.group)["point"]
        feature = QgsFeature(layer.fields())
        feature.setGeometry(QgsGeometry.fromWkt("POINT(1 1)"))
        layer.addFeature(feature)
        with mock.patch.object(type(self.plugin), "_ask_save", return_value=QMessageBox.StandardButton.Cancel):
            self.assertFalse(self.plugin.stop_editing())
        self.assertTrue(layer.isEditable())
        with mock.patch.object(type(self.plugin), "_ask_save", return_value=QMessageBox.StandardButton.Discard):
            self.plugin.stop_editing()
        self.assertEqual(layer.featureCount(), 0)

    def test_stopping_without_editing_says_so(self):
        self.assertFalse(self.plugin.stop_editing())
        self.assertIn("Ingen redigering", self.iface.bar.pushMessage.call_args[0][1])


class IdentityTests(ToolCase):
    def test_assigned_content_has_a_visible_read_only_uuid(self):
        housing = next(c for c in model.CATEGORIES if c.key == "bostadsforsorjning")
        candidate = self.assigned(category=housing, values={"innehallstyp_varde": "Bostadsförsörjning"})
        layer = candidate.layer
        identity = str(layer.getFeature(candidate.fid)["objektidentitet"])
        self.assertRegex(identity, r"^\{?[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\}?$")
        idx = layer.fields().indexOf("objektidentitet")
        self.assertEqual(layer.editorWidgetSetup(idx).type(), "TextEdit")  # syns i formulär och attributtabell
        self.assertTrue(layer.editFormConfig().readOnly(idx))


class PlanDateTests(ToolCase):
    def test_new_content_gets_the_plans_start_date(self):
        candidate = self.assigned()
        value = candidate.layer.getFeature(candidate.fid)["datum_paborjat"]
        self.assertEqual(value.toPyDate() if hasattr(value, "toPyDate") else value, datetime.date(2027, 1, 1))

    def test_the_plan_tab_has_no_digitisation_and_the_defaults_no_second_start_date(self):
        from rita_oversiktsplan.gui.plan_info_dialog import PlanInfoDialog
        dialog = PlanInfoDialog(content.read_plan_info(self.group), ["Samrådsunderlag färdigställt"])
        self.addCleanup(dialog.deleteLater)
        for name in ("digital", "beskrivning", "innehall_paborjat"):
            self.assertFalse(hasattr(dialog, name), name)
        info = dialog.plan_info()
        self.assertTrue(info.digitalt_ursprung)  # planens värde behålls


class GreyedTests(ToolCase):
    def test_tools_that_need_an_editing_session_are_grey_until_the_pen_is_used(self):
        toolbar = self.plugin.toolbar
        self.plugin.refresh_tools()
        self.assertTrue(toolbar.act_start.isEnabled())
        self.assertTrue(toolbar.act_info.isEnabled())
        self.assertTrue(toolbar.act_select.isEnabled())
        for action in (toolbar.act_stop, toolbar.act_draw["polygon"], toolbar.act_import, toolbar.act_assign,
                       toolbar.act_copy, toolbar.act_relate):
            self.assertFalse(action.isEnabled(), action.text())
        self.plugin.start_editing()  # lagrens editingStarted uppdaterar knapparna
        self.assertTrue(toolbar.act_draw["polygon"].isEnabled())
        self.assertTrue(toolbar.act_stop.isEnabled())
        self.assertFalse(toolbar.act_start.isEnabled())
        self.plugin.toolbar.act_assign.setChecked(True)
        with mock.patch.object(type(self.plugin), "_ask_save", return_value=QMessageBox.StandardButton.Discard):
            self.plugin.stop_editing()
        self.assertFalse(toolbar.act_draw["polygon"].isEnabled())
        self.assertFalse(toolbar.act_assign.isChecked())



class NoPlanTests(unittest.TestCase):
    def test_without_a_plan_only_new_and_open_work(self):
        QgsProject.instance().clear()
        iface = FakeIface()
        plugin = classFactory(iface)
        plugin.initGui()
        self.addCleanup(plugin.unload)
        enabled = [a.text() for a in plugin.toolbar.actions() if not a.isSeparator() and a.isEnabled()]
        self.assertEqual(enabled, ["Ny översiktsplan…", "Öppna översiktsplan…"])


class SelectTests(ToolCase):
    def test_a_click_selects_and_makes_the_layer_active(self):
        candidate = self.assigned()
        chosen = self.plugin.select_at(QgsPointXY(50, 50), 1)
        self.assertEqual((chosen.layer, chosen.fid), (candidate.layer, candidate.fid))
        self.assertEqual(candidate.layer.selectedFeatureIds(), [candidate.fid])
        self.assertIs(self.iface.active, candidate.layer)

    def test_a_rectangle_selects_everything_it_touches_and_deselect_clears(self):
        self.assigned()
        self.draft(OTHER)
        count = self.plugin.select_rect(QgsRectangle(-10, -10, 400, 400))
        self.assertEqual(count, 2)
        self.plugin.deselect_all()
        self.assertEqual(editing.selected_count(self.group), 0)

    def test_the_select_button_switches_tools(self):
        self.plugin.toolbar.act_select.setChecked(True)
        self.assertIs(self.iface.canvas.mapTool(), self.plugin.map_tools["select"])
        self.plugin.toolbar.act_assign.setChecked(True)
        self.assertFalse(self.plugin.toolbar.act_select.isChecked())


class CopyTests(ToolCase):
    def test_content_is_copied_to_an_unassigned_object_without_the_name(self):
        self.assigned(values={"innehallstyp_varde": "Bostadsbebyggelse", "namn": "Norr",
                              "kompletterandeInnehallstyp": "Skola"})
        self.draft(OTHER)
        self.assertFalse(self.plugin.copy_at(QgsPointXY(50, 50), 1))  # väljer källan
        self.assertTrue(self.plugin.copy_at(QgsPointXY(250, 50), 1))
        layer = self.layers["innehall_op_markochvattenanvandning_polygon"]
        copied = [f for f in layer.getFeatures() if f.geometry().boundingBox().xMinimum() == 200]
        self.assertEqual(len(copied), 1)
        self.assertEqual((copied[0]["innehallstyp_varde"], copied[0]["kompletterandeInnehallstyp"]),
                         ("Bostadsbebyggelse", "Skola"))
        self.assertIn(copied[0]["namn"], (None, ""))  # namnet hör till objektet
        self.assertEqual(draft_layers(self.group)["polygon"].featureCount(), 0)

    def test_assigned_content_changes_type_and_keeps_its_identity(self):
        self.assigned()
        other = self.assigned(OTHER, RISK, {"innehallstyp_varde": "Risk för ras"})
        identity = other.layer.getFeature(other.fid)["objektidentitet"]
        self.plugin.copy_at(QgsPointXY(50, 50), 1)
        self.assertTrue(self.plugin.copy_at(QgsPointXY(250, 50), 1))
        layer = self.layers["innehall_op_markochvattenanvandning_polygon"]
        moved = next(f for f in layer.getFeatures() if f["objektidentitet"] == identity)
        self.assertEqual(moved["innehallstyp_varde"], "Bostadsbebyggelse")

    def test_the_source_must_have_content(self):
        self.draft()
        self.assertFalse(self.plugin.copy_at(QgsPointXY(50, 50), 1))
        self.assertIsNone(self.plugin.copy_source)
        self.assertIn("innehåll att kopiera", self.iface.bar.pushMessage.call_args[0][1])


class ExportTests(ToolCase):
    def complete_plan(self):
        plan = self.layers["oversiktsplan"]
        plan.startEditing()
        feature = next(plan.getFeatures())
        for name, value in (("planhandelse_varde", "Samrådsunderlag färdigställt"),
                            ("planhandelse_datum", QDate(2027, 3, 1))):
            plan.changeAttributeValue(feature.id(), plan.fields().indexOf(name), value)
        self.assertTrue(plan.commitChanges())
        candidate = self.assigned()
        layer = candidate.layer
        for name, value in (("planhandelse_varde", "Samrådsunderlag färdigställt"),
                            ("planhandelse_datum", QDate(2027, 3, 1))):
            layer.changeAttributeValue(candidate.fid, layer.fields().indexOf(name), value)
        self.assertTrue(layer.commitChanges(False))
        return candidate

    def test_the_collection_has_lantmateriets_structure(self):
        candidate = self.complete_plan()
        identity = str(next(candidate.layer.getFeatures())["objektidentitet"])
        docx = Path(self.tmp.name) / "planhandling.docx"
        docx.write_bytes(b"")
        documents.save(self.group, docx, [documents.SectionLinks("op_abc", "Bostäder", "Ställningstagande",
                                                                 {identity})])
        collection, problems = export_lm.export(self.group)
        self.assertEqual(collection["feature:mediatyp"], "application/vnd.lm.oversiktsplan.v2+json")
        plan, content_feature = collection["features"][0], collection["features"][-1]
        self.assertIsNone(plan["geometry"])
        props = plan["properties"]
        self.assertEqual((props["feature:typ"], props["kommunkod"], props["kommunnamn"]),
                         ("oversiktsplan", "0484", "Eskilstuna"))
        self.assertEqual(set(props["planhandelse"]), {"varde", "vardereferens", "grupp", "gruppreferens"})
        self.assertRegex(props["versionGiltigFran"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d\d:\d\d$")
        item = content_feature["properties"]
        self.assertEqual(item["feature:typ"], "innehallOP")
        self.assertEqual(item["oversiktsplan"], props["objektidentitet"])
        self.assertEqual(item["innehallstyp"]["varde"], "Bostadsbebyggelse")
        self.assertEqual(item["innehallstyp"]["grupp"], "Mark- och vattenanvändning")
        self.assertTrue(item["illustrativaGranser"])
        self.assertEqual(item["geometri"]["typ"], "yta")
        self.assertEqual(item["geometri"]["koordinatsystemPlan"], "EPSG:3006")
        ring = item["geometri"]["position"]["coordinates"][0]
        self.assertGreater(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(ring, ring[1:])), 0)  # moturs
        self.assertEqual(item["dokument"][0]["avsnittsbokmarke"], ["op_abc"])
        self.assertEqual(item["dokument"][0]["avsnittstyp"]["varde"], "Ställningstagande")
        self.assertEqual(item["dokument"][0]["dokument"]["namn"], "planhandling.docx")
        self.assertNotIn("namn", {k for k, v in item.items() if v == ""})  # tomma fält utelämnas
        json.dumps(collection)  # går att skriva
        self.assertTrue(any(p.level == export_lm.FEL and "underlag" in p.text for p in problems))  # inget verktyg än

    def test_missing_required_values_are_reported_with_the_object(self):
        candidate = self.assigned()
        _, problems = export_lm.export(self.group)
        texts = " ".join(p.text for p in problems)
        self.assertIn("Planhändelsen saknas", texts)
        self.assertIn("underlag", texts)
        own = [p for p in problems if p.layer == "innehall_op_markochvattenanvandning_polygon"]
        self.assertTrue(own)
        self.assertEqual(own[0].fid, candidate.fid)

    def test_unassigned_objects_are_left_out_with_a_warning(self):
        self.draft()
        collection, problems = export_lm.export(self.group)
        self.assertEqual(export_lm.counts(collection), {"oversiktsplan": 1})
        self.assertTrue(any("Att tilldela" in p.text for p in problems))

    def test_the_export_button_saves_the_json(self):
        self.complete_plan()
        target = Path(self.tmp.name) / "op.json"

        def run(dialog):
            self.assertIn("1 innehåll", dialog.summary.text())
            dialog.save()
            return 0

        with mock.patch.object(type(self.plugin), "_ask_export_path", return_value=str(target)), \
                mock.patch.object(ExportDialog, "exec", new=run):
            self.plugin.export_plan()
        saved = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(len(saved["features"]), 2)


if __name__ == "__main__":
    unittest.main()
