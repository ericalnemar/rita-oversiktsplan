"""Planens underlag: fliken Underlag i Planens uppgifter, tabellerna och exporten."""
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

from qgis.core import QgsProject  # noqa: E402

from rita_oversiktsplan import classFactory  # noqa: E402
from rita_oversiktsplan.core import content, export_lm, geopackage, model  # noqa: E402
from rita_oversiktsplan.core.project import active_plan_group, load_plan, plan_storage  # noqa: E402
from rita_oversiktsplan.core.underlag import Underlag, read_underlag, save_underlag  # noqa: E402
from rita_oversiktsplan.gui.plan_info_dialog import PlanInfoDialog  # noqa: E402
from test_plugin import FakeIface  # noqa: E402

PLAN = geopackage.NewPlan("0484", "Eskilstuna", "ÖP 2040", datetime.date(2027, 1, 1))
TYPES = ["Länsstyrelsens granskningsyttrande", "Miljökonsekvensbeskrivning", "Planeringsstrategi",
         "Planeringsunderlag", "Översiktsplan", "Övrig handling"]


class UnderlagCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.path = geopackage.create_geopackage(Path(self.tmp.name) / "op.gpkg", PLAN)
        self.layers = load_plan(self.path, QgsProject.instance())
        self.addCleanup(self._clear)
        self.group = active_plan_group(QgsProject.instance())

    def _clear(self):
        for layer in self.layers.values():
            if layer.isEditable():
                layer.rollBack()
        QgsProject.instance().clear()


class StorageTests(UnderlagCase):
    def test_underlag_are_saved_in_boverkets_tables_and_read_back(self):
        items = [Underlag("Planeringsunderlag", "Grönplan", "https://kommun.se/gronplan.pdf",
                          datetime.date(2026, 5, 1)),
                 Underlag("Planeringsunderlag", "Trafikstrategi"),
                 Underlag("Miljökonsekvensbeskrivning", "MKB ÖP 2040")]
        self.assertEqual(save_underlag(self.group, items), 3)
        self.assertEqual(self.layers["oversiktsplan_underlag"].featureCount(), 2)  # en per underlagstyp
        self.assertEqual(self.layers["oversiktsplan_underlag_underlag"].featureCount(), 3)
        self.assertEqual(self.layers["dokumentreferens_op"].featureCount(), 3)
        self.assertEqual(sorted(read_underlag(self.group), key=lambda u: u.namn), sorted(items, key=lambda u: u.namn))

    def test_saving_again_replaces_the_underlag_but_not_the_planhandling(self):
        documents = self.layers["dokumentreferens_op"]
        documents.startEditing()
        from qgis.core import QgsFeature
        planhandling = QgsFeature(documents.fields())
        planhandling["dokumentreferens_id"] = "planhandlingen"
        planhandling["namn"] = "Planhandling.docx"
        documents.addFeature(planhandling)
        self.assertTrue(documents.commitChanges())
        save_underlag(self.group, [Underlag("Planeringsunderlag", "A")])
        save_underlag(self.group, [Underlag("Övrig handling", "B")])
        self.assertEqual([u.namn for u in read_underlag(self.group)], ["B"])
        names = sorted(f["namn"] for f in documents.getFeatures())
        self.assertEqual(names, ["B", "Planhandling.docx"])

    def test_the_export_takes_the_underlag_and_no_longer_reports_them_missing(self):
        _, problems = export_lm.export(self.group)
        self.assertTrue(any("underlag" in p.text for p in problems))
        save_underlag(self.group, [Underlag("Planeringsunderlag", "Grönplan", "https://kommun.se/gronplan.pdf",
                                            datetime.date(2026, 5, 1)),
                                   Underlag("Planeringsunderlag", "Trafikstrategi", r"C:\planer\trafik.pdf")])
        collection, problems = export_lm.export(self.group)
        self.assertFalse(any("underlag" in p.text for p in problems))
        underlag = collection["features"][0]["properties"]["underlag"]
        self.assertEqual(len(underlag), 1)
        self.assertEqual(underlag[0]["underlagstyp"]["varde"], "Planeringsunderlag")
        self.assertEqual(sorted(d["namn"] for d in underlag[0]["underlag"]), ["Grönplan", "Trafikstrategi"])
        green = next(d for d in underlag[0]["underlag"] if d["namn"] == "Grönplan")
        self.assertEqual(green["externReferens"]["lank"], "https://kommun.se/gronplan.pdf")
        self.assertEqual(green["externReferens"]["avser"], "Planeringsunderlag")
        trafik = next(d for d in underlag[0]["underlag"] if d["namn"] == "Trafikstrategi")
        self.assertNotIn("lank", trafik["externReferens"])  # en sökväg på datorn är ingen webbadress


class DialogTests(UnderlagCase):
    def dialog(self, items=()):
        info = content.read_plan_info(self.group)
        dialog = PlanInfoDialog(info, [], None, list(items), TYPES)
        self.addCleanup(dialog.deleteLater)
        return dialog

    def test_the_tab_shows_the_underlag_and_rows_can_be_added_and_removed(self):
        dialog = self.dialog([Underlag("Miljökonsekvensbeskrivning", "MKB", "", datetime.date(2026, 1, 2))])
        self.assertEqual([dialog.tabs.tabText(i) for i in range(dialog.tabs.count())],
                         ["Planen", "Planhändelse", "Beslut", "Underlag", "Standardvärden för innehåll"])
        self.assertEqual(dialog.underlag(), [Underlag("Miljökonsekvensbeskrivning", "MKB", "", datetime.date(2026, 1, 2))])
        row = dialog.add_underlag()
        self.assertEqual(dialog.underlag_table.cellWidget(row, 0).currentText(), "Planeringsunderlag")
        self.assertEqual(len(dialog.underlag()), 1)  # en tom rad räknas inte
        dialog.underlag_table.item(row, 1).setText("Grönplan")
        self.assertEqual(dialog.underlag()[1].namn, "Grönplan")
        dialog.underlag_table.setCurrentCell(0, 1)
        dialog.remove_underlag()
        self.assertEqual([u.namn for u in dialog.underlag()], ["Grönplan"])

    def test_a_file_can_be_chosen(self):
        dialog = self.dialog()
        with mock.patch("rita_oversiktsplan.gui.plan_info_dialog.QFileDialog.getOpenFileName",
                        return_value=(r"C:\planer\Grönplan 2026.pdf", "")):
            dialog.add_underlag_file()
        self.assertEqual(dialog.underlag(), [Underlag("Planeringsunderlag", "Grönplan 2026",
                                                      r"C:\planer\Grönplan 2026.pdf")])

    def test_plan_info_saves_the_underlag(self):
        iface = FakeIface()
        plugin = classFactory(iface)
        plugin.initGui()
        self.addCleanup(plugin.unload)

        def fill(dialog):
            row = dialog.add_underlag()
            dialog.underlag_table.item(row, 1).setText("Grönplan")
            return True

        with mock.patch.object(PlanInfoDialog, "exec", new=fill):
            plugin.open_info()
        self.assertEqual(read_underlag(self.group), [Underlag("Planeringsunderlag", "Grönplan")])
        self.assertIn("Planeringsunderlag", plan_storage(self.group).read_lookup(model.UNDERLAGSTYP_LOOKUP))


if __name__ == "__main__":
    unittest.main()
