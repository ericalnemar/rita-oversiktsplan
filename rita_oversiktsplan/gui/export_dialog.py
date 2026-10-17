"""Dialogen Leverans och export (uppbyggd som i Rita Detaljplan): kontrollen av planen i en egen blå ruta överst, och
tre alternativ i var sin ruta: leverera planen till NGP, spara den som JSON-fil eller samla den i ett arkivpaket.

Dialogen öppnas alltid, även om inställningarna för leverans till NGP inte är gjorda: då går leveransen inte att välja,
rutan säger vad som saknas och har en knapp till inställningarna, medan fil och arkivpaket fungerar ändå."""
from __future__ import annotations

from typing import Callable, Optional

from qgis.PyQt.QtCore import QSize, Qt
from qgis.PyQt.QtGui import QBrush, QColor
from qgis.PyQt.QtWidgets import (QButtonGroup, QCheckBox, QDialog, QDialogButtonBox, QGroupBox, QHBoxLayout, QLabel,
                                 QListWidget, QListWidgetItem, QPushButton, QRadioButton, QVBoxLayout)

from ..core import export_lm
from ..core.ngp_client import NgpConfig
from .delivery_dialog import confirmation_text

MARKS = {export_lm.FEL: "✘", export_lm.VARNING: "▲"}
COLORS = {export_lm.FEL: QColor(179, 38, 30), export_lm.VARNING: QColor(176, 110, 0)}
UPLOAD, FILE, ARCHIVE = "upload", "file", "archive"
# kontrollen är inte ett av alternativen: egen ruta i en egen färg (genomskinlig, så att den fungerar i ljust och mörkt tema)
CHECK_BOX_STYLE = """
QGroupBox#checkBox { background-color: rgba(30, 110, 200, 28); border: 1px solid rgba(30, 110, 200, 150);
                     border-radius: 4px; margin-top: 14px; padding-top: 6px; }
QGroupBox#checkBox::title { subcontrol-origin: margin; subcontrol-position: top left; left: 8px; padding: 0 4px; }
"""


def summary(collection: dict, problems: list[export_lm.Problem]) -> str:
    counts = export_lm.counts(collection)
    parts = [f"{counts.get(kind, 0)} {name}" for kind, name in (("beslutOP", "beslut"), ("innehallOP", "innehåll"))]
    errors = sum(1 for p in problems if p.level == export_lm.FEL)
    warnings = len(problems) - errors
    warning_text = f"{warnings} varning" if warnings == 1 else f"{warnings} varningar"
    text = f"Planen med {parts[0]} och {parts[1]}. "
    if errors:
        text += (f"Kontrollen hittade {errors} fel och {warning_text}. Planen går att spara och arkivera, men den följer "
                 "inte Lantmäteriets format förrän felen är rättade, och NGP stoppar en leverans med fel.")
    elif warnings:
        text += f"Kontrollen hittade inga fel men {warning_text}."
    else:
        text += "Kontrollen hittade inget att anmärka på."
    return text


class _ProblemList(QListWidget):
    """Listan med anmärkningar vill vara låg, så att dialogen inte blir högre än skärmen; den växer om man drar
    dialogen större."""

    def sizeHint(self) -> QSize:  # noqa: N802 - namnet krävs av Qt
        return QSize(400, 120)


def _info(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setEnabled(False)  # dämpad färg: förklaring, inte ett val
    return label


class ExportDialog(QDialog):
    """``show`` anropas med (tabell, fid) när man dubbelklickar på en anmärkning som gäller ett objekt. ``save``,
    ``deliver`` och ``archive`` gör jobbet och returnerar en text när det gick (då stängs dialogen) eller None (då
    ligger dialogen kvar). ``config`` ger inställningarna för NGP och ``resuming`` om en tidigare mottagning
    återanvänds."""

    def __init__(self, collection: dict, problems: list[export_lm.Problem], save: Callable[[], Optional[str]],
                 show: Callable[[str, int], None], parent=None, deliver: Optional[Callable[[], Optional[str]]] = None,
                 archive: Optional[Callable[[], Optional[str]]] = None,
                 settings: Optional[Callable[[], None]] = None,
                 config: Optional[Callable[[], NgpConfig]] = None,
                 resuming: Optional[Callable[[NgpConfig], bool]] = None):
        super().__init__(parent)
        self.setWindowTitle("Leverans och export")
        self.setMinimumWidth(640)
        self.problems = problems
        self.plan = next((f["properties"] for f in collection.get("features", [])
                          if f["properties"].get("feature:typ") == "oversiktsplan"), {})
        self.errors = sum(1 for p in problems if p.level == export_lm.FEL)
        self._save, self._show, self._deliver, self._archive = save, show, deliver, archive
        self._settings, self._config, self._resuming = settings, config, resuming

        # kontrollen
        self.summary = QLabel(summary(collection, problems))
        self.summary.setWordWrap(True)
        self.list = _ProblemList()
        self.list.setMinimumHeight(70)
        self.list.setWordWrap(True)  # långa anmärkningar radbryts i stället för att rulla i sidled
        for problem in problems:
            item = QListWidgetItem(f"{MARKS[problem.level]}  {problem.text}")
            item.setForeground(QBrush(COLORS[problem.level]))
            item.setData(Qt.ItemDataRole.UserRole, problem)
            if problem.layer and problem.fid is not None:
                item.setToolTip("Dubbelklicka för att visa objektet.")
            self.list.addItem(item)
        self.list.setVisible(bool(problems))
        self.list.itemDoubleClicked.connect(self._double_clicked)
        self.list_hint = _info("Dubbelklicka på en anmärkning för att visa objektet i kartan.")
        self.list_hint.setVisible(bool(problems))
        self.check_box = QGroupBox("Kontroll av planen")
        self.check_box.setObjectName("checkBox")
        self.check_box.setStyleSheet(CHECK_BOX_STYLE)
        check_layout = QVBoxLayout(self.check_box)
        check_layout.addWidget(self.summary)
        check_layout.addWidget(self.list, 1)
        check_layout.addWidget(self.list_hint)

        # alternativen
        self.upload = QRadioButton("Leverera till NGP")
        self.upload_info = QLabel()
        self.upload_info.setWordWrap(True)
        self.upload_info.setTextFormat(Qt.TextFormat.RichText)
        self.upload_problems = QLabel()
        self.upload_problems.setWordWrap(True)
        self.upload_problems.setStyleSheet("color: #b3261e;")
        self.settings_button = QPushButton("Inställningar…")
        self.settings_button.setToolTip("Inställningar för leverans till NGP: miljö, adresser och inloggning.")
        self.settings_button.clicked.connect(self._open_settings)
        self.understand = QCheckBox("Jag förstår att en godkänd plan publiceras i produktionsmiljön")
        self.upload_box = QGroupBox()
        upload_layout = QVBoxLayout(self.upload_box)
        upload_layout.addWidget(self.upload)
        upload_layout.addWidget(self.upload_info)
        upload_layout.addWidget(self.upload_problems)
        settings_row = QHBoxLayout()
        settings_row.addWidget(self.settings_button)
        settings_row.addStretch(1)
        upload_layout.addLayout(settings_row)
        upload_layout.addWidget(self.understand)
        self.upload_box.setVisible(deliver is not None)

        self.file = QRadioButton("Spara som JSON-fil")
        file_box = QGroupBox()
        file_layout = QVBoxLayout(file_box)
        file_layout.addWidget(self.file)
        file_layout.addWidget(_info(f"Skriver planen i Lantmäteriets format för översiktsplan (Översiktsplan 2.0, "
                                    f"testversion, {export_lm.MEDIATYP}) till en fil. Den kan granskas, skickas till "
                                    "NGP-supporten eller laddas upp av en producent."))

        self.archive_radio = QRadioButton("Skapa arkivpaket")
        self.archive_box = QGroupBox()
        archive_layout = QVBoxLayout(self.archive_box)
        archive_layout.addWidget(self.archive_radio)
        archive_layout.addWidget(_info("Samlar planen och dess handlingar (planhandlingen, underlagen och egna dokument) "
                                       "i ett arkivpaket med bevarandemetadata för långtidsbevarande, enligt Boverkets "
                                       "specifikation. Inget levereras till NGP."))
        self.archive_box.setVisible(archive is not None)

        self.group = QButtonGroup(self)  # alternativen ligger i olika rutor: koppla ihop dem
        for radio in (self.upload, self.file, self.archive_radio):
            self.group.addButton(radio)
            radio.toggled.connect(self._update)
        self.understand.toggled.connect(self._update)

        self.result = QLabel()
        self.result.setWordWrap(True)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Stäng")
        self.buttons.accepted.connect(self.run)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.check_box, 1)
        layout.addWidget(self.upload_box)
        layout.addWidget(file_box)
        layout.addWidget(self.archive_box)
        layout.addWidget(self.result)
        layout.addWidget(self.buttons)
        self._first = True
        self._forced = False
        self.refresh()

    # -- leveransen till NGP -------------------------------------------------------------
    def config(self) -> Optional[NgpConfig]:
        return self._config() if self._config is not None else None

    def delivery_problems(self) -> list[str]:
        """Skäl till att leveransen inte går: kommunen saknas eller inställningarna är ofullständiga."""
        found = [] if self.plan.get("kommunkod") else [
            "Kommunen saknas i planens uppgifter (den avgör vilken producent som levererar)."]
        config = self.config()
        if config is None:
            return found + ["Inställningarna för leverans till NGP saknas."]
        return found + config.problems()

    def refresh(self) -> None:
        """Läser om inställningarna (till exempel efter Inställningar…) och uppdaterar leveransrutan."""
        problems = self.delivery_problems()
        can_upload = self._deliver is not None and not problems
        config = self.config()
        self.upload.setEnabled(can_upload)
        self.upload_problems.setText("\n".join(problems))
        self.upload_problems.setVisible(bool(problems))
        self.settings_button.setVisible(self._settings is not None)
        self.settings_button.setText("Inställningar…" if problems else "Ändra inställningar…")
        if can_upload:
            resuming = bool(self._resuming(config)) if self._resuming is not None else False
            self.upload_info.setText(confirmation_text(config, self.plan.get("planensTitel", ""),
                                                       self.plan.get("kommunnamn", ""), self.plan.get("kommunkod", ""),
                                                       self.errors, resuming).replace(" Vill du fortsätta?", ""))
        else:
            self.upload_info.setText("Leveransen görs via Lantmäteriets Uppdatering-API och kräver att kommunen har "
                                     "behörighet som producent för översiktsplan.")
        self._fit_upload_info()
        self.understand.setVisible(can_upload and config is not None and config.is_production)
        if not can_upload:
            if self.upload.isChecked() or self._first:  # ett eget val av fil eller arkivpaket ändras inte
                self.file.setChecked(True)
                self._forced = True  # filen valdes av programmet, inte av användaren
        elif self._first or self._forced:
            self.upload.setChecked(True)  # standardval när leveransen går
            self._forced = False
        self._first = False
        self._update()

    def _fit_upload_info(self) -> None:
        """En radbruten etikett med formaterad text får annars för låg höjd i en ruta, och de sista styckena klipps.
        Höjden räknas för dialogens minsta bredd (dialogen kan bli bredare, då blir det bara lite luft kvar)."""
        self.upload_info.setMinimumHeight(self.upload_info.heightForWidth(self.minimumWidth() - 80))
        if self.layout() is not None:
            self.layout().activate()

    def _open_settings(self) -> None:
        if self._settings is not None:
            self._settings()
        self.refresh()

    # -- valet ---------------------------------------------------------------------------
    def choice(self) -> str:
        if self.archive_radio.isChecked() and self._archive is not None:
            return ARCHIVE
        return UPLOAD if self.upload.isChecked() and self.upload.isEnabled() else FILE

    def _update(self, *_) -> None:
        ok = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        choice = self.choice()
        config = self.config()
        if choice == UPLOAD:
            ok.setText("Leverera")
            ok.setEnabled(config is None or not config.is_production or self.understand.isChecked())
        elif choice == ARCHIVE:
            ok.setText("Skapa arkivpaket…")
            ok.setEnabled(True)
        else:
            ok.setText("Spara fil…")
            ok.setEnabled(True)
        self.understand.setEnabled(choice == UPLOAD)

    def run(self) -> Optional[str]:
        """Gör det valda. Gick det stängs dialogen; avbröt man (till exempel filvalet) ligger den kvar."""
        action = {UPLOAD: self._deliver, ARCHIVE: self._archive, FILE: self._save}[self.choice()]
        text = action() if action is not None else None
        if text:
            self.result.setText(text)
            self.accept()
        return text

    # behålls för tester och för den som vill göra ett visst val direkt
    def save(self) -> Optional[str]:
        self.file.setChecked(True)
        return self.run()

    def deliver(self) -> Optional[str]:
        self.upload.setChecked(True)
        return self.run()

    def archive(self) -> Optional[str]:
        self.archive_radio.setChecked(True)
        return self.run()

    def _double_clicked(self, item: QListWidgetItem) -> None:
        problem = item.data(Qt.ItemDataRole.UserRole)
        if problem.layer and problem.fid is not None:
            self._show(problem.layer, problem.fid)
