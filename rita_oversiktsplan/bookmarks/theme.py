"""Färger och stil, desamma som i Tagga planbeskrivning (Rita Detaljplan). Ljust eller mörkt läge följer QGIS tema.
Stilmallen sätts bara på programmets eget fönster, så att QGIS inte påverkas."""
from __future__ import annotations

from qgis.PyQt.QtGui import QGuiApplication, QPalette

from . import session as ss

LIGHT = {
    "bg": "#eef2f0", "surface": "#ffffff", "surface2": "#f5f7f6", "line": "#d6dedb", "line2": "#e6ecea",
    "fg": "#16201e", "muted": "#5a6b66", "accent": "#0e6a5b", "accent_fg": "#ffffff", "accent_soft": "#dcefe9",
    "ok": "#1d7a49", "warn": "#a96a12", "bad": "#b42318", "warn_soft": "#fbefd9", "bad_soft": "#fbe3e0",
    "info": "#2d6db5", "page": "#ffffff",
    "t1": "#6a4cc0", "t2": "#2d6db5", "t3": "#c2410c", "t4": "#866514", "t5": "#56708a", "t6": "#23845f", "t7": "#ad346b",
    "map_bg": "#f5f7f6", "map_line": "#54605d",
}
DARK = {
    "bg": "#0f1514", "surface": "#172020", "surface2": "#1d2726", "line": "#2f3d3a", "line2": "#263230",
    "fg": "#e4ebe9", "muted": "#98aaa5", "accent": "#4cc2a7", "accent_fg": "#052520", "accent_soft": "#173a33",
    "ok": "#5cc98d", "warn": "#e2a64b", "bad": "#f07a6d", "warn_soft": "#3a2e17", "bad_soft": "#3e1f1c",
    "info": "#74a8ea", "page": "#1b2524",
    "t1": "#a691ec", "t2": "#74a8ea", "t3": "#f08a5a", "t4": "#d5b45a", "t5": "#9db3c8", "t6": "#5fcc9f", "t7": "#e47aa8",
    "map_bg": "#1d2726", "map_line": "#9fb0ab",
}
# avsnittstyperna i ÖP-katalogen 2.2 får var sin färg; en typ som inte finns här får en färg efter sin plats i listan
TYPE_TOKEN = {
    "Sammanfattning": "t5", "Översiktsplanens syfte": "t1", "Beskrivning": "t2", "Ställningstagande": "t6",
    "Konsekvens": "t7", "Framtagandeprocess": "t4", "Länsstyrelsens invändning": "t3",
    "Kommentar på länsstyrelsens invändning": "t3", "Övrig information": "t5",
}
STATUS_TOKEN = {ss.FORSLAG: "ok", ss.ANDRAD: "info", ss.GRANSKAD: "accent", ss.HOPPAS: "muted"}

UI_FONT = '"Segoe UI Variable Text", "Segoe UI", sans-serif'
DOC_FONT = '"Cambria", "Georgia", serif'
MONO_FONT = '"Cascadia Mono", "Consolas", monospace'

C: dict = dict(LIGHT)  # aktuella färger


def is_dark() -> bool:
    return QGuiApplication.palette().color(QPalette.ColorRole.Window).lightness() < 128


def load() -> str:
    C.clear()
    C.update(DARK if is_dark() else LIGHT)
    return stylesheet()


def type_color(type_: str) -> str:
    if not type_:
        return C["bad"]
    token = TYPE_TOKEN.get(type_) or f"t{sum(map(ord, type_)) % 7 + 1}"
    return C[token]


def status_color(status) -> str:
    return C[STATUS_TOKEN.get(status, "muted")]


def mix(color: str, alpha: float, base: str | None = None) -> str:
    """``color`` blandad med ``base`` (standard: ytans färg)."""
    base = base or C["surface"]
    a = [int(color[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(base[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x * alpha + y * (1 - alpha)):02x}" for x, y in zip(a, b))


def stylesheet() -> str:
    c = C
    return f"""
* {{ font-family: {UI_FONT}; font-size: 10pt; color: {c['fg']}; }}
QMainWindow, #page {{ background: {c['bg']}; }}
QToolTip {{ background: {c['fg']}; color: {c['bg']}; border: 0; padding: 4px 8px; }}

#topbar {{ background: {c['surface']}; border-bottom: 1px solid {c['line']}; }}
#brand {{ font-weight: 700; font-size: 11pt; }}
#brandSub {{ color: {c['muted']}; font-size: 8.5pt; }}
#fileHint {{ color: {c['muted']}; font-size: 9pt; }}
QPushButton#step {{ border: 0; background: transparent; padding: 7px 12px; border-radius: 8px; color: {c['muted']};
    font-weight: 600; text-align: left; }}
QPushButton#step:hover {{ background: {c['surface2']}; color: {c['fg']}; }}
QPushButton#step:checked {{ background: {c['accent_soft']}; color: {c['fg']}; }}
QPushButton#step:disabled {{ color: {c['line']}; }}

QPushButton {{ border: 1px solid {c['line']}; background: {c['surface']}; padding: 7px 14px; border-radius: 8px;
    font-weight: 600; }}
QPushButton:hover {{ border-color: {c['muted']}; }}
QPushButton:disabled {{ color: {c['muted']}; background: {c['surface2']}; border-color: {c['line2']}; }}
QPushButton[kind="primary"] {{ background: {c['accent']}; color: {c['accent_fg']}; border-color: {c['accent']}; }}
QPushButton[kind="primary"]:hover {{ background: {mix(c['accent'], .85, c['fg'] if not is_dark() else '#ffffff')}; }}
QPushButton[kind="primary"]:disabled {{ background: {c['line']}; border-color: {c['line']}; color: {c['muted']}; }}
QPushButton[kind="ghost"] {{ border-color: transparent; background: transparent; color: {c['muted']}; }}
QPushButton[kind="ghost"]:hover {{ background: {c['surface2']}; color: {c['fg']}; }}
QPushButton[kind="small"] {{ padding: 4px 10px; font-size: 9pt; }}
QPushButton[kind="filter"] {{ border-radius: 11px; padding: 3px 10px; font-size: 9pt; font-weight: 500; color: {c['muted']}; }}
QPushButton[kind="filter"]:checked {{ border-color: {c['accent']}; background: {c['accent_soft']}; color: {c['fg']}; }}

QFrame#panel {{ background: {c['surface']}; border: 1px solid {c['line']}; border-radius: 12px; }}
QFrame#sideLeft {{ background: {c['surface']}; border-right: 1px solid {c['line']}; }}
QFrame#sideRight {{ background: {c['surface']}; border-left: 1px solid {c['line']}; }}
QFrame#chosen {{ background: {c['surface2']}; border: 1px solid {c['line']}; border-radius: 8px; }}
QFrame#chosen[empty="true"] {{ border-style: dashed; }}
QFrame#warning {{ background: {c['warn_soft']}; border: 1px solid {mix(c['warn'], .45)}; border-radius: 8px; }}
QFrame#warning QLabel {{ background: transparent; }}
QFrame#why {{ background: {c['surface2']}; border-radius: 8px; }}
QFrame#docPage {{ background: {c['page']}; border-radius: 4px; border: 1px solid {c['line2']}; }}
QLabel#h1 {{ font-size: 20pt; font-weight: 700; }}
QLabel#h2 {{ font-size: 12pt; font-weight: 700; }}
QLabel#h3 {{ font-size: 13pt; font-weight: 700; }}
QLabel#lead {{ color: {c['muted']}; font-size: 10.5pt; }}
QLabel#muted, QLabel#hint {{ color: {c['muted']}; }}
QLabel#hint {{ font-size: 9pt; }}
QLabel#eyebrow {{ color: {c['muted']}; font-size: 8pt; font-weight: 700; letter-spacing: 1px; }}
QLabel#error {{ color: {c['bad']}; }}
QLabel#fileName {{ font-weight: 600; }}
QLabel#docTitle {{ font-family: {DOC_FONT}; font-size: 20pt; }}
QLabel#docHeading {{ font-family: {DOC_FONT}; font-size: 14pt; }}
QLabel#docHeading[level="1"] {{ font-size: 16pt; }}
QLabel#docText {{ font-family: {DOC_FONT}; font-size: 11.5pt; }}
QLabel#paragraphGrip {{ color: {c['muted']}; font-size: 8.5pt; padding: 2px 0 1px 0; border-top: 1px dashed {c['line2']}; }}
QLabel#paragraphGrip:hover {{ color: {c['accent']}; }}
QLabel#factValue {{ font-weight: 700; }}

QScrollArea {{ border: 0; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QListWidget, QTreeWidget {{ border: 0; background: transparent; outline: 0; }}
QListWidget::item {{ padding: 2px 8px; border-radius: 6px; margin: 1px 4px; }}
QListWidget::item:hover, QTreeWidget::item:hover {{ background: {c['surface2']}; }}
QListWidget::item:selected, QTreeWidget::item:selected {{ background: {c['accent_soft']}; color: {c['fg']}; }}
QTreeWidget::item {{ padding: 3px 2px; }}
QHeaderView::section {{ background: {c['surface2']}; border: 0; border-bottom: 1px solid {c['line']}; padding: 5px 8px;
    color: {c['muted']}; font-weight: 600; }}
QTableWidget {{ border: 0; background: {c['surface']}; gridline-color: {c['line2']}; }}
QComboBox, QLineEdit {{ border: 1px solid {c['line']}; border-radius: 8px; padding: 6px 10px; background: {c['surface']}; }}
QComboBox:disabled {{ color: {c['muted']}; background: {c['surface2']}; }}
QComboBox QAbstractItemView {{ background: {c['surface']}; border: 1px solid {c['line']}; selection-background-color: {c['accent_soft']};
    selection-color: {c['fg']}; }}
QProgressBar {{ border: 0; background: {c['line2']}; border-radius: 4px; max-height: 8px; }}
QProgressBar::chunk {{ background: {c['accent']}; border-radius: 4px; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {c['line']}; border-radius: 4px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {c['line']}; border-radius: 4px; min-width: 30px; }}
#toast {{ background: {c['fg']}; color: {c['bg']}; border-radius: 10px; padding: 10px 16px; }}
"""
