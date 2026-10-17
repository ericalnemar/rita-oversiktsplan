"""Huvudfönstret: toppfält med stegen och en sida per steg, som i Tagga planbeskrivning. Fönstret är inte modalt, så
att man kan arbeta i QGIS (markera, rita) medan det är öppet."""
from __future__ import annotations

from pathlib import Path

from qgis.PyQt.QtCore import QByteArray, QSettings, QSize, Qt
from qgis.PyQt.QtGui import QIcon, QPainter, QPixmap
from qgis.PyQt.QtSvg import QSvgRenderer
from qgis.PyQt.QtWidgets import QButtonGroup, QFrame, QMainWindow, QMessageBox, QStackedWidget, QWidget

from . import APP_NAME, SETTINGS_NAME
from . import session as ss
from . import theme
from .pages import FilesPage, LinkPage, SavePage, SectionsPage
from .widgets import Toast, box, button, label

ICON_FILE = Path(__file__).resolve().parents[1] / "icons" / "planhandling.svg"  # samma ikon som i verktygsfältet

STEPS = ("Filer", "Avsnitt", "Koppling", "Kontroll och spara")


def logo_pixmap(size: int = 28) -> QPixmap:
    renderer = QSvgRenderer(QByteArray(ICON_FILE.read_bytes()))
    pixmap = QPixmap(QSize(size, size) * 2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(2)
    return pixmap


def settings_store() -> ss.Store:
    settings = QSettings("Rita", SETTINGS_NAME)

    def get(key):
        value = settings.value(key)
        return str(value) if value is not None else None

    return ss.Store(get, lambda key, value: settings.setValue(key, value))


class MainWindow(QMainWindow):
    def __init__(self, session: ss.Session, parent=None):
        super().__init__(parent)
        self.session = session
        self.setStyleSheet(theme.load())  # bara det här fönstret, inte QGIS
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QIcon(logo_pixmap(64)))
        self.resize(1380, 880)
        self.toast = Toast(self)

        logo = label()
        logo.setPixmap(logo_pixmap())
        brand = box("h", logo, box("v", label(APP_NAME, "brand"), label("Bokmärken enligt ÖP-modellen", "brandSub"),
                                   spacing=0), spacing=10)
        self.steps = QButtonGroup(self)
        self.steps.setExclusive(True)
        steps = box("h", spacing=4)
        for n, name in enumerate(STEPS, 1):
            b = button(f"{n}   {name}")
            b.setObjectName("step")
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, n=n: self.go(n))
            self.steps.addButton(b, n)
            steps.addWidget(b)
        self.file_hint = label("", "fileHint")
        bar = QFrame()
        bar.setObjectName("topbar")
        bar.setLayout(box("h", brand, 24, steps, None, self.file_hint, margins=(16, 10, 16, 10)))

        self.files = FilesPage(session, self.show_toast)
        self.sections = SectionsPage(session, self.show_toast)
        self.link = LinkPage(session, self.show_toast)
        self.save = SavePage(session, self.show_toast)
        self.pages = (self.files, self.sections, self.link, self.save)
        self.stack = QStackedWidget()
        for page in self.pages:
            self.stack.addWidget(page)
        self.files.loaded.connect(self._loaded)
        self.files.proceed.connect(lambda: self.go(2))
        self.sections.go.connect(self.open_section)
        self.save.open_section.connect(self.open_section)
        self.save.open_object.connect(self.open_object)
        self.save.saved.connect(self._loaded)

        central = QWidget()
        central.setLayout(box("v", bar, self.stack, spacing=0))
        self.setCentralWidget(central)
        self.go(1)

    def show_toast(self, text: str) -> None:
        self.toast.show_text(text)

    def _loaded(self) -> None:
        s = self.session
        self.file_hint.setText("   ·   ".join(p for p in (s.docx.name if s.docx else "", s.plan.title if s.plan else "")
                                             if p))
        self._enable_steps()

    def _enable_steps(self) -> None:
        for n in (2, 3, 4):
            self.steps.button(n).setEnabled(self.session.ready)

    def go(self, step: int) -> None:
        if step > 1 and not self.session.ready:
            step = 1
        self.steps.button(step).setChecked(True)
        page = self.pages[step - 1]
        page.refresh()
        self.stack.setCurrentWidget(page)
        self._enable_steps()
        if step == 2:
            self.sections.setFocus()

    def open_section(self, step: int, index: int) -> None:
        self.go(step)
        if step == 2:
            self.sections.filter = "alla"
            self.sections.refresh()
            self.sections.select(index, scroll=True)
        elif index is not None:
            self.link.select(index)

    def open_object(self, identity: str) -> None:
        self.go(3)
        self.link.focus_object(identity)

    def reload_plan(self) -> None:
        """Läser planen igen (när programmet öppnas på nytt från verktygsfältet)."""
        self.files.reload_from_host()
        self.stack.currentWidget().refresh()

    def closeEvent(self, event) -> None:  # noqa: N802
        if self.session.dirty and QMessageBox.question(
                self, APP_NAME, "Det finns ändringar som inte är sparade. Vill du stänga ändå?") != \
                QMessageBox.StandardButton.Yes:
            event.ignore()
            return
        super().closeEvent(event)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self.toast.isVisible():
            self.toast.move((self.width() - self.toast.width()) // 2, self.height() - self.toast.height() - 24)


def open_window(group, parent=None, store: ss.Store | None = None) -> MainWindow:
    """Öppnar programmet med planen i ``group`` (en egen, inte modal, fönster)."""
    from .host import QgisHost

    window = MainWindow(ss.Session(QgisHost(group), store or settings_store()), parent)
    window.setWindowFlag(Qt.WindowType.Window, True)
    window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
    window.files.reload_from_host()
    window.show()
    window.raise_()
    window.activateWindow()
    return window
