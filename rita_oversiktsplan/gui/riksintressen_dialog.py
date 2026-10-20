"""Dialogen "Hämta riksintressen": välj riksintressen och område, hämta dem ur Boverkets tjänst och lägg in dem som
underlag i planen (se :mod:`..core.riksintressen`)."""
from __future__ import annotations

from typing import Callable, Optional

from qgis.core import QgsBlockingNetworkRequest, QgsGeometry, QgsRectangle
from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtNetwork import QNetworkRequest
from qgis.PyQt.QtWidgets import (QApplication, QCheckBox, QDialog, QDialogButtonBox, QGridLayout, QGroupBox, QLabel,
                                 QPushButton, QRadioButton, QVBoxLayout)

from ..core import riksintressen

INTRO = ("Hämtar riksintressena enligt 3 och 4 kap. miljöbalken ur Boverkets samlade karttjänst och lägger in dem som "
         "underlag i gruppen Riksintressen enligt 3 och 4 kap. MB, med myndighetens id som riksintressets id och dagens "
         "datum som hämtat datum. Boverket sammanställer myndigheternas underlag men kan inte garantera att det är "
         "aktuellt: länsstyrelsen ansvarar för planeringsunderlaget. Riksintressen som redan finns i planen hämtas "
         "inte igen.")

POSITIONS_TIP = ("Varje riksintresse som läggs in kopieras också till Riksintresse, kommunens ställningstagande, med "
                 "samma värde, namn, id och geometri, och kopplas till riksintresset (berör annat innehåll). Ta bort "
                 "de kopior kommunen inte tar ställning till. Vill du välja själv: markera riksintressena i kartan "
                 "och använd Skapa kommunens ställningstagande i menyn.")


def qgis_get(url: str) -> str:
    """Hämtar en adress med QGIS nätverk (QGIS proxy- och certifikatinställningar gäller)."""
    request = QgsBlockingNetworkRequest()
    error = request.get(QNetworkRequest(QUrl(url)))
    if error != QgsBlockingNetworkRequest.ErrorCode.NoError:
        raise OSError(request.errorMessage())
    return bytes(request.reply().content()).decode("utf-8")


class RiksintressenDialog(QDialog):
    def __init__(self, group, epsg: int, plan_area: Optional[QgsGeometry], map_extent: Optional[QgsRectangle],
                 parent=None, get: Callable[[str], str] = qgis_get):
        super().__init__(parent)
        self.group, self.epsg, self.plan_area, self.map_extent, self.get = group, epsg, plan_area, map_extent, get
        self.added: dict[str, int] = {}
        self.setWindowTitle("Hämta riksintressen")
        self.setMinimumWidth(620)
        intro = QLabel(INTRO)
        intro.setWordWrap(True)
        intro.setEnabled(False)

        self.boxes: dict[riksintressen.Source, QCheckBox] = {}
        sources = QGroupBox("Riksintressen")
        grid = QGridLayout(sources)
        for column, chapter in enumerate((3, 4)):
            grid.addWidget(QLabel(f"<b>{chapter} kap. miljöbalken</b>"), 0, column)
            for row, source in enumerate([s for s in riksintressen.SOURCES if s.chapter == chapter], start=1):
                box = QCheckBox(source.title)
                box.setChecked(True)
                self.boxes[source] = box
                grid.addWidget(box, row, column)

        area = QGroupBox("Område")
        area_layout = QVBoxLayout(area)
        self.use_plan = QRadioButton("Planens avgränsning (Plangeometri)")
        self.use_map = QRadioButton("Kartans utsnitt")
        self.use_plan.setEnabled(plan_area is not None and not plan_area.isEmpty())
        if not self.use_plan.isEnabled():
            self.use_plan.setToolTip("Rita planens avgränsning i Plangeometri först, eller använd kartans utsnitt.")
        (self.use_plan if self.use_plan.isEnabled() else self.use_map).setChecked(True)
        self.clip = QCheckBox("Klipp riksintressena mot planens avgränsning")
        self.clip.setChecked(self.use_plan.isEnabled())
        self.clip.setEnabled(self.use_plan.isEnabled())
        for widget in (self.use_plan, self.use_map, self.clip):
            area_layout.addWidget(widget)
        self.positions = QCheckBox("Lägg också in dem som kommunens ställningstagande")
        self.positions.setToolTip(POSITIONS_TIP)

        self.message = QLabel()
        self.message.setWordWrap(True)
        self.fetch_button = QPushButton("Hämta")
        self.fetch_button.clicked.connect(self.fetch)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText("Stäng")
        buttons.addButton(self.fetch_button, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addWidget(sources)
        layout.addWidget(area)
        layout.addWidget(self.positions)
        layout.addWidget(self.message)
        layout.addWidget(buttons)

    def chosen(self) -> list[riksintressen.Source]:
        return [source for source, box in self.boxes.items() if box.isChecked()]

    def bbox(self) -> Optional[tuple[float, float, float, float]]:
        if self.use_plan.isChecked() and self.plan_area is not None:
            r = self.plan_area.boundingBox()
        elif self.map_extent is not None:
            r = self.map_extent
        else:
            return None
        return r.xMinimum(), r.yMinimum(), r.xMaximum(), r.yMaximum()

    def _say(self, text: str) -> None:
        self.message.setText(text)
        QApplication.processEvents()

    def fetch(self) -> Optional[dict[str, int]]:
        """Hämtar de valda riksintressena och lägger in dem i planen. Returnerar antal per lager, eller None."""
        sources, bbox = self.chosen(), self.bbox()
        if not sources:
            self._say("Välj minst ett riksintresse.")
            return None
        if bbox is None:
            self._say("Det finns inget område att hämta inom.")
            return None
        records: list[riksintressen.Record] = []
        try:
            for source in sources:
                records += riksintressen.fetch(self.get, source, bbox, self.epsg, progress=self._say)
        except riksintressen.FetchError as exc:
            self._say(str(exc))
            return None
        clip = self.plan_area if self.clip.isChecked() and self.clip.isEnabled() else None
        try:
            self.added = riksintressen.import_records(self.group, riksintressen.unique(records), clip,
                                                      positions=self.positions.isChecked())
        except ValueError as exc:
            self._say(str(exc))
            return None
        positions = sum(n for name, n in self.added.items() if riksintressen.is_position_layer(name))
        total = sum(self.added.values()) - positions
        self._say(f"Hämtade {len(records)} objekt ur Boverkets tjänst; {total} lades in som underlag i planen"
                  + (" (riksintressen som redan fanns, eller låg utanför planen, hoppades över)." if total < len(records)
                     else ".")
                  + (f" {positions} kopierades till kommunens ställningstagande." if positions else "")
                  + " Spara med Avsluta redigering (disketten).")
        return self.added
