"""Dialogrutan för att öppna en översiktsplan som ligger i en PostGIS-databas (som i Rita Detaljplan)."""
from __future__ import annotations

from typing import Optional

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QListWidget,
                                 QListWidgetItem, QVBoxLayout)

from ..core import storage


class PostgisPlanDialog(QDialog):
    def __init__(self, parent=None, connections: Optional[dict] = None):
        super().__init__(parent)
        self.setWindowTitle("Öppna översiktsplan från databas")
        self.setMinimumWidth(440)
        self._connections = connections if connections is not None else storage.postgis_connections()
        self.connection = QComboBox()
        for name in sorted(self._connections):
            self.connection.addItem(name, name)
        self.schema = QComboBox()
        self.plans = QListWidget()
        self.error = QLabel()
        self.error.setWordWrap(True)
        self.error.setStyleSheet("color: #b3261e;")
        hint = QLabel("En plan som öppnas från databasen är skrivskyddad. Checka ut den för att redigera.")
        hint.setWordWrap(True)
        hint.setEnabled(False)  # dämpad färg
        form = QFormLayout()
        form.addRow("Anslutning", self.connection)
        form.addRow("Schema", self.schema)
        form.addRow("Översiktsplaner", self.plans)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Öppna")
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Avbryt")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(hint)
        layout.addWidget(self.error)
        layout.addWidget(self.buttons)
        self.connection.currentIndexChanged.connect(self.reload_schemas)
        self.schema.currentIndexChanged.connect(self.reload_plans)
        self.plans.itemSelectionChanged.connect(self._update_ok)
        self.plans.itemDoubleClicked.connect(lambda *_: self.accept() if self.selection() else None)
        self.reload_schemas()

    def _current_connection(self):
        return self._connections.get(self.connection.currentData() or "")

    def reload_schemas(self, *_) -> None:
        """Listar scheman som pluginet har skapat i den valda databasen."""
        self.schema.blockSignals(True)
        self.schema.clear()
        self.error.setText("")
        connection = self._current_connection()
        if connection is not None:
            try:
                for schema in storage.list_plugin_schemas(connection):
                    self.schema.addItem(schema, schema)
            except storage.PostgisError as exc:
                self.error.setText(str(exc))
            else:
                if not self.schema.count():
                    self.error.setText("Databasen har inga scheman med översiktsplaner från Rita Översiktsplan.")
        self.schema.blockSignals(False)
        self.reload_plans()

    def reload_plans(self, *_) -> None:
        """Listar planerna i det valda schemat."""
        self.plans.clear()
        connection, schema = self._current_connection(), self.schema.currentData()
        if connection is not None and schema:
            try:
                for plan_id, title in storage.list_plans(connection, schema):
                    item = QListWidgetItem(f"{title} ({plan_id})" if title else plan_id)
                    item.setData(Qt.ItemDataRole.UserRole, plan_id)
                    self.plans.addItem(item)
            except storage.PostgisError as exc:
                self.error.setText(str(exc))
            else:
                if not self.plans.count() and not self.error.text():
                    self.error.setText("Schemat innehåller inga planer.")
        self._update_ok()

    def selection(self) -> Optional[tuple[str, str, str]]:
        """(anslutning, schema, planens id) för den valda planen, eller None."""
        item = self.plans.currentItem()
        if item is None or not self.connection.currentData() or not self.schema.currentData():
            return None
        return self.connection.currentData(), self.schema.currentData(), item.data(Qt.ItemDataRole.UserRole)

    def _update_ok(self) -> None:
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(self.selection() is not None)
