"""Dialogruta för att skapa en ny översiktsplan, uppbyggd som Ny detaljplan i Rita Detaljplan: kommun och namn,
var planen lagras (lokal fil eller PostGIS-databas) och koordinatsystem. Inget digitaliseringsläge: en översiktsplan
som tas fram med pluginet är ny och har digitalt ursprung (det går att ändra under Planens uppgifter)."""
from __future__ import annotations

import datetime
import re
from pathlib import Path

from qgis.core import QgsCoordinateReferenceSystem
from qgis.gui import QgsFileWidget
from qgis.PyQt.QtCore import QDate
from qgis.PyQt.QtWidgets import (QComboBox, QDateEdit, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
                                 QLabel, QLineEdit, QRadioButton, QVBoxLayout, QWidget)

from ..core import geopackage, model, storage
from ..core.opkatalog import bundled
from .kommun_combo import KommunCombo


def safe_filename(name: str) -> str:
    """Gör en titel till ett filnamn (behåller å, ä, ö)."""
    return re.sub(r"[^\w\-]+", "_", name.strip(), flags=re.UNICODE).strip("_")


FILE, DATABASE = "file", "database"
DEFAULT_SCHEMA = "oversiktsplan"
CRS_TIP = ("Planens koordinatsystem. Lantmäteriets specifikation tillåter SWEREF 99 TM och de tolv lokala SWEREF "
           "99-zonerna; Boverkets GIS-databasmodell använder SWEREF 99 TM. Välj den zon kommunen arbetar i. Kan inte "
           "ändras efteråt. I en databas delar alla planer i samma schema koordinatsystem.")


class NewPlanDialog(QDialog):
    def __init__(self, parent=None, connections: dict | None = None):
        super().__init__(parent)
        self._connections = connections if connections is not None else storage.postgis_connections()
        self.setWindowTitle("Ny översiktsplan")
        self.setMinimumWidth(480)

        self.kommun = KommunCombo()
        self.kommun.setToolTip("Kommunen som planen gäller. Kommunkoden och namnet sparas i planen.")
        self.titel = QLineEdit()
        self.titel.setPlaceholderText("t.ex. Översiktsplan 2045")
        self.titel.setToolTip("Planens titel. Filnamnet och planens id i databasen föreslås utifrån den.")

        # -- var planen ska lagras ------------------------------------------------------------------------------
        self.use_file = QRadioButton("Lokal fil (GeoPackage)")
        self.use_postgis = QRadioButton("PostGIS-databas")
        self.use_file.setChecked(True)
        if not self._connections:
            self.use_postgis.setEnabled(False)
            self.use_postgis.setToolTip("Det finns inga PostgreSQL-anslutningar i QGIS. Lägg till en i "
                                        "Datakällshanteraren → PostgreSQL → Ny.")
        where = QHBoxLayout()
        where.addWidget(self.use_file)
        where.addWidget(self.use_postgis)
        where.addStretch(1)

        self.filnamn = QLineEdit()
        self.filnamn.setToolTip("Namnet på planfilen (.gpkg) och QGIS-projektfilen (.qgz), som sparas direkt. "
                                "Föreslås utifrån titeln.")
        self._filnamn_edited = False
        self.folder = QgsFileWidget()
        self.folder.setStorageMode(QgsFileWidget.StorageMode.GetDirectory)
        self.folder.setToolTip("Mappen där planfilen och projektfilen sparas. För en plan i databasen sparas bara "
                               "projektfilen här.")
        self.file_box = QWidget()
        file_form = QFormLayout(self.file_box)
        file_form.setContentsMargins(0, 0, 0, 0)
        file_form.addRow("Filnamn", self.filnamn)
        file_form.addRow("Spara i mapp", self.folder)
        self.file_note = QLabel("Planen sparas som .gpkg och QGIS-projektet som .qgz i mappen.")
        self.file_note.setWordWrap(True)
        self.file_note.setEnabled(False)  # dämpad färg
        file_form.addRow("", self.file_note)

        self.connection = QComboBox()
        for name in sorted(self._connections):
            self.connection.addItem(name, name)
        self.connection.setToolTip("En av QGIS sparade PostgreSQL-anslutningar.")
        self.schema = QLineEdit()
        self.schema.setPlaceholderText(f"schemanamn, t.ex. {DEFAULT_SCHEMA}")
        self.schema.setToolTip("Schemat i databasen som planen läggs i. Delas av alla planer som lagts där: finns det "
                               "redan läggs planen till (samma koordinatsystem krävs), annars skapas det. Gemener a–z, "
                               "siffror och understreck.")
        self._schema_edited = False
        self.plan_id = QLineEdit()
        self.plan_id.setPlaceholderText("plan-id, t.ex. op_2045")
        self.plan_id.setToolTip("Planens id i schemat (måste vara unikt där). Föreslås utifrån titeln. Gemener a–z, "
                                "siffror och understreck.")
        self._plan_id_edited = False
        self.postgis_box = QWidget()
        postgis_form = QFormLayout(self.postgis_box)
        postgis_form.setContentsMargins(0, 0, 0, 0)
        postgis_form.addRow("Anslutning", self.connection)
        postgis_form.addRow("Schema", self.schema)
        postgis_form.addRow("Plan-id", self.plan_id)
        self.postgis_box.setVisible(False)

        # -- planen ----------------------------------------------------------------------------------------------
        self.crs = QComboBox()
        for epsg in model.EPSG_CODES:
            self.crs.addItem(f"EPSG:{epsg} – {QgsCoordinateReferenceSystem(f'EPSG:{epsg}').description()}", epsg)
        self.crs.setCurrentIndex(self.crs.findData(model.EPSG))
        self.crs.setToolTip(CRS_TIP)
        self.paborjad = QDateEdit(QDate.currentDate())
        self.paborjad.setCalendarPopup(True)
        self.paborjad.setDisplayFormat("yyyy-MM-dd")
        self.paborjad.setToolTip("Dagen arbetet med planen påbörjades. Planer som påbörjas 1 januari 2027 eller senare "
                                 "ska kunna tillgängliggöras och behandlas digitalt.")

        form = QFormLayout()
        form.addRow("Kommun", self.kommun)
        form.addRow("Planens titel", self.titel)
        form.addRow("Lagras i", where)
        form.addRow("", self.file_box)
        form.addRow("", self.postgis_box)
        form.addRow("Koordinatsystem", self.crs)
        form.addRow("Påbörjad", self.paborjad)

        self.about = QLabel(f"Planen skapas med Boverkets GIS-databasmodell och värden ur ÖP-katalogen "
                            f"{bundled().version}.")
        self.about.setWordWrap(True)
        self.about.setEnabled(False)  # dämpad färg

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Skapa")
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Avbryt")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.about)
        layout.addWidget(self.buttons)

        self.titel.textChanged.connect(self._suggest)
        self.filnamn.textEdited.connect(lambda *_: setattr(self, "_filnamn_edited", True))
        self.schema.textEdited.connect(lambda *_: setattr(self, "_schema_edited", True))
        self.plan_id.textEdited.connect(lambda *_: setattr(self, "_plan_id_edited", True))
        self.use_postgis.toggled.connect(self._on_storage_changed)
        for signal in (self.kommun.currentTextChanged, self.titel.textChanged, self.filnamn.textChanged,
                       self.folder.fileChanged, self.schema.textChanged, self.plan_id.textChanged,
                       self.connection.currentIndexChanged):
            signal.connect(self._update_ok)
        self._update_ok()

    # -- val --------------------------------------------------------------------------------------------------------
    def is_postgis(self) -> bool:
        return self.use_postgis.isChecked()

    def destination(self) -> str:
        return DATABASE if self.is_postgis() else FILE

    def _on_storage_changed(self, *_) -> None:
        database = self.is_postgis()
        self.postgis_box.setVisible(database)
        # filnamnet och mappen gäller projektfilen även när planen ligger i databasen
        self.file_note.setText("QGIS-projektet sparas som .qgz i mappen; planen ligger i databasen." if database
                               else "Planen sparas som .gpkg och QGIS-projektet som .qgz i mappen.")
        if database and not self._schema_edited and not self.schema.text():
            self.schema.setText(DEFAULT_SCHEMA)  # ett schema som delas av kommunens översiktsplaner
        self._update_ok()

    def _suggest(self, *_) -> None:
        if not self._filnamn_edited:
            self.filnamn.setText(safe_filename(self.titel.text()))
        if not self._plan_id_edited:
            self.plan_id.setText(storage.identifier(self.titel.text()))

    def _update_ok(self, *_) -> None:
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(self.is_valid())

    def is_valid(self) -> bool:
        if not (self.kommun.selected() is not None and self.titel.text().strip()):
            return False
        has_file = bool(safe_filename(self.filnamn.text()) and self.folder.filePath().strip())
        if self.is_postgis():
            return has_file and bool(self.connection.currentData() and
                                     storage.is_valid_schema(self.schema.text().strip()) and
                                     storage.is_valid_plan_id(self.plan_id.text().strip()))
        return has_file

    # -- resultat ---------------------------------------------------------------------------------------------------
    def database_target(self) -> tuple[str, str, str]:
        """(anslutning, schema, planens id) när planen ska läggas i en databas."""
        return self.connection.currentData(), self.schema.text().strip(), self.plan_id.text().strip()

    def target(self) -> Path:
        return Path(self.folder.filePath()) / f"{safe_filename(self.filnamn.text())}.gpkg"

    def project_file(self) -> Path:
        """QGIS-projektfilen, som sparas direkt när planen skapats (samma namn och mapp som planfilen)."""
        return Path(self.folder.filePath()) / f"{safe_filename(self.filnamn.text())}.qgz"

    def epsg(self) -> int:
        return int(self.crs.currentData())

    def plan(self) -> geopackage.NewPlan:
        kommun = self.kommun.selected()
        d = self.paborjad.date()
        return geopackage.NewPlan(kommunkod=kommun.kod, kommunnamn=kommun.namn, titel=self.titel.text().strip(),
                                  datum_paborjat=datetime.date(d.year(), d.month(), d.day()),
                                  epsg=self.epsg())  # en ny översiktsplan har digitalt ursprung
