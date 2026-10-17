"""Programmets fyra steg: Filer, Avsnitt, Koppling och Kontroll och spara. Upplägget och utseendet följer Tagga
planbeskrivning i Rita Detaljplan (``pbapp/pages.py``)."""
from __future__ import annotations

import csv
import html
from pathlib import Path
from typing import Optional

from qgis.PyQt.QtCore import QSize, Qt, QUrl, pyqtSignal
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import (QAbstractItemView, QButtonGroup, QCheckBox, QComboBox, QFileDialog, QFrame, QGridLayout,
                                 QHeaderView, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QProgressBar,
                                 QSplitter, QTableWidget, QTableWidgetItem, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
                                 QWidget)

from . import session as ss
from . import theme
from .widgets import (Card, Facts, MapView, ObjectChip, ParagraphText, Pill, TypeChip, box, button, dot_icon, frame,
                      label, restyle, scrolled, short)

ROLE = Qt.ItemDataRole.UserRole


def clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()


# -- steg 1: filer ----------------------------------------------------------------------------------------------------
class FilesPage(QWidget):
    loaded = pyqtSignal()
    proceed = pyqtSignal()

    def __init__(self, session: ss.Session, toast):
        super().__init__()
        self.session, self.toast = session, toast
        self.setObjectName("page")
        self.setAcceptDrops(True)
        host = session.host.name

        self.doc_name, self.doc_path, self.doc_facts = label("Ingen fil vald", "fileName"), label("", "hint"), Facts()
        choose = button("Välj…", "small")
        choose.clicked.connect(self.choose_docx)
        self.doc_frame = frame("chosen", box("h", box("v", self.doc_name, self.doc_path, spacing=2), None, choose,
                                             margins=(12, 10, 12, 10)))
        self.plan_name, self.plan_path, self.plan_facts = label("Ingen plan", "fileName"), label("", "hint"), Facts()
        reload = button(f"Läs om från {host}", "small",
                        f"Hämta planens innehåll från {host} igen, till exempel efter att du ritat mer.")
        reload.clicked.connect(self.reload_from_host)
        self.plan_frame = frame("chosen", box("h", box("v", self.plan_name, self.plan_path, spacing=2), None, reload,
                                              margins=(12, 10, 12, 10)))

        doc_panel = frame("panel", box(
            "v", self._head("Planhandling", "Översiktsplanens text som Word-dokument (.docx). Originalet ändras aldrig: "
                                            "bokmärkena läggs i en kopia."),
            self.doc_frame, self.doc_facts, None, spacing=14, margins=(20, 20, 20, 20)))
        plan_panel = frame("panel", box(
            "v", self._head("Översiktsplan", f"Den aktiva planen i {host}, med det som inte sparats än."),
            self.plan_frame, self.plan_facts, None, spacing=14, margins=(20, 20, 20, 20)))

        self.go = button("Fortsätt till avsnitten  →", "primary")
        self.go.clicked.connect(self.proceed.emit)
        self.recent = button("", "ghost")
        self.recent.clicked.connect(self.open_recent)
        self.error = label("", "error", wrap=True)
        self.error.hide()
        self.other_text = label("", wrap=True)
        self.other_button = button("", "small")
        self.other_button.clicked.connect(self.open_other)
        self.other = frame("warning", box("v", self.other_text, box("h", self.other_button, None), spacing=8,
                                          margins=(14, 12, 14, 12)))
        self.other.hide()

        column = QWidget()
        column.setMaximumWidth(1040)
        files = QGridLayout()
        files.setSpacing(16)
        files.addWidget(doc_panel, 0, 0)
        files.addWidget(plan_panel, 0, 1)
        column.setLayout(box(
            "v", label("PLANHANDLING", "eyebrow"), label("Välj översiktsplanens planhandling", "h1"),
            label("Programmet läser Word-filen och delar den i avsnitt efter rubrikerna. Du granskar avsnittstyperna, "
                  "kopplar avsnitten till planens innehåll och sparar. Resultatet är en kopia av Word-filen med ett "
                  "bokmärke per avsnitt, och kopplingarna i planens tabeller, som i Boverkets ÖP-modell.",
                  "lead", wrap=True),
            12, files, self.other, self.error, box("h", self.go, self.recent, None),
            label("Du kan också dra Word-filen hit.", "hint"), None, spacing=10, margins=(16, 36, 16, 36)))
        outer = QWidget()
        outer.setLayout(box("h", None, column, None))
        self.setLayout(box("v", scrolled(outer)))
        self.refresh()

    def _head(self, title: str, sub: str) -> QWidget:
        widget = QWidget()
        widget.setLayout(box("v", label(title, "h2"), label(sub, "muted", wrap=True), spacing=2))
        return widget

    def _show_error(self, exc: Exception) -> None:
        self.error.setText(str(exc))
        self.error.show()

    def choose_docx(self) -> None:
        plan_folder = Path(self.session.plan.path).parent if self.session.plan else None
        start = str(self.session.docx.parent) if self.session.docx else (
            str(plan_folder) if plan_folder is not None and plan_folder.is_dir() else "")
        path, _ = QFileDialog.getOpenFileName(self, "Välj planhandling", start, "Word-dokument (*.docx)")
        if path:
            self.load(path)

    def load(self, docx) -> bool:
        self.error.hide()
        try:
            self.session.load_docx(docx)
        except ss.SessionError as exc:
            self._show_error(exc)
            self.refresh()
            return False
        self.refresh()
        self.loaded.emit()
        return True

    def reload_from_host(self) -> None:
        self.error.hide()
        try:
            self.session.load_plan()
        except ss.SessionError as exc:
            self._show_error(exc)
        self.refresh()
        self.loaded.emit()

    def open_other(self) -> None:
        other = self.session.other_document
        if other is not None and other.exists():
            self.load(other)

    def open_recent(self) -> None:
        recent = self.session.recent_docx()
        if recent:
            self.load(recent)

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802
        paths = [Path(u.toLocalFile()) for u in event.mimeData().urls() if u.isLocalFile()]
        docx = next((p for p in paths if p.suffix.lower() == ".docx"), None)
        if docx:
            self.load(docx)
        else:
            self.toast("Dra hit planhandlingen som Word-dokument (.docx).")

    def refresh(self) -> None:
        s = self.session
        self.doc_name.setText(s.docx.name if s.docx else "Ingen fil vald")
        self.doc_path.setText(str(s.docx.parent) if s.docx else "Välj en fil eller dra den hit")
        self.doc_frame.setProperty("empty", s.docx is None)
        restyle(self.doc_frame)
        if s.document is not None:
            sections = s.sections
            self.doc_facts.set([("Avsnitt", str(len(sections))),
                                ("Med text", str(sum(1 for x in sections if x.text))),
                                ("Har bokmärke", str(sum(1 for x in sections if x.bookmark))),
                                ("Sparade kopplingar", str(sum(1 for i in s.saved_from if s.links.get(i))))])
        else:
            self.doc_facts.set([])
        self.plan_name.setText(s.plan.title if s.plan else "Ingen plan")
        self.plan_path.setText(f"Aktiv plan i {s.host.name}" + (f" · {s.plan.source}" if s.plan and s.plan.source
                                                                    else ""))
        self.plan_frame.setProperty("empty", s.plan is None)
        restyle(self.plan_frame)
        if s.plan is not None:
            objects = [o for o in s.plan.objects if o.kind != ss.PLAN_KIND]
            self.plan_facts.set([("Kommun", s.plan.kommun or "–"),
                                 ("Innehåll", str(sum(1 for o in objects if o.kind != ss.NONE_KIND))),
                                 ("Utan geometri", str(sum(1 for o in objects if o.kind == ss.NONE_KIND))),
                                 ("Avsnittstyper", str(len(s.plan.types)))])
        else:
            self.plan_facts.set([])
        self.go.setEnabled(s.ready)
        self.go.setToolTip("" if s.ready else "Välj planhandlingen först.")
        other = s.other_document if s.document is not None else None
        self.other.setVisible(other is not None)
        if other is not None:
            found = other.exists()
            self.other_text.setText(
                f"Planen är redan kopplad till {other.name}, men {s.docx.name} saknar bokmärken. Arbetar du vidare i "
                "originalet i stället för kopian med bokmärken får avsnitten nya bokmärken, och de gamla kopplingarna "
                "försvinner när du sparar." + ("" if found else f" ({other.name} finns inte kvar på {other.parent}.)"))
            self.other_button.setText(f"Öppna {other.name} i stället")
            self.other_button.setVisible(found)
        recent = s.recent_docx() if s.document is None else None
        self.recent.setVisible(recent is not None)
        if recent is not None:
            self.recent.setText(f"Öppna senaste: {recent.name}")


# -- steg 2: avsnitt ---------------------------------------------------------------------------------------------------
class SectionCard(Card):
    def __init__(self, page: "SectionsPage", section):
        super().__init__()
        self.page, self.index, self.section = page, section.index, section
        self.chip, self.pill = TypeChip(), Pill()
        self.links = label("", "hint")
        heading = label(section.heading, "docHeading", wrap=True)
        heading.setProperty("level", str(section.level))
        row = box("h", self.chip, self.pill, None, self.links)
        rows = [row, heading]
        if section.text:
            rows.append(ParagraphText(section.text))
        else:
            rows.append(label("Ingen text under rubriken.", "hint"))
        self.setLayout(box("v", *rows, spacing=4, margins=(14 + 14 * (section.level - 1), 8, 14, 8)))
        self.clicked.connect(lambda: page.select(self.index))
        self.refresh()

    def refresh(self) -> None:
        session = self.page.session
        status = session.status(self.index)
        skipped = status == ss.HOPPAS
        self.chip.set(session.types[self.index], muted=skipped)
        self.pill.set(status)
        count = len(session.links[self.index])
        self.links.setText(f"Kopplat till {count} objekt" if count else "")
        self.set_accent(theme.C["line"] if skipped else theme.type_color(session.types[self.index]))


class SectionsPage(QWidget):
    go = pyqtSignal(int, int)  # (steg, avsnitt)
    changed = pyqtSignal()

    FILTERS = (("alla", "Alla"), ("granska", "Att granska"), (ss.GRANSKAD, "Granskade"), (ss.HOPPAS, "Inget bokmärke"))

    def __init__(self, session: ss.Session, toast):
        super().__init__()
        self.session, self.toast = session, toast
        self.setObjectName("page")
        self.selected: Optional[int] = None
        self.filter = "alla"
        self.cards: dict[int, SectionCard] = {}
        self._built_for = None
        self._loading = False

        self.filter_buttons = QButtonGroup(self)
        filters = QGridLayout()
        filters.setContentsMargins(0, 0, 0, 0)
        filters.setSpacing(6)
        for number, (key, text) in enumerate(self.FILTERS):
            b = button(text, "filter")
            b.setCheckable(True)
            b.setChecked(key == self.filter)
            b.clicked.connect(lambda _=False, k=key: self.set_filter(k))
            self.filter_buttons.addButton(b)
            filters.addWidget(b, number // 2, number % 2)
        filters.setColumnStretch(2, 1)
        self.outline = QListWidget()
        self.outline.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.outline.itemClicked.connect(lambda item: self.select(item.data(ROLE), scroll=True))
        self.summary = label("", "hint", wrap=True)
        left = frame("sideLeft", box("v", label("Avsnitt", "h2"), filters, self.summary, self.outline,
                                     spacing=10, margins=(12, 14, 6, 6)))

        self.doc_layout = QVBoxLayout()
        self.doc_layout.setSpacing(6)
        self.doc_title, self.doc_sub = label("", "docTitle", wrap=True), label("", "hint")
        page = frame("docPage", box("v", self.doc_title, self.doc_sub, 12, self.doc_layout, None,
                                    margins=(20, 24, 20, 32)))
        page.setMaximumWidth(1000)
        holder_layout = box("h", None, page, None, margins=(6, 12, 6, 24))
        holder_layout.setStretch(0, 1)
        holder_layout.setStretch(1, 100)
        holder_layout.setStretch(2, 1)
        holder = QWidget()
        holder.setLayout(holder_layout)
        self.doc_scroll = scrolled(holder)
        self.doc_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.insp_heading, self.insp_pill = label("", "h3", wrap=True), Pill()
        self.why = label("", wrap=True)
        why_frame = frame("why", box("v", label("VARFÖR", "eyebrow"), self.why, spacing=4, margins=(12, 10, 12, 10)))
        self.type_combo = QComboBox()
        self.type_combo.activated.connect(self._type_chosen)
        self.approve_button = button("Godkänn", "primary")
        self.approve_button.clicked.connect(self.approve)
        self.skip_button = button("Inget bokmärke")
        self.skip_button.clicked.connect(self.toggle_skip)
        self.next_button = button("Nästa att granska  →", "ghost")
        self.next_button.clicked.connect(lambda: self.next_to_review(quiet=False))
        self.link_button = button("Koppla avsnittet  →", "small", "Gå till steget Koppling med det här avsnittet.")
        self.link_button.clicked.connect(lambda: self.go.emit(3, self.selected))
        self.inspector = QWidget()
        self.inspector.setLayout(box(
            "v", label("VALT AVSNITT", "eyebrow"), self.insp_heading, box("h", self.insp_pill, None), why_frame,
            label("Avsnittstyp (ÖP-katalogen)", "muted"), self.type_combo, 8,
            box("h", self.approve_button, self.skip_button, None), self.next_button, self.link_button,
            label("Tangenter: J och K bläddrar, Enter godkänner.", "hint", wrap=True),
            label("Avsnitt markerade Inget bokmärke får inget bokmärke och kan inte kopplas till planen.", "hint", wrap=True),
            None, spacing=6, margins=(16, 16, 16, 16)))
        self.empty_inspector = label("Välj ett avsnitt i listan eller i texten.", "muted", wrap=True)
        self.empty_inspector.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right = frame("sideRight", box("v", scrolled(self.inspector), self.empty_inspector))

        splitter = QSplitter()
        splitter.addWidget(left)
        splitter.addWidget(self.doc_scroll)
        splitter.addWidget(right)
        splitter.setSizes([240, 840, 320])
        splitter.setStretchFactor(1, 1)
        splitter.setChildrenCollapsible(False)
        self.setLayout(box("v", splitter))

    # -- bygga upp --
    def refresh(self) -> None:
        if self.session.document is None:
            return
        if self._built_for is not self.session.document:
            self._build()
        for card in self.cards.values():
            card.refresh()
        self._fill_outline()
        if self.selected is None or self.selected not in self.cards:
            first = next((s.index for s in self.session.sections if self.session.status(s.index) in ss.NEEDS_LOOK),
                         0 if self.cards else None)
            if first is not None:
                self.select(first, scroll=True)
        self._show_inspector()

    def _build(self) -> None:
        clear_layout(self.doc_layout)
        self.cards = {}
        for section in self.session.sections:
            card = SectionCard(self, section)
            self.cards[section.index] = card
            self.doc_layout.addWidget(card)
        self.doc_title.setText(self.session.plan.title if self.session.plan else "")
        self.doc_sub.setText(self.session.docx.name if self.session.docx else "")
        self.type_combo.clear()
        self.type_combo.addItems(self.session.plan.types)
        self._built_for = self.session.document
        self.selected = None

    def _fill_outline(self) -> None:
        session = self.session
        counts = session.counts()
        review = sum(counts[s] for s in ss.NEEDS_LOOK)
        totals = {"alla": len(session.sections), "granska": review, ss.GRANSKAD: counts[ss.GRANSKAD],
                  ss.HOPPAS: counts[ss.HOPPAS]}
        for b, (key, text) in zip(self.filter_buttons.buttons(), self.FILTERS):
            b.setText(f"{text}  {totals[key]}")
        self.summary.setText(f"{len(session.tagged())} av {len(session.sections)} avsnitt får bokmärken. "
                             + (f"{review} behöver granskas." if review else "Allt är granskat."))
        self.outline.clear()
        for section in session.sections:
            status = session.status(section.index)
            if not self._visible(status):
                continue
            item = QListWidgetItem(dot_icon(theme.status_color(status)),
                                   ("   " * (section.level - 1)) + section.heading)
            item.setData(ROLE, section.index)
            item.setToolTip(" › ".join(section.path) + f"\n{session.types[section.index]} · {ss.STATUS_TEXT[status]}")
            item.setSizeHint(QSize(0, 30))
            self.outline.addItem(item)
            if section.index == self.selected:
                self.outline.setCurrentItem(item)
        if not self.outline.count():
            empty = QListWidgetItem("Inga avsnitt i det här urvalet.")
            empty.setFlags(Qt.ItemFlag.NoItemFlags)
            self.outline.addItem(empty)

    def _visible(self, status: str) -> bool:
        if self.filter == "alla":
            return True
        if self.filter == "granska":
            return status in ss.NEEDS_LOOK
        return status == self.filter

    def set_filter(self, key: str) -> None:
        self.filter = key
        self._fill_outline()

    # -- välja --
    def select(self, index: Optional[int], scroll: bool = False) -> None:
        if index is None or index not in self.cards:
            return
        if self.selected in self.cards:
            self.cards[self.selected].set_selected(False)
        self.selected = index
        card = self.cards[index]
        card.set_selected(True)
        if scroll:
            self.doc_scroll.ensureWidgetVisible(card, 0, 120)
        for row in range(self.outline.count()):
            item = self.outline.item(row)
            if item.data(ROLE) == index:
                self.outline.setCurrentItem(item)
                self.outline.scrollToItem(item)
                break
        else:
            self.outline.clearSelection()
        self._show_inspector()
        self.setFocus()

    def _show_inspector(self) -> None:
        index = self.selected
        self.inspector.setVisible(index is not None)
        self.empty_inspector.setVisible(index is None)
        if index is None:
            return
        self._loading = True
        session = self.session
        section = session.sections[index]
        status = session.status(index)
        self.insp_heading.setText(" › ".join(section.path))
        self.insp_pill.set(status)
        self.why.setText(session.why(index))
        self.type_combo.setCurrentIndex(max(0, self.type_combo.findText(session.types[index])))
        self.approve_button.setEnabled(status in ss.NEEDS_LOOK)
        self.skip_button.setText("Skapa bokmärke" if status == ss.HOPPAS else "Inget bokmärke")
        self.link_button.setEnabled(status != ss.HOPPAS)
        self._loading = False

    # -- ändra --
    def _type_chosen(self, _index: int) -> None:
        if self._loading or self.selected is None:
            return
        self.session.set_type(self.selected, self.type_combo.currentText())
        self._after_change("Avsnittstypen är ändrad.")

    def approve(self) -> None:
        if self.selected is None or not self.approve_button.isEnabled():
            return
        heading = self.session.sections[self.selected].heading
        self.session.approve(self.selected)
        self._after_change(f"Godkänt: {heading}")
        self.next_to_review(quiet=True)

    def toggle_skip(self) -> None:
        if self.selected is None:
            return
        heading = self.session.sections[self.selected].heading
        skip = self.session.status(self.selected) != ss.HOPPAS
        self.session.skip(self.selected, skip)
        self._after_change(f"\"{heading}\" får inget bokmärke." if skip else f"\"{heading}\" får bokmärke igen.")

    def _after_change(self, message: str) -> None:
        for card in self.cards.values():
            card.refresh()
        self._fill_outline()
        self._show_inspector()
        self.changed.emit()
        if message:
            self.toast(message)

    def next_to_review(self, quiet: bool = False) -> None:
        sections = self.session.sections
        start = (self.selected or 0) + 1
        order = list(range(start, len(sections))) + list(range(0, start))
        found = next((n for n in order if self.session.status(n) in ss.NEEDS_LOOK), None)
        if found is not None:
            self.select(found, scroll=True)
        elif not quiet:
            self.toast("Inga fler avsnitt att granska.")

    def step(self, delta: int) -> None:
        visible = [self.outline.item(r).data(ROLE) for r in range(self.outline.count())]
        visible = [v for v in visible if v is not None]
        if not visible:
            return
        target = visible[(visible.index(self.selected) + delta) % len(visible)] if self.selected in visible \
            else visible[0]
        self.select(target, scroll=True)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        key = event.key()
        if key == Qt.Key.Key_J:
            self.step(1)
        elif key == Qt.Key.Key_K:
            self.step(-1)
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.approve()
        else:
            super().keyPressEvent(event)


# -- steg 3: koppling --------------------------------------------------------------------------------------------------
class LinkPage(QWidget):
    changed = pyqtSignal()

    FILTERS = (("alla", "Alla"), ("utan", "Utan koppling"))

    def __init__(self, session: ss.Session, toast):
        super().__init__()
        self.session, self.toast = session, toast
        self.setObjectName("page")
        self.selected: Optional[int] = None
        self.filter = "alla"
        self._built_for = None
        self._plan_for = None
        self._loading = False

        # vänster: avsnitten som får bokmärken
        self.filter_buttons = QButtonGroup(self)
        filters = box("h", spacing=6)
        for key, text in self.FILTERS:
            b = button(text, "filter")
            b.setCheckable(True)
            b.setChecked(key == self.filter)
            b.clicked.connect(lambda _=False, k=key: self.set_filter(k))
            self.filter_buttons.addButton(b)
            filters.addWidget(b)
        filters.addStretch(1)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.summary = label("", "hint", wrap=True)
        self.outline = QListWidget()
        self.outline.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.outline.itemClicked.connect(lambda item: self.select(item.data(ROLE)))
        left = frame("sideLeft", box("v", label("Avsnitt", "h2"), filters, self.progress, self.summary, self.outline,
                                     spacing=10, margins=(12, 14, 6, 6)))

        # mitten: valt avsnitt och det det är kopplat till
        self.path = label("", "hint", wrap=True)
        self.heading = label("", "docHeading", wrap=True)
        self.heading.setProperty("level", "1")
        self.chip = TypeChip()
        self.text = ParagraphText("", lines=6)
        self.chips = QVBoxLayout()
        self.chips.setSpacing(6)
        self.no_links = label("Inte kopplat än. Klicka på innehållet i kartan, kryssa i listan till höger eller hämta "
                              f"det som är markerat i {session.host.name}.", "muted", wrap=True)
        self.btn_selected = button(f"Hämta markerat i {session.host.name}", "small",
                                   f"Kopplar avsnittet till planens innehåll som är markerat i {session.host.name}.")
        self.btn_selected.clicked.connect(self.link_selected)
        self.btn_plan = button("Gäller hela planen", "small",
                               "Kopplar avsnittet till planen som helhet, till exempel syftet eller sammanfattningen.")
        self.btn_plan.clicked.connect(self.link_plan)
        self.btn_new = button("Nytt innehåll utan geometri…", "small",
                              "Skapar innehåll som bara beskrivs i texten, till exempel bostadsförsörjning, och kopplar "
                              "det till avsnittet.")
        self.btn_new.clicked.connect(self.new_without_geometry)
        self.btn_show = button(f"Visa i {session.host.name}", "small",
                               f"Markerar avsnittets innehåll i {session.host.name}s karta.")
        self.btn_show.clicked.connect(self.show_in_host)
        self.btn_clear = button("Ta bort alla", "ghost", "Tar bort avsnittets alla kopplingar.")
        self.btn_clear.clicked.connect(self.clear_links)
        actions = QGridLayout()
        actions.setSpacing(6)
        for n, b in enumerate((self.btn_selected, self.btn_plan, self.btn_new, self.btn_show)):
            actions.addWidget(b, n // 2, n % 2)
        actions.setColumnStretch(2, 1)
        paper = frame("docPage", box(
            "v", label("VALT AVSNITT", "eyebrow"), self.path, self.heading, box("h", self.chip, None), self.text, 10,
            box("h", label("KOPPLAT TILL", "eyebrow"), None, self.btn_clear), self.chips, self.no_links, 6, actions,
            None, spacing=8, margins=(20, 20, 20, 24)))
        paper.setMaximumWidth(900)
        holder_layout = box("h", None, paper, None, margins=(6, 12, 6, 24))
        holder_layout.setStretch(1, 100)
        holder = QWidget()
        holder.setLayout(holder_layout)
        middle = scrolled(holder)
        middle.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # höger: kartan och planens innehåll
        self.map = MapView()
        self.map.clicked.connect(self._map_clicked)
        show_all = button("Hela kartan", "small")
        show_all.clicked.connect(self.map.reset_view)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Sök innehåll…")
        self.search.textChanged.connect(self._filter_tree)
        self.tree = QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels(["Planens innehåll", "Avsnitt"])
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.tree.itemChanged.connect(self._tree_changed)
        self.tree.itemDoubleClicked.connect(lambda item, _c: self._zoom_item(item))
        right_splitter = QSplitter(Qt.Orientation.Vertical)
        map_box = QWidget()
        map_box.setLayout(box("v", box("h", label("KARTA", "eyebrow"), None, show_all), self.map,
                              label("Klicka på innehåll för att koppla eller koppla loss.", "hint", wrap=True),
                              spacing=6))
        list_box = QWidget()
        list_box.setLayout(box("v", label("PLANENS INNEHÅLL", "eyebrow"), self.search, self.tree, spacing=6))
        right_splitter.addWidget(map_box)
        right_splitter.addWidget(list_box)
        right_splitter.setSizes([420, 380])
        right_splitter.setChildrenCollapsible(False)
        right = frame("sideRight", box("v", right_splitter, margins=(14, 14, 10, 10)))
        right.setMinimumWidth(380)

        splitter = QSplitter()
        splitter.addWidget(left)
        splitter.addWidget(middle)
        splitter.addWidget(right)
        splitter.setSizes([250, 560, 560])
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 1)
        splitter.setChildrenCollapsible(False)
        self.setLayout(box("v", splitter))

    # -- bygga upp --
    def refresh(self) -> None:
        session = self.session
        if not session.ready:
            return
        if self._plan_for is not session.plan:
            self.map.set_objects(session.plan.objects)
            self._fill_tree()
            self._plan_for = session.plan
        if self._built_for is not session.document:
            self._built_for = session.document
            self.selected = None
        tagged = [s.index for s in session.tagged()]
        if self.selected not in tagged:
            self.selected = next((i for i in tagged if not session.links[i]), tagged[0] if tagged else None)
        self._fill_outline()
        self._show_section()

    def _fill_outline(self) -> None:
        session = self.session
        tagged = session.tagged()
        linked = session.linked_count()
        self.progress.setMaximum(max(1, len(tagged)))
        self.progress.setValue(linked)
        self.summary.setText(f"{linked} av {len(tagged)} avsnitt är kopplade till planen.")
        for b, (key, text) in zip(self.filter_buttons.buttons(), self.FILTERS):
            b.setText(f"{text}  {len(tagged) if key == 'alla' else len(tagged) - linked}")
        self.outline.clear()
        c = theme.C
        for section in tagged:
            count = len(session.links[section.index])
            if self.filter == "utan" and count:
                continue
            item = QListWidgetItem(dot_icon(c["accent"] if count else c["line"]),
                                   ("   " * (section.level - 1)) + section.heading + (f"   · {count}" if count else ""))
            item.setData(ROLE, section.index)
            item.setToolTip(" › ".join(section.path) + f"\n{session.types[section.index]}"
                            + (f"\nKopplat till {count} objekt" if count else "\nInte kopplat"))
            item.setSizeHint(QSize(0, 30))
            self.outline.addItem(item)
            if section.index == self.selected:
                self.outline.setCurrentItem(item)
        if not self.outline.count():
            empty = QListWidgetItem("Inga avsnitt i det här urvalet." if tagged else "Inga avsnitt får bokmärken.")
            empty.setFlags(Qt.ItemFlag.NoItemFlags)
            self.outline.addItem(empty)

    def _fill_tree(self) -> None:
        self._loading = True
        self.tree.clear()
        groups: dict[str, QTreeWidgetItem] = {}
        for obj in self.session.plan.objects:
            if obj.kind == ss.PLAN_KIND:
                item = QTreeWidgetItem(["Hela planen", ""])
                self.tree.addTopLevelItem(item)
            else:
                parent = groups.get(obj.category)
                if parent is None:
                    parent = QTreeWidgetItem([obj.category, ""])
                    parent.setFlags(Qt.ItemFlag.ItemIsEnabled)
                    groups[obj.category] = parent
                    self.tree.addTopLevelItem(parent)
                    parent.setExpanded(True)
                item = QTreeWidgetItem([obj.title() + (" · utan geometri" if obj.kind == ss.NONE_KIND else ""), ""])
                parent.addChild(item)
            item.setIcon(0, dot_icon(theme.C["accent"] if obj.kind == ss.PLAN_KIND else obj.color, square=True))
            item.setData(0, ROLE, obj.identity)
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(0, Qt.CheckState.Unchecked)
        for parent in groups.values():
            parent.setText(1, "")
        self._loading = False
        self._filter_tree(self.search.text())

    def _object_items(self) -> list[QTreeWidgetItem]:
        items = []
        for n in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(n)
            if top.data(0, ROLE):
                items.append(top)
            items += [top.child(m) for m in range(top.childCount())]
        return items

    def _filter_tree(self, text: str) -> None:
        text = text.strip().casefold()
        for n in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(n)
            if top.data(0, ROLE):
                top.setHidden(bool(text) and text not in top.text(0).casefold())
                continue
            group_hit = text in top.text(0).casefold()
            visible = 0
            for m in range(top.childCount()):
                child = top.child(m)
                hidden = bool(text) and not group_hit and text not in child.text(0).casefold()
                child.setHidden(hidden)
                visible += not hidden
            top.setHidden(visible == 0)

    def _update_tree(self) -> None:
        session = self.session
        linked = session.links.get(self.selected, set()) if self.selected is not None else set()
        self._loading = True
        for item in self._object_items():
            identity = item.data(0, ROLE)
            item.setCheckState(0, Qt.CheckState.Checked if identity in linked else Qt.CheckState.Unchecked)
            sections = session.sections_for(identity)
            item.setText(1, str(len(sections)) if sections else "")
            item.setToolTip(0, "\n".join(session.sections[i].heading for i in sections) or "Inte kopplat till något "
                                                                                           "avsnitt")
            item.setDisabled(self.selected is None)
        self._loading = False

    # -- välja --
    def set_filter(self, key: str) -> None:
        self.filter = key
        self._fill_outline()

    def select(self, index: Optional[int]) -> None:
        if index is None:
            return
        self.selected = index
        self._fill_outline()
        self._show_section()
        linked = self.session.links.get(index, set())
        if linked and self.map.bounds([o for o in self.map.objects if o.identity in linked]):
            self.map.zoom_to(linked)

    def focus_object(self, identity: str) -> None:
        """Visar ett objekt (från kontrollen): zoomar dit i kartan och markerar det i listan."""
        self.map.zoom_to({identity})
        for item in self._object_items():
            if item.data(0, ROLE) == identity:
                self.tree.scrollToItem(item)
                self.tree.setCurrentItem(item)
        self.toast("Välj avsnittet till vänster och klicka på objektet för att koppla det.")

    def _show_section(self) -> None:
        session = self.session
        index = self.selected
        clear_layout(self.chips)
        has = index is not None
        for b in (self.btn_selected, self.btn_plan, self.btn_new, self.btn_show, self.btn_clear):
            b.setEnabled(has)
        if not has:
            self.path.setText("")
            self.heading.setText("Inga avsnitt att koppla")
            self.text.set_text("Alla avsnitt är markerade Inget bokmärke i steget Avsnitt.")
            self.chip.hide()
            self.no_links.hide()
            self.map.highlight(set())
            self._update_tree()
            return
        section = session.sections[index]
        self.chip.show()
        self.path.setText(" › ".join(section.path[:-1]))
        self.heading.setText(section.heading)
        self.chip.set(session.types[index])
        self.text.set_text(section.text or "Ingen text under rubriken.")
        linked = session.links[index]
        objects = [session.plan.object(i) or ss.PlanObject(i, "Saknas i planen", i[:8] + "…") for i in linked]
        for obj in sorted(objects, key=lambda o: (o.kind != ss.PLAN_KIND, o.long_title())):
            chip = ObjectChip(obj)
            chip.removed.connect(self._remove)
            chip.clicked.connect(lambda identity: self.map.zoom_to({identity}))
            self.chips.addWidget(chip)
        self.no_links.setVisible(not linked)
        self.btn_clear.setVisible(bool(linked))
        self.btn_show.setEnabled(bool(linked))
        plan = session.plan.plan_object()
        self.btn_plan.setEnabled(plan is not None and plan.identity not in linked)
        self.map.highlight(linked)
        self._update_tree()

    # -- ändra --
    def _after_change(self, message: str = "") -> None:
        self._fill_outline()
        self._show_section()
        self.changed.emit()
        if message:
            self.toast(message)

    def _map_clicked(self, identity: str) -> None:
        if self.selected is None:
            return
        obj = self.session.plan.object(identity)
        linked = self.session.toggle(self.selected, identity)
        name = obj.long_title() if obj else identity
        self._after_change(f"Kopplat: {name}" if linked else f"Kopplingen är borttagen: {name}")

    def _tree_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if self._loading or column != 0 or self.selected is None:
            return
        identity = item.data(0, ROLE)
        if not identity:
            return
        if item.checkState(0) == Qt.CheckState.Checked:
            self.session.link(self.selected, [identity])
        else:
            self.session.unlink(self.selected, identity)
        self._after_change()

    def _zoom_item(self, item: QTreeWidgetItem) -> None:
        identity = item.data(0, ROLE)
        if identity:
            self.map.zoom_to({identity})

    def _remove(self, identity: str) -> None:
        if self.selected is not None:
            self.session.unlink(self.selected, identity)
            self._after_change("Kopplingen är borttagen.")

    def link_selected(self) -> int:
        if self.selected is None:
            return 0
        identities = self.session.host.selected_identities()
        if not identities:
            self.toast(f"Inget av planens innehåll är markerat i {self.session.host.name}. Markera objekten med "
                       "markeringsverktyget först.")
            return 0
        added = self.session.link(self.selected, identities)
        self._after_change(f"{added} objekt kopplades." if added else "Det markerade var redan kopplat.")
        return added

    def link_plan(self) -> None:
        plan = self.session.plan.plan_object()
        if plan is not None and self.selected is not None:
            self.session.link(self.selected, [plan.identity])
            self._after_change("Avsnittet gäller hela planen.")

    def new_without_geometry(self) -> Optional[str]:
        if self.selected is None:
            return None
        heading = self.session.sections[self.selected].heading
        try:
            obj = self.session.host.create_without_geometry(heading, self.window())
        except ValueError as exc:
            self.toast(str(exc))
            return None
        if obj is None:
            return None
        self.session.plan.objects.append(obj)
        self._fill_tree()
        self.session.link(self.selected, [obj.identity])
        self._after_change(f"Nytt innehåll utan geometri: {obj.long_title()}")
        return obj.identity

    def show_in_host(self) -> None:
        if self.selected is None:
            return
        count = self.session.host.select_in_map(self.session.links[self.selected])
        self.toast(f"{count} objekt är markerade i {self.session.host.name}." if count else
                   f"Inget av avsnittets innehåll finns i {self.session.host.name}s karta (hela planen och innehåll "
                   "utan geometri syns inte där).")

    def clear_links(self) -> None:
        if self.selected is not None:
            self.session.clear_links(self.selected)
            self._after_change("Avsnittets kopplingar är borttagna.")


# -- steg 4: kontroll och spara ----------------------------------------------------------------------------------------
class SavePage(QWidget):
    open_section = pyqtSignal(int, int)  # (steg, avsnitt)
    open_object = pyqtSignal(str)
    saved = pyqtSignal()

    def __init__(self, session: ss.Session, toast):
        super().__init__()
        self.session, self.toast = session, toast
        self.setObjectName("page")
        self.check_summary = label("", "muted", wrap=True)
        self.findings_layout = QVBoxLayout()
        self.findings_layout.setSpacing(0)
        checks = frame("panel", box("v", self.findings_layout, margins=(0, 4, 0, 4)))
        self.result = label("", wrap=True, rich=True)
        self.result.linkActivated.connect(lambda url: QDesktopServices.openUrl(QUrl.fromLocalFile(url)))
        self.result.hide()
        exports = box("v", spacing=10)
        self.save_button = self._export_row(
            exports, "Kopia med bokmärken och kopplingar",
            "En kopia av Word-filen med ett bokmärke per avsnitt (originalet ändras inte), och kopplingarna i planens "
            "tabeller dokumentavsnitt, avsnittsbokmärke och dokumentreferens_op. Sparas direkt i planen.",
            "Spara…", self.save, primary=True)
        self.web = QCheckBox("Spara också en webbversion (HTML) bredvid kopian")
        self.web.setToolTip("En webbsida med planhandlingens text, där varje avsnitt har sitt bokmärke som adress "
                            "(planhandling.html#op_…), så att en webbkarta kan länka från planens innehåll till texten.")
        self.web.setChecked(session.store.get("webbversion") != "0")
        self.web.toggled.connect(lambda on: session.store.put("webbversion", "1" if on else "0"))
        exports.addWidget(self.web)
        self._export_row(exports, "Översikt över kopplingarna",
                         "Tabell (CSV) som öppnas i Excel: bokmärke, rubrik, avsnittstyp och objekt.", "Spara…",
                         self.save_overview)
        export_panel = frame("panel", box("v", label("Spara", "h2"), exports, self.result,
                                          spacing=12, margins=(16, 16, 16, 16)))
        left = QWidget()
        left.setLayout(box("v", label("Kontroll", "h2"), self.check_summary, checks, 8, export_panel, None,
                           spacing=8, margins=(20, 20, 10, 20)))

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Bokmärke", "Rubrik", "Avsnittstyp", "Objekt"])
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        header = self.table.horizontalHeader()
        for column, mode in enumerate((QHeaderView.ResizeMode.ResizeToContents, QHeaderView.ResizeMode.Interactive,
                                       QHeaderView.ResizeMode.ResizeToContents, QHeaderView.ResizeMode.Stretch)):
            header.setSectionResizeMode(column, mode)
        self.table.setColumnWidth(1, 220)
        self.table_hint = label("", "hint", wrap=True)
        right = frame("panel", box("v", label("Det här sparas i planen", "h2"), self.table_hint, self.table,
                                   spacing=10, margins=(16, 16, 16, 16)))
        holder = QWidget()
        holder.setLayout(box("v", right, margins=(10, 20, 20, 20)))
        splitter = QSplitter()
        splitter.addWidget(scrolled(left))
        splitter.addWidget(holder)
        splitter.setSizes([620, 700])
        splitter.setChildrenCollapsible(False)
        self.setLayout(box("v", splitter))

    def _export_row(self, layout, title, text, action, slot, primary=False):
        b = button(action, "primary" if primary else "small")
        b.clicked.connect(slot)
        row = QFrame()
        row.setObjectName("chosen")
        row.setLayout(box("h", box("v", label(title, "fileName"), label(text, "hint", wrap=True), spacing=2), b,
                          spacing=12, margins=(12, 10, 12, 10)))
        layout.addWidget(row)
        return b

    def refresh(self) -> None:
        session = self.session
        if not session.ready:
            return
        clear_layout(self.findings_layout)
        findings = session.findings()
        errors = sum(1 for f in findings if f.level == ss.FEL)
        warnings = sum(1 for f in findings if f.level == ss.VARNING)
        self.check_summary.setText(
            f"{errors} fel och {warnings} varningar." if errors or warnings else
            "Inga fel eller varningar. Det som står som information går bra att spara med.")
        for n, finding in enumerate(findings):
            self.findings_layout.addWidget(self._finding_row(finding, first=n == 0))
        if not findings:
            self.findings_layout.addWidget(label("Allt ser bra ut.", "muted"))
        rows = session.overview_rows()
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for column, value in enumerate(row):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                self.table.setItem(r, column, item)
        tagged = session.tagged()
        links = sum(len(session.links[s.index]) for s in tagged)
        self.table_hint.setText(
            f"{len(tagged)} bokmärken i Word-filen och i avsnittsbokmärke, {links} {'rad' if links == 1 else 'rader'} "
            "i dokumentavsnitt (en per koppling). Ett avsnitt utan bokmärke får sitt namn (op_ och tolv tecken) när du "
            "sparar och behåller det sedan.")

    def _finding_row(self, finding: ss.Finding, first: bool) -> QWidget:
        c = theme.C
        color = {ss.FEL: c["bad"], ss.VARNING: c["warn"], ss.INFO: c["info"]}[finding.level]
        icon = label({ss.FEL: "×", ss.VARNING: "!", ss.INFO: "i"}[finding.level])
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setFixedSize(22, 22)
        icon.setStyleSheet(f"QLabel {{ background: {theme.mix(color, .16)}; color: {color}; border-radius: 11px; "
                           "font-weight: 700; }")
        texts = box("v", label(finding.text, wrap=True), label(finding.where, "hint", wrap=True) if finding.where else None,
                    spacing=2)
        row = QFrame()
        row.setStyleSheet("" if first else f"QFrame {{ border-top: 1px solid {c['line2']}; }} QLabel {{ border: 0; }}")
        items = [icon, texts]
        action = self._action_for(finding)
        if action is not None:
            go = button("Gå till", "small")
            go.clicked.connect(action)
            items.append(go)
        layout = box("h", *items, spacing=10, margins=(14, 10, 14, 10))
        layout.setAlignment(icon, Qt.AlignmentFlag.AlignTop)
        row.setLayout(layout)
        return row

    def _action_for(self, finding: ss.Finding):
        if finding.section is not None:
            index = finding.section
            step = 2 if self.session.status(index) in ss.NEEDS_LOOK else 3
            return lambda: self.open_section.emit(step, index)
        if finding.identity is not None:
            identity = finding.identity
            return lambda: self.open_object.emit(identity)
        return None

    def _done(self, path: Path, text: str, web: Optional[Path] = None) -> None:
        folder = html.escape(str(path.parent))
        page = f' · <a href="{html.escape(str(web))}">Öppna webbversionen</a>' if web else ""
        self.result.setText(f"{html.escape(text)}<br><a href=\"{html.escape(str(path))}\">Öppna filen</a>{page} · "
                            f"<a href=\"{folder}\">Öppna mappen</a>")
        self.result.show()
        self.toast(text)

    def _fail(self, exc: Exception) -> None:
        self.result.setText(f'<span style="color:{theme.C["bad"]}">{html.escape(str(exc))}</span>')
        self.result.show()

    def ask_destination(self) -> Optional[Path]:
        path, _ = QFileDialog.getSaveFileName(self, "Spara kopia med bokmärken", str(self.session.default_destination()),
                                              "Word-dokument (*.docx)")
        return Path(path) if path else None

    def save(self) -> Optional[Path]:
        errors = sum(1 for f in self.session.findings() if f.level == ss.FEL)
        if errors and QMessageBox.question(
                self, "Spara ändå?", f"Kontrollen hittade {errors} fel. Vill du spara ändå?") != \
                QMessageBox.StandardButton.Yes:
            return None
        destination = self.ask_destination()
        if destination is None:
            return None
        try:
            message = self.session.save(destination, web=self.web.isChecked())
        except ss.SessionError as exc:
            self._fail(exc)
            return None
        page = destination.with_suffix(".html")
        self._done(destination, message, page if self.web.isChecked() and page.exists() else None)
        self.refresh()
        self.saved.emit()
        return destination

    def save_overview(self) -> Optional[Path]:
        suggestion = self.session.docx.with_name(f"{self.session.docx.stem}_kopplingar.csv")
        path, _ = QFileDialog.getSaveFileName(self, "Spara översikt", str(suggestion), "CSV (*.csv)")
        if not path:
            return None
        path = Path(path)
        try:
            with path.open("w", newline="", encoding="utf-8-sig") as out:  # utf-8-sig: Excel visar å, ä och ö rätt
                writer = csv.writer(out, delimiter=";")
                writer.writerow(["Bokmärke", "Rubrik", "Avsnittstyp", "Objekt"])
                writer.writerows(self.session.overview_rows())
        except OSError as exc:
            self._fail(exc)
            return None
        self._done(path, f"Sparade {path.name}.")
        return path
