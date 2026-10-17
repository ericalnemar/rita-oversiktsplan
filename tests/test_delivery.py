"""Arkivpaket ur en riktig plan och leveransflödet i pluginet (Leverans och export → Leverera till NGP)."""
import datetime
import json
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from qgis_app import get_app  # noqa: E402

get_app()

from rita_oversiktsplan.core import archive, content, export_lm  # noqa: E402
from rita_oversiktsplan.core import ngp_client as ngp  # noqa: E402
from rita_oversiktsplan.gui import archive_dialog  # noqa: E402
from rita_oversiktsplan.gui.archive_dialog import ArchiveDialog, ArchiveOptions, build_archive  # noqa: E402
from rita_oversiktsplan.gui.delivery_dialog import DeliveryDialog  # noqa: E402
from rita_oversiktsplan.gui.export_dialog import ExportDialog  # noqa: E402
from test_tools import ToolCase  # noqa: E402

APP = archive.App("Rita Översiktsplan", "0.1.1")
NOW = datetime.datetime(2027, 6, 2, 10, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=2)))


class ArchivePlanTests(ToolCase):
    def options(self, **kwargs):
        folder = Path(self.tmp.name) / "arkiv"
        folder.mkdir(exist_ok=True)
        return ArchiveOptions(folder, **kwargs)

    def test_the_package_has_the_geopackage_the_export_and_the_plans_metadata(self):
        self.assigned()
        info = content.read_plan_info(self.group)
        info.beslut = content.Decision("KS 2027/1", datetime.date(2027, 5, 1), None, datetime.date(2027, 6, 1))
        content.write_plan_info(self.group, info, update_content=False)
        package = build_archive(self.group, self.options(), APP, NOW)
        names = sorted(Path(r.path).name for r in package.records)
        self.assertEqual(names, ["ÖP_2040.gpkg", "ÖP_2040.json"])
        self.assertTrue((package.folder / "oversiktsplan.xml").is_file())
        self.assertTrue((package.folder / "metadata" / "PREMIS.xml").is_file())
        general = package.general.read_text(encoding="utf-8")
        for expected in ("ÖP 2040", "Eskilstuna", "0484", "KS 2027/1", "2027-06-01", "Översiktsplan"):
            self.assertIn(expected, general)
        ET.fromstring(general)  # välformad
        exported = json.loads((package.folder / "content" / "ÖP_2040.json").read_text(encoding="utf-8"))
        self.assertEqual(exported["feature:mediatyp"], export_lm.MEDIATYP)
        self.assertTrue(archive.verify_package(package.folder).clean)

    def test_own_documents_and_local_underlag_files_are_included(self):
        pdf = Path(self.tmp.name) / "planhandling.pdf"
        pdf.write_bytes(b"%PDF-1.7\n%%EOF\n")
        with mock.patch.object(archive_dialog, "underlag_files", return_value=[pdf]):
            package = build_archive(self.group, self.options(geopackage=False, documents=[pdf]), APP, NOW)
        names = [Path(r.path).name for r in package.records]
        self.assertEqual(names.count("planhandling.pdf"), 1)  # samma fil bara en gång

    def test_a_changed_file_is_found_when_the_package_is_checked(self):
        package = build_archive(self.group, self.options(geopackage=False), APP, NOW)
        changed = package.folder / package.records[0].path
        changed.write_text("{}", encoding="utf-8")
        report = archive.verify_package(package.folder)
        self.assertFalse(report.clean)
        self.assertEqual(len(report.changed), 1)

    def test_the_dialog_asks_to_stop_editing_first(self):
        self.plugin.start_editing()
        self.assigned()
        dialog = ArchiveDialog(self.group)
        self.assertIn("redigeras", dialog.problem())

    def test_the_menu_entry_builds_the_package_from_the_dialog(self):
        folder = Path(self.tmp.name) / "arkiv"
        folder.mkdir()
        with mock.patch.object(ArchiveDialog, "exec", new=lambda dialog: 1), \
                mock.patch.object(ArchiveDialog, "options", new=lambda dialog: ArchiveOptions(folder)):
            text = self.plugin.open_archive(self.group)
        self.assertTrue(text)
        self.assertEqual(len([p for p in folder.iterdir() if p.is_dir()]), 1)


class FakeClient:
    def __init__(self, status="validerad"):
        self.status, self.calls = status, []

    def deliver(self, collection, kommunkod, existing=None, progress=None):
        self.calls.append((kommunkod, existing))
        return ngp.Delivery("mottagning-1", collection["features"][0]["properties"]["objektidentitet"],
                            ngp.Status(self.status))

    def refresh(self, reception, plan):
        return ngp.Delivery(reception, plan, ngp.Status(self.status))


class PluginDeliveryTests(ToolCase):
    def setUp(self):
        super().setUp()
        self.client = FakeClient()
        self.config = ngp.environment_config("ver", "test-cfg")
        self.shown = []
        for patcher in (mock.patch("rita_oversiktsplan.core.settings.ngp_config", return_value=self.config),
                        mock.patch.object(type(self.plugin), "_make_client", side_effect=lambda config: self.client),
                        mock.patch.object(type(self.plugin), "_run_delivery",
                                          new=lambda plugin, work, done: done(None, work(lambda text: None))),
                        mock.patch.object(DeliveryDialog, "exec", new=lambda dialog: self.shown.append(dialog))):
            patcher.start()
            self.addCleanup(patcher.stop)

    def deliver(self, answer=True):
        collection, problems = export_lm.export(self.group)
        with mock.patch.object(type(self.plugin), "_ask_yes", return_value=answer) as asked:
            result = self.plugin.deliver_ngp(self.group, collection, 0)
        return result, asked

    def test_a_confirmed_delivery_is_sent_remembered_and_shown(self):
        result, asked = self.deliver()
        self.assertIn("bakgrunden", result)
        self.assertIn("ÖP 2040", asked.call_args[0][1])
        self.assertEqual(self.client.calls, [("0484", None)])
        self.assertEqual(self.plugin.last_delivery(self.group)["mottagning"], "mottagning-1")
        self.assertEqual(len(self.shown), 1)

    def test_nothing_is_sent_when_the_user_says_no(self):
        result, _ = self.deliver(answer=False)
        self.assertIsNone(result)
        self.assertEqual(self.client.calls, [])

    def test_a_later_delivery_continues_on_the_earlier_reception(self):
        self.deliver()
        self.deliver()
        self.assertEqual(self.client.calls[1], ("0484", "mottagning-1"))

    def test_missing_settings_stop_the_delivery_with_a_message(self):
        self.config = ngp.NgpConfig("egen", "", "", "")
        with mock.patch("rita_oversiktsplan.core.settings.ngp_config", return_value=self.config):
            result, asked = self.deliver()
        self.assertIsNone(result)
        asked.assert_not_called()
        self.assertIn("Adress", self.iface.bar.pushMessage.call_args[0][1])

    def test_the_dialog_chooses_delivery_and_delivers_without_asking_again(self):
        def run(dialog):
            self.assertTrue(dialog.upload.isEnabled())
            self.assertEqual(dialog.choice(), "upload")
            self.assertIn("ÖP 2040", dialog.upload_info.text())
            self.assertIsNotNone(dialog.run())
            return 0

        with mock.patch.object(ExportDialog, "exec", new=run), \
                mock.patch.object(type(self.plugin), "_ask_yes") as asked:
            self.plugin.export_plan()
        asked.assert_not_called()
        self.assertEqual(self.client.calls, [("0484", None)])

    def test_without_settings_the_file_is_chosen_and_the_reason_is_shown(self):
        self.config = ngp.NgpConfig("egen", "", "", "")

        def run(dialog):
            self.assertFalse(dialog.upload.isEnabled())
            self.assertEqual(dialog.choice(), "file")
            self.assertIn("Adress", dialog.upload_problems.text())
            self.assertFalse(dialog.settings_button.isHidden())
            ok = dialog.buttons.button(dialog.buttons.StandardButton.Ok)
            self.assertEqual(ok.text(), "Spara fil…")
            dialog.archive_radio.setChecked(True)
            self.assertEqual(ok.text(), "Skapa arkivpaket…")
            return 0

        with mock.patch("rita_oversiktsplan.core.settings.ngp_config", return_value=self.config), \
                mock.patch.object(ExportDialog, "exec", new=run):
            self.plugin.export_plan()

    def test_production_needs_the_confirmation_box(self):
        self.config = ngp.environment_config("prod", "test-cfg")

        def run(dialog):
            ok = dialog.buttons.button(dialog.buttons.StandardButton.Ok)
            self.assertFalse(ok.isEnabled())
            dialog.understand.setChecked(True)
            self.assertTrue(ok.isEnabled())
            return 0

        with mock.patch("rita_oversiktsplan.core.settings.ngp_config", return_value=self.config), \
                mock.patch.object(ExportDialog, "exec", new=run):
            self.plugin.export_plan()

    def test_a_cancelled_save_keeps_the_dialog_open(self):
        def run(dialog):
            self.assertIsNone(dialog.save())
            self.assertFalse(dialog.result.text())
            return 0

        with mock.patch.object(type(self.plugin), "_ask_export_path", return_value=""), \
                mock.patch.object(ExportDialog, "exec", new=run):
            self.plugin.export_plan()


if __name__ == "__main__":
    unittest.main()
