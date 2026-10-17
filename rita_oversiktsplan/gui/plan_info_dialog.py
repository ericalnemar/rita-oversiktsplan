"""Dialogen "Planens uppgifter", med flikarna Planen, Planhändelse, Beslut, Underlag och Standardvärden för nytt
innehåll.

Det som gäller hela planen ställs in här i stället för på varje objekt: planhändelsen följer med allt innehåll, och
standardvärdena (vertikal avgränsning, under ersättning …) sätts på varje objekt som tilldelas innehåll. Värden som
är unika för varje objekt, som objektidentitet och versionsdatum, får sitt värde automatiskt."""
from __future__ import annotations

import datetime
from typing import Optional

from qgis.PyQt.QtCore import QDate, Qt
from qgis.PyQt.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox,
                                 QFileDialog, QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPlainTextEdit,
                                 QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout,
                                 QWidget)

from ..core import model
from ..core.content import Decision, PlanInfo
from ..core.underlag import Underlag

NONE = "– ingen än –"
NO_LIMIT = "Ingen vertikal avgränsning"


class OptionalDate(QWidget):
    """Ett datum som kan saknas: en kryssruta och en datumruta."""

    def __init__(self, label: str, value: Optional[datetime.date], parent=None):
        super().__init__(parent)
        self.enabled = QCheckBox(label)
        self.edit = QDateEdit()
        self.edit.setCalendarPopup(True)
        self.edit.setDisplayFormat("yyyy-MM-dd")
        self.edit.setDate(QDate(value.year, value.month, value.day) if value else QDate.currentDate())
        self.enabled.setChecked(value is not None)
        self.edit.setEnabled(value is not None)
        self.enabled.toggled.connect(self.edit.setEnabled)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.enabled)
        layout.addWidget(self.edit, 1)

    def value(self) -> Optional[datetime.date]:
        if not self.enabled.isChecked():
            return None
        d = self.edit.date()
        return datetime.date(d.year(), d.month(), d.day())


class PlanInfoDialog(QDialog):
    def __init__(self, info: PlanInfo, planhandelser: list[str], parent=None, underlag: list[Underlag] | None = None,
                 underlagstyper: list[str] | None = None):
        super().__init__(parent)
        self.info = info
        self.setWindowTitle("Planens uppgifter")
        self.setMinimumWidth(560)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._plan_tab(info), "Planen")
        self.tabs.addTab(self._event_tab(info, planhandelser), "Planhändelse")
        self.tabs.addTab(self._decision_tab(info), "Beslut")
        self.underlagstyper = list(underlagstyper or [])
        self.underlag_tab = self._underlag_tab(underlag or []) if self.underlagstyper else None
        if self.underlag_tab is not None:
            self.tabs.addTab(self.underlag_tab, "Underlag")
        self.tabs.addTab(self._defaults_tab(info), "Standardvärden för innehåll")

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Spara")
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Avbryt")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs)
        layout.addWidget(self.buttons)

    # -- flikar -------------------------------------------------------------------------
    def _plan_tab(self, info: PlanInfo) -> QWidget:
        self.kommun = QLabel(f"{info.kommunnamn} ({info.kommunkod})")
        self.titel = QLineEdit(info.titel)
        self.paborjad = QDateEdit()
        self.paborjad.setCalendarPopup(True)
        self.paborjad.setDisplayFormat("yyyy-MM-dd")
        d = info.datum_paborjat or datetime.date.today()
        self.paborjad.setDate(QDate(d.year, d.month, d.day))
        self.digital = QCheckBox("Planen har tagits fram digitalt")
        self.digital.setToolTip("Avmarkera om planen är en befintlig, analog plan som digitaliseras "
                                "(digitaltUrsprung i Lantmäteriets specifikation).")
        self.digital.setChecked(info.digitalt_ursprung)
        self.beskrivning = QPlainTextEdit(info.digitaliseringsbeskrivning)
        self.beskrivning.setPlaceholderText("Hur den analoga planen har digitaliserats")
        self.beskrivning.setFixedHeight(4 * self.beskrivning.fontMetrics().lineSpacing() + 14)
        self.beskrivning.setEnabled(not info.digitalt_ursprung)
        self.digital.toggled.connect(lambda on: self.beskrivning.setEnabled(not on))
        page = QWidget()
        form = QFormLayout(page)
        form.addRow("Kommun", self.kommun)
        form.addRow("Planens titel", self.titel)
        form.addRow("Påbörjad", self.paborjad)
        form.addRow("", self.digital)
        form.addRow("Digitalisering", self.beskrivning)
        return page

    def _event_tab(self, info: PlanInfo, planhandelser: list[str]) -> QWidget:
        self.planhandelse = QComboBox()
        self.planhandelse.addItem(NONE, None)
        for value in planhandelser:
            self.planhandelse.addItem(value, value)
        index = self.planhandelse.findData(info.planhandelse)
        self.planhandelse.setCurrentIndex(max(index, 0))
        self.handelse_datum = OptionalDate("Datum", info.planhandelse_datum)
        self.update_content = QCheckBox("Ge allt innehåll i planen samma planhändelse")
        self.update_content.setChecked(True)
        self.update_content.setToolTip("Planhändelsen gäller i regel hela planen. Avmarkera om enskilt innehåll ska "
                                       "ha en annan planhändelse (den ändras då i objektets attributformulär).")
        note = QLabel("Planhändelsen är det senaste som hänt planen, till exempel att samrådsunderlaget är färdigställt "
                      "eller att planen är antagen. Nytt innehåll får planens planhändelse.")
        note.setWordWrap(True)
        note.setEnabled(False)
        page = QWidget()
        form = QFormLayout(page)
        form.addRow("Planhändelse", self.planhandelse)
        form.addRow("", self.handelse_datum)
        form.addRow("", self.update_content)
        form.addRow(note)
        return page

    def _decision_tab(self, info: PlanInfo) -> QWidget:
        decision = info.beslut
        self.diarienummer = QLineEdit(decision.diarienummer)
        self.diarienummer.setPlaceholderText("t.ex. KS 2027/123")
        self.instans = QLabel(f"{model.BESLUT_INSTANS.capitalize()} i {info.kommunnamn}")
        self.fattat = OptionalDate("Datum", decision.fattat)
        self.overklagat = OptionalDate("Datum", decision.overklagat)
        self.laga_kraft = OptionalDate("Datum", decision.laga_kraft)
        note = QLabel("Antagandebeslutet. Boverkets föreskrifter (BFS 2024:2, 2 kap. 2 §) kräver att översiktsplanen "
                      "redovisar antagandebeslutets diarienummer och datum när beslutet fick laga kraft. Fyll i dem "
                      "när planen är antagen. Beslutet gäller planen och allt innehåll som inte redan hör till ett "
                      "annat beslut.")
        note.setWordWrap(True)
        note.setEnabled(False)
        page = QWidget()
        form = QFormLayout(page)
        form.addRow("Diarienummer", self.diarienummer)
        form.addRow("Beslutande", self.instans)
        form.addRow("Antagen", self.fattat)
        form.addRow("Överklagad", self.overklagat)
        form.addRow("Laga kraft", self.laga_kraft)
        form.addRow(note)
        return page

    def _defaults_tab(self, info: PlanInfo) -> QWidget:
        defaults = info.defaults
        self.avgransning = QComboBox()
        self.avgransning.addItem(NO_LIMIT, "")
        for value in model.AVGRANSNING:
            self.avgransning.addItem(value, value)
        self.avgransning.setCurrentIndex(max(self.avgransning.findData(defaults["vertikal_avgransning"]), 0))
        self.under_ersattning = QCheckBox("Innehållet är under ersättning")
        self.under_ersattning.setChecked(defaults["under_ersattning"] == "1")
        date = datetime.date.fromisoformat(defaults["datum_paborjat"]) if defaults["datum_paborjat"] else None
        self.innehall_paborjat = OptionalDate("Datum", date)
        self.skala = QSpinBox()
        self.skala.setRange(0, 10_000_000)
        self.skala.setSingleStep(5000)
        self.skala.setPrefix("1:")
        self.skala.setSpecialValueText("Ingen")
        self.skala.setValue(int(defaults["presentationsskala"] or 0))
        note = QLabel("Värdena sätts på varje objekt som tilldelas innehåll från och med nu. Ett enskilt objekt kan "
                      "ändras i attributformuläret. Illustrativa gränser är alltid ja, som specifikationen kräver.")
        note.setWordWrap(True)
        note.setEnabled(False)
        page = QWidget()
        form = QFormLayout(page)
        form.addRow("Vertikal avgränsning", self.avgransning)
        form.addRow("", self.under_ersattning)
        form.addRow("Påbörjad", self.innehall_paborjat)
        form.addRow("Presentationsskala", self.skala)
        form.addRow(note)
        return page

    def _underlag_tab(self, items: list[Underlag]) -> QWidget:
        """Planens underlag: ett dokument per rad, med underlagstyp, namn, länk och datum."""
        self.underlag_table = QTableWidget(0, 4)
        self.underlag_table.setHorizontalHeaderLabels(["Underlagstyp", "Dokument", "Länk eller fil", "Datum"])
        self.underlag_table.verticalHeader().hide()
        self.underlag_table.setTextElideMode(Qt.TextElideMode.ElideMiddle)  # långa sökvägar: början och slutet syns
        self.underlag_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        header = self.underlag_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        for item in items:
            self.add_underlag(item)
        add = QPushButton("Lägg till")
        add.setToolTip("Lägg till ett underlag och skriv namnet och gärna en webbadress.")
        add.clicked.connect(lambda: self.add_underlag())
        add_file = QPushButton("Lägg till fil…")
        add_file.setToolTip("Välj ett dokument på datorn eller servern. Namnet och sökvägen fylls i.")
        add_file.clicked.connect(self.add_underlag_file)
        remove = QPushButton("Ta bort")
        remove.clicked.connect(self.remove_underlag)
        buttons = QHBoxLayout()
        for button in (add, add_file, remove):
            buttons.addWidget(button)
        buttons.addStretch(1)
        note = QLabel("Underlag är de dokument planen bygger på, till exempel planeringsunderlag och "
                      "miljökonsekvensbeskrivning. Lantmäteriets format kräver minst ett. Dokument med samma "
                      "underlagstyp samlas under samma underlag. En webbadress följer med i exporten; en sökväg på "
                      "datorn gör det inte.")
        note.setWordWrap(True)
        note.setEnabled(False)
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(self.underlag_table, 1)
        layout.addLayout(buttons)
        layout.addWidget(note)
        return page

    def add_underlag(self, item: Optional[Underlag] = None) -> int:
        """Lägger till en rad (tom eller med ``item``). Returnerar radens nummer."""
        table = self.underlag_table
        row = table.rowCount()
        table.insertRow(row)
        typ = QComboBox()
        typ.addItems(self.underlagstyper)
        wanted = item.typ if item else "Planeringsunderlag"
        typ.setCurrentIndex(max(typ.findText(wanted), 0))
        table.setCellWidget(row, 0, typ)
        table.setItem(row, 1, QTableWidgetItem(item.namn if item else ""))
        table.setItem(row, 2, QTableWidgetItem(item.lank if item else ""))
        date = OptionalDate("", item.datum if item else None)
        table.setCellWidget(row, 3, date)
        if item is None:
            table.setCurrentCell(row, 1)
            table.editItem(table.item(row, 1))
        return row

    def add_underlag_file(self) -> Optional[int]:
        path, _ = QFileDialog.getOpenFileName(self, "Välj underlag", "", "Alla filer (*)")
        if not path:
            return None
        from pathlib import Path
        row = self.add_underlag(Underlag(self.underlagstyper[0] if self.underlagstyper else "", Path(path).stem,
                                         path))
        typ = self.underlag_table.cellWidget(row, 0)
        typ.setCurrentIndex(max(typ.findText("Planeringsunderlag"), 0))
        return row

    def remove_underlag(self) -> None:
        rows = sorted({index.row() for index in self.underlag_table.selectedIndexes()}, reverse=True)
        if not rows and self.underlag_table.currentRow() >= 0:
            rows = [self.underlag_table.currentRow()]
        for row in rows:
            self.underlag_table.removeRow(row)

    def underlag(self) -> list[Underlag]:
        """Underlagen i fliken (rader utan dokumentnamn räknas inte)."""
        result = []
        if self.underlag_tab is None:
            return result
        table = self.underlag_table
        for row in range(table.rowCount()):
            name = table.item(row, 1).text().strip() if table.item(row, 1) else ""
            if not name:
                continue
            link = table.item(row, 2).text().strip() if table.item(row, 2) else ""
            result.append(Underlag(table.cellWidget(row, 0).currentText(), name, link,
                                   table.cellWidget(row, 3).value()))
        return result

    # -- resultat -----------------------------------------------------------------------
    def plan_info(self) -> PlanInfo:
        d = self.paborjad.date()
        start = self.innehall_paborjat.value()
        return PlanInfo(
            kommunnamn=self.info.kommunnamn, kommunkod=self.info.kommunkod, titel=self.titel.text().strip(),
            datum_paborjat=datetime.date(d.year(), d.month(), d.day()),
            digitalt_ursprung=self.digital.isChecked(),
            digitaliseringsbeskrivning="" if self.digital.isChecked() else self.beskrivning.toPlainText().strip(),
            planhandelse=self.planhandelse.currentData(), planhandelse_datum=self.handelse_datum.value(),
            defaults={"vertikal_avgransning": self.avgransning.currentData(),
                      "under_ersattning": "1" if self.under_ersattning.isChecked() else "0",
                      "datum_paborjat": start.isoformat() if start else "",
                      "presentationsskala": str(self.skala.value()) if self.skala.value() else ""},
            beslut=Decision(diarienummer=self.diarienummer.text().strip(), fattat=self.fattat.value(),
                            overklagat=self.overklagat.value(), laga_kraft=self.laga_kraft.value()),
        )
