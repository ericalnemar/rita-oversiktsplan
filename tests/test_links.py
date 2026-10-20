"""Kopplingar: Berör annat innehåll, riksintressets id och vilket innehåll antagandebeslutet gäller."""
import datetime
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from qgis_app import get_app  # noqa: E402

get_app()

from qgis.core import NULL, QgsPointXY  # noqa: E402

from rita_oversiktsplan.core import content, export_lm, model, relations  # noqa: E402
from rita_oversiktsplan.core.project import plan_storage  # noqa: E402
from rita_oversiktsplan.gui.assign_dialog import AssignDialog  # noqa: E402
from test_tools import LAND_USE, OTHER, RISK, ToolCase  # noqa: E402

NATIONAL = next(c for c in model.CATEGORIES if c.key == "riksintressenop")


def features(collection, kind):
    return [f["properties"] for f in collection["features"] if f["properties"]["feature:typ"] == kind]


class RelateTests(ToolCase):
    def identity(self, candidate):
        return str(candidate.layer.getFeature(candidate.fid)["objektidentitet"])

    def test_toggle_links_and_unlinks_in_the_edit_buffer(self):
        housing = self.assigned()
        risk = self.assigned(OTHER, RISK, {"innehallstyp_varde": "Risk för ras"})
        self.assertTrue(relations.toggle(self.group, risk.layer, risk.fid, self.identity(housing)))
        self.assertEqual(relations.related(self.group, risk.layer, risk.fid), {self.identity(housing)})
        self.assertTrue(risk.layer.isEditable())
        self.assertFalse(relations.toggle(self.group, risk.layer, risk.fid, self.identity(housing)))
        self.assertEqual(relations.related(self.group, risk.layer, risk.fid), set())

    def test_content_cannot_concern_itself(self):
        housing = self.assigned()
        with self.assertRaises(ValueError):
            relations.toggle(self.group, housing.layer, housing.fid, self.identity(housing))

    def test_the_export_lists_what_the_content_concerns(self):
        housing = self.assigned()
        risk = self.assigned(OTHER, RISK, {"innehallstyp_varde": "Risk för ras"})
        risk_id, housing_id = self.identity(risk), self.identity(housing)
        relations.toggle(self.group, risk.layer, risk.fid, housing_id)
        for layer in (risk.layer, relations._table(self.group)):
            self.assertTrue(layer.commitChanges(False))
        collection, _ = export_lm.export(self.group)
        by_id = {p["objektidentitet"]: p for p in features(collection, "innehallOP")}
        self.assertEqual(by_id[risk_id]["berorAnnatInnehall"], [housing_id])
        self.assertNotIn("berorAnnatInnehall", by_id[housing_id])

    def test_the_tool_picks_a_source_and_then_links_the_clicked_content(self):
        housing = self.assigned()
        risk = self.assigned(OTHER, RISK, {"innehallstyp_varde": "Risk för ras"})
        self.plugin.start_editing()
        self.plugin.toolbar.act_relate.setChecked(True)
        self.assertIn("relate", self.plugin.map_tools)
        self.assertIsNone(self.plugin.relate_at(QgsPointXY(250, 50), 1))  # källan
        self.assertTrue(self.plugin.relate_at(QgsPointXY(50, 50), 1))
        self.assertEqual(relations.related(self.group, risk.layer, risk.fid), {self.identity(housing)})
        self.assertIsNone(self.plugin.relate_at(QgsPointXY(250, 50), 1))  # samma objekt igen: inget händer
        self.assertFalse(self.plugin.relate_at(QgsPointXY(50, 50), 1))

    def test_the_button_is_grey_outside_an_editing_session(self):
        self.plugin.refresh_tools()
        self.assertFalse(self.plugin.toolbar.act_relate.isEnabled())
        self.plugin.start_editing()
        self.assertTrue(self.plugin.toolbar.act_relate.isEnabled())


class NationalInterestTests(ToolCase):
    def value(self):
        lookup = next(l for l in model.LOOKUPS if l.name == NATIONAL.lookup)
        return next(iter(plan_storage(self.group).read_lookup_values(lookup)))

    def test_the_dialog_shows_the_field_only_for_national_interests(self):
        lookups = {l.name: plan_storage(self.group).read_lookup_values(l) for l in model.LOOKUPS}
        dialog = AssignDialog("polygon", lookups)
        dialog.group.setCurrentIndex(dialog.categories.index(NATIONAL))
        self.assertTrue(dialog.form.isRowVisible(dialog.riksintresse))
        dialog.riksintresse.setText(" RI-123 ")
        self.assertEqual(dialog.assignment().values["objektidentitet_ri"], "RI-123")
        dialog.group.setCurrentIndex(dialog.categories.index(LAND_USE))
        self.assertFalse(dialog.form.isRowVisible(dialog.riksintresse))
        self.assertNotIn("objektidentitet_ri", dialog.assignment().values)

    def test_the_id_becomes_an_external_reference_in_the_export(self):
        self.assigned(category=NATIONAL, values={"innehallstyp_varde": self.value(), "objektidentitet_ri": "RI-123"})
        collection, _ = export_lm.export(self.group)
        item = features(collection, "innehallOP")[0]
        reference = item["externReferens"][0]
        self.assertEqual((reference["identitet"], reference["producentensIdentitet"], reference["avser"]),
                         ("RI-123", "RI-123", "Riksintresse"))
        self.assertRegex(reference["tidsstampel"], r"^\d{4}-\d\d-\d\dT")


class DecisionTests(ToolCase):
    def save_decision(self):
        info = content.read_plan_info(self.group)
        info.beslut = content.Decision("KS 2027/1", datetime.date(2027, 5, 1), None, datetime.date(2027, 6, 1))
        content.write_plan_info(self.group, info, update_content=False)
        return content.read_plan_info(self.group).beslut, str(content.decision_feature(self.group)["objektidentitet"])

    def test_the_adoption_decision_affects_the_plan_and_not_the_content(self):
        housing = self.assigned()
        _, decision = self.save_decision()
        self.assertIn(housing.layer.getFeature(housing.fid)["beslut"], (None, NULL))  # innehållet rörs inte
        collection, problems = export_lm.export(self.group)
        (beslut,) = features(collection, "beslutOP")
        self.assertEqual([a["objekttyp"] for a in beslut["paverkar"]], ["oversiktsplan"])  # OP-JSON-005
        self.assertFalse([p for p in problems if "OP-JSON-005" in p.text])

    def test_old_content_pointing_at_the_adoption_decision_is_exported_without_it(self):
        housing = self.assigned()
        _, decision = self.save_decision()
        layer = housing.layer
        layer.changeAttributeValue(housing.fid, layer.fields().indexOf("beslut"), decision)  # som i 0.1.1–0.1.4
        collection, _ = export_lm.export(self.group)
        self.assertNotIn("beslut", features(collection, "innehallOP")[0])
        (beslut,) = features(collection, "beslutOP")
        self.assertEqual([a["objekttyp"] for a in beslut["paverkar"]], ["oversiktsplan"])

if __name__ == "__main__":
    unittest.main()
