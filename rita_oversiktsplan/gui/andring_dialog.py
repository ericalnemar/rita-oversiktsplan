"""Dialogen "Ändring av översiktsplanen": påbörja en ändring, lägg innehåll i den, markera innehåll som ska ersättas,
fyll i beslutet och anta ändringen (se :mod:`..core.andring`)."""
from __future__ import annotations

import datetime
from typing import Optional

from qgis.PyQt.QtCore import QDate
from qgis.PyQt.QtWidgets import (QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox, QFormLayout, QGroupBox,
                                 QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QStackedWidget, QVBoxLayout,
                                 QWidget)

from ..core import andring
from .plan_info_dialog import OptionalDate

NONE = "– ingen än –"
START_NOTE = ("En ändring är ett eget planärende för en del av översiktsplanen, med egen planhändelse och eget "
              "beslut. Medan ändringen pågår får allt nytt innehåll ändringens planhändelse och datum påbörjat, och "
              "hör till ändringen. Innehåll i den gällande planen som ändringen ska ersätta markeras som under "
              "ersättning.")
ONGOING_NOTE = ("Rita och tilldela nytt innehåll som vanligt: det hör till ändringen. Markera befintligt innehåll i "
                "kartan (verktyget Markera) och lägg det i ändringen om det ändras, eller markera det som under "
                "ersättning om nytt innehåll ska ersätta det. När ändringen är antagen fyller du i beslutet och "
                "klickar Anta ändringen.")


def _date_edit(value: Optional[datetime.date] = None) -> QDateEdit:
    edit = QDateEdit()
    edit.setCalendarPopup(True)
    edit.setDisplayFormat("yyyy-MM-dd")
    d = value or datetime.date.today()
    edit.setDate(QDate(d.year, d.month, d.day))
    return edit


def _py(edit: QDateEdit) -> datetime.date:
    d = edit.date()
    return datetime.date(d.year(), d.month(), d.day())


def _note(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setEnabled(False)  # dämpad färg
    return label


class AndringDialog(QDialog):
    def __init__(self, group, events: list[str], parent=None):
        super().__init__(parent)
        self.group = group
        self.events = events
        self.setWindowTitle("Ändring av översiktsplanen")
        self.setMinimumWidth(560)
        self.pages = QStackedWidget()
        self.pages.addWidget(self._start_page())
        self.pages.addWidget(self._ongoing_page())
        self.message = QLabel()
        self.message.setWordWrap(True)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText("Stäng")
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(self.pages)
        layout.addWidget(self.message)
        layout.addStretch(1)
        layout.addWidget(buttons)
        self.refresh()

    # -- sidor --------------------------------------------------------------------------------------------------------
    def _event_combo(self) -> QComboBox:
        combo = QComboBox()
        combo.addItem(NONE, None)
        for event in self.events:
            combo.addItem(event, event)
        return combo

    def _start_page(self) -> QWidget:
        self.start_name = QLineEdit()
        self.start_name.setPlaceholderText("t.ex. Tillägg för vindbruk")
        self.start_diarienummer = QLineEdit()
        self.start_diarienummer.setPlaceholderText("ändringsärendets diarienummer (kan fyllas i senare)")
        self.start_date = _date_edit()
        self.start_date.setToolTip("Datum för kommunens beslut att påbörja ändringen (datumPaborjat på innehållet).")
        self.start_event = self._event_combo()
        self.start_event_date = OptionalDate("Datum", None)
        self.start_button = QPushButton("Påbörja ändringen")
        self.start_button.clicked.connect(self.start)
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        form = QFormLayout()
        form.addRow("Namn", self.start_name)
        form.addRow("Diarienummer", self.start_diarienummer)
        form.addRow("Påbörjad", self.start_date)
        form.addRow("Planhändelse", self.start_event)
        form.addRow("", self.start_event_date)
        layout.addWidget(_note(START_NOTE))
        layout.addLayout(form)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.start_button)
        layout.addLayout(row)
        return page

    def _ongoing_page(self) -> QWidget:
        self.title = QLabel()
        self.counts = QLabel()
        self.counts.setWordWrap(True)
        self.event = self._event_combo()
        self.event_date = OptionalDate("Datum", None)
        self.diarienummer = QLineEdit()
        self.fattat = OptionalDate("Datum", None)
        self.overklagat = OptionalDate("Datum", None)
        self.laga_kraft = OptionalDate("Datum", None)
        self.save_button = QPushButton("Spara uppgifterna")
        self.save_button.clicked.connect(self.save)
        self.add_button = QPushButton("Lägg markerat innehåll i ändringen")
        self.add_button.setToolTip("Det markerade innehållet ändras i ändringen: det får ändringens planhändelse, "
                                   "datum påbörjat och beslut.")
        self.add_button.clicked.connect(self.add_selected)
        self.replace_button = QPushButton("Markera som under ersättning")
        self.replace_button.setToolTip("Det markerade innehållet i den gällande planen ska ersättas av ändringen.")
        self.replace_button.clicked.connect(lambda: self.mark_replaced(True))
        self.unreplace_button = QPushButton("Ta bort markeringen")
        self.unreplace_button.clicked.connect(lambda: self.mark_replaced(False))
        self.remove_replaced = QCheckBox("Ta bort innehållet under ersättning när ändringen antas")
        self.remove_replaced.setChecked(True)
        self.adopt_button = QPushButton("Anta ändringen")
        self.adopt_button.clicked.connect(self.adopt)
        self.cancel_button = QPushButton("Avbryt ändringen")
        self.cancel_button.clicked.connect(self.cancel)

        details = QGroupBox("Ändringens planhändelse och beslut")
        form = QFormLayout(details)
        form.addRow("Planhändelse", self.event)
        form.addRow("", self.event_date)
        form.addRow("Diarienummer", self.diarienummer)
        form.addRow("Antagen", self.fattat)
        form.addRow("Överklagad", self.overklagat)
        form.addRow("Laga kraft", self.laga_kraft)
        save_row = QHBoxLayout()
        save_row.addStretch(1)
        save_row.addWidget(self.save_button)
        form.addRow(save_row)

        content = QGroupBox("Innehåll")
        content_layout = QVBoxLayout(content)
        content_layout.addWidget(self.counts)
        buttons = QHBoxLayout()
        for button in (self.add_button, self.replace_button, self.unreplace_button):
            buttons.addWidget(button)
        buttons.addStretch(1)
        content_layout.addLayout(buttons)

        finish = QHBoxLayout()
        finish.addWidget(self.remove_replaced)
        finish.addStretch(1)
        finish.addWidget(self.cancel_button)
        finish.addWidget(self.adopt_button)

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.title)
        layout.addWidget(_note(ONGOING_NOTE))
        layout.addWidget(details)
        layout.addWidget(content)
        layout.addLayout(finish)
        return page

    # -- läge ---------------------------------------------------------------------------------------------------------
    def refresh(self) -> None:
        change = andring.active(self.group)
        self.pages.setCurrentIndex(0 if change is None else 1)
        if change is None:
            return
        started = change.paborjat.isoformat() if change.paborjat else "okänt datum"
        self.title.setText(f"<b>Pågående ändring: {change.namn}</b> (påbörjad {started})")
        self.event.setCurrentIndex(max(self.event.findData(change.planhandelse), 0))
        self._set_date(self.event_date, change.planhandelse_datum)
        self.diarienummer.setText(change.diarienummer)
        for widget, value in ((self.fattat, change.fattat), (self.overklagat, change.overklagat),
                              (self.laga_kraft, change.laga_kraft)):
            self._set_date(widget, value)
        self.counts.setText(f"{andring.members(self.group, change.beslut)} innehåll hör till ändringen. "
                            f"{andring.replaced(self.group)} innehåll är under ersättning. "
                            f"{len(andring.selected(self.group))} innehåll är markerat i kartan.")

    @staticmethod
    def _set_date(widget: OptionalDate, value: Optional[datetime.date]) -> None:
        widget.enabled.setChecked(value is not None)
        if value is not None:
            widget.edit.setDate(QDate(value.year, value.month, value.day))

    def _report(self, text: str) -> None:
        self.message.setText(text)
        self.refresh()

    def _ask(self, title: str, text: str) -> bool:  # byts ut i tester
        return QMessageBox.question(self, title, text) == QMessageBox.StandardButton.Yes

    def _run(self, action) -> Optional[object]:
        try:
            return action()
        except ValueError as exc:
            self.message.setText(str(exc))
            return None

    # -- åtgärder -------------------------------------------------------------------------------------------------------
    def start(self) -> Optional[andring.Andring]:
        change = self._run(lambda: andring.start(
            self.group, self.start_name.text(), self.start_diarienummer.text(), _py(self.start_date),
            self.start_event.currentData(), self.start_event_date.value()))
        if change is not None:
            self._report(f"Ändringen {change.namn} är påbörjad. Nytt innehåll hör nu till den.")
        return change

    def save(self) -> Optional[int]:
        changed = self._run(lambda: andring.update(
            self.group, self.event.currentData(), self.event_date.value(), self.diarienummer.text(),
            self.fattat.value(), self.overklagat.value(), self.laga_kraft.value()))
        if changed is not None:
            self._report(f"Sparade. {changed} innehåll har ändringens planhändelse.")
        return changed

    def add_selected(self) -> Optional[int]:
        count = self._run(lambda: andring.add_selected(self.group))
        if count is not None:
            self._report(f"{count} innehåll lades i ändringen." if count else "Markera innehåll i kartan först.")
        return count

    def mark_replaced(self, on: bool) -> Optional[int]:
        count = self._run(lambda: andring.mark_replaced(self.group, on))
        if count is not None:
            self._report((f"{count} innehåll är under ersättning." if on else
                          f"{count} innehåll är inte längre under ersättning.") if count
                         else "Markera innehåll i den gällande planen i kartan först.")
        return count

    def adopt(self) -> Optional[tuple[int, int]]:
        if self.save() is None:
            return None
        remove = self.remove_replaced.isChecked()
        replaced = andring.replaced(self.group)
        if remove and replaced and not self._ask(
                "Anta ändringen", f"{replaced} innehåll under ersättning tas bort. Vill du fortsätta?"):
            return None
        done = self._run(lambda: andring.finish(self.group, remove))
        if done is not None:
            adopted, removed = done
            self._report(f"Ändringen är antagen: {adopted} innehåll fick planhändelsen Antagen"
                         + (f" och {removed} ersatt innehåll togs bort." if removed else "."))
        return done

    def cancel(self) -> bool:
        if not self._ask("Avbryt ändringen", "Ändringen avbryts: nytt innehåll hör inte längre automatiskt till den. "
                                             "Innehållet och beslutet finns kvar. Vill du fortsätta?"):
            return False
        andring.cancel(self.group)
        self._report("Ändringen är avbruten.")
        return True
