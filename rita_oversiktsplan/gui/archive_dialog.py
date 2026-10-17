"""Skapa arkivpaket för översiktsplanen (se ``core.archive``), som i Rita Detaljplan.

Med i paketet, efter val: planen som GeoPackage (en ögonblickskopia), planen i Lantmäteriets format (JSON),
planhandlingen med bokmärken och dess webbversion, underlagens filer som finns på datorn, och andra handlingar man
lägger till (till exempel planhandlingen som PDF/A). Originalen ändras inte."""
from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from qgis.core import QgsProject
from qgis.PyQt.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QGroupBox, QHBoxLayout, QLabel,
                                 QLineEdit, QListWidget, QPushButton, QVBoxLayout)

from ..core import archive, documents, editing, export_lm, geopackage, storage, underlag
from ..core.content import decision_feature, plain, plan_feature
from ..core.project import plan_storage
from .about_dialog import metadata

DOCUMENT_FILTER = "Dokument (*.pdf *.docx *.odt);;Alla filer (*)"
EDITING_TEXT = ("Planen redigeras just nu. Avsluta redigeringen (disketten) först, annars kommer inte det du ritat sedan "
                "senast med i paketet.")


def app_info() -> archive.App:
    meta = metadata()
    return archive.App(meta.get("name", "Rita Översiktsplan"), meta.get("version", ""), meta.get("repository", ""))


@dataclass
class ArchiveOptions:
    folder: Path
    geopackage: bool = True
    export_file: bool = True
    planhandling: bool = True
    underlag: bool = True
    documents: list[Path] = field(default_factory=list)
    performer: Optional[str] = None


def _text(value) -> str:
    value = plain(value)
    if value is None:
        return ""
    if hasattr(value, "toString"):
        return value.toString("yyyy-MM-dd")
    return str(value).strip()


def plan_metadata(group) -> dict[str, str]:
    """Planens uppgifter till ``oversiktsplan.xml``: titel, kommun, planhändelse och datum, och antagandebeslutets
    diarienummer och datum för laga kraft. Bara det som är ifyllt tas med (tolkning: Boverket anger inte vad den
    generella metadatan ska innehålla)."""
    found: dict[str, str] = {}
    plan = plan_feature(group)
    if plan is not None:
        for key, column in (("objektidentitet", "objektidentitet"), ("namn", "planens_titel"),
                            ("kommun", "kommunnamn"), ("kommunkod", "kommunkod"), ("planhandelse", "planhandelse_varde"),
                            ("datumPlanhandelse", "planhandelse_datum"), ("datumPaborjat", "datum_paborjat")):
            text = _text(plan[column])
            if text:
                found[key] = text
    found["typ"] = "Översiktsplan"
    decision = decision_feature(group)
    if decision is not None:
        for key, column in (("diarienummer", "diarienummer"), ("datumAntagen", "datum_fattat"),
                            ("datumLagakraft", "datum_laga_kraft")):
            text = _text(decision[column])
            if text:
                found[key] = text
    return found


def planhandling_files(group) -> list[Path]:
    """Planhandlingen med bokmärken (den senast sparade som planen är kopplad till) och dess webbversion, om de finns."""
    files = []
    for path in documents.linked_documents(group)[:1]:
        if path.is_file():
            files.append(path)
            page = path.with_suffix(".html")
            if page.is_file():
                files.append(page)
    return files


def underlag_files(group) -> list[Path]:
    """Underlagens filer som finns på datorn (webbadresser kan inte läggas i paketet)."""
    found = []
    for item in underlag.read_underlag(group):
        if item.lank and "://" not in item.lank and Path(item.lank).is_file() and Path(item.lank) not in found:
            found.append(Path(item.lank))
    return found


def build_archive(group, options: ArchiveOptions, app: Optional[archive.App] = None, now: Optional[datetime] = None,
                  progress: Optional[Callable[[str], None]] = None) -> archive.Package:
    """Samlar det som ska med (ur planen till en tillfällig mapp) och skapar paketet."""
    app = app or app_info()
    say = progress or (lambda _text: None)
    meta = plan_metadata(group)
    name = meta.get("namn") or plan_storage(group).name or "oversiktsplan"
    stem = archive.clean_filename(name, "oversiktsplan").replace(" ", "_")
    plugin = (app.name, app.version)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        work = Path(temp)
        items: list[archive.Item] = []
        if options.geopackage:
            where = plan_storage(group)
            if not isinstance(where, storage.GeoPackageStorage):
                raise archive.ArchiveError("Planen ligger i en databas och finns inte som GeoPackage-fil. Checka ut "
                                           "den, eller ta bort valet för GeoPackage: exportfilen innehåller hela planen.")
            say("Kopierar planens GeoPackage")
            items.append(archive.Item(geopackage.snapshot(where.path, work / f"{stem}.gpkg"), creator=plugin))
        if options.export_file:
            say("Skapar exportfilen")
            path = work / f"{stem}.json"
            collection, _problems = export_lm.export(group)
            path.write_text(export_lm.dumps(collection), encoding="utf-8")
            items.append(archive.Item(path, creator=plugin))
        files = (planhandling_files(group) if options.planhandling else []) + \
            (underlag_files(group) if options.underlag else []) + list(options.documents)
        seen: set[Path] = set()
        for path in files:
            if path.resolve() not in seen:
                seen.add(path.resolve())
                items.append(archive.Item(Path(path)))
        return archive.build_package(options.folder, name, items, app, options.performer or None, now, progress,
                                     plan=meta)


class ArchiveDialog(QDialog):
    """Frågar vad som ska med i arkivpaketet och var det ska sparas. ``options()`` ger valen."""

    def __init__(self, group, parent=None):
        super().__init__(parent)
        self.group = group
        self.documents: list[Path] = []
        self.setWindowTitle("Skapa arkivpaket")
        self.setMinimumWidth(580)

        intro = QLabel("Samlar planen och dess handlingar i en mapp och beskriver dem med bevarandemetadata enligt "
                       "Boverkets specifikation för långtidsbevarande (PREMIS), så att de kan sparas i arkivet. "
                       "Originalen ändras inte. Pluginet gör inga filer till PDF/A: se själv till att handlingarna är "
                       "PDF/A och kontrollerade med en PDF/A-validerare.")
        intro.setWordWrap(True)
        meta = plan_metadata(group)
        self.plan_label = QLabel(f"Plan: {meta.get('namn') or 'utan titel'}")

        self.folder = QLineEdit(str(Path(QgsProject.instance().homePath() or Path.home())))
        self.folder.textChanged.connect(self._update)
        browse = QPushButton("Välj mapp…")
        browse.clicked.connect(self._choose_folder)
        folder_row = QHBoxLayout()
        folder_row.addWidget(QLabel("Spara paketet i mappen:"))
        folder_row.addWidget(self.folder, 1)
        folder_row.addWidget(browse)

        is_file = isinstance(plan_storage(group), storage.GeoPackageStorage)
        self.chk_gpkg = QCheckBox("Planen som GeoPackage-fil")
        self.chk_gpkg.setChecked(is_file)
        self.chk_gpkg.setEnabled(is_file)
        if not is_file:
            self.chk_gpkg.setToolTip("Planen ligger i en databas. Checka ut den för att få med den som fil.")
        self.chk_json = QCheckBox("Planen i Lantmäteriets format (JSON, Översiktsplan 2.0)")
        self.chk_json.setChecked(True)
        self.planhandling = planhandling_files(group)
        self.chk_planhandling = QCheckBox(
            "Planhandlingen med bokmärken och webbversionen (" + ", ".join(p.name for p in self.planhandling) + ")"
            if self.planhandling else "Planhandlingen med bokmärken (ingen sparad än)")
        self.chk_planhandling.setChecked(bool(self.planhandling))
        self.chk_planhandling.setEnabled(bool(self.planhandling))
        self.underlag = underlag_files(group)
        self.chk_underlag = QCheckBox(f"Underlagens filer ({len(self.underlag)} på datorn)" if self.underlag
                                      else "Underlagens filer (inga på datorn; webbadresser följer med i JSON-filen)")
        self.chk_underlag.setChecked(bool(self.underlag))
        self.chk_underlag.setEnabled(bool(self.underlag))
        box = QGroupBox("Ur planen")
        box_layout = QVBoxLayout(box)
        for check in (self.chk_gpkg, self.chk_json, self.chk_planhandling, self.chk_underlag):
            box_layout.addWidget(check)
            check.toggled.connect(self._update)

        self.list = QListWidget()
        self.list.setMinimumHeight(70)
        self.list.setMaximumHeight(120)
        add = QPushButton("Lägg till filer…")
        add.clicked.connect(self._add_documents)
        remove = QPushButton("Ta bort")
        remove.clicked.connect(self._remove_selected)
        buttons_col = QVBoxLayout()
        buttons_col.addWidget(add)
        buttons_col.addWidget(remove)
        buttons_col.addStretch(1)
        docs_row = QHBoxLayout()
        docs_row.addWidget(self.list, 1)
        docs_row.addLayout(buttons_col)
        docs = QGroupBox("Andra handlingar")
        docs_layout = QVBoxLayout(docs)
        docs_layout.addWidget(QLabel("Färdiga filer att lägga med, till exempel planhandlingen och kartorna som PDF/A:"))
        docs_layout.addLayout(docs_row)

        self.performer = QLineEdit()
        self.performer.setPlaceholderText("valfritt, förs in som den som skapade paketet")
        performer_row = QHBoxLayout()
        performer_row.addWidget(QLabel("Utförd av:"))
        performer_row.addWidget(self.performer, 1)

        self.hint = QLabel("")
        self.hint.setWordWrap(True)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.ok = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.ok.setText("Skapa paket")
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Avbryt")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        for widget in (intro, self.plan_label):
            layout.addWidget(widget)
        layout.addLayout(folder_row)
        layout.addWidget(box)
        layout.addWidget(docs)
        layout.addLayout(performer_row)
        layout.addWidget(self.hint)
        layout.addWidget(self.buttons)
        self._update()

    def options(self) -> ArchiveOptions:
        return ArchiveOptions(folder=Path(self.folder.text().strip()), geopackage=self.chk_gpkg.isChecked(),
                              export_file=self.chk_json.isChecked(), planhandling=self.chk_planhandling.isChecked(),
                              underlag=self.chk_underlag.isChecked(), documents=list(self.documents),
                              performer=self.performer.text().strip() or None)

    def _choose_folder(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Välj mapp för arkivpaketet", self.folder.text())
        if chosen:
            self.folder.setText(chosen)

    def _add_documents(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "Välj handlingar", self.folder.text(), DOCUMENT_FILTER)
        self.add_documents([Path(f) for f in files])

    def add_documents(self, paths: list[Path]) -> None:
        for path in paths:
            if path not in self.documents:
                self.documents.append(path)
                self.list.addItem(path.name)
        self._update()

    def _remove_selected(self) -> None:
        for item in self.list.selectedItems():
            row = self.list.row(item)
            self.list.takeItem(row)
            del self.documents[row]
        self._update()

    def notes(self) -> list[str]:
        """Råd om filerna, till exempel att en PDF inte säger sig vara PDF/A."""
        found = []
        for path in self.documents:
            try:
                found += [f"{path.name}: {note}" for note in archive.sniff_format(path)[2]]
            except OSError:
                found.append(f"{path.name}: filen kan inte läsas.")
        return found

    def problem(self) -> str:
        if editing.has_edits(self.group):
            return EDITING_TEXT
        if not Path(self.folder.text().strip()).is_dir():
            return "Välj en mapp som finns."
        o = self.options()
        if not (o.geopackage or o.export_file or (o.planhandling and self.planhandling)
                or (o.underlag and self.underlag) or o.documents):
            return "Välj minst en fil att lägga i paketet."
        return ""

    def _update(self, *_) -> None:
        problem = self.problem()
        self.ok.setEnabled(not problem)
        self.hint.setText("\n".join([problem] if problem else self.notes()))
