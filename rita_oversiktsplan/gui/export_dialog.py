"""Dialogen Leverans och export (som i Rita Detaljplan): kontrollen av planen mot Lantmäteriets format, och knapparna
som sparar planen som JSON, levererar den till NGP och samlar den i ett arkivpaket."""
from __future__ import annotations

from typing import Callable, Optional

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QBrush, QColor
from qgis.PyQt.QtWidgets import (QDialog, QDialogButtonBox, QLabel, QListWidget, QListWidgetItem, QPushButton,
                                 QVBoxLayout)

from ..core import export_lm

MARKS = {export_lm.FEL: "✘", export_lm.VARNING: "▲"}
COLORS = {export_lm.FEL: QColor(179, 38, 30), export_lm.VARNING: QColor(176, 110, 0)}


def summary(collection: dict, problems: list[export_lm.Problem]) -> str:
    counts = export_lm.counts(collection)
    parts = [f"{counts.get(kind, 0)} {name}" for kind, name in (("beslutOP", "beslut"), ("innehallOP", "innehåll"))]
    errors = sum(1 for p in problems if p.level == export_lm.FEL)
    warnings = len(problems) - errors
    warning_text = f"{warnings} varning" if warnings == 1 else f"{warnings} varningar"
    text = f"Exporten innehåller planen, {parts[0]} och {parts[1]}. "
    if errors:
        text += (f"Kontrollen hittade {errors} fel och {warning_text}. Filen går att spara, men den följer inte "
                 "Lantmäteriets format förrän felen är rättade.")
    elif warnings:
        text += f"Kontrollen hittade inga fel men {warning_text}."
    else:
        text += "Kontrollen hittade inget att anmärka på."
    return text


class ExportDialog(QDialog):
    """``show`` anropas med (tabell, fid) när man dubbelklickar på en anmärkning som gäller ett objekt."""

    def __init__(self, collection: dict, problems: list[export_lm.Problem], save: Callable[[], Optional[str]],
                 show: Callable[[str, int], None], parent=None, deliver: Optional[Callable[[], Optional[str]]] = None,
                 archive: Optional[Callable[[], Optional[str]]] = None,
                 settings: Optional[Callable[[], None]] = None):
        super().__init__(parent)
        self.setWindowTitle("Leverans och export")
        self.setMinimumSize(680, 440)
        self.problems = problems
        self._save, self._show, self._deliver, self._archive = save, show, deliver, archive
        intro = QLabel("Kontrollen gäller Lantmäteriets format för översiktsplan (JSON, Översiktsplan 2.0, testversion). "
                       "Spara planen som fil, leverera den till Nationella geodataplattformen (NGP, kräver "
                       "producentbehörighet) eller samla den och handlingarna i ett arkivpaket.")
        intro.setWordWrap(True)
        self.summary = QLabel(summary(collection, problems))
        self.summary.setWordWrap(True)
        self.list = QListWidget()
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
        self.result = QLabel()
        self.result.setWordWrap(True)
        self.save_button = QPushButton("Spara som JSON…")
        self.save_button.clicked.connect(self.save)
        self.deliver_button = QPushButton("Leverera till NGP…")
        self.deliver_button.setToolTip("Levererar planen till Nationella geodataplattformen via Lantmäteriets "
                                       "Uppdatering-API. Kräver producentbehörighet och inställningar.")
        self.deliver_button.clicked.connect(self.deliver)
        self.deliver_button.setVisible(deliver is not None)
        self.archive_button = QPushButton("Skapa arkivpaket…")
        self.archive_button.setToolTip("Samlar planen och handlingarna med bevarandemetadata enligt Boverkets "
                                       "specifikation för långtidsbevarande.")
        self.archive_button.clicked.connect(self.archive)
        self.archive_button.setVisible(archive is not None)
        self.settings_button = QPushButton("Inställningar…")
        self.settings_button.setToolTip("Inställningar för leverans till NGP: miljö, adresser och inloggning.")
        self.settings_button.clicked.connect(lambda: settings() if settings else None)
        self.settings_button.setVisible(settings is not None)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText("Stäng")
        for button in (self.save_button, self.deliver_button, self.archive_button, self.settings_button):
            buttons.addButton(button, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addWidget(self.summary)
        layout.addWidget(self.list, 1)
        layout.addWidget(self.result)
        layout.addWidget(buttons)

    def _double_clicked(self, item: QListWidgetItem) -> None:
        problem = item.data(Qt.ItemDataRole.UserRole)
        if problem.layer and problem.fid is not None:
            self._show(problem.layer, problem.fid)

    def _run(self, action) -> Optional[str]:
        text = action() if action is not None else None
        if text:
            self.result.setText(text)
        return text

    def save(self) -> Optional[str]:
        return self._run(self._save)

    def deliver(self) -> Optional[str]:
        return self._run(self._deliver)

    def archive(self) -> Optional[str]:
        return self._run(self._archive)
