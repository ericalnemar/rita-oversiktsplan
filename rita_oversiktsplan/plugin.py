"""Pluginets huvudklass: meny, verktygsfält och kommandon.

Arbetsgången är som i Rita Detaljplan: man ritar först en yta, linje eller punkt (den hamnar i lagren under *Att
tilldela*), och ger den sedan innehåll med verktyget *Tilldela innehåll*. Det som gäller hela planen ställs in under
*Planens uppgifter*. *Avsluta redigering* (disketten) sparar eller förkastar ändringarna, som i Rita Detaljplan."""
from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Optional

import json

from qgis.core import Qgis, QgsApplication, QgsPointXY, QgsProject, QgsRectangle, QgsTask, QgsVectorLayer
from qgis.PyQt.QtCore import Qt, QTimer
from qgis.PyQt.QtGui import QCursor, QIcon
from qgis.PyQt.QtWidgets import QAction, QApplication, QFileDialog, QMenu, QMessageBox
from qgis.PyQt import sip

from .core import (archive, checkout, content, editing, export_lm, geopackage, importer, model, relations, settings,
                   kommunyta, riksintressen, sld, storage, underlag, utbyggnad)
from .core import ngp_client as ngp
from .core.project import (PlanError, active_plan_group, draft_layers, is_read_only, layer_in_group, load_plan,
                           plan_groups, plan_storage)
from .gui.about_dialog import AboutDialog
from .gui.andring_dialog import AndringDialog
from .gui.archive_dialog import ArchiveDialog, build_archive
from .gui.topografi_dialog import TopografiDialog
from .gui.riksintressen_dialog import RiksintressenDialog, qgis_get
from .gui.assign_dialog import AssignDialog
from .gui.assign_tool import AssignTool
from .gui.checkout_actions import CheckoutActions
from .gui.copy_tool import CopyTool
from .gui.delivery_dialog import DeliveryDialog, confirmation_text
from .gui.export_dialog import ExportDialog
from .gui.import_dialog import ImportDialog
from .gui.messages import push
from .gui.new_plan_dialog import DATABASE, NewPlanDialog
from .gui.plan_info_dialog import PlanInfoDialog
from .gui.postgis_plan_dialog import PostgisPlanDialog
from .gui.select_tool import SelectTool
from .gui.settings_dialog import SettingsDialog
from .gui.toolbar import PlanToolBar, icon

MENU = "&Rita Översiktsplan"
TITLE = "Rita Översiktsplan"
BRAND_ICON = Path(__file__).parent / "icon.svg"
NO_PLAN = "Ingen översiktsplan är öppen. Skapa en med Ny översiktsplan eller öppna en befintlig."


class OversiktsplanPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.actions: list[QAction] = []
        self.toolbar: PlanToolBar | None = None
        self.map_tools: dict = {}  # kartverktygen (assign, select, copy), skapas när de används första gången
        self.copy_source: Optional[content.Candidate] = None  # Kopiera innehåll: objektet man kopierar från
        self.copy_assignment: Optional[content.Assignment] = None
        self.relate_source: Optional[content.Candidate] = None  # Berör annat innehåll: innehållet man utgår från
        self.document_window = None  # programmet Skapa bokmärken i planhandling, om det är öppet
        self._tasks: list = []  # leveranser till NGP som pågår i bakgrunden
        self.checkout = CheckoutActions(lambda text, warning: (self._warn if warning else self._info)(text),
                                        iface.mainWindow(), after=self.refresh_tools)

    @property
    def assign_tool(self) -> Optional[AssignTool]:
        return self.map_tools.get("assign")

    # -- livscykel ----------------------------------------------------------------
    def initGui(self):  # noqa: N802 - namnet krävs av QGIS
        self.toolbar = PlanToolBar(self.iface, self, self.iface.mainWindow())
        self.iface.addToolBar(self.toolbar)
        if hasattr(self.iface, "currentLayerChanged"):  # knapparna följer planen man arbetar med
            self.iface.currentLayerChanged.connect(self.refresh_tools)
        project = QgsProject.instance()
        project.readProject.connect(self.project_read)
        project.layersAdded.connect(self._watch_layers)
        project.layersRemoved.connect(self._refresh_later)
        self._watch_layers(list(project.mapLayers().values()))
        self.refresh_tools()

        self._add_action("Ny översiktsplan…", self.new_plan, icon("new.svg"))  # samma ikoner som i verktygsfältet
        self._add_action("Öppna översiktsplan…", self.open_plan, icon("open.svg"))
        self._add_action("Importera geometri…", self.import_geometry, icon("import.svg"))
        self._add_action("Planens uppgifter…", self.open_info, icon("info.svg"))
        self._add_action("Ändring av översiktsplanen…", self.open_andring)
        self._add_action("Hämta riksintressen…", self.fetch_riksintressen)
        self._add_action("Skapa kommunens ställningstagande för markerade riksintressen", self.create_positions)
        self._add_action("Markanvändning från Topografi 10…", self.open_topografi, icon("topografi.svg"))
        self._add_action("Leverans och export…", self.export_plan, icon("export.svg"))
        self._add_action("Skapa arkivpaket…", self.open_archive)
        self._add_action("Kontrollera arkivpaket…", self.verify_archive)
        self._add_action("Inställningar för leverans till NGP…", self.open_settings)
        self._add_action("Spara stilar för GeoServer (SLD)…", self.export_sld)
        self._add_action("Skapa bokmärken i planhandling…", self.open_document, icon("planhandling.svg"))
        self._add_action("Spara alla redigeringar", self.save_all, icon("save.svg"))
        self.iface.addPluginToMenu(MENU, self._separator())
        toggle = self.toolbar.toggleViewAction()  # visa eller dölj verktygsfältet, som i QGIS lista över verktygsfält
        self.iface.addPluginToMenu(MENU, toggle)
        self.actions.append(toggle)
        self.iface.addPluginToMenu(MENU, self._separator())
        self._add_action("Om Rita Översiktsplan…", self.open_about)
        self._brand_menu()

    def unload(self):
        project = QgsProject.instance()
        for signal, slot in ((project.readProject, self.project_read), (project.layersAdded, self._watch_layers),
                             (project.layersRemoved, self._refresh_later)):
            try:
                signal.disconnect(slot)
            except TypeError:
                pass
        for layer in project.mapLayers().values():
            if isinstance(layer, QgsVectorLayer):
                for signal in (layer.editingStarted, layer.editingStopped):
                    try:
                        signal.disconnect(self.refresh_tools)
                    except TypeError:
                        pass
        if hasattr(self.iface, "currentLayerChanged"):
            try:
                self.iface.currentLayerChanged.disconnect(self.refresh_tools)
            except TypeError:
                pass
        for name in tuple(self.map_tools):
            self._set_tool(name, False)
        window = self._document_window()
        if window is not None:
            window.session.dirty = False  # pluginet stängs: fråga inte
            window.close()
        self.document_window = None
        for action in self.actions:
            self.iface.removePluginMenu(MENU, action)
        self.actions.clear()
        if self.toolbar is not None:
            main_window = self.iface.mainWindow()
            if main_window is not None:
                main_window.removeToolBar(self.toolbar)
            self.toolbar.deleteLater()
            self.toolbar = None

    # -- planen -------------------------------------------------------------------
    def _save_project_file(self, qgz: Path) -> str:
        """Sparar det öppna projektet som den nya planens projektfil (som i Rita Detaljplan), så att man inte behöver
        spara det separat. Ett projekt som redan är sparat som något annat (planen lades till i ett befintligt
        projekt) rörs inte. Returnerar en mening om vad som hände, eller tom text."""
        project = QgsProject.instance()
        if project.fileName():
            return ""
        if project.write(str(qgz)):
            return f" Projektet är sparat som {qgz.name}."
        self._warn(f"Kunde inte spara projektfilen {qgz}: {project.error()}")
        return ""

    def new_plan(self):
        dialog = NewPlanDialog(self.iface.mainWindow())
        if not dialog.exec():
            return
        qgz = dialog.project_file()
        if qgz.exists() and not QgsProject.instance().fileName():
            self._warn(f"Det finns redan en projektfil som heter {qgz.name} i mappen. Välj ett annat filnamn.")
            return
        plan, area_note = self._with_municipality_area(dialog.plan(), dialog.municipality_area.isChecked())
        if dialog.destination() == DATABASE:
            connection, schema, plan_id = dialog.database_target()
            try:
                target = storage.create_postgis_plan(connection, schema, plan_id, plan)
            except (storage.PostgisError, OSError, RuntimeError, ValueError) as exc:
                self._warn(f"Kunde inte skapa översiktsplanen i databasen: {exc}")
                return
            if self._load(target):
                self._info(f"Skapade planen {plan_id} i schemat {schema}.{area_note} Den är skrivskyddad i databasen: "
                           "checka ut den för att rita." + self._save_project_file(qgz))
            return
        target = dialog.target()
        try:
            geopackage.create_geopackage(target, plan)
        except FileExistsError:
            self._warn(f"Det finns redan en fil som heter {target.name} i mappen. Välj ett annat filnamn.")
            return
        except (OSError, RuntimeError, ValueError) as exc:
            self._warn(f"Kunde inte skapa översiktsplanen: {exc}")
            return
        if self._load(target):
            self._info(f"Skapade {target.name}.{area_note} Rita en yta, linje eller punkt och ge den innehåll med "
                       "Tilldela innehåll." + self._save_project_file(qgz))

    def _with_municipality_area(self, plan: geopackage.NewPlan, wanted: bool) -> tuple[geopackage.NewPlan, str]:
        """Planen med kommunens yta som plangeometri (om den önskas och går att hämta), och en mening om vad som
        hände. Går den inte att hämta skapas planen ändå, utan plangeometri."""
        if not wanted:
            return plan, ""
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            shapes = kommunyta.fetch_municipality(qgis_get, plan.kommunkod, plan.epsg)
        except (riksintressen.FetchError, ValueError, OSError) as exc:
            self._warn(f"Kunde inte hämta kommunens yta: {exc} Planen skapas utan plangeometri; rita den själv.")
            return plan, " Kommunens yta kunde inte hämtas, så plangeometrin saknas."
        finally:
            QApplication.restoreOverrideCursor()
        return dataclasses.replace(plan, plan_area=tuple(shapes)), " Kommunens yta är plangeometri."

    def open_plan(self):
        """Öppnar en plan från en fil, eller (om QGIS har PostgreSQL-anslutningar) från en databas."""
        source = self._ask_open_source() if storage.postgis_connections() else "file"
        if source == "database":
            self.open_database_plan()
            return
        if source != "file":
            return
        path, _ = QFileDialog.getOpenFileName(self.iface.mainWindow(), "Öppna översiktsplan", "",
                                              "GeoPackage (*.gpkg)")
        if path and self._load(Path(path)):
            self._info(f"Öppnade {Path(path).name}.")

    def open_database_plan(self) -> bool:
        dialog = PostgisPlanDialog(self.iface.mainWindow())
        if not dialog.exec() or dialog.selection() is None:
            return False
        connection, schema, plan_id = dialog.selection()
        if not self._load(storage.PostgisStorage(connection, schema, plan_id)):
            return False
        self._info(f"Öppnade planen {plan_id} från databasen. Den är skrivskyddad: checka ut den för att rita.")
        return True

    def _ask_open_source(self) -> Optional[str]:
        """En liten meny vid muspekaren (som i Rita Detaljplan): fil eller databas."""
        menu = QMenu(self.iface.mainWindow())
        file_action = menu.addAction(icon("open.svg"), "Lokal fil (GeoPackage)…")
        db_action = menu.addAction(icon("checkout.svg"), "PostGIS-databas…")
        chosen = menu.exec(QCursor.pos())
        return "file" if chosen is file_action else "database" if chosen is db_action else None

    # -- checka ut och in -------------------------------------------------------------
    def toggle_checkout(self) -> bool:
        """Knappen Checka ut / Checka in, beroende på var planen ligger just nu."""
        group = self._group()
        if group is None:
            return False
        state = checkout.state(group)
        if state == checkout.LOCAL:
            for name in tuple(self.map_tools):
                self._set_tool(name, False)
            return self.checkout.check_in(group)
        if state == checkout.DATABASE:
            return self.checkout.check_out(group)
        self._info("Planen ligger i en fil och behöver inte checkas ut.")
        return False

    def project_read(self, *_) -> None:
        """Ett sparat projekt öppnas: planer som läses direkt från databasen ska vara skrivskyddade."""
        for group in plan_groups(QgsProject.instance()):
            checkout.enforce_read_only(group)
        self.refresh_tools()

    def _refresh_later(self, *_) -> None:
        """Lager tas bort (till exempel när projektet töms): uppdatera knapparna först när det är klart, inte mitt i."""
        QTimer.singleShot(0, self.refresh_tools)

    def _watch_layers(self, layers) -> None:
        """Knapparna som kräver en redigeringssession följer lagrens redigeringsläge."""
        for layer in layers:
            if isinstance(layer, QgsVectorLayer):
                layer.editingStarted.connect(self.refresh_tools)
                layer.editingStopped.connect(self.refresh_tools)
        self.refresh_tools()

    def refresh_tools(self, *_) -> None:
        """Gråar knappar som inte kan användas just nu: allt utom Ny och Öppna kräver en öppen plan, och att rita,
        importera, tilldela och kopiera kräver att redigeringen är påbörjad (pennan)."""
        if self.toolbar is None:
            return
        group = active_plan_group(QgsProject.instance(), self.iface.activeLayer())
        is_editing = group is not None and editing.is_editing(group)
        if not is_editing:
            for name in ("assign", "copy", "relate"):
                if name in self.map_tools:
                    self._set_tool(name, False)
        self.toolbar.set_state(group is not None, is_editing,
                               checkout.state(group) if group is not None else checkout.FILE)
        self._apply_label_visibility()  # en plan som just lästs in har sina texter påslagna

    def labels_hidden(self) -> bool:
        return self.toolbar is not None and self.toolbar.act_hide_labels.isChecked()

    def set_labels_hidden(self, hidden: bool) -> None:
        """Dölj texter (som i Rita Detaljplan): namnen på kartan är avstängda i alla öppna planer så länge knappen är
        nedtryckt."""
        self._apply_label_visibility(repaint=True)

    def _apply_label_visibility(self, repaint: bool = False) -> None:
        show = not self.labels_hidden()
        for group in plan_groups(QgsProject.instance()):
            for layer_def in model.CONTENT_LAYERS:
                layer = layer_in_group(group, layer_def.name)
                if layer is None or layer.labeling() is None:
                    continue
                if layer.labelsEnabled() != show:
                    layer.setLabelsEnabled(show)
                    layer.triggerRepaint()
                elif repaint:
                    layer.triggerRepaint()

    def _editable(self, group) -> bool:
        """En plan i databasen är skrivskyddad: erbjud att checka ut den. True om planen går att ändra."""
        if not is_read_only(group):
            return True
        return self.checkout.check_out(group)

    def open_info(self):
        """Planens uppgifter: planen, planhändelsen och standardvärdena för nytt innehåll. Sparas direkt med
        dialogens Spara-knapp."""
        group = self._group()
        if group is None:
            return
        try:
            info = content.read_plan_info(group)
        except ValueError as exc:
            self._warn(f"{exc}. Skapa planen på nytt med Ny översiktsplan.")
            return
        if not self._editable(group):
            return
        events = plan_storage(group).read_lookup(model.PLANHANDELSE_LOOKUP)
        try:
            current = underlag.read_underlag(group)
        except ValueError as exc:
            self._warn(str(exc))
            return
        stages = utbyggnad.read(group)
        dialog = PlanInfoDialog(info, events, self.iface.mainWindow(), current,
                                plan_storage(group).read_lookup(model.UNDERLAGSTYP_LOOKUP), stages)
        if not dialog.exec():
            return
        try:
            changed = content.write_plan_info(group, dialog.plan_info(), dialog.update_content.isChecked())
            if dialog.underlag() != current:
                underlag.save_underlag(group, dialog.underlag())
            new_stages = dialog.stages()
            if [stage for _, stage in new_stages] != stages:
                utbyggnad.write(group, [stage for _, stage in new_stages])
                utbyggnad.rename_in_plan(group, utbyggnad.renames(stages, new_stages))
                utbyggnad.refresh(group)
        except ValueError as exc:
            self._warn(str(exc))
            return
        group.setName(f"Översiktsplan – {dialog.plan_info().titel or plan_storage(group).name}")
        self._info("Sparade planens uppgifter." + (f" {changed} objekt fick planens planhändelse." if changed else ""))

    def open_andring(self) -> Optional[AndringDialog]:
        """Ändring av översiktsplanen: påbörja, sköta och anta en ändring (se ``core.andring``)."""
        group = self._group()
        if group is None or not self._editable(group):
            return None
        dialog = AndringDialog(group, plan_storage(group).read_lookup(model.PLANHANDELSE_LOOKUP),
                               self.iface.mainWindow())
        dialog.exec()
        self.refresh_tools()
        return dialog

    def _plan_area(self, group):
        """Planens avgränsning: plangeometrins ytor sammanslagna, eller None."""
        return kommunyta.plan_area(group)

    def _map_extent(self, group):
        """Kartans utsnitt i planens koordinatsystem."""
        from qgis.core import QgsCoordinateReferenceSystem, QgsCoordinateTransform
        canvas = self.iface.mapCanvas()
        target = QgsCoordinateReferenceSystem(f"EPSG:{plan_storage(group).epsg}")
        transform = QgsCoordinateTransform(canvas.mapSettings().destinationCrs(), target, QgsProject.instance())
        return transform.transformBoundingBox(canvas.extent())

    def fetch_riksintressen(self) -> Optional[RiksintressenDialog]:
        """Hämta riksintressen ur Boverkets tjänst som underlag i planen (se ``core.riksintressen``)."""
        group = self._group()
        if group is None or not self._editable(group):
            return None
        if not editing.is_editing(group) and not self.start_editing():
            return None
        dialog = RiksintressenDialog(group, plan_storage(group).epsg, self._plan_area(group), self._map_extent(group),
                                     self.iface.mainWindow())
        dialog.exec()
        if dialog.added:
            self._info(f"Lade in {sum(dialog.added.values())} riksintressen som underlag. Spara med Avsluta "
                       "redigering (disketten).")
        return dialog

    def open_topografi(self) -> Optional[TopografiDialog]:
        """Befintlig mark- och vattenanvändning ur Lantmäteriets Topografi 10 eller Marktäcke (se ``core.topografi``)."""
        from qgis.core import QgsCoordinateReferenceSystem
        group = self._group()
        if group is None:
            self._warn("Ingen översiktsplan är öppen.")
            return None
        if not self._editable(group):
            return None
        if not editing.is_editing(group) and not self.start_editing():
            return None
        land_use = next(c for c in model.CATEGORIES if c.key == "markochvattenanvandning")
        lookup = next(l for l in model.LOOKUPS if l.name == land_use.lookup)
        storage_ = plan_storage(group)
        dialog = TopografiDialog(group, storage_.read_lookup(lookup),
                                 QgsCoordinateReferenceSystem(f"EPSG:{storage_.epsg}"), self._plan_area(group),
                                 self.iface.mainWindow())
        dialog.exec()
        if dialog.outcome is not None:
            self._info("Skapade befintlig mark- och vattenanvändning från Lantmäteriet. Spara med Avsluta "
                       "redigering (disketten).")
        self.refresh_tools()
        return dialog

    def create_positions(self) -> int:
        """Kopierar de markerade hämtade riksintressena till Riksintresse, kommunens ställningstagande (se
        ``core.riksintressen.create_positions``). Returnerar antalet nya ställningstaganden."""
        group = self._group()
        if group is None:
            self._warn("Ingen översiktsplan är öppen.")
            return 0
        sources = riksintressen.selected_sources(group)
        if not sources:
            self._warn("Markera först de riksintressen kommunen tar ställning till, med verktyget Markera, i gruppen "
                       "Riksintressen enligt 3 och 4 kap. MB.")
            return 0
        if not self._editable(group):
            return 0
        if not editing.is_editing(group) and not self.start_editing():
            return 0
        try:
            added = sum(riksintressen.create_positions(group, sources).values())
        except ValueError as exc:
            self._warn(str(exc))
            return 0
        skipped = len(sources) - added
        self._info(f"Skapade {added} ställningstaganden i Riksintresse, kommunens ställningstagande"
                   + (f"; {skipped} riksintressen hade redan ett." if skipped else ".")
                   + " Justera gränserna vid behov och spara med Avsluta redigering (disketten).")
        self.refresh_tools()
        return added

    def export_plan(self) -> Optional[ExportDialog]:
        """Leverans och export: kontrollerar planen och sparar, levererar eller arkiverar den. Planen läses med osparade
        ändringar."""
        group = self._group()
        if group is None:
            return None
        try:
            collection, problems = export_lm.export(group)
        except (OSError, ValueError, RuntimeError) as exc:
            self._warn(f"Kunde inte exportera planen: {exc}")
            return None

        def save() -> Optional[str]:
            where = plan_storage(group)
            name = (group.name().split("–", 1)[-1].strip() or where.name)
            safe = "".join(c if c.isalnum() or c in "-_ " else "_" for c in name).strip() or "oversiktsplan"
            folder = where.path.parent if isinstance(where, storage.GeoPackageStorage) else Path.home()
            path = self._ask_export_path(str(folder / f"{safe}.json"))
            if not path:
                return None
            try:
                Path(path).write_text(export_lm.dumps(collection), encoding="utf-8")
            except OSError as exc:
                self._warn(f"Kunde inte spara: {exc}")
                return None
            text = f"Sparade {Path(path).name}."
            self._info(text)
            return text

        errors = sum(1 for p in problems if p.level == export_lm.FEL)
        plan_id = next((f["properties"].get("objektidentitet") for f in collection["features"]
                        if f["properties"].get("feature:typ") == "oversiktsplan"), None)
        dialog = ExportDialog(collection, problems, save, lambda table, fid: self._show_feature(group, table, fid),
                              self.iface.mainWindow(),
                              deliver=lambda: self.deliver_ngp(group, collection, errors, confirmed=True),
                              archive=lambda: self.open_archive(group), settings=self.open_settings,
                              config=lambda: settings.ngp_config(),
                              resuming=lambda config: self._resuming(group, config, plan_id))
        dialog.exec()
        return dialog

    # -- NGP och arkiv ------------------------------------------------------------------
    NGP_PROPERTY = "rita_oversiktsplan/ngp"  # på planens grupp: senaste leveransen (mottagning, plan, miljö) som JSON

    def last_delivery(self, group) -> dict:
        try:
            return json.loads(group.customProperty(self.NGP_PROPERTY) or "{}")
        except ValueError:
            return {}

    def remember_delivery(self, group, reception: str, plan: str, environment: str) -> None:
        group.setCustomProperty(self.NGP_PROPERTY, json.dumps({"mottagning": reception, "plan": plan,
                                                               "miljo": environment}))

    def _ask_yes(self, title: str, text: str, yes: str) -> bool:  # byts ut i tester
        box = QMessageBox(self.iface.mainWindow())
        box.setWindowTitle(title)
        box.setTextFormat(Qt.TextFormat.RichText)
        box.setText(text)
        ok = box.addButton(yes, QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Avbryt", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        return box.clickedButton() is ok

    def _make_client(self, config: "ngp.NgpConfig") -> "ngp.NgpClient":  # byts ut i tester
        return ngp.NgpClient(config)

    def _resuming(self, group, config, plan_id) -> bool:
        """Om leveransen fortsätter på den tidigare mottagningen (samma miljö och samma plan)."""
        last = self.last_delivery(group)
        return bool(last) and last.get("miljo") == config.environment and last.get("plan") == plan_id

    def deliver_ngp(self, group, collection: dict, errors: int, confirmed: bool = False) -> Optional[str]:
        """Levererar planen till NGP i en bakgrundsuppgift. Utan ``confirmed`` frågar pluginet först och säger vart och
        med vilka fel (i dialogen Leverans och export står det redan i leveransrutan). En tidigare mottagning som fick
        valideringsfel återanvänds. Resultatet visas i en egen dialog."""
        config = settings.ngp_config()
        plan = next((f["properties"] for f in collection["features"]
                     if f["properties"].get("feature:typ") == "oversiktsplan"), {})
        problems = ([] if plan.get("kommunkod") else ["Kommunkoden saknas i planen."]) + config.problems()
        if problems:
            self._warn("Leverans till NGP: " + " ".join(problems) + " Öppna Inställningar i dialogen Leverans och "
                       "export.")
            return None
        last = self.last_delivery(group)
        resuming = self._resuming(group, config, plan.get("objektidentitet"))
        text = confirmation_text(config, plan.get("planensTitel", ""), plan.get("kommunnamn", ""),
                                 plan.get("kommunkod", ""), errors, resuming)
        if not confirmed and not self._ask_yes("Leverera till NGP", text, "Leverera"):
            return None
        client = self._make_client(config)
        existing = last.get("mottagning") if resuming else None
        self._info("Levererar planen till NGP i bakgrunden …")

        def work(progress):
            return client.deliver(collection, plan["kommunkod"], existing, progress)

        def done(exception, result=None):
            if exception is not None:
                message = str(exception) if isinstance(exception, ngp.NgpError) else \
                    f"{type(exception).__name__}: {exception}"
                self._warn(f"Leveransen till NGP misslyckades. {message}")
                return
            self.remember_delivery(group, result.mottagningsid, result.plan_id, config.environment)
            (self._info if result.ok else self._warn)(f"Leveransen till NGP ({config.title}) fick status "
                                                      f"{result.status.typ}.")
            DeliveryDialog(result, config.title, lambda: client.refresh(result.mottagningsid, result.plan_id),
                           self.iface.mainWindow()).exec()

        self._run_delivery(work, done)
        return "Leveransen till NGP pågår i bakgrunden. Resultatet visas när den är klar."

    def _run_delivery(self, work, done) -> None:
        """Kör ``work(progress)`` i en bakgrundsuppgift och anropar ``done(exception, result)`` i huvudtråden."""
        holder = {}

        def run(task):
            return work(lambda text: task.setDescription(f"Levererar till NGP: {text}"))

        def finished(exception, result=None):
            self._tasks = [t for t in self._tasks if t is not holder.get("task")]
            done(exception, result)

        task = QgsTask.fromFunction("Levererar översiktsplanen till NGP", run, on_finished=finished)
        holder["task"] = task
        self._tasks.append(task)
        QgsApplication.taskManager().addTask(task)

    def open_settings(self) -> None:
        SettingsDialog(self.iface.mainWindow()).exec()

    def open_archive(self, group=None) -> Optional[str]:
        """Skapar ett arkivpaket med bevarandemetadata (se ``core.archive``). Returnerar en text om resultatet."""
        group = group or self._group()
        if group is None:
            return None
        dialog = ArchiveDialog(group, self.iface.mainWindow())
        if not dialog.exec():
            return None
        QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
        try:
            package = build_archive(group, dialog.options())
        except archive.ArchiveError as exc:
            self._warn(str(exc))
            return None
        finally:
            QApplication.restoreOverrideCursor()
        text = f"Arkivpaketet {package.folder.name} är skapat med {len(package.records)} filer i {package.folder.parent}."
        self._info(text)
        if package.notes:
            self._warn("Att tänka på: " + " ".join(package.notes))
        return text

    def _ask_folder(self, title: str) -> str:  # byts ut i tester
        home = QgsProject.instance().homePath() or ""
        return QFileDialog.getExistingDirectory(self.iface.mainWindow(), title, home)

    def export_sld(self, group=None) -> Optional[list[Path]]:
        """Sparar en stilfil (SLD) per innehållslager, anpassad för GeoServer: pilspetsarna i utvecklingsinriktningens
        linjeändar görs om till GeoServers form (se ``core.sld``). Filen heter som tabellen."""
        from qgis.core import QgsSldExportContext
        group = group or self._group()
        if group is None:
            return None
        chosen = self._ask_folder("Välj mapp för stilfilerna (SLD)")
        if not chosen:
            return None
        written = []
        for layer_def in model.CONTENT_LAYERS:
            layer = layer_in_group(group, layer_def.name)
            if layer is None:
                continue
            context = QgsSldExportContext()
            text = sld.for_geoserver(layer.exportSldStyleV3(context).toString())
            target = Path(chosen) / f"{layer_def.name}.sld"
            try:
                target.write_text(text, encoding="utf-8")
            except OSError as exc:
                self._warn(f"Kunde inte spara {target.name}: {exc}")
                return None
            written.append(target)
        self._info(f"Sparade {len(written)} stilfiler (SLD) för GeoServer i {chosen}. Lagrens namn i GeoServer ska "
                   "vara tabellernas namn, och geometrikolumnen heter geom.")
        return written

    def verify_archive(self) -> Optional["archive.VerifyReport"]:
        """Räknar om kontrollsummorna i ett arkivpaket och visar om något ändrats."""
        home = QgsProject.instance().homePath() or ""
        chosen = QFileDialog.getExistingDirectory(self.iface.mainWindow(), "Välj arkivpaketets mapp", home)
        if not chosen:
            return None
        try:
            report = archive.verify_package(Path(chosen))
        except archive.ArchiveError as exc:
            self._warn(str(exc))
            return None
        box = QMessageBox(self.iface.mainWindow())
        box.setWindowTitle("Kontrollera arkivpaket")
        box.setIcon(QMessageBox.Icon.Information if report.clean else QMessageBox.Icon.Warning)
        box.setText("Arkivpaketet är oförändrat." if report.clean else "Arkivpaketet skiljer sig från hur det skapades.")
        box.setInformativeText(report.text())
        box.exec()
        return report

    def _ask_export_path(self, suggestion: str) -> str:
        path, _ = QFileDialog.getSaveFileName(self.iface.mainWindow(), "Spara översiktsplanen som JSON", suggestion,
                                              "Översiktsplan (JSON) (*.json)")
        return path

    def _show_feature(self, group, table: str, fid: int) -> None:
        """Markerar och zoomar till ett objekt som kontrollen pekar på."""
        layer = layer_in_group(group, table)
        if layer is None:
            return
        self.iface.setActiveLayer(layer)
        if layer.isSpatial():
            editing.clear_selection(group)
            layer.selectByIds([fid])
            feature = layer.getFeature(fid)
            canvas = self.iface.mapCanvas() if hasattr(self.iface, "mapCanvas") else None
            if canvas is not None and feature.hasGeometry():
                canvas.zoomToFeatureIds(layer, [fid])
        elif hasattr(self.iface, "showAttributeTable"):
            self.iface.showAttributeTable(layer)

    def _document_window(self):
        window = self.document_window
        return window if window is not None and not sip.isdeleted(window) else None

    def open_document(self):
        """Skapa bokmärken i planhandling: ett eget fönster (som Tagga planbeskrivning i Rita Detaljplan) där planhandlingens
        avsnitt granskas och kopplas till planens innehåll. Fönstret är inte modalt, så att man kan markera och rita i
        kartan medan det är öppet. Är det redan öppet för samma plan läses planen om och fönstret visas."""
        group = self._group()
        if group is None:
            return
        from .bookmarks.main import open_window

        window = self._document_window()
        if window is not None and window.session.host.group is group:
            window.reload_plan()
            window.show()
            window.raise_()
            window.activateWindow()
            return
        if window is not None:
            window.close()
        self.document_window = open_window(group, self.iface.mainWindow())

    # -- rita och tilldela ----------------------------------------------------------
    def draw(self, suffix: str):
        """Ritar en ny yta, linje eller punkt utan innehåll: lagret under Att tilldela blir aktivt och synligt,
        redigeringen slås på och verktyget för att lägga till objekt väljs."""
        group = self._group()
        if group is None:
            return
        if not self._editable(group):
            return
        layer = draft_layers(group).get(suffix)
        if layer is None:
            self._warn(f"Lagret {model.DRAFT_LAYERS[suffix].alias} saknas i planen. Öppna planen på nytt.")
            return
        for name in tuple(self.map_tools):
            self._set_tool(name, False)
        node = QgsProject.instance().layerTreeRoot().findLayer(layer.id())
        if node is not None:
            node.setItemVisibilityCheckedParentRecursive(True)
        self.iface.setActiveLayer(layer)
        if not layer.isEditable():
            layer.startEditing()
        self.iface.actionAddFeature().trigger()

    def import_geometry(self) -> Optional[importer.ImportResult]:
        """Importerar geometri (utan attribut) från ett annat lager till lagren under Att tilldela. Objekten läggs i
        redigeringsbufferten och sparas med Spara."""
        group = self._group()
        if group is None:
            return None
        if not self._editable(group):
            return None
        targets = draft_layers(group)
        if any(layer is None for layer in targets.values()):
            self._warn("Lagren under Att tilldela saknas i planen. Öppna planen på nytt.")
            return None
        own = [node.layer() for node in group.findLayers() if node.layer() is not None]
        dialog = ImportDialog(self.iface, own, self.iface.mainWindow(), targets["polygon"].crs().postgisSrid()
                              or model.EPSG)
        accepted = dialog.exec()
        source, selected_only = dialog.source(), dialog.selected_only.isChecked()
        dialog.release()
        dialog.deleteLater()
        if not accepted or source is None:
            return None
        result = importer.import_geometries(source, targets, selected_only)
        for kind, count in result.counts.items():
            node = QgsProject.instance().layerTreeRoot().findLayer(targets[kind].id())
            if count and node is not None:
                node.setItemVisibilityCheckedParentRecursive(True)
        text = result.text() + (" Spara med Avsluta redigering (disketten) när du är nöjd, eller ångra med Ctrl+Z i lagret." if result.total else "")
        (self._info if result.total and not result.invalid else self._warn)(text)
        return result

    # -- kartverktygen -------------------------------------------------------------
    def _set_tool(self, name: str, on: bool, factory=None) -> None:
        """Slår på eller av ett av pluginets kartverktyg. Byter man till ett annat verktyg släpps knappen upp."""
        canvas = self.iface.mapCanvas() if hasattr(self.iface, "mapCanvas") else None
        tool = self.map_tools.get(name)
        if on:
            if canvas is None or factory is None and tool is None:
                self._set_checked(name, False)
                return
            if tool is None:
                tool = factory(canvas)
                tool.deactivated.connect(lambda n=name: self._set_checked(n, False))
                self.map_tools[name] = tool
            canvas.setMapTool(tool)
        elif tool is not None and canvas is not None and canvas.mapTool() is tool:
            canvas.unsetMapTool(tool)
        self._set_checked(name, on)

    def _set_checked(self, name: str, on: bool) -> None:
        action = getattr(self.toolbar, f"act_{name}", None) if self.toolbar is not None else None
        if action is not None and action.isChecked() != on:
            action.blockSignals(True)
            action.setChecked(on)
            action.blockSignals(False)
        if name == "copy" and not on:
            self.reset_copy_source()
        if name == "relate" and not on:
            self.reset_relate_source()

    def set_assigning(self, on: bool):
        """Slår på eller av verktyget Tilldela innehåll."""
        if on and not self._tool_allowed():
            self._set_checked("assign", False)
            return
        self._set_tool("assign", on, lambda canvas: AssignTool(canvas, self.assign_at))

    def set_selecting(self, on: bool):
        """Slår på eller av verktyget Markera."""
        self._set_tool("select", on, lambda canvas: SelectTool(canvas, self.select_at, self.select_rect,
                                                               self.deselect_all))

    def set_copying(self, on: bool):
        """Slår på eller av verktyget Kopiera innehåll."""
        if on and not self._tool_allowed():
            self._set_checked("copy", False)
            return
        self._set_tool("copy", on, lambda canvas: CopyTool(canvas, self.copy_at, self.reset_copy_source))
        if on and "copy" in self.map_tools:
            self._info("Kopiera innehåll: klicka på objektet du vill kopiera från.")

    def set_relating(self, on: bool):
        """Slår på eller av verktyget Berör annat innehåll."""
        if on and not self._tool_allowed():
            self._set_checked("relate", False)
            return
        self._set_tool("relate", on, lambda canvas: CopyTool(canvas, self.relate_at, self.reset_relate_source))
        if on and "relate" in self.map_tools:
            self._info("Berör annat innehåll: klicka på innehållet du utgår från.")

    def _tool_allowed(self) -> bool:
        group = active_plan_group(QgsProject.instance(), self.iface.activeLayer())
        return group is None or self._editable(group)

    # -- pennan ---------------------------------------------------------------------
    def start_editing(self) -> bool:
        """Öppnar alla planens lager för redigering (som pennan i Rita Detaljplan). En plan i databasen checkas ut
        först."""
        group = self._group()
        if group is None or not self._editable(group):
            return False
        failed = editing.start_editing(group)
        if failed:
            self._warn(f"{failed} av planens lager kunde inte öppnas för redigering.")
            return False
        self._info("Planens lager är öppna för redigering. Rita, importera eller tilldela innehåll; avsluta med "
                   "Avsluta redigering.")
        return True

    def stop_editing(self) -> bool:
        """Avslutar redigeringen i planens lager. Finns det ändringar frågar pluginet om de ska sparas."""
        group = self._group()
        if group is None:
            return False
        if not editing.is_editing(group):
            self._info("Ingen redigering pågår i planen.")
            return False
        answer = QMessageBox.StandardButton.Save
        if editing.has_edits(group):
            answer = self._ask_save()
            if answer == QMessageBox.StandardButton.Cancel:
                return False
        save = answer == QMessageBox.StandardButton.Save
        for name in tuple(self.map_tools):
            self._set_tool(name, False)
        errors = editing.stop_editing(group, save)
        if errors:
            self._warn("Kunde inte spara: " + " | ".join(errors))
            return False
        self._info("Sparade planen och avslutade redigeringen." if save else "Kastade ändringarna.")
        return True

    def _ask_save(self):
        """Frågan när redigeringen avslutas (disketten), som i Rita Detaljplan."""
        box = QMessageBox(self.iface.mainWindow())
        box.setWindowTitle("Avsluta redigering")
        box.setText("Vill du spara ändringarna i planen?")
        box.setStandardButtons(QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
                               | QMessageBox.StandardButton.Cancel)
        box.button(QMessageBox.StandardButton.Save).setText("Spara och avsluta")
        box.button(QMessageBox.StandardButton.Discard).setText("Förkasta och avsluta")
        box.button(QMessageBox.StandardButton.Cancel).setText("Avbryt")
        box.setDefaultButton(QMessageBox.StandardButton.Save)
        return QMessageBox.StandardButton(box.exec())

    # -- markera ----------------------------------------------------------------------
    def select_at(self, point: QgsPointXY, tolerance: float, add: bool = False) -> Optional[content.Candidate]:
        """Klick med Markera: markerar objektet under klicket (en meny om flera ligger på varandra) och gör dess lager
        aktivt, så att QGIS redigeringsverktyg fungerar direkt."""
        group = self._group()
        if group is None:
            return None
        candidates = content.candidates_at(group, point, tolerance)
        if not candidates:
            if not add:
                editing.clear_selection(group)
            return None
        chosen = candidates[0] if len(candidates) == 1 else self.choose_candidate(candidates)
        if chosen is None:
            return None
        editing.select(group, chosen, add)
        self.iface.setActiveLayer(chosen.layer)
        return chosen

    def select_rect(self, rect: QgsRectangle, add: bool = False) -> int:
        group = self._group()
        return editing.select_in_rect(group, rect, add) if group is not None else 0

    def deselect_all(self) -> None:
        group = self._group()
        if group is not None:
            editing.clear_selection(group)

    # -- kopiera innehåll -------------------------------------------------------------
    def reset_copy_source(self) -> None:
        self.copy_source, self.copy_assignment = None, None
        tool = self.map_tools.get("copy")
        if tool is not None:
            tool.show_source(None)

    # -- berör annat innehåll -----------------------------------------------------------
    def reset_relate_source(self) -> None:
        self.relate_source = None
        tool = self.map_tools.get("relate")
        if tool is not None:
            tool.show_source(None)
            tool.show_targets([])

    def _show_related(self, group) -> None:
        tool, source = self.map_tools.get("relate"), self.relate_source
        if tool is None or source is None:
            return
        wanted = relations.related(group, source.layer, source.fid)
        found = []
        for layer_def in model.CONTENT_LAYERS:
            layer = layer_in_group(group, layer_def.name)
            if layer is None:
                continue
            for feature in layer.getFeatures():
                if str(content.plain(feature["objektidentitet"])) in wanted and feature.hasGeometry():
                    found.append((feature.geometry(), layer))
        tool.show_targets(found)

    def relate_at(self, point: QgsPointXY, tolerance: float) -> Optional[bool]:
        """Första klicket väljer innehållet man utgår från, nästa klick kopplar (eller kopplar loss) innehållet det
        berör. Returnerar True/False för kopplat/loss, eller None när källan valdes eller inget hände."""
        group = self._group()
        if group is None:
            return None
        source = self.relate_source
        if source is not None and not source.layer.getFeature(source.fid).isValid():
            self.reset_relate_source()
            source = None
        assigned = [c for c in content.candidates_at(group, point, tolerance) if c.assigned]
        if source is None:
            if not assigned:
                self._warn("Klicka på ett innehåll (otilldelad geometri kan inte beröra något).")
                return None
            chosen = assigned[0] if len(assigned) == 1 else self.choose_candidate(assigned)
            if chosen is None:
                return None
            self.relate_source = chosen
            tool = self.map_tools.get("relate")
            if tool is not None:
                tool.show_source(chosen.layer.getFeature(chosen.fid).geometry(), chosen.layer)
            self._show_related(group)
            count = len(relations.related(group, chosen.layer, chosen.fid))
            self._info(f"{chosen.label()} berör {count} annat innehåll. Klicka på innehåll för att koppla eller "
                       "koppla loss.")
            return None
        targets = [c for c in assigned if not (c.layer is source.layer and c.fid == source.fid)]
        if not targets:
            self._warn("Klicka på ett annat innehåll.")
            return None
        target = targets[0] if len(targets) == 1 else self.choose_candidate(targets)
        if target is None:
            return None
        identity = str(content.plain(target.layer.getFeature(target.fid)["objektidentitet"]))
        try:
            linked = relations.toggle(group, source.layer, source.fid, identity)
        except ValueError as exc:
            self._warn(str(exc))
            return None
        self._show_related(group)
        self._info(("Kopplat: " if linked else "Kopplingen är borttagen: ") + target.label()
                   + ". Spara med Avsluta redigering (disketten).")
        return linked

    def copy_at(self, point: QgsPointXY, tolerance: float) -> bool:
        """Första klicket väljer objektet att kopiera från, nästa klick ger ett annat objekt samma innehåll. Returnerar
        True när något kopierades."""
        group = self._group()
        if group is None:
            return False
        source = self.copy_source
        if source is not None and not source.layer.getFeature(source.fid).isValid():
            self.reset_copy_source()
            source = None
        candidates = content.candidates_at(group, point, tolerance)
        if source is None:
            assigned = [c for c in candidates if c.assigned]
            if not assigned:
                self._warn("Klicka på ett objekt med innehåll att kopiera från.")
                return False
            chosen = assigned[0] if len(assigned) == 1 else self.choose_candidate(assigned)
            if chosen is None:
                return False
            self.copy_source, self.copy_assignment = chosen, editing.assignment_from(chosen)
            tool = self.map_tools.get("copy")
            if tool is not None:
                tool.show_source(chosen.layer.getFeature(chosen.fid).geometry(), chosen.layer)
            self._info(f"Kopierar {editing.describe(self.copy_assignment)}. Klicka på objekten som ska få samma "
                       "innehåll; högerklick väljer en ny källa.")
            return False
        targets = [c for c in candidates if not (c.layer is source.layer and c.fid == source.fid)]
        if not targets:
            self._warn("Klicka på ett annat objekt: otilldelad geometri eller annat innehåll.")
            return False
        drafts = [c for c in targets if not c.assigned]
        target = drafts[0] if drafts else (targets[0] if len(targets) == 1 else self.choose_candidate(targets))
        if target is None:
            return False
        try:
            layer, _ = content.assign(group, target, self.copy_assignment)
        except ValueError as exc:
            self._warn(str(exc))
            return False
        layer.triggerRepaint()
        target.layer.triggerRepaint()
        self._info(f"Kopierade {editing.describe(self.copy_assignment)}. Avsluta redigering (disketten) när du är klar.")
        return True

    def assign_at(self, point: QgsPointXY, tolerance: float) -> None:
        """Klick med Tilldela innehåll: otilldelad geometri under klicket får innehåll, tilldelat innehåll kan byta
        typ. Ligger flera tilldelade objekt på varandra väljer man vilket."""
        group = self._group()
        if group is None:
            return
        candidates = content.candidates_at(group, point, tolerance)
        if not candidates:
            self._warn("Inget ritat här. Rita en yta, linje eller punkt först, eller klicka på ett objekt i planen.")
            return
        drafts = [c for c in candidates if not c.assigned]
        candidate = drafts[0] if drafts else (candidates[0] if len(candidates) == 1
                                              else self.choose_candidate(candidates))
        if candidate is None:
            return
        self.assign(group, candidate)

    def assign(self, group, candidate: content.Candidate) -> bool:
        if self.assign_tool is not None:
            self.assign_tool.highlight(candidate.layer, candidate.fid)
        lookups = {lookup.name: plan_storage(group).read_lookup(lookup) for lookup in model.LOOKUPS}
        current = None
        if candidate.assigned:
            feature = candidate.layer.getFeature(candidate.fid)
            current = {name: content.plain(feature[name]) for name in content.CONTENT_FIELDS
                       if feature.fields().indexOf(name) >= 0}
        lookups[utbyggnad.KEY] = [stage.label for stage in utbyggnad.read(group)]
        dialog = AssignDialog(candidate.suffix, lookups, current, candidate.category, self.iface.mainWindow())
        accepted = dialog.exec()
        if self.assign_tool is not None:
            self.assign_tool.clear_highlight()
        if not accepted:
            return False
        assignment = dialog.assignment()
        try:
            layer, _ = content.assign(group, candidate, assignment)
        except ValueError as exc:
            self._warn(str(exc))
            return False
        layer.triggerRepaint()
        candidate.layer.triggerRepaint()
        self._info(f"{assignment.category.alias}: {assignment.values.get('innehallstyp_varde')}. Spara med "
                   "Avsluta redigering (disketten) när du är klar.")
        return True

    def choose_candidate(self, candidates: list[content.Candidate]) -> Optional[content.Candidate]:
        """Meny vid muspekaren när flera objekt ligger på varandra."""
        menu = QMenu(self.iface.mainWindow())
        for i, candidate in enumerate(candidates):
            menu.addAction(candidate.label()).setData(i)
        chosen = menu.exec(QCursor.pos())
        return candidates[chosen.data()] if chosen is not None else None

    # -- spara --------------------------------------------------------------------
    def save_all(self) -> int:
        """Sparar redigeringarna i alla lager i projektet. Redigeringen fortsätter, så att man kan rita vidare.
        Returnerar antalet lager som sparades."""
        saved, failed = 0, []
        for layer in QgsProject.instance().mapLayers().values():
            if isinstance(layer, QgsVectorLayer) and layer.isEditable() and layer.isModified():
                if layer.commitChanges(False):
                    saved += 1
                else:
                    failed.append(f"{layer.name()}: " + "; ".join(layer.commitErrors()))
        if failed:
            self._warn("Kunde inte spara " + " | ".join(failed))
        elif saved:
            self._info(f"Sparade {saved} lager.")
        else:
            self._info("Det fanns inget osparat.")
        return saved

    def open_about(self):
        AboutDialog(self.iface.mainWindow()).exec()

    # -- hjälpare -----------------------------------------------------------------
    def _group(self):
        group = active_plan_group(QgsProject.instance(), self.iface.activeLayer())
        if group is None:
            self._warn(NO_PLAN)
        return group

    def _load(self, source) -> bool:
        try:
            load_plan(source, QgsProject.instance())
        except (PlanError, storage.PostgisError) as exc:
            self._warn(str(exc))
            return False
        self.refresh_tools()
        return True

    def _brand_menu(self):
        """Märket framför Rita Översiktsplan i menyn Insticksprogram (QGIS skapar undermenyn utan ikon)."""
        plugin_menu = self.iface.pluginMenu()
        if plugin_menu is None:
            return
        for entry in plugin_menu.actions():
            if entry.menu() is not None and entry.menu().title() == MENU:
                entry.setIcon(QIcon(str(BRAND_ICON)))
                return

    def _separator(self):
        action = QAction(self.iface.mainWindow())
        action.setSeparator(True)
        self.actions.append(action)
        return action

    def _add_action(self, text, callback, icon=None):
        action = QAction(icon, text, self.iface.mainWindow()) if icon else QAction(text, self.iface.mainWindow())
        action.triggered.connect(lambda _=False: callback())
        self.iface.addPluginToMenu(MENU, action)
        self.actions.append(action)
        return action

    # -- meddelanden --------------------------------------------------------------
    def _info(self, text):
        push(self.iface.messageBar(), TITLE, text, Qgis.MessageLevel.Success)

    def _warn(self, text):
        push(self.iface.messageBar(), TITLE, text, Qgis.MessageLevel.Warning)
