"""Lantmäteriets regler för en leverans av översiktsplan (core/rules.py). Ren Python, utan QGIS."""
import copy
import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORE = ROOT / "rita_oversiktsplan" / "core"


def _load(name):
    spec = importlib.util.spec_from_file_location(f"op_{name}", CORE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


rules = _load("rules")
opkatalog = _load("opkatalog")
CATALOG = opkatalog.bundled()
MVA = CATALOG.find("Mark- och vattenanvändning", "Bostadsbebyggelse")


def value(v):
    return {"varde": v.varde, "vardereferens": v.vardereferens, "grupp": v.grupp, "gruppreferens": v.gruppreferens}


def catalog_value(category, name, itself=False):
    found = CATALOG.find(category, name, itself=itself)
    assert found is not None, (category, name)
    return value(found)


PLAN_ID = "11111111-1111-4111-8111-111111111111"
CONTENT_ID = "22222222-2222-4222-8222-222222222222"
DECISION_ID = "33333333-3333-4333-8333-333333333333"
SQUARE = {"typ": "yta", "position": {"type": "Polygon", "coordinates": [[[0, 0], [100, 0], [100, 100], [0, 100],
                                                                         [0, 0]]]}}


def collection():
    plan = {"feature:typ": "oversiktsplan", "objektidentitet": PLAN_ID, "kommunkod": "1494",
            "kommunnamn": "Lidköping", "planhandelse": catalog_value("Planhändelse", "Samrådsunderlag färdigställt"),
            "digitaltUrsprung": True,
            "underlag": [{"underlagstyp": catalog_value("Underlagstyp", "Planeringsunderlag"), "underlag": []}]}
    content = {"feature:typ": "innehallOP", "objektidentitet": CONTENT_ID, "oversiktsplan": PLAN_ID,
               "innehallstyp": value(MVA), "geometri": SQUARE}
    return {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": None, "properties": p}
                                                      for p in (plan, content)]}


def props(data, kind):
    return next(f["properties"] for f in data["features"] if f["properties"]["feature:typ"] == kind)


def rule_ids(data):
    return sorted({f.rule for f in rules.check(data, CATALOG) if f.level == rules.FEL})


class RuleTests(unittest.TestCase):
    def test_a_correct_collection_has_no_errors(self):
        self.assertEqual(rule_ids(collection()), [])

    def test_there_is_exactly_one_plan_and_only_known_feature_types(self):
        data = collection()
        data["features"].append(copy.deepcopy(data["features"][0]))
        data["features"].append({"type": "Feature", "properties": {"feature:typ": "detaljplan"}})
        self.assertEqual(rule_ids(data), ["OP-JSON-001", "OP-JSON-002"])

    def test_the_kommunkod_is_four_digits(self):
        data = collection()
        props(data, "oversiktsplan")["kommunkod"] = "149"
        self.assertEqual(rule_ids(data), ["OP-JSON-004"])

    def test_a_decision_affects_either_the_plan_or_content_never_both(self):
        data = collection()
        data["features"].append({"type": "Feature", "properties": {
            "feature:typ": "beslutOP", "objektidentitet": DECISION_ID,
            "paverkar": [{"identitet": PLAN_ID, "objekttyp": "oversiktsplan"},
                         {"identitet": CONTENT_ID, "objekttyp": "innehallOP"}]}})
        self.assertEqual(rule_ids(data), ["OP-JSON-005"])
        props(data, "beslutOP")["paverkar"] = [{"identitet": CONTENT_ID, "objekttyp": "innehallOP"}]
        self.assertEqual(rule_ids(data), [])
        props(data, "beslutOP")["paverkar"] = []
        self.assertEqual(rule_ids(data), ["OP-JSON-005"])

    def test_an_adopted_plan_needs_review_statement_eia_and_a_decision(self):
        data = collection()
        props(data, "oversiktsplan")["planhandelse"] = catalog_value("Planhändelse", "Antagen")
        found = [f for f in rules.check(data, CATALOG) if f.level == rules.FEL]
        self.assertEqual(sorted({f.rule for f in found}), ["OP-JSON-042", "OP-JSON-044"])
        self.assertEqual(sum(1 for f in found if f.rule == "OP-JSON-042"), 2)  # granskningsyttrande och MKB
        plan = props(data, "oversiktsplan")
        plan["underlag"] += [{"underlagstyp": catalog_value("Underlagstyp", name), "underlag": []}
                             for name in rules.REQUIRED_UNDERLAG]
        data["features"].append({"type": "Feature", "properties": {
            "feature:typ": "beslutOP", "objektidentitet": DECISION_ID,
            "paverkar": [{"identitet": PLAN_ID, "objekttyp": "oversiktsplan"}]}})
        self.assertEqual(rule_ids(data), [])

    def test_plan_geometry_and_area_must_have_a_geometry(self):
        data = collection()
        content = props(data, "innehallOP")
        content["innehallstyp"] = catalog_value("Plangeometri", "Plangeometri")
        del content["geometri"]
        self.assertEqual(rule_ids(data), ["OP-JSON-034"])
        content["innehallstyp"] = catalog_value("Område", "Område")
        self.assertEqual(rule_ids(data), ["OP-JSON-038"])

    def test_bookmarks_and_the_plan_document_format(self):
        data = collection()
        props(data, "innehallOP")["dokument"] = [{"avsnittsbokmarke": ["op_1a2b3c", "1fel"],
                                                  "dokument": {"namn": "Planhandling.pdf"}}]
        self.assertEqual(rule_ids(data), ["OP-JSON-003", "ÖP-X07"])
        props(data, "innehallOP")["dokument"] = [{"avsnittsbokmarke": ["op_1a2b3c"],
                                                  "dokument": {"namn": "Planhandling_bokmarken.docx"}}]
        self.assertEqual(rule_ids(data), [])

    def test_a_catalog_value_must_match_its_id(self):
        data = collection()
        props(data, "innehallOP")["innehallstyp"]["varde"] = "Bostäder"
        self.assertEqual(rule_ids(data), ["OP-JSON-006"])

    def test_an_id_from_another_catalog_version_is_a_warning(self):
        data = collection()
        props(data, "innehallOP")["innehallstyp"]["vardereferens"] = "00000000-0000-4000-8000-000000000000"
        found = rules.check(data, CATALOG)
        self.assertEqual([(f.level, f.rule) for f in found], [(rules.VARNING, "OP-JSON-006")])

    def test_digitised_plans_follow_their_own_rules(self):
        data = collection()
        props(data, "oversiktsplan")["digitaltUrsprung"] = False
        self.assertIn("OP-JSON-032", rule_ids(data))


class GeometryTests(unittest.TestCase):
    def test_a_line_that_crosses_itself_is_found(self):
        self.assertEqual(rules.self_crossings([[0, 0], [10, 10], [10, 0], [0, 10]]), 1)
        self.assertEqual(rules.self_crossings([[0, 0], [10, 0], [10, 10]]), 0)
        self.assertEqual(rules.self_crossings([[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]), 0)  # sluten linje

    def test_a_long_line_is_checked_quickly(self):
        import time
        line = [[i, (i % 2) * 0.5] for i in range(20000)]  # sicksack utan korsningar
        start = time.time()
        self.assertEqual(rules.self_crossings(line), 0)
        self.assertLess(time.time() - start, 5)

    def test_spikes_of_twelve_degrees_or_less_are_found(self):
        self.assertEqual(rules.spikes([[0, 0], [100, 0], [0, 10]], False), 1)  # ca 5,7 grader
        self.assertEqual(rules.spikes([[0, 0], [100, 0], [0, 50]], False), 0)  # ca 26,6 grader
        self.assertEqual(rules.spikes(SQUARE["position"]["coordinates"][0], True), 0)
        self.assertEqual(rules.spikes([[0, 0], [100, 0], [100, 10], [200, 11], [100, 12], [0, 10], [0, 0]], True), 1)

    def test_the_rules_report_lines_and_spikes_on_the_content(self):
        data = collection()
        content = props(data, "innehallOP")
        content["geometri"] = {"typ": "linje", "position": {"type": "LineString",
                                                            "coordinates": [[0, 0], [10, 10], [10, 0], [0, 10]]}}
        found = rules.check(data, CATALOG)
        self.assertIn("ÖP-X04", [f.rule for f in found])
        self.assertTrue(all(f.identity == CONTENT_ID for f in found if f.rule == "ÖP-X04"))


if __name__ == "__main__":
    unittest.main()
