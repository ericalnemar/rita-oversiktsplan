"""Programmet Skapa bokmärken i planhandling: tillståndet (session) med en låtsasvärd, och fönstret med en riktig plan i QGIS."""
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

from docx_case import TYPES, write_docx  # noqa: E402
from qgis.core import QgsFeature, QgsGeometry, QgsProject  # noqa: E402
from qgis.PyQt.QtCore import QPointF  # noqa: E402
from qgis.PyQt.QtWidgets import QMessageBox  # noqa: E402

from rita_oversiktsplan.core import documents, geopackage  # noqa: E402
from rita_oversiktsplan.core.project import active_plan_group, load_plan  # noqa: E402
from rita_oversiktsplan.gui.assign_dialog import AssignDialog  # noqa: E402
from rita_oversiktsplan.bookmarks import session as ss  # noqa: E402
from rita_oversiktsplan.bookmarks.main import MainWindow, open_window  # noqa: E402
from rita_oversiktsplan.bookmarks.pages import SavePage  # noqa: E402

PLAN = geopackage.NewPlan("0484", "Eskilstuna", "ÖP 2040", datetime.date(2027, 1, 1))
RISK = "11111111-2222-3333-4444-555555555555"
HOUSING = "22222222-3333-4444-5555-666666666666"
SQUARE = [[(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]]


class FakeHost(ss.Host):
    name = "Testvärd"

    def __init__(self):
        self.saved = {}
        self.objects = [
            ss.PlanObject("plan", "Översiktsplan", "", "ÖP 2040", ss.PLAN_KIND),
            ss.PlanObject(RISK, "Klimatrelaterade risker", "Risk för översvämning", "", "polygon", SQUARE, "#2d6db5"),
            ss.PlanObject(HOUSING, "Mark- och vattenanvändning", "Bostadsbebyggelse", "Norr", "polygon",
                          [[(20, 0), (30, 0), (30, 10), (20, 10), (20, 0)]], "#f5d76e", filled=True,
                          required_text=True),
        ]

    def load_plan(self):
        return ss.PlanData("ÖP 2040", "Eskilstuna", "op.gpkg", list(TYPES), list(self.objects))

    def read_links(self, docx):
        return self.saved.get(Path(docx).name, {})

    def save(self, docx, sections):
        self.saved[Path(docx).name] = {s.bookmark: ss.SavedSection(s.type, set(s.identities)) for s in sections}
        self.paths = [Path(docx)]

    def linked_documents(self):
        return getattr(self, "paths", [])


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.docx = write_docx(Path(self.tmp.name) / "planhandling.docx")
        self.host = FakeHost()
        self.session = ss.Session(self.host)
        self.session.load_plan()
        self.session.load_docx(self.docx)

    def test_sections_get_suggested_types_and_a_reason(self):
        s = self.session
        self.assertEqual([x.heading for x in s.sections][:3], ["Sammanfattning", "Översiktsplanens syfte",
                                                              "Ställningstaganden"])
        self.assertEqual(s.types[0], "Sammanfattning")
        self.assertEqual(s.status(0), ss.FORSLAG)
        self.assertIn("liknar", s.why(0))
        self.assertIn("ovanför", s.why(4))  # Bostadsförsörjning ärver från Bostäder
        self.assertEqual(s.status(7), ss.HOPPAS)  # "Tom rubrik" har ingen text

    def test_changing_the_type_marks_it_as_changed_and_approving_as_reviewed(self):
        s = self.session
        s.set_type(1, "Beskrivning")
        self.assertEqual(s.status(1), ss.ANDRAD)
        self.assertEqual(s.why(1), "Du har valt avsnittstypen.")
        s.approve(1)
        self.assertEqual(s.status(1), ss.GRANSKAD)
        self.assertTrue(s.dirty)

    def test_links_go_both_ways(self):
        s = self.session
        self.assertTrue(s.toggle(5, RISK))
        s.link(6, [RISK])
        self.assertEqual(s.sections_for(RISK), [5, 6])
        self.assertFalse(s.toggle(5, RISK))
        self.assertEqual(s.sections_for(RISK), [6])

    def test_linking_a_skipped_section_tags_it_again(self):
        s = self.session
        s.link(7, ["plan"])
        self.assertNotEqual(s.status(7), ss.HOPPAS)

    def test_the_check_warns_about_land_use_without_text_and_points_to_it(self):
        findings = self.session.findings()
        land_use = [f for f in findings if f.identity == HOUSING]
        self.assertEqual(land_use[0].level, ss.VARNING)
        self.assertTrue(any("hela planen" in f.text for f in findings))
        self.session.link(3, [HOUSING])
        self.assertFalse([f for f in self.session.findings() if f.identity == HOUSING])

    def test_a_link_to_an_object_no_longer_in_the_plan_is_an_error(self):
        self.session.link(5, ["borttagen"])
        errors = [f for f in self.session.findings() if f.level == ss.FEL]
        self.assertEqual(errors[0].section, 5)

    def test_saving_writes_bookmarks_saves_links_and_continues_in_the_copy(self):
        s = self.session
        s.link(0, ["plan"])
        s.link(5, [RISK])
        destination = s.default_destination()
        self.assertEqual(destination.name, "planhandling_bokmarken.docx")
        message = s.save(destination)
        self.assertIn("planhandling_bokmarken.docx", message)
        self.assertEqual(s.docx, destination)
        self.assertFalse(s.dirty)
        bookmark = s.sections[5].bookmark
        self.assertTrue(bookmark.startswith("op_"))
        self.assertEqual(self.host.saved[destination.name][bookmark].identities, {RISK})
        self.assertEqual(len(self.host.saved[destination.name]), len(s.tagged()))
        # öppnas kopian igen är typerna och kopplingarna kvar
        again = ss.Session(self.host)
        again.load_plan()
        again.load_docx(destination)
        self.assertEqual(again.links[5], {RISK})
        self.assertEqual(again.status(5), ss.GRANSKAD)
        self.assertIn("sparade", again.why(5))

    def test_saving_can_also_write_the_web_version_with_the_bookmarks(self):
        s = self.session
        s.link(5, [RISK])
        message = s.save(s.default_destination(), web=True)
        page = s.default_destination().with_suffix(".html")
        self.assertIn(page.name, message)
        text = page.read_text(encoding="utf-8")
        self.assertIn(f'<section id="{s.sections[5].bookmark}" data-avsnittstyp="Ställningstagande">', text)
        self.assertIn("<h1>ÖP 2040</h1>", text)

    def test_opening_the_original_of_a_tagged_plan_warns(self):
        s = self.session
        s.save(s.default_destination())
        again = ss.Session(self.host)
        again.load_plan()
        again.load_docx(self.docx)  # originalet, utan bokmärken
        self.assertEqual(again.other_document, s.default_destination())
        again.load_docx(s.default_destination())  # kopian med bokmärken: ingen varning
        self.assertIsNone(again.other_document)

    def test_the_overview_has_one_row_per_link(self):
        self.session.link(5, [RISK, "plan"])
        rows = [r for r in self.session.overview_rows() if r[1] == "Klimatrisker"]
        self.assertEqual(sorted(r[3] for r in rows), ["Hela planen (ÖP 2040)",
                                                      "Klimatrelaterade risker: Risk för översvämning"])
        self.assertEqual(rows[0][0], "(nytt)")

    def test_the_last_document_is_remembered_per_plan(self):
        self.assertEqual(self.session.recent_docx(), self.docx)


class WindowCase(unittest.TestCase):
    """Fönstret med en riktig plan i QGIS (QgisHost)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.path = geopackage.create_geopackage(Path(self.tmp.name) / "op.gpkg", PLAN)
        self.layers = load_plan(self.path, QgsProject.instance())
        self.addCleanup(self._clear)
        self.group = active_plan_group(QgsProject.instance())
        self.docx = write_docx(Path(self.tmp.name) / "planhandling.docx")

    def _clear(self):
        for layer in self.layers.values():
            if layer.isEditable():
                layer.rollBack()
        QgsProject.instance().clear()

    def add_content(self, table="innehall_op_klimatrelateradrisk_polygon", value="Risk för översvämning",
                    identity=RISK, wkt="MULTIPOLYGON(((0 0, 10 0, 10 10, 0 10, 0 0)))"):
        layer = self.layers[table]
        layer.startEditing()
        feature = QgsFeature(layer.fields())
        feature.setGeometry(QgsGeometry.fromWkt(wkt))
        feature["objektidentitet"] = identity
        feature["innehallstyp_varde"] = value
        layer.addFeature(feature)
        self.assertTrue(layer.commitChanges())
        return layer

    def window(self) -> MainWindow:
        window = open_window(self.group, store=ss.Store())
        self.addCleanup(self._close, window)
        return window

    @staticmethod
    def _close(window):
        window.session.dirty = False
        window.close()

    def loaded(self) -> MainWindow:
        window = self.window()
        self.assertTrue(window.files.load(self.docx))
        return window


class WindowTests(WindowCase):
    def test_the_plan_is_read_from_qgis_with_its_content(self):
        self.add_content()
        self.add_content("innehall_op_markochvattenanvandning_polygon", "Bostadsbebyggelse", HOUSING,
                         "MULTIPOLYGON(((20 0, 30 0, 30 10, 20 10, 20 0)))")
        window = self.window()
        plan = window.session.plan
        self.assertEqual(plan.title, "ÖP 2040")
        self.assertIn("Sammanfattning", plan.types)
        risk = plan.object(RISK)
        self.assertEqual((risk.category, risk.kind, risk.value), ("Klimatrelaterade risker", "polygon",
                                                                  "Risk för översvämning"))
        housing = plan.object(HOUSING)
        self.assertTrue(housing.filled and housing.required_text)
        self.assertEqual(plan.plan_object().kind, ss.PLAN_KIND)

    def test_the_steps_open_only_when_a_document_is_chosen(self):
        window = self.window()
        self.assertFalse(window.steps.button(2).isEnabled())
        window.go(3)
        self.assertIs(window.stack.currentWidget(), window.files)
        window.files.load(self.docx)
        self.assertTrue(window.steps.button(2).isEnabled())
        self.assertIn("planhandling.docx", window.file_hint.text())

    def test_a_document_without_headings_shows_an_error(self):
        window = self.window()
        bad = write_docx(Path(self.tmp.name) / "tom.docx",
                         '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                         "<w:body><w:p><w:r><w:t>Text</w:t></w:r></w:p></w:body></w:document>")
        self.assertFalse(window.files.load(bad))
        self.assertIn("rubriker", window.files.error.text())

    def test_sections_are_reviewed_with_cards_and_keys(self):
        window = self.loaded()
        window.go(2)
        page = window.sections
        self.assertEqual(len(page.cards), 8)
        self.assertEqual(page.selected, 0)
        page.approve()
        self.assertEqual(window.session.status(0), ss.GRANSKAD)
        self.assertEqual(page.selected, 1)  # nästa att granska
        page.type_combo.setCurrentText("Beskrivning")
        page._type_chosen(0)
        self.assertEqual(window.session.types[1], "Beskrivning")
        page.toggle_skip()
        self.assertEqual(window.session.status(1), ss.HOPPAS)
        self.assertEqual(page.skip_button.text(), "Skapa bokmärke")

    def test_clicking_on_the_map_links_and_unlinks(self):
        self.add_content()
        window = self.loaded()
        window.open_section(3, 5)  # Klimatrisker
        page = window.link
        page.map.resize(400, 300)
        page.map.reset_view()
        hit = page.map.object_at(QPointF(200, 150))
        self.assertEqual(hit, RISK)
        page._map_clicked(hit)
        self.assertEqual(window.session.links[5], {RISK})
        self.assertEqual(page.chips.count(), 1)
        item = next(i for i in page._object_items() if i.data(0, 256) == RISK)
        self.assertEqual(item.text(1), "1")  # antalet avsnitt, åt andra hållet
        page._map_clicked(hit)
        self.assertEqual(window.session.links[5], set())

    def test_what_is_selected_in_qgis_and_the_whole_plan_can_be_linked(self):
        layer = self.add_content()
        layer.selectAll()
        window = self.loaded()
        window.open_section(3, 5)
        self.assertEqual(window.link.link_selected(), 1)
        window.link.link_plan()
        self.assertEqual(window.session.links[5], {RISK, documents.plan_identity(self.group)})
        layer.removeSelection()
        window.link.show_in_host()
        self.assertEqual(layer.selectedFeatureCount(), 1)

    def test_new_content_without_geometry_is_created_and_linked(self):
        def choose(assign_dialog):
            assign_dialog.group.setCurrentIndex(assign_dialog.group.findData("bostadsforsorjning"))
            return True

        window = self.loaded()
        window.open_section(3, 4)  # Bostadsförsörjning
        with mock.patch.object(AssignDialog, "exec", new=choose):
            identity = window.link.new_without_geometry()
        self.assertIn(identity, window.session.links[4])
        feature = next(self.layers["innehall_op_bostadsforsorjning_polygon"].getFeatures())
        self.assertEqual(feature["namn"], "Bostadsförsörjning")  # rubriken föreslås som namn
        self.assertIn("utan geometri", window.session.plan.object(identity).long_title())
        self.assertEqual(window.link.chips.count(), 1)

    def test_saving_writes_the_copy_and_the_links_in_the_plan(self):
        self.add_content()
        window = self.loaded()
        window.session.link(0, [documents.plan_identity(self.group)])
        window.session.link(5, [RISK])
        window.go(4)
        self.assertGreater(window.save.table.rowCount(), 0)
        destination = Path(self.tmp.name) / "planhandling_bokmarken.docx"
        with mock.patch.object(SavePage, "ask_destination", return_value=destination):
            self.assertEqual(window.save.save(), destination)
        bookmark = window.session.sections[5].bookmark
        links = documents.read_links(self.group, destination)
        self.assertEqual(links[bookmark].identities, {RISK})
        self.assertEqual(links[bookmark].type, "Ställningstagande")
        self.assertIn("planhandling_bokmarken.docx", window.save.result.text())
        self.assertEqual(self.layers["dokumentavsnitt"].featureCount(), 2)

    def test_saving_with_the_web_box_ticked_writes_the_html_and_the_original_then_warns(self):
        self.add_content()
        window = self.loaded()
        window.session.link(5, [RISK])
        window.go(4)
        window.save.web.setChecked(True)
        destination = Path(self.tmp.name) / "planhandling_bokmarken.docx"
        with mock.patch.object(SavePage, "ask_destination", return_value=destination):
            window.save.save()
        self.assertTrue(destination.with_suffix(".html").exists())
        self.assertIn("Öppna webbversionen", window.save.result.text())
        window.files.load(self.docx)  # originalet igen
        self.assertFalse(window.files.other.isHidden())
        self.assertIn("planhandling_bokmarken.docx", window.files.other_text.text())
        window.files.open_other()
        self.assertEqual(window.session.docx, destination)
        self.assertTrue(window.files.other.isHidden())

    def test_a_check_finding_goes_to_the_section(self):
        window = self.loaded()
        window.go(4)
        finding = next(f for f in window.session.findings() if f.section is not None)
        window.save._action_for(finding)()
        self.assertIn(window.stack.currentWidget(), (window.sections, window.link))

    def test_closing_with_unsaved_changes_asks_first(self):
        window = self.loaded()
        window.session.link(0, [documents.plan_identity(self.group)])
        with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No) as asked:
            window.close()
        asked.assert_called_once()
        self.assertTrue(window.isVisible())


if __name__ == "__main__":
    unittest.main()
