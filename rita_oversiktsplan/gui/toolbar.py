"""Verktygsfältet Rita Översiktsplan, i samma ordning som i Rita Detaljplan: ny och öppna plan, checka ut eller in
(planer i en databas); pennan (börja och avsluta redigeringen), planens uppgifter, export och Skapa bokmärken i
planhandling; markera och avmarkera; rita yta, linje och punkt och importera geometri; tilldela och kopiera innehåll."""
from __future__ import annotations

from pathlib import Path

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QToolBar

ICONS = Path(__file__).resolve().parent.parent / "icons"
TITLE = "Rita Översiktsplan"
NEW_TIP = "Ny översiktsplan…"
OPEN_TIP = "Öppna översiktsplan (fil eller databas)…"
CHECKOUT_TIP = ("Checka ut: lås planen i databasen och redigera en lokal kopia. En plan som öppnats från en databas är "
                "skrivskyddad tills den checkas ut.")
CHECKIN_TIP = ("Checka in: skriv planen tillbaka till databasen, släpp låset och ta bort den lokala kopian (eller "
               "kasta utcheckningen).")
CHECKOUT_FILE_TIP = "Checka ut eller in: bara för planer i en PostGIS-databas. Den här planen ligger i en fil."
START_TIP = "Börja redigera: alla planens lager öppnas för redigering."
STOP_TIP = "Avsluta redigering: spara och avsluta, förkasta och avsluta, eller avbryt."
INFO_TIP = "Planens uppgifter: planen, planhändelse, beslut och standardvärden för nytt innehåll"
EXPORT_TIP = ("Leverans och export: kontrollera planen mot Lantmäteriets format för översiktsplan, spara den som "
              "JSON-fil, leverera den till Nationella geodataplattformen (kräver producentbehörighet) eller samla den i "
              "ett arkivpaket")
DOCUMENT_TIP = ("Skapa bokmärken i planhandling: öppnar programmet som ger planhandlingens textavsnitt (Word) "
                "bokmärken i en kopia av dokumentet och kopplar dem till planens innehåll")
SELECT_TIP = ("Markera: klicka eller dra en rektangel för att markera planens innehåll (välj objekt om flera ligger på "
              "varandra vid ett klick). Ctrl-klick eller Skift-klick lägger till. Högerklick avmarkerar allt.")
DESELECT_TIP = "Avmarkera alla: ta bort markeringen i planens lager."
DRAW_TIPS = {
    "polygon": "Rita yta: ritas först utan innehåll, tilldela sedan innehållet med Tilldela innehåll",
    "line": "Rita linje: ritas först utan innehåll, tilldela sedan innehållet med Tilldela innehåll",
    "point": "Rita punkt: ritas först utan innehåll, tilldela sedan innehållet med Tilldela innehåll",
}
DRAW_TEXTS = {"polygon": "Rita yta", "line": "Rita linje", "point": "Rita punkt"}
DRAW_ICONS = {"polygon": "draw_polygon.svg", "line": "draw_line.svg", "point": "draw_point.svg"}
IMPORT_TIP = ("Importera geometri: kopierar ytor, linjer och punkter från ett annat lager eller en datakälla till "
              "Att tilldela, utan attribut")
ASSIGN_TIP = ("Tilldela innehåll: klicka på en ritad yta, linje eller punkt och välj grupp och innehållstyp. "
              "Klicka på tilldelat innehåll för att byta typ.")
RELATE_TIP = ("Berör annat innehåll: klicka på ett innehåll och sedan på det innehåll det berör (klicka igen för att ta "
              "bort kopplingen). Det berörda visas i blått. Högerklick eller Esc väljer ett nytt innehåll.")
COPY_TIP = ("Kopiera innehåll: klicka på ett objekt med innehåll och sedan på de objekt som ska få samma innehåll "
            "(grupp, innehållstyp och övriga val i Tilldela innehåll, inte namnet). Högerklick eller Esc väljer en ny "
            "källa.")


def icon(name: str) -> QIcon:
    return QIcon(str(ICONS / name))


class PlanToolBar(QToolBar):
    """``handler`` är pluginet: verktygsfältet anropar dess kommandon (new_plan, draw, set_assigning …)."""

    def __init__(self, iface, handler, parent=None):
        super().__init__(TITLE, parent)
        self.setObjectName("RitaOversiktsplanToolBar")  # QGIS minns var verktygsfältet låg
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.setIconSize(iface.iconSize())  # QGIS egen ikonstorlek, inte ett fast värde
        h = handler

        self.act_new = self._action("new.svg", NEW_TIP, h.new_plan)
        self.act_open = self._action("open.svg", "Öppna översiktsplan…", h.open_plan, OPEN_TIP)
        self.act_checkout = self._action("checkout.svg", "Checka ut", h.toggle_checkout, CHECKOUT_TIP)
        self.addSeparator()
        self.act_start = self._action("start.svg", "Börja redigera", h.start_editing, START_TIP)
        self.act_stop = self._action("stop.svg", "Avsluta redigering", h.stop_editing, STOP_TIP)
        self.act_info = self._action("info.svg", "Planens uppgifter", h.open_info, INFO_TIP)
        self.act_export = self._action("export.svg", "Leverans och export", h.export_plan, EXPORT_TIP)
        self.act_document = self._action("planhandling.svg", "Skapa bokmärken i planhandling", h.open_document,
                                         DOCUMENT_TIP)
        self.addSeparator()
        self.act_select = self._toggle("select.svg", "Markera", h.set_selecting, SELECT_TIP)
        self.act_deselect = self._action("deselect.svg", "Avmarkera alla", h.deselect_all, DESELECT_TIP)
        self.addSeparator()
        self.act_draw = {suffix: self._action(DRAW_ICONS[suffix], DRAW_TEXTS[suffix],
                                              lambda s=suffix: h.draw(s), DRAW_TIPS[suffix])
                         for suffix in ("polygon", "line", "point")}
        self.act_import = self._action("import.svg", "Importera geometri", h.import_geometry, IMPORT_TIP)
        self.addSeparator()
        self.act_assign = self._toggle("assign.svg", "Tilldela innehåll", h.set_assigning, ASSIGN_TIP)
        self.act_copy = self._toggle("copy.svg", "Kopiera innehåll", h.set_copying, COPY_TIP)
        self.act_relate = self._toggle("relate.svg", "Berör annat innehåll", h.set_relating, RELATE_TIP)

    def set_state(self, has_plan: bool, editing: bool, checkout_state: str) -> None:
        """Gråar det som inte går att använda: utan plan går bara Ny och Öppna, och att rita, importera, tilldela och
        kopiera kräver en redigeringssession (pennan)."""
        self.set_checkout_state(checkout_state if has_plan else "none")
        self.act_start.setEnabled(has_plan and not editing)
        self.act_stop.setEnabled(has_plan and editing)
        for action in (self.act_info, self.act_export, self.act_document, self.act_select, self.act_deselect):
            action.setEnabled(has_plan)
        for action in (*self.act_draw.values(), self.act_import, self.act_assign, self.act_copy, self.act_relate):
            action.setEnabled(has_plan and editing)

    def set_checkout_state(self, state: str) -> None:
        """Knappen visar Checka ut för en plan i databasen och Checka in för en utcheckad plan. För en plan i en fil
        är den avstängd."""
        checked_out = state == "local"
        self.act_checkout.setIcon(icon("checkin.svg" if checked_out else "checkout.svg"))
        self.act_checkout.setText("Checka in" if checked_out else "Checka ut")
        self.act_checkout.setToolTip(CHECKIN_TIP if checked_out else CHECKOUT_TIP if state == "database"
                                     else CHECKOUT_FILE_TIP if state == "file" else CHECKOUT_TIP)
        self.act_checkout.setEnabled(state in ("local", "database"))

    def _action(self, icon_name: str, text: str, callback, tip: str = "") -> QAction:
        action = QAction(icon(icon_name), text, self)
        action.setToolTip(tip or text)
        action.triggered.connect(lambda _=False: callback())
        self.addAction(action)
        return action

    def _toggle(self, icon_name: str, text: str, callback, tip: str) -> QAction:
        """Ett kartverktyg: intryckt så länge verktyget är aktivt."""
        action = QAction(icon(icon_name), text, self)
        action.setToolTip(tip)
        action.setCheckable(True)
        action.toggled.connect(callback)
        self.addAction(action)
        return action
