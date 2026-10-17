"""Dialogen "Tilldela innehåll": välj grupp och innehållstyp för en ritad yta, linje eller punkt, och fyll i det som
gäller just det objektet (namn, precisering, kompletterande innehållstyp …). Det som gäller allt innehåll i planen,
som planhändelse och vertikal avgränsning, ställs in under Planens uppgifter och följer med automatiskt."""
from __future__ import annotations

from typing import Optional

from qgis.PyQt.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit,
                                 QPlainTextEdit, QVBoxLayout)

from ..core import model, opkatalog
from ..core.content import Assignment

NONE = "– ingen –"
GEOMETRY_WORDS = {**{suffix: word for suffix, _, word in model.GEOMETRIES}, model.NO_GEOMETRY: "utan geometri"}


class AssignDialog(QDialog):
    def __init__(self, suffix: str, lookups: dict[str, list[str]], current: Optional[dict] = None,
                 category: Optional[model.Category] = None, parent=None):
        """``suffix`` är geometrin (polygon, line, point), ``lookups`` värdena i planens uppslagstabeller och
        ``current``/``category`` det objektet redan har, när man byter typ på tilldelat innehåll."""
        super().__init__(parent)
        self.lookups = lookups
        self.catalog = opkatalog.bundled()
        self.categories = model.categories_for(suffix)
        self.setWindowTitle(f"Tilldela innehåll – {GEOMETRY_WORDS[suffix]}")
        self.setMinimumWidth(520)

        self.group = QComboBox()
        for c in self.categories:
            self.group.addItem(c.alias, c.key)
        self.value = QComboBox()
        self.complement = QComboBox()
        self.sambandsniva = QComboBox()
        self.namn = QLineEdit()
        self.namn.setPlaceholderText("Valfritt, t.ex. ett områdes namn")
        self.precisering = QPlainTextEdit()
        self.precisering.setPlaceholderText("Kommunens precisering av innehållet (valfritt)")
        self.precisering.setFixedHeight(4 * self.precisering.fontMetrics().lineSpacing() + 14)
        self.utbyggnadsordning = QLineEdit()
        self.description = QLabel()
        self.description.setWordWrap(True)
        self.description.setEnabled(False)  # dämpad färg

        self.form = QFormLayout()
        self.form.addRow("Grupp", self.group)
        self.form.addRow("Innehållstyp", self.value)
        self.form.addRow("", self.description)
        self.form.addRow("Kompletterande", self.complement)
        self.form.addRow("Sambandsnivå", self.sambandsniva)
        self.form.addRow("Namn", self.namn)
        self.form.addRow("Precisering", self.precisering)
        self.form.addRow("Utbyggnadsordning", self.utbyggnadsordning)
        note = QLabel("Planhändelse, vertikal avgränsning och andra uppgifter som gäller allt innehåll ställs in "
                      "under Planens uppgifter.")
        note.setWordWrap(True)
        note.setEnabled(False)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Tilldela")
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Avbryt")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(self.form)
        layout.addWidget(note)
        layout.addWidget(self.buttons)

        self.group.currentIndexChanged.connect(self._on_group)
        self.value.currentIndexChanged.connect(self._on_value)
        if category is not None and category in self.categories:
            self.group.setCurrentIndex(self.categories.index(category))
        self._on_group()
        if current:
            self._fill(current)

    # -- grupp och värden ---------------------------------------------------------------
    def category(self) -> model.Category:
        return self.categories[self.group.currentIndex()]

    def _has(self, field: str) -> bool:
        layer_def = next(d for d in model.CONTENT_LAYERS if d.category == self.category())
        return any(f.name == field for f in layer_def.fields)

    def _on_group(self, *_):
        category = self.category()
        self.value.blockSignals(True)
        self.value.clear()
        self.value.addItems(self.lookups.get(category.lookup, []))
        self.value.blockSignals(False)
        self._fill_combo(self.complement, self.lookups.get(category.kompletterande, []) if category.kompletterande
                         else [])
        self._fill_combo(self.sambandsniva, self.lookups.get(model.SAMBANDSNIVA_LOOKUP.name, [])
                         if self._has("sambandsniva_varde") else [])
        # Boverkets tabeller har kolumnen för kompletterande innehållstyp överallt, men bara Mark- och
        # vattenanvändning och Utvecklingsinriktning har en kompletterande lista i ÖP-katalogen.
        self.form.setRowVisible(self.complement, category.kompletterande is not None)
        for widget, field in ((self.sambandsniva, "sambandsniva_varde"), (self.precisering, "precisering"),
                              (self.utbyggnadsordning, "utbyggnadsordning")):
            self.form.setRowVisible(widget, self._has(field))
        self._on_value()

    def _fill_combo(self, combo: QComboBox, values: list[str]) -> None:
        combo.clear()
        combo.addItem(NONE, None)
        for value in values:
            combo.addItem(value, value)

    def _on_value(self, *_):
        category = self.category()
        lookup = next(l for l in model.LOOKUPS if l.name == category.lookup)
        found = self.catalog.find(lookup.category, self.value.currentText(), lookup.group, lookup.itself)
        self.description.setText(found.beskrivning if found is not None else "")
        self.form.setRowVisible(self.description, bool(self.description.text()))

    def _fill(self, current: dict) -> None:
        index = self.value.findText(str(current.get("innehallstyp_varde") or ""))
        if index >= 0:
            self.value.setCurrentIndex(index)
        for combo, field in ((self.complement, "kompletterandeInnehallstyp"), (self.sambandsniva, "sambandsniva_varde")):
            index = combo.findData(current.get(field))
            if index >= 0:
                combo.setCurrentIndex(index)
        self.namn.setText(str(current.get("namn") or ""))
        self.precisering.setPlainText(str(current.get("precisering") or ""))
        self.utbyggnadsordning.setText(str(current.get("utbyggnadsordning") or ""))

    # -- resultat -----------------------------------------------------------------------
    def assignment(self) -> Assignment:
        values: dict[str, object] = {"innehallstyp_varde": self.value.currentText() or None,
                                     "namn": self.namn.text().strip() or None}
        if self.category().kompletterande is not None:
            values["kompletterandeInnehallstyp"] = self.complement.currentData()
        if self._has("sambandsniva_varde"):
            values["sambandsniva_varde"] = self.sambandsniva.currentData()
        if self._has("precisering"):
            values["precisering"] = self.precisering.toPlainText().strip() or None
        if self._has("utbyggnadsordning"):
            values["utbyggnadsordning"] = self.utbyggnadsordning.text().strip() or None
        return Assignment(self.category(), values)
