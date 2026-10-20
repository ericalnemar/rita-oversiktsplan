"""Dialogen "Tilldela innehåll": välj grupp och innehållstyp för en ritad yta, linje eller punkt, och fyll i det som
gäller just det objektet (namn, precisering, kompletterande innehållstyp …). Det som gäller allt innehåll i planen,
som planhändelse och vertikal avgränsning, ställs in under Planens uppgifter och följer med automatiskt."""
from __future__ import annotations

from typing import Optional

from qgis.PyQt.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel,
                                 QLineEdit, QPlainTextEdit, QVBoxLayout, QWidget)

from ..core import model, opkatalog, styles
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
        self.utbyggnadsordning = QComboBox()
        self.utbyggnadsordning.setEditable(True)  # planens etapper, eller egen text
        self.utbyggnadsordning.addItem("")
        self.utbyggnadsordning.addItems(lookups.get("utbyggnadsordning", []))
        self.utbyggnadsordning.lineEdit().setPlaceholderText("Ingen etapp (befintligt)")
        self.utbyggnadsordning.setToolTip("Etappen i planens utbyggnadsordning (ställs in under Planens uppgifter, "
                                          "fliken Utbyggnadsordning). Tom för befintlig eller bevarad användning.")
        self.riksintresse = QLineEdit()
        self.riksintresse.setPlaceholderText("Id hos den myndighet som pekat ut riksintresset (valfritt)")
        self.riksintresse.setToolTip("Riksintressets identitet i den ansvariga myndighetens data, till exempel "
                                     "Naturvårdsverkets eller Trafikverkets. Följer med i exporten som en extern "
                                     "referens.")
        self.arrow_end = QCheckBox("där linjen slutar")
        self.arrow_start = QCheckBox("där linjen börjar")
        self.arrow_end.setToolTip("En pilspets i linjens sista punkt, där du slutade rita.")
        self.arrow_start.setToolTip("En pilspets i linjens första punkt, där du började rita.")
        self.arrows = QWidget()
        arrows_row = QHBoxLayout(self.arrows)
        arrows_row.setContentsMargins(0, 0, 0, 0)
        arrows_row.addWidget(self.arrow_end)
        arrows_row.addWidget(self.arrow_start)
        arrows_row.addStretch(1)
        self._arrows_touched = False  # följer temat tills man själv kryssar
        for box in (self.arrow_end, self.arrow_start):
            box.clicked.connect(lambda *_: setattr(self, "_arrows_touched", True))
        self.complement.currentIndexChanged.connect(self._default_arrows)
        self.suffix = suffix
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
        self.form.addRow("Riksintressets id", self.riksintresse)
        self.form.addRow("Pilspets", self.arrows)
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
        """Om lagret som objektet hamnar i har fältet (geometrin avgör: pilspetsar finns bara för linjer)."""
        layer_defs = [d for d in model.CONTENT_LAYERS if d.category == self.category()]
        layer_def = next((d for d in layer_defs if d.name.endswith(f"_{self.suffix}")), layer_defs[0])
        return any(f.name == field for f in layer_def.fields)

    def _default_arrows(self, *_) -> None:
        if self._arrows_touched:
            return
        end, start = styles.default_arrows(self.complement.currentData())
        self.arrow_end.setChecked(end)
        self.arrow_start.setChecked(start)

    def arrow_value(self) -> Optional[str]:
        """Fältets värde: tomt så länge kryssen är temats standard (då följer pilarna temat), annars valet."""
        chosen = (self.arrow_end.isChecked(), self.arrow_start.isChecked())
        if chosen == styles.default_arrows(self.complement.currentData()):
            return None
        return {(True, False): model.ARROW_END, (False, True): model.ARROW_START, (True, True): model.ARROW_BOTH,
                (False, False): model.ARROW_NONE}[chosen]

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
                              (self.utbyggnadsordning, "utbyggnadsordning"),
                              (self.riksintresse, "objektidentitet_ri"), (self.arrows, model.ARROW_FIELD)):
            self.form.setRowVisible(widget, self._has(field))
        self._default_arrows()
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
        self.utbyggnadsordning.setCurrentText(str(current.get("utbyggnadsordning") or ""))
        self.riksintresse.setText(str(current.get("objektidentitet_ri") or ""))
        chosen = {model.ARROW_END: (True, False), model.ARROW_START: (False, True), model.ARROW_BOTH: (True, True),
                  model.ARROW_NONE: (False, False)}.get(current.get(model.ARROW_FIELD))
        if chosen is not None:
            self.arrow_end.setChecked(chosen[0])
            self.arrow_start.setChecked(chosen[1])
            self._arrows_touched = True
        else:
            self._default_arrows()

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
            values["utbyggnadsordning"] = self.utbyggnadsordning.currentText().strip() or None
        if self._has("objektidentitet_ri"):
            values["objektidentitet_ri"] = self.riksintresse.text().strip() or None
        if self._has(model.ARROW_FIELD):
            values[model.ARROW_FIELD] = self.arrow_value()
        return Assignment(self.category(), values)
