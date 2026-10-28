"""Splatter VHS look: black cases, blood red, cream tape labels. Paper stays paper."""

INK = "#0c0a0e"
PANEL = "#16121a"
PANEL2 = "#1f1924"
LINE = "#2e2533"
TEXT = "#ece5ea"
DIM = "#9a8f98"
BLOOD = "#d11a22"
BLOOD_HI = "#ff3b3b"
LABEL = "#f1e6c8"

QSS = f"""
* {{ color: {TEXT}; font-size: 10pt; }}
QMainWindow, QWidget {{ background: {INK}; }}
QToolTip {{ background: {PANEL2}; color: {TEXT}; border: 1px solid {BLOOD}; }}
QMenuBar {{ background: {INK}; border-bottom: 1px solid {LINE}; }}
QMenuBar::item:selected, QMenu::item:selected {{ background: {BLOOD}; color: white; }}
QMenu {{ background: {PANEL}; border: 1px solid {LINE}; }}
QMenu::separator {{ height: 1px; background: {LINE}; margin: 4px 8px; }}
QToolBar {{ background: {INK}; border: none; border-bottom: 2px solid {BLOOD}; spacing: 4px; padding: 4px; }}
QToolButton {{ background: transparent; border: 1px solid transparent; border-radius: 3px;
              padding: 4px 8px; font-weight: bold; letter-spacing: 1px; }}
QToolButton:hover {{ border-color: {BLOOD}; background: {PANEL2}; }}
QDockWidget {{ titlebar-close-icon: none; }}
QDockWidget::title {{ background: {PANEL}; padding: 6px 8px; border-bottom: 2px solid {BLOOD};
                     font-weight: bold; letter-spacing: 2px; text-transform: uppercase; }}
QLabel#Section {{ color: {BLOOD_HI}; font-weight: bold; letter-spacing: 2px; font-size: 8pt;
                 padding-top: 6px; background: transparent; }}
QLabel#SceneHeader {{ background: {LABEL}; color: #1a1418; font-family: 'Courier Prime', 'Courier New';
                     font-weight: bold; padding: 6px 8px; border-left: 6px solid {BLOOD}; }}
QFrame#BeatGuide {{ background: {PANEL2}; border: 1px solid {LINE}; border-top: 3px solid {BLOOD}; }}
QFrame#BeatGuide QLabel {{ background: transparent; }}
QLabel#BeatName {{ color: {BLOOD_HI}; font-weight: bold; letter-spacing: 2px; }}
QLabel#BeatPace {{ color: {TEXT}; font-size: 9pt; }}
QLabel#BeatText {{ color: {TEXT}; font-size: 9pt; }}
QLabel#BeatHorror {{ color: {DIM}; font-size: 9pt; font-style: italic; }}
QListWidget, QTreeWidget, QTableWidget, QPlainTextEdit, QLineEdit, QComboBox, QSpinBox, QTextBrowser {{
    background: {PANEL}; border: 1px solid {LINE}; border-radius: 2px;
    selection-background-color: {BLOOD}; selection-color: white; }}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus {{ border-color: {BLOOD}; }}
QListWidget::item, QTreeWidget::item {{ padding: 3px; }}
QListWidget::item:selected, QTreeWidget::item:selected {{ background: {BLOOD}; color: white; }}
QHeaderView::section {{ background: {PANEL2}; border: none; border-right: 1px solid {LINE};
                       padding: 4px; font-weight: bold; color: {DIM}; }}
QComboBox QAbstractItemView {{ background: {PANEL}; border: 1px solid {BLOOD}; }}
QPushButton {{ background: {PANEL2}; border: 1px solid {LINE}; padding: 5px 10px; border-radius: 2px; }}
QPushButton:hover {{ border-color: {BLOOD}; }}
QPushButton#Primary {{ background: {BLOOD}; border-color: {BLOOD}; color: white; font-weight: bold; }}
QPushButton#Primary:hover {{ background: {BLOOD_HI}; }}
QTabWidget::pane {{ border: none; }}
QTabBar::tab {{ background: {LABEL}; color: #2a1f22; padding: 6px 16px; margin-right: 3px;
               font-family: 'Courier Prime', 'Courier New'; font-weight: bold; letter-spacing: 1px;
               border-bottom-left-radius: 3px; border-bottom-right-radius: 3px; }}
QTabBar::tab:selected {{ background: {BLOOD}; color: white; }}
QTabBar::tab:disabled {{ background: {PANEL2}; color: #555; }}
QStatusBar {{ background: {INK}; border-top: 1px solid {LINE}; color: {DIM}; }}
QStatusBar QLabel {{ color: {DIM}; background: transparent; padding: 0 8px; }}
QScrollArea#Desk, QWidget#DeskInner {{ background: #1a141c; }}
QScrollArea#Desk > QWidget > QWidget {{ background: #1a141c; }}
QTextEdit#ScriptPage {{ font-family: 'Courier Prime', 'Courier New', monospace; font-size: 12pt; }}
QPlainTextEdit#NovelPage {{ font-family: Georgia, 'DejaVu Serif', serif; font-size: 13pt; }}
QTextEdit#ScriptPage, QPlainTextEdit#NovelPage {{ background: #fdfcf8; color: #111;
    border: none; selection-background-color: #f2b8bb; selection-color: #111; }}
QFrame#Paper {{ background: #fdfcf8; }}
QFrame#Paper QLabel#PaperLabel {{ background: transparent; color: #8a7f86; font-family: 'Courier Prime', 'Courier New'; }}
QLineEdit#PaperField, QPlainTextEdit#PaperField {{ background: #fdfcf8; color: #111; border: 1px dashed #c9bfc5; }}
QPlainTextEdit#Scratch {{ background: {LABEL}; color: #1f1a1c; font-family: 'Courier Prime', 'Courier New';
                         font-size: 12pt; border: none; padding: 16px; }}
QTextBrowser#ReportPaper {{ background: #fdfcf8; color: #111; border: none; padding: 20px; }}
QFrame#Card {{ background: {LABEL}; border-top: 6px solid {BLOOD}; border-radius: 2px; }}
QFrame#Card QLabel {{ background: transparent; color: #1a1418; font-family: 'Courier Prime', 'Courier New'; }}
QFrame#Card QPushButton {{ background: #1a1418; color: {LABEL}; border: none; padding: 2px; }}
QPlainTextEdit#CardBody {{ background: transparent; border: none; color: #1a1418;
                          font-family: 'Courier Prime', 'Courier New'; }}
QLabel#CardFootFX {{ color: {BLOOD}; font-weight: bold; }}
QLabel#CardFoot {{ color: #6b5f65; }}
QScrollBar:vertical {{ background: {INK}; width: 12px; }}
QScrollBar::handle:vertical {{ background: {LINE}; min-height: 30px; border-radius: 4px; }}
QScrollBar::handle:vertical:hover {{ background: {BLOOD}; }}
QScrollBar:horizontal {{ background: {INK}; height: 12px; }}
QScrollBar::handle:horizontal {{ background: {LINE}; min-width: 30px; border-radius: 4px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QSplitter::handle {{ background: {LINE}; }}
QDialog {{ background: {PANEL}; }}
"""
