"""Dialogen Exportera: kontrollen av planen mot Lantmäteriets format, och knappen som sparar planen som JSON."""
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
                 show: Callable[[str, int], None], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Exportera översiktsplanen")
        self.setMinimumSize(640, 420)
        self.problems = problems
        self._save, self._show = save, show
        intro = QLabel("Planen sparas i Lantmäteriets format för översiktsplan (JSON, Översiktsplan 2.0, "
                       "testversion), som används vid leverans till Nationella geodataplattformen.")
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
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText("Stäng")
        buttons.addButton(self.save_button, QDialogButtonBox.ButtonRole.ActionRole)
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

    def save(self) -> Optional[str]:
        text = self._save()
        if text:
            self.result.setText(text)
        return text
