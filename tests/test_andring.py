"""Ändring av översiktsplanen: påbörja, lägga innehåll i ändringen, under ersättning, anta, och exporten."""
import datetime
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from qgis_app import get_app  # noqa: E402

get_app()

from qgis.core import NULL  # noqa: E402

from rita_oversiktsplan.core import andring, content, export_lm  # noqa: E402
from rita_oversiktsplan.gui.andring_dialog import AndringDialog  # noqa: E402
from test_tools import OTHER, SQUARE, ToolCase  # noqa: E402

THIRD = "MULTIPOLYGON(((400 0, 500 0, 500 100, 400 100, 400 0)))"
STARTED = datetime.date(2028, 3, 1)


def props(collection, kind):
    return [f["properties"] for f in collection["features"] if f["properties"]["feature:typ"] == kind]


def plain(value):
    return None if value is None or value == NULL else value


class AndringCase(ToolCase):
    def adopt_plan(self):
        """Den gällande planen: antagen, med antagandebeslut."""
        info = content.read_plan_info(self.group)
        info.planhandelse, info.planhandelse_datum = "Antagen", datetime.date(2027, 6, 1)
        info.beslut = content.Decision("KS 2027/1", datetime.date(2027, 6, 1), None, datetime.date(2027, 7, 1))
        content.write_plan_info(self.group, info, update_content=True)

    def start(self):
        return andring.start(self.group, "Vindbruk", "KS 2028/5", STARTED, "Samrådsunderlag färdigställt",
                             datetime.date(2028, 5, 1))

    def feature(self, layer, identity):
        return next(f for f in layer.getFeatures() if f["objektidentitet"] == identity)


class AndringTests(AndringCase):
    def test_new_content_belongs_to_the_change_while_it_is_ongoing(self):
        self.adopt_plan()
        change = self.start()
        self.assertEqual(andring.active(self.group).namn, "Vindbruk")
        candidate = self.assigned(OTHER, values={"innehallstyp_varde": "Verksamheter", "namn": "Vind"})
        feature = candidate.layer.getFeature(candidate.fid)
        self.assertEqual(str(feature["beslut"]), change.beslut)
        self.assertEqual(feature["planhandelse_varde"], "Samrådsunderlag färdigställt")
        self.assertEqual(feature["datum_paborjat"].toPyDate(), STARTED)

    def test_an_ongoing_change_exports_without_its_decision(self):
        self.adopt_plan()
        self.start()
        self.assigned(OTHER, values={"innehallstyp_varde": "Verksamheter", "namn": "Vind"})
        collection, problems = export_lm.export(self.group)
        decisions = props(collection, "beslutOP")
        self.assertEqual(len(decisions), 1)  # bara antagandebeslutet
        self.assertEqual([a["objekttyp"] for a in decisions[0]["paverkar"]], ["oversiktsplan"])
        self.assertTrue(all("beslut" not in c for c in props(collection, "innehallOP")))
        self.assertFalse([p for p in problems if "OP-JSON-005" in p.text])

    def test_marking_replaced_and_adopting_the_change(self):
        old = self.assigned(values={"innehallstyp_varde": "Bostadsbebyggelse", "namn": "Gammal"})
        old.layer.commitChanges(False)
        self.adopt_plan()
        old_id = next(f for f in old.layer.getFeatures() if f["namn"] == "Gammal")["objektidentitet"]
        change = self.start()
        new = self.assigned(OTHER, values={"innehallstyp_varde": "Verksamheter", "namn": "Ny"})
        new.layer.commitChanges(False)
        old_layer = old.layer
        old_layer.selectByIds([self.feature(old_layer, old_id).id()])
        self.assertEqual(andring.mark_replaced(self.group), 1)
        self.assertTrue(self.feature(old_layer, old_id)["under_ersattning"])
        collection, _ = export_lm.export(self.group)
        replaced = next(c for c in props(collection, "innehallOP") if c["objektidentitet"] == old_id)
        self.assertTrue(replaced["underErsattning"])

        with self.assertRaisesRegex(ValueError, "diarienummer och datum"):
            andring.finish(self.group, True)
        andring.update(self.group, "Antagen", datetime.date(2028, 9, 1), "KS 2028/5", datetime.date(2028, 9, 1),
                       None, None)
        adopted, removed = andring.finish(self.group, True)
        self.assertEqual((adopted, removed), (1, 1))
        self.assertIsNone(andring.active(self.group))
        self.assertFalse([f for f in old_layer.getFeatures() if f["objektidentitet"] == old_id])
        collection, problems = export_lm.export(self.group)
        decisions = {d["objektidentitet"]: d for d in props(collection, "beslutOP")}
        self.assertEqual([a["objekttyp"] for a in decisions[change.beslut]["paverkar"]], ["innehallOP"])
        new_content = next(c for c in props(collection, "innehallOP") if c.get("namn") == "Ny")
        self.assertEqual(new_content["beslut"], change.beslut)
        self.assertEqual(new_content["planhandelse"]["varde"], "Antagen")
        self.assertEqual(new_content["datumPaborjat"], STARTED.isoformat())
        self.assertFalse([p for p in problems if "OP-JSON-005" in p.text])

    def test_existing_content_can_be_added_to_the_change(self):
        old = self.assigned(values={"innehallstyp_varde": "Bostadsbebyggelse", "namn": "Ändras"})
        old.layer.commitChanges(False)
        self.adopt_plan()
        change = self.start()
        feature = next(f for f in old.layer.getFeatures() if f["namn"] == "Ändras")
        old.layer.selectByIds([feature.id()])
        self.assertEqual(andring.add_selected(self.group), 1)
        feature = next(f for f in old.layer.getFeatures() if f["namn"] == "Ändras")
        self.assertEqual(str(feature["beslut"]), change.beslut)
        self.assertEqual(feature["planhandelse_varde"], "Samrådsunderlag färdigställt")
        self.assertEqual(andring.members(self.group, change.beslut), 1)

    def test_the_plans_event_does_not_overwrite_the_changes_content(self):
        self.adopt_plan()
        self.start()
        candidate = self.assigned(OTHER, values={"innehallstyp_varde": "Verksamheter", "namn": "Vind"})
        candidate.layer.commitChanges(False)
        info = content.read_plan_info(self.group)
        info.planhandelse = "Fastställd som aktuell"
        content.write_plan_info(self.group, info, update_content=True)
        feature = next(f for f in candidate.layer.getFeatures() if f["namn"] == "Vind")
        self.assertEqual(feature["planhandelse_varde"], "Samrådsunderlag färdigställt")

    def test_only_one_change_at_a_time(self):
        self.start()
        with self.assertRaisesRegex(ValueError, "pågår redan"):
            self.start()
        andring.cancel(self.group)
        self.assertIsNone(andring.active(self.group))


class AndringDialogTests(AndringCase):
    def test_the_dialog_starts_and_adopts_a_change(self):
        dialog = AndringDialog(self.group, ["Samrådsunderlag färdigställt", "Antagen"])
        self.addCleanup(dialog.deleteLater)
        self.assertEqual(dialog.pages.currentIndex(), 0)
        dialog.start_name.setText("Tillägg för vindbruk")
        self.assertIsNotNone(dialog.start())
        self.assertEqual(dialog.pages.currentIndex(), 1)
        self.assertIn("Tillägg för vindbruk", dialog.title.text())
        self.assertIsNone(dialog.adopt())  # beslutet saknas
        self.assertIn("diarienummer och datum", dialog.message.text())
        dialog.diarienummer.setText("KS 2028/5")
        dialog.fattat.enabled.setChecked(True)
        with mock.patch.object(AndringDialog, "_ask", return_value=True):
            self.assertEqual(dialog.adopt(), (0, 0))
        self.assertEqual(dialog.pages.currentIndex(), 0)

    def test_a_change_needs_a_name(self):
        dialog = AndringDialog(self.group, [])
        self.addCleanup(dialog.deleteLater)
        self.assertIsNone(dialog.start())
        self.assertIn("namn", dialog.message.text())


if __name__ == "__main__":
    unittest.main()
