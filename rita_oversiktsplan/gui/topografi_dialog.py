"""Dialogen "Markanvändning från Topografi 10": välj Lantmäteriets Topografi 10 (eller Marktäcke), se och ändra
omklassningen till ÖP-katalogens mark- och vattenanvändning, och skapa befintlig markanvändning i planen (se
:mod:`..core.topografi`)."""
from __future__ import annotations

import json
from typing import Optional

from qgis.core import QgsSettings
from qgis.gui import QgsFileWidget
from qgis.PyQt.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
                                 QHeaderView, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout)

from ..core import topografi
from ..core.topografi import Key

SETTINGS_KEY = "rita_oversiktsplan/topografi_omklassning"
SKIP_TEXT = "– tas inte med –"
KIND_TEXT = {"polygon": "Yta", "line": "Linje", "point": "Punkt"}
INTRO = ("Skapar befintlig mark- och vattenanvändning ur Lantmäteriets Topografi 10 eller Marktäcke. Ladda först ner "
         "kommunen från Lantmäteriets Geotorget (kräver inloggning) och välj zip-filen eller en GeoPackage. Varje "
         "objekttyp omklassas till ett värde i ÖP-katalogen: ytor (markslag, anläggningsområden) blir mark- och "
         "vattenanvändning som yta, vägar, järnvägar, vattendrag och ledningar som linje, och vissa punkter som punkt. "
         "Ytor och linjer med samma värde slås ihop och klipps mot planens avgränsning. Topografi 10 visar vad som "
         "finns på marken, inte alltid vad den används till: se över resultatet och rätta för hand.")


def load_saved() -> dict[str, Optional[str]]:
    try:
        saved = json.loads(QgsSettings().value(SETTINGS_KEY, "{}") or "{}")
    except ValueError:
        return {}
    return saved if isinstance(saved, dict) else {}


def save(mapping: dict[str, Optional[str]]) -> None:
    saved = load_saved()
    saved.update(mapping)
    QgsSettings().setValue(SETTINGS_KEY, json.dumps(saved, ensure_ascii=False))


class TopografiDialog(QDialog):
    def __init__(self, group, values: list[str], crs, plan_area, parent=None):
        """``values`` är ÖP-katalogens värden för mark- och vattenanvändning i planen, ``plan_area`` planens
        avgränsning (eller None)."""
        super().__init__(parent)
        self.group, self.values, self.crs, self.plan_area = group, values, crs, plan_area
        self.keys: list[Key] = []
        self.outcome: Optional[tuple[dict[str, int], int]] = None
        self.setWindowTitle("Markanvändning från Topografi 10")
        self.setMinimumWidth(720)
        intro = QLabel(INTRO)
        intro.setWordWrap(True)
        intro.setEnabled(False)

        self.file = QgsFileWidget()
        self.file.setFilter("Topografi 10 eller Marktäcke (*.zip *.gpkg)")
        self.file.setToolTip("Zip-filen från Geotorget (en GeoPackage per tema), eller en GeoPackage.")
        self.file.fileChanged.connect(self.load_file)
        self.clip = QCheckBox("Klipp mot planens avgränsning (plangeometrin)")
        self.clip.setChecked(plan_area is not None)
        self.clip.setEnabled(plan_area is not None)
        if plan_area is None:
            self.clip.setToolTip("Planen har ingen plangeometri: hela filen tas med.")
        self.replace = QCheckBox("Ersätt markanvändning som tidigare skapats från Lantmäteriet")
        self.replace.setChecked(True)
        self.replace.setToolTip("Objekt som du själv ritat eller tilldelat rörs inte; bara de vars precisering börjar "
                                f"med \"{topografi.MARK}\".")

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Skikt", "Geometri", "Objekttyp (ändamål)",
                                              "Mark- och vattenanvändning i ÖP"])
        self.table.verticalHeader().hide()
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.reset_button = QPushButton("Återställ förslaget")
        self.reset_button.clicked.connect(self.reset)

        form = QFormLayout()
        form.addRow("Fil", self.file)
        form.addRow("", self.clip)
        form.addRow("", self.replace)

        self.message = QLabel()
        self.message.setWordWrap(True)
        self.run_button = QPushButton("Skapa markanvändning")
        self.run_button.setEnabled(False)
        self.run_button.clicked.connect(self.run)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText("Stäng")
        buttons.addButton(self.reset_button, QDialogButtonBox.ButtonRole.ResetRole)
        buttons.addButton(self.run_button, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addLayout(form)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.message)
        layout.addWidget(buttons)

    # -- omklassningen -------------------------------------------------------------------------------------------------
    def load_file(self, path: str = "") -> list[Key]:
        """Läser objekttyperna i filen och fyller tabellen med omklassningen (sparad, annars förslaget)."""
        path = path or self.file.filePath()
        self.table.setRowCount(0)
        self.keys = []
        self.run_button.setEnabled(False)
        if not path:
            return []
        self._say("Läser filen …")
        try:
            self.keys = topografi.read_keys(path)
        except (ValueError, OSError) as exc:
            self._say(str(exc))
            return []
        self.fill(topografi.mapping_for(self.keys, load_saved()))
        self._say(f"{len(self.keys)} objekttyper i filen. Ändra omklassningen vid behov och klicka Skapa "
                  "markanvändning.")
        self.run_button.setEnabled(bool(self.keys))
        return self.keys

    def fill(self, mapping: dict[str, Optional[str]]) -> None:
        self.table.setRowCount(0)
        for row, key in enumerate(self.keys):
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(key.layer))
            self.table.setItem(row, 1, QTableWidgetItem(KIND_TEXT[key.kind]))
            self.table.setItem(row, 2, QTableWidgetItem(key.label))
            combo = QComboBox()
            combo.addItem(SKIP_TEXT, None)
            for v in self.values:
                combo.addItem(v, v)
            combo.setCurrentIndex(max(combo.findData(mapping.get(key.id)), 0))
            self.table.setCellWidget(row, 3, combo)

    def mapping(self) -> dict[str, Optional[str]]:
        return {key.id: self.table.cellWidget(row, 3).currentData() for row, key in enumerate(self.keys)}

    def value_for(self, label: str, layer: str = "") -> Optional[str]:
        """Värdet i tabellen för en objekttyp (för tester och bilder)."""
        for row, key in enumerate(self.keys):
            if key.label == label and (not layer or key.layer == layer):
                return self.table.cellWidget(row, 3).currentData()
        raise KeyError(label)

    def set_value(self, label: str, value: Optional[str]) -> None:
        for row, key in enumerate(self.keys):
            if key.label == label:
                combo = self.table.cellWidget(row, 3)
                combo.setCurrentIndex(max(combo.findData(value), 0))

    def reset(self) -> None:
        self.fill(topografi.mapping_for(self.keys))

    # -- skapa ----------------------------------------------------------------------------------------------------------
    def _say(self, text: str) -> None:
        self.message.setText(text)
        QApplication.processEvents()

    def run(self) -> Optional[tuple[dict[str, int], int]]:
        mapping = self.mapping()
        if not any(mapping.values()):
            self._say("Ingen objekttyp är omklassad till mark- och vattenanvändning.")
            return None
        save(mapping)
        clip = self.plan_area if self.clip.isChecked() and self.clip.isEnabled() else None
        try:
            built = topografi.build(self.file.filePath(), mapping, clip, self.crs, self._say)
            added, removed = topografi.add_to_plan(self.group, built, self.replace.isChecked())
        except (ValueError, OSError) as exc:
            self._say(str(exc))
            return None
        self.outcome = (added, removed)
        lines = [f"{name}: {count}" for name, count in sorted(added.items())]
        self._say("Skapade befintlig mark- och vattenanvändning: " + (", ".join(lines) if lines else "inget")
                  + "." + (f" {removed} tidigare objekt från Lantmäteriet ersattes." if removed else "")
                  + " Spara med Avsluta redigering (disketten).")
        return self.outcome
