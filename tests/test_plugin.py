"""Pluginet i QGIS: meny och verktygsfält, Ny översiktsplan, rita först och tilldela sedan innehåll, Planens
uppgifter med standardvärden, Spara, och dialogerna."""
import datetime
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from qgis_app import get_app  # noqa: E402

get_app()

from qgis.core import NULL, QgsEditFormConfig, QgsFeature, QgsGeometry, QgsPointXY, QgsProject  # noqa: E402
from qgis.gui import QgsMapCanvas, QgsMapToolPan  # noqa: E402
from qgis.PyQt.QtCore import QCoreApplication, QDate, QEvent, QSize  # noqa: E402
from qgis.PyQt.QtWidgets import QMainWindow, QMenu, QToolBar  # noqa: E402

from rita_oversiktsplan import classFactory  # noqa: E402
from rita_oversiktsplan.core import content, geopackage, kommuner, model  # noqa: E402
from rita_oversiktsplan.core.project import (active_plan_group, draft_layers, find_plan_group,  # noqa: E402
                                             layer_in_group, load_plan)
from rita_oversiktsplan.gui.about_dialog import AboutDialog, metadata  # noqa: E402
from rita_oversiktsplan.gui.assign_dialog import AssignDialog  # noqa: E402
from rita_oversiktsplan.gui.new_plan_dialog import NewPlanDialog, safe_filename  # noqa: E402
from rita_oversiktsplan.gui.plan_info_dialog import PlanInfoDialog  # noqa: E402
from rita_oversiktsplan.plugin import MENU  # noqa: E402

PLAN = geopackage.NewPlan("0484", "Eskilstuna", "ÖP 2040", datetime.date(2027, 1, 1))
SQUARE = "MULTIPOLYGON(((0 0, 100 0, 100 100, 0 100, 0 0)))"


class FakeIface:
    """Det lilla av QgisInterface som pluginet använder."""

    def __init__(self):
        self.window = QMainWindow()
        self.plugin_menu = QMenu()
        self.menus: dict[str, QMenu] = {}
        self.bar = mock.Mock()
        self.toolbars = []
        self.active = None
        self.add_feature = mock.Mock()
        self.canvas = QgsMapCanvas()

    def messageBar(self):  # noqa: N802
        return self.bar

    def iconSize(self):  # noqa: N802
        return QSize(24, 24)

    def addToolBar(self, toolbar):  # noqa: N802
        self.window.addToolBar(toolbar)
        self.toolbars.append(toolbar)

    def activeLayer(self):  # noqa: N802
        return self.active

    def setActiveLayer(self, layer):  # noqa: N802
        self.active = layer

    def actionAddFeature(self):  # noqa: N802
        return self.add_feature

    def mapCanvas(self):  # noqa: N802
        return self.canvas

    def mainWindow(self):  # noqa: N802
        return self.window

    def pluginMenu(self):  # noqa: N802
        return self.plugin_menu

    def addPluginToMenu(self, name, action):  # noqa: N802
        if name not in self.menus:
            self.menus[name] = QMenu(name)
            self.plugin_menu.addMenu(self.menus[name])
        self.menus[name].addAction(action)

    def removePluginMenu(self, name, action):  # noqa: N802
        self.menus[name].removeAction(action)

    def last_message(self) -> str:
        return self.bar.pushMessage.call_args.args[1]


class PluginTests(unittest.TestCase):
    def setUp(self):
        self.iface = FakeIface()
        self.plugin = classFactory(self.iface)
        self.plugin.initGui()

    def tearDown(self):
        self.plugin.unload()

    def test_the_menu_offers_the_commands_the_toolbar_toggle_and_the_about_dialog(self):
        texts = [a.text() for a in self.iface.menus[MENU].actions() if not a.isSeparator()]
        self.assertEqual(texts, ["Ny översiktsplan…", "Öppna översiktsplan…", "Importera geometri…", "Planens uppgifter…",
                                 "Exportera…", "Skapa bokmärken i planhandling…", "Spara alla redigeringar", "Rita Översiktsplan",
                                 "Om Rita Översiktsplan…"])

    def test_the_toolbar_has_plan_draw_assign_info_and_save_buttons(self):
        (toolbar,) = self.iface.toolbars
        self.assertEqual(toolbar.objectName(), "RitaOversiktsplanToolBar")
        texts = [a.text() for a in toolbar.actions() if not a.isSeparator()]
        self.assertEqual(texts, ["Ny översiktsplan…", "Öppna översiktsplan…", "Checka ut", "Börja redigera",
                                 "Avsluta redigering",
                                 "Planens uppgifter", "Exportera", "Skapa bokmärken i planhandling", "Markera", "Avmarkera alla",
                                 "Rita yta", "Rita linje", "Rita punkt", "Importera geometri", "Tilldela innehåll",
                                 "Kopiera innehåll"])
        for action in toolbar.actions():
            if not action.isSeparator():
                self.assertFalse(action.icon().isNull(), action.text())
        self.assertTrue(toolbar.act_assign.isCheckable())

    def test_unloading_removes_the_toolbar(self):
        self.plugin.unload()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)  # kör deleteLater
        self.assertEqual(self.iface.window.findChildren(QToolBar), [])
        self.assertIsNone(self.plugin.toolbar)

    def test_the_menu_gets_the_brand_icon(self):
        entry = next(a for a in self.iface.plugin_menu.actions() if a.menu() is self.iface.menus[MENU])
        self.assertFalse(entry.icon().isNull())

    def test_unloading_removes_the_menu_entries(self):
        self.plugin.unload()
        self.assertEqual(self.iface.menus[MENU].actions(), [])

    def test_a_new_plan_is_created_and_loaded_into_the_map(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            target = Path(tmp) / "op.gpkg"
            with mock.patch.object(NewPlanDialog, "exec", return_value=True), \
                    mock.patch.object(NewPlanDialog, "target", return_value=target), \
                    mock.patch.object(NewPlanDialog, "plan", return_value=PLAN):
                self.plugin.new_plan()
            self.assertTrue(target.exists())
            self.assertIsNotNone(find_plan_group(QgsProject.instance(), target))
            QgsProject.instance().clear()

    def test_an_existing_file_gives_a_warning_and_is_left_alone(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            target = Path(tmp) / "op.gpkg"
            target.write_bytes(b"x")
            with mock.patch.object(NewPlanDialog, "exec", return_value=True), \
                    mock.patch.object(NewPlanDialog, "target", return_value=target), \
                    mock.patch.object(NewPlanDialog, "plan", return_value=PLAN):
                self.plugin.new_plan()
            self.assertEqual(target.read_bytes(), b"x")
            self.assertIn("finns redan", self.iface.last_message())

    def test_without_an_open_plan_the_plan_commands_say_so(self):
        QgsProject.instance().clear()
        self.plugin.draw("polygon")
        self.assertIn("Ingen översiktsplan är öppen", self.iface.last_message())
        self.iface.add_feature.trigger.assert_not_called()

    def test_the_about_entry_opens_the_dialog(self):
        with mock.patch.object(AboutDialog, "exec") as exec_:
            self.plugin.open_about()
        exec_.assert_called_once()


def choose(group_key, value, **fields):
    """Ersätter dialogens exec: väljer grupp och innehållstyp (och fyller i fält) och klickar Tilldela."""
    def exec_(dialog):
        dialog.group.setCurrentIndex(dialog.group.findData(group_key))
        dialog.value.setCurrentText(value)
        for name, text in fields.items():
            getattr(dialog, name).setText(text)
        return True
    return exec_


class PlanCommandTests(unittest.TestCase):
    """Rita först, tilldela sedan, Planens uppgifter och Spara, med en riktig plan i kartan."""

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
        return layer

    def test_drawing_happens_in_the_unassigned_layer_without_a_form(self):
        self.plugin.draw("line")
        layer = draft_layers(self.group)["line"]
        self.assertIs(self.iface.active, layer)
        self.assertTrue(layer.isEditable())
        self.iface.add_feature.trigger.assert_called_once()
        self.assertEqual(layer.editFormConfig().suppress(), QgsEditFormConfig.FeatureFormSuppress.SuppressOn)
        layer.rollBack()

    def test_the_unassigned_layers_are_at_the_top_of_the_plan(self):
        names = [child.name() for child in self.group.children()]
        self.assertEqual(names[:2], ["Översiktsplan", "Att tilldela"])

    def test_assigning_moves_the_geometry_to_the_content_layer_with_defaults_and_the_plan_event(self):
        info = content.read_plan_info(self.group)
        info.planhandelse, info.planhandelse_datum = "Samrådsunderlag färdigställt", datetime.date(2027, 5, 1)
        info.defaults["vertikal_avgransning"] = "nedåt"
        content.write_plan_info(self.group, info, update_content=False)
        draft = self.draft()
        with mock.patch.object(AssignDialog, "exec", new=choose("markochvattenanvandning", "Bostadsbebyggelse", namn="Norr")):
            self.plugin.assign_at(QgsPointXY(50, 50), 1.0)
        self.assertEqual(self.plugin.save_all(), 2)
        target = self.layers["innehall_op_markochvattenanvandning_polygon"]
        self.assertEqual(draft.featureCount(), 0)
        self.assertEqual(target.featureCount(), 1)
        feature = next(target.getFeatures())
        self.assertEqual(feature["innehallstyp_varde"], "Bostadsbebyggelse")
        self.assertEqual(feature["namn"], "Norr")
        self.assertEqual(feature["planhandelse_varde"], "Samrådsunderlag färdigställt")
        self.assertEqual(feature["vertikal_avgransning"], "nedåt")
        self.assertTrue(feature["illustrativa_granser"])
        self.assertRegex(str(feature["objektidentitet"]), r"^[0-9a-f-]{36}$")
        self.assertTrue(target.isEditable(), "redigeringen fortsätter efter Spara")

    def test_a_point_can_only_get_groups_that_have_points(self):
        dialog = AssignDialog("point", {lookup.name: [] for lookup in model.LOOKUPS})
        keys = [dialog.group.itemData(i) for i in range(dialog.group.count())]
        self.assertNotIn("plangeometri", keys)
        self.assertNotIn("omrade", keys)
        self.assertIn("klimatrelateradrisk", keys)

    def test_assigned_content_can_change_type_and_keeps_its_identity(self):
        self.draft()
        with mock.patch.object(AssignDialog, "exec", new=choose("markochvattenanvandning", "Jordbruk")):
            self.plugin.assign_at(QgsPointXY(50, 50), 1.0)
        self.plugin.save_all()
        mva = self.layers["innehall_op_markochvattenanvandning_polygon"]
        identity = next(mva.getFeatures())["objektidentitet"]
        with mock.patch.object(AssignDialog, "exec", new=choose("riksintressenop", "Naturvård")):
            self.plugin.assign_at(QgsPointXY(50, 50), 1.0)
        self.plugin.save_all()
        ri = self.layers["innehall_op_riksintressenop_polygon"]
        self.assertEqual(mva.featureCount(), 0)
        self.assertEqual(next(ri.getFeatures())["objektidentitet"], identity)

    def test_overlapping_content_lets_you_choose_which_one(self):
        self.draft()
        with mock.patch.object(AssignDialog, "exec", new=choose("markochvattenanvandning", "Jordbruk")):
            self.plugin.assign_at(QgsPointXY(50, 50), 1.0)
        self.draft()
        with mock.patch.object(AssignDialog, "exec", new=choose("riksintressenop", "Naturvård")):
            self.plugin.assign_at(QgsPointXY(50, 50), 1.0)
        with mock.patch.object(self.plugin, "choose_candidate", return_value=None) as chooser, \
                mock.patch.object(AssignDialog, "exec") as exec_:
            self.plugin.assign_at(QgsPointXY(50, 50), 1.0)
        self.assertEqual(len(chooser.call_args.args[0]), 2)
        exec_.assert_not_called()

    def test_unassigned_geometry_is_picked_before_content_under_it(self):
        self.draft()
        candidates = content.candidates_at(self.group, QgsPointXY(50, 50), 1.0)
        self.assertFalse(candidates[0].assigned)

    def test_clicking_on_nothing_says_so(self):
        self.plugin.assign_at(QgsPointXY(500, 500), 1.0)
        self.assertIn("Inget ritat här", self.iface.last_message())

    def test_cancel_leaves_the_geometry_unassigned(self):
        draft = self.draft()
        with mock.patch.object(AssignDialog, "exec", return_value=False):
            self.plugin.assign_at(QgsPointXY(50, 50), 1.0)
        self.assertEqual(draft.featureCount(), 1)
        self.assertFalse(draft.isModified())

    def test_the_assign_button_turns_the_map_tool_on_and_off(self):
        self.plugin.toolbar.act_assign.setChecked(True)
        self.assertIs(self.iface.canvas.mapTool(), self.plugin.assign_tool)
        pan = QgsMapToolPan(self.iface.canvas)
        self.iface.canvas.setMapTool(pan)  # ett annat verktyg väljs
        self.assertFalse(self.plugin.toolbar.act_assign.isChecked())

    def test_plan_info_saves_the_plan_the_event_and_the_defaults(self):
        self.draft()
        with mock.patch.object(AssignDialog, "exec", new=choose("lis", "LIS")):
            self.plugin.assign_at(QgsPointXY(50, 50), 1.0)
        self.plugin.save_all()

        def fill(dialog):
            dialog.titel.setText("ÖP 2045")
            dialog.planhandelse.setCurrentIndex(dialog.planhandelse.findData("Antagen"))
            dialog.handelse_datum.enabled.setChecked(True)
            dialog.avgransning.setCurrentIndex(dialog.avgransning.findData("uppåt"))
            dialog.skala.setValue(50000)
            return True

        with mock.patch.object(PlanInfoDialog, "exec", new=fill):
            self.plugin.open_info()
        plan = next(self.layers["oversiktsplan"].getFeatures())
        self.assertEqual(plan["planens_titel"], "ÖP 2045")
        self.assertEqual(plan["planhandelse_varde"], "Antagen")
        self.assertFalse(self.layers["oversiktsplan"].isEditable())
        defaults = geopackage.read_defaults(self.path)
        self.assertEqual((defaults["vertikal_avgransning"], defaults["presentationsskala"]), ("uppåt", "50000"))
        lis = next(self.layers["innehall_op_lis_polygon"].getFeatures())
        self.assertEqual(lis["planhandelse_varde"], "Antagen")  # allt innehåll får planens planhändelse
        self.assertEqual(self.group.name(), "Översiktsplan – ÖP 2045")

    def test_the_adoption_decision_is_saved_and_the_plan_points_at_it(self):
        def fill(dialog):
            dialog.diarienummer.setText(" KS 2027/123 ")
            dialog.fattat.enabled.setChecked(True)
            dialog.fattat.edit.setDate(QDate(2028, 6, 10))
            dialog.laga_kraft.enabled.setChecked(True)
            dialog.laga_kraft.edit.setDate(QDate(2028, 7, 15))
            return True

        with mock.patch.object(PlanInfoDialog, "exec", new=fill):
            self.plugin.open_info()
        decisions = list(self.layers["beslut_op"].getFeatures())
        self.assertEqual(len(decisions), 1)
        decision = decisions[0]
        self.assertEqual(decision["diarienummer"], "KS 2027/123")
        self.assertEqual(decision["beslutande_organisation"], "Eskilstuna")
        self.assertEqual(decision["beslutande_instans"], "kommunfullmäktige")
        self.assertEqual(decision["datum_laga_kraft"], QDate(2028, 7, 15))
        self.assertRegex(str(decision["objektidentitet"]), r"^[0-9a-f-]{36}$")
        plan = next(self.layers["oversiktsplan"].getFeatures())
        self.assertEqual(plan["beslut"], decision["objektidentitet"])
        read = content.read_plan_info(self.group).beslut
        self.assertEqual((read.diarienummer, read.fattat, read.overklagat, read.laga_kraft),
                         ("KS 2027/123", datetime.date(2028, 6, 10), None, datetime.date(2028, 7, 15)))

    def test_saving_again_updates_the_same_decision(self):
        info = content.read_plan_info(self.group)
        info.beslut = content.Decision(diarienummer="KS 1")
        content.write_plan_info(self.group, info, update_content=False)
        info = content.read_plan_info(self.group)
        info.beslut.diarienummer = "KS 2"
        content.write_plan_info(self.group, info, update_content=False)
        self.assertEqual([f["diarienummer"] for f in self.layers["beslut_op"].getFeatures()], ["KS 2"])

    def test_no_decision_is_created_while_the_fields_are_empty(self):
        content.write_plan_info(self.group, content.read_plan_info(self.group), update_content=False)
        self.assertEqual(self.layers["beslut_op"].featureCount(), 0)
        self.assertIn(next(self.layers["oversiktsplan"].getFeatures())["beslut"], (None, NULL))

    def test_plan_info_cancel_changes_nothing(self):
        with mock.patch.object(PlanInfoDialog, "exec", return_value=False):
            self.plugin.open_info()
        plan = next(self.layers["oversiktsplan"].getFeatures())
        self.assertEqual(plan["planens_titel"], "ÖP 2040")
        self.assertIn(plan["planhandelse_varde"], (None, NULL))

    def test_the_tagging_program_opens_in_its_own_window_without_blocking_and_is_reused(self):
        self.plugin.open_document()
        window = self.plugin.document_window
        self.assertIsNotNone(window)
        self.assertTrue(window.isWindow())
        self.assertFalse(window.isModal())
        self.assertEqual(window.session.plan.title, "ÖP 2040")  # planen är redan vald
        self.plugin.open_document()
        self.assertIs(self.plugin.document_window, window)

    def test_save_with_nothing_to_save_says_so(self):
        self.assertEqual(self.plugin.save_all(), 0)
        self.assertIn("inget osparat", self.iface.last_message())

    def test_the_active_plan_is_the_one_the_selected_layer_belongs_to(self):
        other = geopackage.create_geopackage(Path(self.tmp.name) / "annan.gpkg", geopackage.NewPlan(
            "0180", "Stockholm", "Annan plan", datetime.date(2027, 1, 1)))
        other_layers = load_plan(other, QgsProject.instance())  # hamnar överst
        self.assertEqual(active_plan_group(QgsProject.instance()).name(), "Översiktsplan – Annan plan")
        group = active_plan_group(QgsProject.instance(), self.layers["innehall_op_omrade"])
        self.assertEqual(group.name(), "Översiktsplan – ÖP 2040")
        self.assertIs(layer_in_group(group, "innehall_op_omrade"), self.layers["innehall_op_omrade"])
        self.assertIsNot(layer_in_group(group, "innehall_op_omrade"), other_layers["innehall_op_omrade"])


class UpgradeTests(unittest.TestCase):
    def test_a_plan_from_the_first_version_gets_the_new_tables_when_opened(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            path = geopackage.create_geopackage(Path(tmp) / "gammal.gpkg", PLAN)
            with closing(sqlite3.connect(path)) as con:  # gör filen till schema 1
                for layer_def in model.ADDED_TABLES:
                    for (name,) in con.execute("SELECT name FROM sqlite_master WHERE type = 'trigger' AND name LIKE ?",
                                               (f"rtree_{layer_def.name}_%",)).fetchall():
                        con.execute(f'DROP TRIGGER "{name}"')
                    con.execute(f'DROP TABLE IF EXISTS "rtree_{layer_def.name}_geom"')
                    con.execute(f'DROP TABLE "{layer_def.name}"')
                    for table in ("gpkg_contents", "gpkg_geometry_columns", "gpkg_extensions"):
                        con.execute(f"DELETE FROM {table} WHERE table_name = ?", (layer_def.name,))
                con.execute(f"DELETE FROM {model.META_TABLE} WHERE key LIKE 'standard_%'")
                con.execute(f"UPDATE {model.META_TABLE} SET value = '1' WHERE key = 'schema_version'")
                con.commit()
            project = QgsProject()
            layers = load_plan(path, project)
            self.assertIn("rita_otilldelad_yta", layers)
            self.assertIn("beslut_op", layers)
            self.assertEqual(geopackage.read_meta(path)["schema_version"], str(model.SCHEMA_VERSION))
            self.assertEqual(geopackage.read_defaults(path)["under_ersattning"], "0")
            project.clear()


class AboutDialogTests(unittest.TestCase):
    def test_it_shows_the_name_version_and_points_at_this_projects_documentation(self):
        dialog = AboutDialog()
        self.assertEqual(dialog.windowTitle(), "Om Rita Översiktsplan")
        self.assertEqual(dialog.name.text(), "Rita Översiktsplan")
        self.assertIn(metadata()["version"], dialog.version.text())
        self.assertIn("översiktsplaner", dialog.tagline.text())
        self.assertEqual(dialog.docs_url(),
                         "https://github.com/ericalnemar/rita-oversiktsplan/blob/main/docs/anvandning.md")


class NewPlanDialogTests(unittest.TestCase):
    def setUp(self):
        self.dialog = NewPlanDialog()
        self.addCleanup(self.dialog.deleteLater)

    def ok(self):
        return self.dialog.buttons.button(self.dialog.buttons.StandardButton.Ok)

    def test_create_is_only_possible_with_kommun_title_and_folder(self):
        self.assertFalse(self.ok().isEnabled())
        self.dialog.kommun.set_kommun("Eskilstuna")
        self.dialog.titel.setText("Översiktsplan 2040")
        self.assertFalse(self.ok().isEnabled())
        self.dialog.folder.setFilePath(tempfile.gettempdir())
        self.assertTrue(self.ok().isEnabled())

    def test_the_filename_follows_the_title_until_the_user_writes_one(self):
        self.dialog.titel.setText("Översiktsplan 2040")
        self.assertEqual(self.dialog.filnamn.text(), "Översiktsplan_2040")
        self.dialog.filnamn.textEdited.emit("op")
        self.dialog.filnamn.setText("op")
        self.dialog.titel.setText("Annan titel")
        self.assertEqual(self.dialog.filnamn.text(), "op")

    def test_the_values_become_a_new_plan(self):
        self.dialog.kommun.set_kommun("Eskilstuna")
        self.dialog.titel.setText(" ÖP 2040 ")
        self.dialog.folder.setFilePath(tempfile.gettempdir())
        plan = self.dialog.plan()
        self.assertEqual((plan.kommunkod, plan.kommunnamn, plan.titel, plan.digitalt_ursprung),
                         ("0484", "Eskilstuna", "ÖP 2040", True))  # en ny översiktsplan har digitalt ursprung
        self.assertEqual(self.dialog.target(), Path(tempfile.gettempdir()) / "ÖP_2040.gpkg")

    def test_sweref_99_tm_is_preselected_and_a_local_zone_can_be_chosen(self):
        self.assertEqual(self.dialog.epsg(), 3006)
        self.assertEqual(self.dialog.crs.count(), 13)  # SWEREF 99 TM och de tolv lokala zonerna
        self.dialog.crs.setCurrentIndex(self.dialog.crs.findData(3010))
        self.dialog.kommun.set_kommun("Eskilstuna")
        self.dialog.titel.setText("ÖP")
        self.assertEqual(self.dialog.plan().epsg, 3010)

    def test_the_database_choice_shows_its_own_fields(self):
        self.assertTrue(self.dialog.file_box.isVisibleTo(self.dialog))
        self.assertFalse(self.dialog.postgis_box.isVisibleTo(self.dialog))
        if self.dialog.use_postgis.isEnabled():
            self.dialog.use_postgis.setChecked(True)
            self.assertTrue(self.dialog.postgis_box.isVisibleTo(self.dialog))
            self.assertEqual(self.dialog.schema.text(), "oversiktsplan")

    def test_filenames_keep_swedish_letters_but_not_odd_characters(self):
        self.assertEqual(safe_filename(" Översiktsplan: Västra delen / 2040 "), "Översiktsplan_Västra_delen_2040")


class AssignDialogTests(unittest.TestCase):
    def setUp(self):
        catalog_values = {}
        from rita_oversiktsplan.core import opkatalog
        catalog = opkatalog.bundled()
        for lookup in model.LOOKUPS:
            catalog_values[lookup.name] = [v.varde for v in catalog.values(lookup.category, lookup.group,
                                                                           lookup.itself)]
        self.lookups = catalog_values

    def test_only_the_fields_the_group_has_are_shown(self):
        dialog = AssignDialog("polygon", self.lookups)
        dialog.group.setCurrentIndex(dialog.group.findData("markochvattenanvandning"))
        self.assertTrue(dialog.form.isRowVisible(dialog.complement))
        self.assertTrue(dialog.form.isRowVisible(dialog.utbyggnadsordning))
        self.assertFalse(dialog.form.isRowVisible(dialog.sambandsniva))
        dialog.group.setCurrentIndex(dialog.group.findData("mellankommunalaochregionalaintressen"))
        self.assertTrue(dialog.form.isRowVisible(dialog.sambandsniva))
        self.assertFalse(dialog.form.isRowVisible(dialog.complement))

    def test_the_catalog_description_of_the_chosen_value_is_shown(self):
        dialog = AssignDialog("polygon", self.lookups)
        dialog.group.setCurrentIndex(dialog.group.findData("markochvattenanvandning"))
        dialog.value.setCurrentText("Bostadsbebyggelse")
        self.assertTrue(dialog.description.text())

    def test_the_choice_becomes_an_assignment_with_only_the_groups_fields(self):
        dialog = AssignDialog("line", self.lookups)
        dialog.group.setCurrentIndex(dialog.group.findData("utvecklingsinriktning"))
        dialog.complement.setCurrentIndex(dialog.complement.findData("Kommunikation"))
        dialog.namn.setText(" Stråket ")
        assignment = dialog.assignment()
        self.assertEqual(assignment.category.key, "utvecklingsinriktning")
        self.assertEqual(assignment.values["innehallstyp_varde"], "Utvecklingsinriktning")
        self.assertEqual(assignment.values["kompletterandeInnehallstyp"], "Kommunikation")
        self.assertEqual(assignment.values["namn"], "Stråket")

    def test_changing_type_starts_from_the_current_values(self):
        category = next(c for c in model.CATEGORIES if c.key == "klimatrelateradrisk")
        dialog = AssignDialog("polygon", self.lookups, {"innehallstyp_varde": "Risk för ras", "namn": "Branten"},
                              category)
        self.assertEqual(dialog.group.currentData(), "klimatrelateradrisk")
        self.assertEqual(dialog.value.currentText(), "Risk för ras")
        self.assertEqual(dialog.namn.text(), "Branten")


class KommunerTests(unittest.TestCase):
    def test_a_kommun_is_found_by_name_and_by_code(self):
        self.assertEqual(kommuner.by_name("eskilstuna").kod, "0484")
        self.assertEqual(kommuner.by_code("0484").namn, "Eskilstuna")
        self.assertIsNone(kommuner.by_code("9999"))


if __name__ == "__main__":
    unittest.main()
