"""Utbyggnadsordning: planens etapper under Planens uppgifter, valbara i Tilldela innehåll och formuläret, och
mark- och vattenanvändningens symboler efter etapp (mörk för första etappen, ljus för sista)."""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from qgis_app import get_app  # noqa: E402

get_app()

from qgis.core import QgsProject, QgsRuleBasedRenderer, QgsSldExportContext  # noqa: E402

from rita_oversiktsplan.core import content, model, styles, utbyggnad  # noqa: E402
from rita_oversiktsplan.core.project import load_plan  # noqa: E402
from rita_oversiktsplan.core.utbyggnad import Stage  # noqa: E402
from rita_oversiktsplan.gui.assign_dialog import AssignDialog  # noqa: E402
from rita_oversiktsplan.gui.plan_info_dialog import PlanInfoDialog  # noqa: E402
from test_tools import ToolCase  # noqa: E402

STAGES = [Stage("Etapp 1", "2027–2035"), Stage("Etapp 2", "2035–2045"), Stage("Reserv")]
MVA = "innehall_op_markochvattenanvandning_polygon"


class StageTests(unittest.TestCase):
    def test_a_stage_is_its_name_and_period(self):
        self.assertEqual([s.label for s in STAGES], ["Etapp 1 (2027–2035)", "Etapp 2 (2035–2045)", "Reserv"])

    def test_the_stages_survive_the_metadata(self):
        self.assertEqual(utbyggnad.parse(utbyggnad.dump(STAGES)), STAGES)
        self.assertEqual(utbyggnad.parse(""), [])
        self.assertEqual(utbyggnad.parse("inte json"), [])

    def test_two_stages_cannot_have_the_same_text(self):
        with self.assertRaisesRegex(ValueError, "Etapp 1"):
            utbyggnad.check([Stage("Etapp 1"), Stage("Etapp 1")])

    def test_a_renamed_stage_is_found_by_its_place_in_the_old_list(self):
        new = [(1, Stage("Etapp 2", "2035–2040")), (0, STAGES[0]), (None, Stage("Etapp 3"))]
        self.assertEqual(utbyggnad.renames(STAGES, new), {"Etapp 2 (2035–2045)": "Etapp 2 (2035–2040)"})

    def test_the_first_stage_is_darkest_and_the_last_lightest(self):
        color = (255, 255, 206)
        tones = [sum(styles.stage_color(color, i, 3)) for i in range(3)]
        self.assertEqual(tones, sorted(tones))
        self.assertLess(tones[0], sum(color))
        self.assertGreater(tones[-1], sum(styles.stage_color(color, 0, 1)))


class PlanStageTests(ToolCase):
    def setUp(self):
        super().setUp()
        utbyggnad.write(self.group, STAGES)
        utbyggnad.refresh(self.group)

    def test_land_use_gets_a_rule_per_stage_and_one_for_existing(self):
        renderer = self.layers[MVA].renderer()
        self.assertIsInstance(renderer, QgsRuleBasedRenderer)
        root = renderer.rootRule()
        bostad = next(r for r in root.children() if r.label() == "Bostadsbebyggelse")
        children = bostad.children()
        self.assertEqual([c.label() for c in children],
                         ["Ingen etapp (befintligt)", *[s.label for s in STAGES]])
        edge = children[1].symbol().symbolLayer(1)
        self.assertTrue(edge.useCustomDashPattern())  # etapperna har streckad kant
        fills = [c.symbol().symbolLayer(0).color() for c in children[1:]]
        lightness = [f.red() + f.green() + f.blue() for f in fills]
        self.assertEqual(lightness, sorted(lightness))  # mörk till ljus

    def test_the_stage_is_written_under_the_name_in_the_map(self):
        labeling = self.layers[MVA].labeling()
        settings = labeling.settings()
        self.assertTrue(settings.isExpression)
        self.assertIn("utbyggnadsordning", settings.fieldName)

    def test_the_form_offers_the_stages(self):
        layer = self.layers[MVA]
        setup = layer.editorWidgetSetup(layer.fields().indexOf("utbyggnadsordning"))
        self.assertEqual(setup.type(), "ValueMap")
        labels = [list(entry.values())[0] for entry in setup.config()["map"]]
        self.assertIn("Etapp 1 (2027–2035)", labels)

    def test_a_renamed_stage_follows_into_the_content(self):
        self.assigned(values={"innehallstyp_varde": "Bostadsbebyggelse", "namn": "Norr",
                              "utbyggnadsordning": "Etapp 2 (2035–2045)"}).layer.commitChanges(False)
        new = [(0, STAGES[0]), (1, Stage("Etapp 2", "2035–2040")), (2, STAGES[2])]
        utbyggnad.write(self.group, [s for _, s in new])
        self.assertEqual(utbyggnad.rename_in_plan(self.group, utbyggnad.renames(STAGES, new)), 1)
        layer = self.layers[MVA]
        self.assertEqual(next(layer.getFeatures())["utbyggnadsordning"], "Etapp 2 (2035–2040)")

    def test_the_stages_are_there_when_the_plan_is_opened_again(self):
        self.assertEqual(utbyggnad.read(self.group), STAGES)
        project = QgsProject()
        self.addCleanup(project.clear)
        layers = load_plan(self.path, project)
        self.assertIsInstance(layers[MVA].renderer(), QgsRuleBasedRenderer)

    def test_without_stages_land_use_is_drawn_as_before(self):
        utbyggnad.write(self.group, [])
        utbyggnad.refresh(self.group)
        self.assertNotIsInstance(self.layers[MVA].renderer(), QgsRuleBasedRenderer)
        layer = self.layers[MVA]
        self.assertNotEqual(layer.editorWidgetSetup(layer.fields().indexOf("utbyggnadsordning")).type(), "ValueMap")

    def test_the_style_reaches_geoserver_without_functions_in_the_filters(self):
        sld = self.layers[MVA].exportSldStyleV3(QgsSldExportContext()).toString()
        rules = re.sub(r"<se:TextSymbolizer>.*?</se:TextSymbolizer>", "", sld, flags=re.S)
        self.assertNotIn("<ogc:Function", rules)
        self.assertIn("Etapp 1 (2027–2035)", rules)


class DialogTests(ToolCase):
    def test_the_tab_lists_moves_and_returns_the_stages(self):
        dialog = PlanInfoDialog(content.read_plan_info(self.group), [], stages=STAGES)
        self.addCleanup(dialog.deleteLater)
        self.assertEqual(dialog.tabs.tabText(dialog.tabs.count() - 2), "Utbyggnadsordning")
        dialog.stage_table.setCurrentCell(1, 0)
        dialog.move_stage(-1)
        dialog.add_stage(Stage("Etapp 3"))
        self.assertEqual(dialog.stages(), [(1, STAGES[1]), (0, STAGES[0]), (2, STAGES[2]), (None, Stage("Etapp 3"))])

    def test_assigning_land_use_offers_the_plans_stages(self):
        lookups = {lookup.name: [] for lookup in model.LOOKUPS}
        lookups[model.LOOKUPS[0].name] = []
        lookups["utbyggnadsordning"] = [s.label for s in STAGES]
        dialog = AssignDialog("polygon", lookups)
        self.addCleanup(dialog.deleteLater)
        dialog.group.setCurrentIndex(dialog.group.findData("markochvattenanvandning"))
        texts = [dialog.utbyggnadsordning.itemText(i) for i in range(dialog.utbyggnadsordning.count())]
        self.assertEqual(texts, ["", *[s.label for s in STAGES]])
        dialog.utbyggnadsordning.setCurrentIndex(2)
        self.assertEqual(dialog.assignment().values["utbyggnadsordning"], "Etapp 2 (2035–2045)")


if __name__ == "__main__":
    unittest.main()
