"""Side panels and the non-script tabs."""
from __future__ import annotations

from PySide6.QtCore import QMimeData, QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QDrag, QFont, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QFileDialog, QFormLayout,
                               QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
                               QPlainTextEdit, QPushButton, QScrollArea, QSizePolicy,
                               QSpinBox, QTableWidget, QTableWidgetItem, QTextBrowser,
                               QVBoxLayout, QWidget)

from . import reports
from .editor import ScriptEdit, script_font
from .model import (CATEGORIES, CATEGORY_COLOURS, CHARACTER, MAKEUP_CATEGORIES,
                    SPFX_CATEGORIES, beat_info)


def section(text: str) -> QLabel:
    l = QLabel(text.upper())
    l.setObjectName("Section")
    return l


# ===================================================================== BEAT GUIDE
class BeatGuide(QFrame):
    """Shows which Save the Cat beat the cursor is in and whether you're on pace."""
    targetChanged = Signal(int)

    def __init__(self):
        super().__init__()
        self.setObjectName("BeatGuide")
        v = QVBoxLayout(self)
        v.setContentsMargins(10, 8, 10, 8)
        v.setSpacing(3)
        top = QHBoxLayout()
        self.name = QLabel("No beat")
        self.name.setObjectName("BeatName")
        top.addWidget(self.name, 1)
        top.addWidget(QLabel("Target"))
        self.target = QSpinBox()
        self.target.setRange(5, 200)
        self.target.setValue(100)
        self.target.setSuffix(" pp")
        self.target.valueChanged.connect(self.targetChanged.emit)
        top.addWidget(self.target)
        v.addLayout(top)
        self.pace = QLabel("")
        self.pace.setObjectName("BeatPace")
        v.addWidget(self.pace)
        self.guide = QLabel("Script → Insert Save the Cat Beats to add a pre-filled guide.")
        self.guide.setWordWrap(True)
        self.guide.setObjectName("BeatText")
        self.guide.setMinimumHeight(36)
        v.addWidget(self.guide)
        self.horror = QLabel("")
        self.horror.setWordWrap(True)
        self.horror.setObjectName("BeatHorror")
        self.horror.setMinimumHeight(36)
        v.addWidget(self.horror)

    def update_for(self, beat: str | None, page_now: float, target: int):
        info = beat_info(beat) if beat else None
        if not beat:
            self.name.setText("NO BEAT")
            self.pace.setText(f"You're on ~p.{page_now:.0f}")
            self.guide.setText("Script → Insert Save the Cat Beats to add a pre-filled guide.")
            self.horror.setText("")
            return
        self.name.setText(beat.split("(")[0].strip().upper())
        if info:
            lo, hi = max(1.0, info[1] * target), max(1.0, info[2] * target)
            slack = max(2, target * 0.03)
            if page_now < lo - slack:
                state, col = "early", "#58a6ff"
            elif page_now > hi + slack:
                state, col = "running long", "#ff4d4f"
            else:
                state, col = "on track", "#3fb950"
            self.pace.setText(f"Aim p.{lo:.0f}–{hi:.0f} · you're on ~p.{page_now:.0f} · "
                              f"<span style='color:{col}'><b>{state}</b></span>")
            self.guide.setText(info[3])
            self.horror.setText(info[4])
        else:
            self.pace.setText(f"Custom beat · you're on ~p.{page_now:.0f}")
            self.guide.setText("")
            self.horror.setText("")


# ===================================================================== BREAKDOWN
class BreakdownPanel(QWidget):
    changed = Signal()

    def __init__(self):
        super().__init__()
        self.editor: ScriptEdit | None = None
        self.sid = None
        v = QVBoxLayout(self)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(6)

        self.beat = BeatGuide()
        v.addWidget(self.beat)

        self.header = QLabel("NO SCENE")
        self.header.setObjectName("SceneHeader")
        self.header.setWordWrap(True)
        v.addWidget(self.header)

        v.addWidget(section("Synopsis"))
        self.synopsis = QPlainTextEdit()
        self.synopsis.setPlaceholderText("One line on what happens in this scene (shows on index cards)")
        self.synopsis.setMaximumHeight(64)
        self.synopsis.textChanged.connect(self._syn_changed)
        v.addWidget(self.synopsis)

        v.addWidget(section("Breakdown"))
        f = QFormLayout()
        f.setLabelAlignment(Qt.AlignRight)
        self.cat = QComboBox()
        for i, c in enumerate(CATEGORIES):
            if i == len(SPFX_CATEGORIES):
                self.cat.insertSeparator(self.cat.count())
            self.cat.addItem(c)
            self.cat.setItemData(self.cat.count() - 1, QColor(CATEGORY_COLOURS.get(c, "#ccc")),
                                 Qt.ForegroundRole)
        f.addRow("Type", self.cat)
        self.item = QLineEdit()
        self.item.setPlaceholderText("e.g. Throat slash appliance")
        self.item.returnPressed.connect(self.add_item)
        f.addRow("Item", self.item)
        self.char = QComboBox()
        self.char.setEditable(True)
        self.char.lineEdit().setPlaceholderText("Who wears / uses it")
        f.addRow("Who", self.char)
        self.note = QLineEdit()
        self.note.setPlaceholderText("Repeats, blood qty, rig notes…")
        self.note.returnPressed.connect(self.add_item)
        f.addRow("Notes", self.note)
        v.addLayout(f)
        h = QHBoxLayout()
        add = QPushButton("Add to scene")
        add.setObjectName("Primary")
        add.clicked.connect(self.add_item)
        rem = QPushButton("Remove")
        rem.clicked.connect(self.remove_item)
        h.addWidget(add, 1)
        h.addWidget(rem)
        v.addLayout(h)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Type", "Item", "Who", "Notes"])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setWordWrap(False)
        for col, wdt in enumerate((130, 160, 80)):
            self.table.setColumnWidth(col, wdt)
        self.table.itemChanged.connect(self._cell_changed)
        v.addWidget(self.table, 1)
        self.setEnabled(False)

    # ------------------------------------------------------------
    def set_editor(self, ed: ScriptEdit | None):
        self.editor = ed
        self.setEnabled(ed is not None)
        if ed:
            self.set_scene(ed.current_scene_id())

    def _items(self):
        if not (self.editor and self.sid):
            return None
        return self.editor.scene_data.setdefault(self.sid, {"synopsis": "", "items": []})

    def refresh_characters(self):
        if not self.editor:
            return
        names = set()
        b = self.editor.document().firstBlock()
        while b.isValid():
            if self.editor.element_of(b) == CHARACTER and b.text().strip():
                names.add(reports._clean_char(b.text()))
            b = b.next()
        cur = self.char.currentText()
        self.char.blockSignals(True)
        self.char.clear()
        self.char.addItem("")
        self.char.addItems(sorted(n for n in names if n))
        self.char.setEditText(cur)
        self.char.blockSignals(False)

    def set_scene(self, sid):
        self.sid = sid
        data = self._items()
        self.synopsis.blockSignals(True)
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        if data is None:
            self.header.setText("NO SCENE — add a Scene Heading to start a breakdown")
            self.synopsis.setPlainText("")
            self.synopsis.setEnabled(False)
        else:
            num, text = "", ""
            for n, t, s, _b in self.editor.scene_blocks():
                if s == sid:
                    num, text = n, t
            self.header.setText(f"SCENE {num} · {text}")
            self.synopsis.setEnabled(True)
            self.synopsis.setPlainText(data.get("synopsis", ""))
            for it in data["items"]:
                self._add_row(it)
        self.synopsis.blockSignals(False)
        self.table.blockSignals(False)
        self.refresh_characters()

    def _add_row(self, it):
        r = self.table.rowCount()
        self.table.insertRow(r)
        for col, key in enumerate(("cat", "item", "char", "note")):
            cell = QTableWidgetItem(it.get(key, ""))
            if key == "cat":
                cell.setFlags(cell.flags() & ~Qt.ItemIsEditable)
                cell.setForeground(QColor(CATEGORY_COLOURS.get(it["cat"], "#ccc")))
                f = cell.font()
                f.setBold(it["cat"] in MAKEUP_CATEGORIES)
                cell.setFont(f)
            self.table.setItem(r, col, cell)

    def add_item(self, cat=None, text=None):
        data = self._items()
        if data is None:
            QMessageBox.information(self, "No scene", "Put the cursor inside a scene first.")
            return
        it = {"cat": cat or self.cat.currentText(),
              "item": (text if text is not None else self.item.text()).strip(),
              "char": self.char.currentText().strip().upper() if text is None else "",
              "note": self.note.text().strip() if text is None else ""}
        if not it["item"]:
            self.item.setFocus()
            return
        data["items"].append(it)
        self.table.blockSignals(True)
        self._add_row(it)
        self.table.blockSignals(False)
        if text is None:
            self.item.clear()
            self.note.clear()
        self.changed.emit()

    def remove_item(self):
        data = self._items()
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        if data is None or not rows:
            return
        for r in rows:
            del data["items"][r]
            self.table.removeRow(r)
        self.changed.emit()

    def _cell_changed(self, cell):
        data = self._items()
        if data is None:
            return
        key = ("cat", "item", "char", "note")[cell.column()]
        data["items"][cell.row()][key] = cell.text()
        self.changed.emit()

    def _syn_changed(self):
        data = self._items()
        if data is not None:
            data["synopsis"] = self.synopsis.toPlainText()
            self.changed.emit()


# ===================================================================== TITLE PAGE
class TitlePageView(QScrollArea):
    changed = Signal()
    FIELDS = [("title", "Title", False), ("credit", "Credit (e.g. Written by)", False),
              ("author", "Author", False), ("source", "Based on", False),
              ("draft", "Draft / date", False), ("copyright", "Copyright", True),
              ("contact", "Contact information", True)]

    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        self.setObjectName("Desk")
        self.data: dict = {}
        page = QFrame()
        page.setObjectName("Paper")
        page.setFixedWidth(720)
        v = QVBoxLayout(page)
        v.setContentsMargins(60, 50, 60, 50)
        self.widgets = {}
        for key, label, multi in self.FIELDS:
            l = QLabel(label)
            l.setObjectName("PaperLabel")
            l.setAlignment(Qt.AlignCenter)
            v.addWidget(l)
            w = QPlainTextEdit() if multi else QLineEdit()
            w.setFont(script_font(12))
            if multi:
                w.setFixedHeight(80)
                w.textChanged.connect(lambda k=key, w=w: self._set(k, w.toPlainText()))
            else:
                w.setAlignment(Qt.AlignCenter)
                w.textChanged.connect(lambda t, k=key: self._set(k, t))
            w.setObjectName("PaperField")
            v.addWidget(w)
            v.addSpacing(14)
            self.widgets[key] = w
        v.addStretch(1)
        outer = QWidget()
        h = QHBoxLayout(outer)
        h.addStretch(1)
        h.addWidget(page)
        h.addStretch(1)
        h.setContentsMargins(0, 30, 0, 30)
        self.setWidget(outer)

    def load(self, data: dict):
        self.data = data
        for key, w in self.widgets.items():
            w.blockSignals(True)
            (w.setPlainText if isinstance(w, QPlainTextEdit) else w.setText)(data.get(key, ""))
            w.blockSignals(False)

    def _set(self, key, value):
        self.data[key] = value
        self.changed.emit()


# ===================================================================== INDEX CARDS
CARD_MIME = "application/x-goredraft-chunk"


class Card(QFrame):
    """An index card. Drag it by its header onto another card to reorder."""
    goto = Signal(object)
    changed = Signal()
    dropped = Signal(int, int, bool)   # source chunk, target chunk, after?

    def __init__(self, num, heading, sid, block, data, beat, chunk, length=""):
        super().__init__()
        self.setObjectName("Card")
        self.setFixedSize(300, 200)
        self.setAcceptDrops(True)
        self.block, self.data, self.chunk = block, data, chunk
        self._press = None
        v = QVBoxLayout(self)
        v.setContentsMargins(10, 8, 10, 8)
        v.setSpacing(4)
        top = QHBoxLayout()
        grip = QLabel("⠿")
        grip.setToolTip("Drag to reorder")
        grip.setObjectName("CardGrip")
        top.addWidget(grip)
        h = QLabel(f"<b>{num}.</b> {heading}")
        h.setObjectName("CardHead")
        h.setWordWrap(True)
        h.setToolTip("Drag to reorder")
        top.addWidget(h, 1)
        go = QPushButton("Go")
        go.setFixedWidth(40)
        go.clicked.connect(lambda: self.goto.emit(self.block))
        top.addWidget(go)
        v.addLayout(top)
        syn = QPlainTextEdit(data.get("synopsis", ""))
        syn.setPlaceholderText("What happens…")
        syn.setObjectName("CardBody")
        syn.textChanged.connect(lambda: (data.__setitem__("synopsis", syn.toPlainText()), self.changed.emit()))
        v.addWidget(syn, 1)
        fx = [i for i in data.get("items", []) if i["cat"] in SPFX_CATEGORIES]
        bits = [x for x in (length, beat.split("(")[0].strip() if beat else "",
                            ("FX ×" + str(len(fx))) if fx else "") if x]
        foot = QLabel("   ".join(bits))
        foot.setObjectName("CardFootFX" if fx else "CardFoot")
        foot.setAlignment(Qt.AlignRight)
        v.addWidget(foot)
        self.setCursor(Qt.OpenHandCursor)

    # -- drag source (header area; the synopsis box keeps normal text dragging)
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._press = e.position().toPoint()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._press is None or (e.position().toPoint() - self._press).manhattanLength() < 8:
            return
        self._press = None
        drag = QDrag(self)
        md = QMimeData()
        md.setData(CARD_MIME, str(self.chunk).encode())
        drag.setMimeData(md)
        pix = self.grab()
        drag.setPixmap(pix.scaledToWidth(220, Qt.SmoothTransformation))
        drag.setHotSpot(QPoint(110, 20))
        self.setProperty("dragging", True)
        drag.exec(Qt.MoveAction)

    # -- drop target
    def dragEnterEvent(self, e):
        if e.mimeData().hasFormat(CARD_MIME):
            e.acceptProposedAction()
            self.setStyleSheet("QFrame#Card { border-left: 6px solid #d11a22; }")

    def dragLeaveEvent(self, e):
        self.setStyleSheet("")

    def dropEvent(self, e):
        self.setStyleSheet("")
        src = int(bytes(e.mimeData().data(CARD_MIME)).decode())
        after = e.position().x() > self.width() / 2
        e.acceptProposedAction()
        if src != self.chunk:
            # emit after the drag finishes so the card isn't deleted mid-drop
            QTimer.singleShot(0, lambda: self.dropped.emit(src, self.chunk, after))


class IndexCardsView(QScrollArea):
    goto = Signal(object)
    changed = Signal()
    reordered = Signal()

    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        self.setObjectName("Desk")
        self.cards: list[Card] = []
        self.editor = None
        self._cols = 0
        self.inner = QWidget()
        self.grid = QGridLayout(self.inner)
        self.grid.setSpacing(16)
        self.grid.setContentsMargins(20, 20, 20, 20)
        self.setWidget(self.inner)

    def refresh(self, ed: ScriptEdit | None):
        for c in self.cards:
            c.deleteLater()
        self.cards = []
        self.editor = ed
        if not ed:
            return
        _, chunks = ed.chunks()
        blocks = {sid: (n, t, b) for n, t, sid, b in ed.scene_blocks()}
        beat = None
        for ci, ch in enumerate(chunks):
            if ch["kind"] == "beat":
                beat = ch["title"]
                continue
            n, t, b = blocks.get(ch["sid"], (0, ch["title"], None))
            if b is None:
                continue
            data = ed.scene_data.setdefault(ch["sid"], {"synopsis": "", "items": []})
            sd = reports.ScriptData(paras=ch["paras"])
            mins = reports.estimate_pages(sd) * reports.MINUTES_PER_PAGE
            card = Card(n, t, ch["sid"], b, data, beat, ci, reports.fmt_runtime(mins))
            card.goto.connect(self.goto.emit)
            card.changed.connect(self.changed.emit)
            card.dropped.connect(self._dropped)
            self.cards.append(card)
        self._layout(force=True)

    def _dropped(self, src, dst, after):
        if self.editor and self.editor.move_chunk(src, dst + (1 if after else 0)):
            self.refresh(self.editor)
            self.reordered.emit()

    def _layout(self, force=False):
        cols = max(1, (self.viewport().width() - 40) // 316)
        if cols == self._cols and not force:
            return
        self._cols = cols
        for i, c in enumerate(self.cards):
            self.grid.addWidget(c, i // cols, i % cols, Qt.AlignTop | Qt.AlignLeft)
        self.grid.setRowStretch(len(self.cards) // cols + 1, 1)
        self.grid.setColumnStretch(cols, 1)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._layout()


# ===================================================================== REPORTS
class ReportsView(QWidget):
    def __init__(self):
        super().__init__()
        self.source = None       # callable -> ("screenplay", ScriptData) | ("novel", (title, text))
        self.page_size = lambda: "A4"
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        left = QVBoxLayout()
        left.setContentsMargins(8, 8, 0, 8)
        left.addWidget(section("Reports"))
        self.list = QListWidget()
        self.list.setFixedWidth(250)
        self.list.currentRowChanged.connect(lambda _: self.render())
        left.addWidget(self.list, 1)
        self.char = QComboBox()
        self.char.currentIndexChanged.connect(lambda _: self.render())
        self.char_label = QLabel("Dialogue filter")
        left.addWidget(self.char_label)
        left.addWidget(self.char)
        for label, fn in (("Refresh", self.render), ("Export PDF…", self.export_pdf),
                          ("Export HTML…", self.export_html)):
            b = QPushButton(label)
            b.clicked.connect(fn)
            left.addWidget(b)
        h.addLayout(left)
        self.view = QTextBrowser()
        self.view.setObjectName("ReportPaper")
        self.view.setOpenLinks(False)
        h.addWidget(self.view, 1)
        self._html = ""

    def set_kind(self, kind):
        self.list.blockSignals(True)
        self.list.clear()
        names = list(reports.SCREENPLAY_REPORTS) if kind == "screenplay" else ["Manuscript Stats"]
        for n in names:
            QListWidgetItem(n, self.list)
        self.list.setCurrentRow(0)
        self.list.blockSignals(False)

    def render(self):
        if not self.source:
            return
        kind, payload = self.source()
        item = self.list.currentItem()
        if not item:
            return
        name = item.text()
        self.char.setVisible(name == "Dialogue")
        self.char_label.setVisible(name == "Dialogue")
        if kind == "screenplay":
            if name == "Dialogue":
                chars = sorted({c for s in reports.scenes(payload) for c in s["chars"]})
                cur = self.char.currentText()
                self.char.blockSignals(True)
                self.char.clear()
                self.char.addItem("All characters")
                self.char.addItems(chars)
                i = self.char.findText(cur)
                self.char.setCurrentIndex(max(0, i))
                self.char.blockSignals(False)
                who = self.char.currentText()
                html = reports.dialogue(payload, None if who in ("", "All characters") else who)
            else:
                html = reports.SCREENPLAY_REPORTS[name](payload)
        else:
            html = reports.novel_stats(*payload)
        self._html = html
        self.view.setHtml(html)

    def _name(self):
        it = self.list.currentItem()
        return (it.text() if it else "report").replace(" ", "_").replace("&", "and")

    def export_pdf(self):
        from .pdfexport import export_html
        path, _ = QFileDialog.getSaveFileName(self, "Export report", f"{self._name()}.pdf", "PDF (*.pdf)")
        if path:
            export_html(self._html, path, self.page_size(), self._name())

    def export_html(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export report", f"{self._name()}.html", "HTML (*.html)")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"<!doctype html><meta charset='utf-8'><title>{self._name()}</title>{self._html}")
