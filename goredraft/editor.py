"""Script and novel editors."""
from __future__ import annotations

import re

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import (QAction, QColor, QFont, QFontMetricsF, QKeyEvent,
                           QSyntaxHighlighter, QTextBlockFormat, QTextCharFormat,
                           QTextCursor, QTextDocument, QTextFormat, QTextFrameFormat)
from PySide6.QtWidgets import QMenu, QPlainTextEdit, QTextEdit

from .spell import SpellHighlighter, add_spell_menu, misspelt_ranges, squiggle
from .model import (ACTION, BEAT, CATEGORIES, CHARACTER, DIALOGUE, ELEMENTS,
                    ENTER_EMPTY, ENTER_NEXT, HEADING, HEADING_RE, PAREN, SHOT,
                    TAB_EMPTY, TAB_NEXT, TRANSITION, UPPERCASE_ELEMENTS, ScriptData, new_id)

SCENE_ID = QTextFormat.UserProperty + 1
ELEMENT = QTextFormat.UserProperty + 2   # stored in the block format so undo/redo restores it
SCRIPT_FONTS = ["Courier Prime", "Courier New", "Courier", "Liberation Mono", "DejaVu Sans Mono"]

# indents in inches from the left text margin (1.5" page margin), and right indents
LAYOUT = {
    HEADING:    (0.0, 0.0),
    ACTION:     (0.0, 0.0),
    CHARACTER:  (2.2, 0.0),
    PAREN:      (1.6, 2.0),
    DIALOGUE:   (1.0, 1.5),
    TRANSITION: (0.0, 0.0),
    SHOT:       (0.0, 0.0),
    BEAT:       (0.0, 0.0),
}
SPACE_BEFORE = {HEADING: 2, ACTION: 1, CHARACTER: 1, TRANSITION: 1, SHOT: 1,
                PAREN: 0, DIALOGUE: 0, BEAT: 2}


def script_font(pt: float) -> QFont:
    f = QFont()
    f.setFamilies(SCRIPT_FONTS)
    f.setPointSizeF(pt)
    f.setStyleHint(QFont.Monospace)
    return f


def block_formats(element: int, inch: float, line_h: float, first=False, pt: float = 12.0):
    """(QTextBlockFormat, QTextCharFormat) for an element. Used by both the
    editor and the PDF exporter so screen and print match."""
    left, right = LAYOUT[element]
    bf = QTextBlockFormat()
    bf.setLeftMargin(left * inch)
    bf.setRightMargin(right * inch)
    bf.setTopMargin(0 if first else SPACE_BEFORE[element] * line_h)
    bf.setBottomMargin(0)
    bf.setAlignment(Qt.AlignRight if element == TRANSITION else Qt.AlignLeft)
    bf.setProperty(ELEMENT, element)
    if element == CHARACTER:
        bf.setPageBreakPolicy(QTextFormat.PageBreak_Auto)
    cf = QTextCharFormat()
    cf.setFontFamilies(SCRIPT_FONTS)
    cf.setFontPointSize(pt)
    cf.setFontCapitalization(QFont.AllUppercase if element in UPPERCASE_ELEMENTS else QFont.MixedCase)
    cf.setFontWeight(QFont.Bold if element == BEAT else QFont.Normal)
    if element == BEAT:
        cf.setForeground(QColor("#8a1c22"))
        bf.setBackground(QColor("#fbe9ea"))
    else:
        cf.setForeground(QColor("#111111"))
    return bf, cf


class ScriptEdit(QTextEdit):
    """A paginated-ish screenplay page with Celtx-style element flow."""
    elementChanged = Signal(int)
    sceneChanged = Signal(object)       # scene id or None
    scenesUpdated = Signal()
    tagRequested = Signal(str, str)     # category, selected text
    modified = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptRichText(False)
        self.setTabChangesFocus(False)
        self.setObjectName("ScriptPage")
        self.scene_data: dict = {}      # sid -> {"synopsis", "items"}
        self.title: dict = {}
        self.zoom = 1.0
        self._cur_sid = None
        self._cur_el = None
        self._apply_metrics()
        self.document().setUndoRedoEnabled(True)
        self.spell = SpellHighlighter(self.document())
        self._refresh_timer = QTimer(self, singleShot=True, interval=400)
        self._refresh_timer.timeout.connect(self._refresh)
        self.document().contentsChanged.connect(self._on_change)
        self.cursorPositionChanged.connect(self._on_cursor)
        self.set_script(ScriptData())

    # ---------------------------------------------------------- metrics
    def _apply_metrics(self):
        pt = 12 * self.zoom
        self.font_ = script_font(pt)
        self.document().setDefaultFont(self.font_)
        fm = QFontMetricsF(self.font_)
        self.inch = fm.horizontalAdvance("0") * 10  # Courier: 10 chars per inch
        self.line_h = fm.lineSpacing()
        self._apply_frame()
        self.setFixedWidth(int(8.5 * self.inch) + self.verticalScrollBar().sizeHint().width() + 4)

    def _apply_frame(self):
        """Page margins live on the root frame (document.clear() resets them)."""
        self.document().setDocumentMargin(0)
        root = self.document().rootFrame()
        ff = root.frameFormat()
        ff.setLeftMargin(1.5 * self.inch)
        ff.setRightMargin(1.0 * self.inch)
        ff.setTopMargin(1.0 * self.inch)
        ff.setBottomMargin(1.0 * self.inch)
        root.setFrameFormat(ff)

    def changeEvent(self, e):
        super().changeEvent(e)
        if e.type() in (e.Type.FontChange, e.Type.StyleChange) and not getattr(self, "_in_metrics", False):
            self._in_metrics = True
            self.document().setDefaultFont(self.font_)
            self._in_metrics = False

    def set_zoom(self, z: float):
        self.zoom = z
        self._apply_metrics()
        self.reformat_all()

    # ---------------------------------------------------------- element helpers
    def element_of(self, block) -> int:
        v = block.blockFormat().property(ELEMENT)
        if isinstance(v, int) and 0 <= v < len(ELEMENTS):
            return v
        s = block.userState()
        return s if 0 <= s < len(ELEMENTS) else ACTION

    def apply_element(self, block, el: int, cursor: QTextCursor | None = None):
        bf, cf = block_formats(el, self.inch, self.line_h, first=block.blockNumber() == 0,
                               pt=12 * self.zoom)
        c = QTextCursor(block)
        # keep the scene id on headings
        sid = block.blockFormat().property(SCENE_ID)
        if el == HEADING:
            if not sid:
                sid = new_id()
            bf.setProperty(SCENE_ID, sid)
            self.scene_data.setdefault(sid, {"synopsis": "", "items": []})
        c.setBlockFormat(bf)
        c.movePosition(QTextCursor.StartOfBlock)
        c.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
        c.setCharFormat(cf)
        c.setBlockCharFormat(cf)
        block.setUserState(el)
        if cursor is not None and cursor.block() == block:
            self.setCurrentCharFormat(cf)

    def current_element(self) -> int:
        return self.element_of(self.textCursor().block())

    def set_current_element(self, el: int):
        c = self.textCursor()
        c.beginEditBlock()
        b = c.block()
        if el == PAREN and not b.text().strip():
            self.apply_element(b, el, c)
            c.insertText("()")
            c.movePosition(QTextCursor.Left)
            self.setTextCursor(c)
        else:
            self.apply_element(b, el, c)
        c.endEditBlock()
        self._on_cursor(force=True)

    def reformat_all(self):
        c = QTextCursor(self.document())
        c.beginEditBlock()
        b = self.document().firstBlock()
        while b.isValid():
            self.apply_element(b, self.element_of(b))
            b = b.next()
        c.endEditBlock()

    # ---------------------------------------------------------- load / save
    def set_script(self, sd: ScriptData):
        self.blockSignals(True)
        self.document().blockSignals(True)
        self.document().clear()
        self._apply_frame()
        self.scene_data = {k: {"synopsis": v.get("synopsis", ""), "items": list(v.get("items", []))}
                           for k, v in sd.scenes.items()}
        self.title = dict(sd.title)
        paras = sd.paras or [{"e": HEADING, "t": ""}]
        c = QTextCursor(self.document())
        for i, p in enumerate(paras):
            if i:
                c.insertBlock()
            c.insertText(p["t"])
            b = c.block()
            if p["e"] == HEADING and p.get("sid"):
                bf = b.blockFormat()
                bf.setProperty(SCENE_ID, p["sid"])
                QTextCursor(b).setBlockFormat(bf)
            self.apply_element(b, p["e"])
        self.document().blockSignals(False)
        self.blockSignals(False)
        self.document().clearUndoRedoStacks()
        self.document().setModified(False)
        self.moveCursor(QTextCursor.Start)
        self._refresh()
        self._on_cursor(force=True)

    def to_script(self) -> ScriptData:
        sd = ScriptData(title=dict(self.title))
        seen = set()
        b = self.document().firstBlock()
        while b.isValid():
            el = self.element_of(b)
            p = {"e": el, "t": b.text()}
            if el == HEADING:
                sid = b.blockFormat().property(SCENE_ID) or new_id()
                if sid in seen:  # duplicated by copy/paste: give it its own id
                    old = sid
                    sid = new_id()
                    self.scene_data[sid] = {"synopsis": "", "items": []}
                    _ = old
                seen.add(sid)
                p["sid"] = sid
                sd.scenes[sid] = self.scene_data.setdefault(sid, {"synopsis": "", "items": []})
            sd.paras.append(p)
            b = b.next()
        # drop a lone empty heading in an otherwise empty script
        if len(sd.paras) == 1 and not sd.paras[0]["t"].strip():
            sd.paras, sd.scenes = [], {}
        return sd

    # ---------------------------------------------------------- scenes
    def scene_blocks(self):
        """[(number, heading text, sid, block)]"""
        out, n = [], 0
        b = self.document().firstBlock()
        while b.isValid():
            if self.element_of(b) == HEADING:
                n += 1
                sid = b.blockFormat().property(SCENE_ID)
                out.append((n, b.text().upper() or "(untitled scene)", sid, b))
            b = b.next()
        return out

    def beat_blocks(self):
        out = []
        b = self.document().firstBlock()
        while b.isValid():
            if self.element_of(b) == BEAT:
                out.append((b.text(), b))
            b = b.next()
        return out

    def current_scene_id(self):
        b = self.textCursor().block()
        while b.isValid():
            if self.element_of(b) == HEADING:
                return b.blockFormat().property(SCENE_ID)
            b = b.previous()
        return None

    def current_beat(self):
        b = self.textCursor().block()
        while b.isValid():
            if self.element_of(b) == BEAT:
                return b.text()
            b = b.previous()
        return None

    def current_para_index(self):
        return self.textCursor().blockNumber()

    def goto_block(self, block):
        c = QTextCursor(block)
        c.movePosition(QTextCursor.EndOfBlock)
        self.setTextCursor(c)
        self.ensureCursorVisible()
        self.setFocus()

    def insert_paras(self, paras):
        c = self.textCursor()
        c.beginEditBlock()
        if c.block().text().strip():
            c.movePosition(QTextCursor.EndOfBlock)
            c.insertBlock()
        for i, p in enumerate(paras):
            if i:
                c.insertBlock()
            c.insertText(p["t"])
            self.apply_element(c.block(), p["e"])
        c.endEditBlock()
        self.setTextCursor(c)

    # ---------------------------------------------------------- moving scenes
    def chunks(self):
        """Split the script into movable pieces. A new piece starts at every
        Scene Heading and every Beat marker; anything before the first one is
        a fixed preamble. Returns (preamble_paras, [chunk dicts])."""
        sd = self.to_script()
        pre, out = [], []
        for p in sd.paras:
            if p["e"] in (HEADING, BEAT):
                out.append({"kind": "beat" if p["e"] == BEAT else "scene",
                            "title": p["t"].upper(), "sid": p.get("sid"), "paras": [p]})
            elif out:
                out[-1]["paras"].append(p)
            else:
                pre.append(p)
        return pre, out

    def reorder_chunks(self, order: list[int]):
        """Rebuild the script with chunks in a new order, as ONE undoable edit."""
        pre, chunks = self.chunks()
        if sorted(order) != list(range(len(chunks))) or order == list(range(len(chunks))):
            return False
        paras = pre + [p for i in order for p in chunks[i]["paras"]]
        here_sid = self.current_scene_id()
        c = QTextCursor(self.document())
        c.beginEditBlock()
        c.select(QTextCursor.Document)
        c.removeSelectedText()
        for i, p in enumerate(paras):
            if i:
                c.insertBlock()
            c.insertText(p["t"])
            b = c.block()
            if p["e"] == HEADING and p.get("sid"):
                bf = b.blockFormat()
                bf.setProperty(SCENE_ID, p["sid"])
                c.setBlockFormat(bf)
            self.apply_element(b, p["e"])
        c.endEditBlock()
        # put the cursor back on the scene you were in
        for _n, _t, sid, b in self.scene_blocks():
            if sid == here_sid:
                self.goto_block(b)
                break
        self._refresh()
        return True

    def move_chunk(self, src: int, dst: int):
        """Move chunk `src` so it sits before chunk `dst` (dst == len → end)."""
        _, chunks = self.chunks()
        order = list(range(len(chunks)))
        if not (0 <= src < len(order)) or src == dst:
            return False
        order.pop(src)
        dst = dst - 1 if dst > src else dst
        order.insert(max(0, min(dst, len(order))), src)
        return self.reorder_chunks(order)

    def move_current_scene(self, delta: int):
        """Ctrl+Shift+Up/Down: swap the scene under the cursor with its neighbour."""
        _, chunks = self.chunks()
        sid = self.current_scene_id()
        idx = next((i for i, ch in enumerate(chunks) if ch["kind"] == "scene" and ch["sid"] == sid), None)
        if idx is None:
            return
        j = idx + delta
        if 0 <= j < len(chunks):
            self.move_chunk(idx, j if delta < 0 else j + 1)

    # ---------------------------------------------------------- events
    def _on_change(self):
        self.modified.emit()
        self._refresh_timer.start()

    def _refresh(self):
        # fix any blocks with no element (e.g. pasted text) and heading ids
        b = self.document().firstBlock()
        fix = []
        while b.isValid():
            if not b.blockFormat().hasProperty(ELEMENT):
                fix.append(b)
            elif self.element_of(b) == HEADING and not b.blockFormat().property(SCENE_ID):
                fix.append(b)
            b = b.next()
        if fix:
            self.document().blockSignals(True)
            for b in fix:
                self.apply_element(b, self.element_of(b))
            self.document().blockSignals(False)
        self.scenesUpdated.emit()

    def _on_cursor(self, force=False):
        el = self.current_element()
        if force or el != self._cur_el:
            self._cur_el = el
            self.elementChanged.emit(el)
        sid = self.current_scene_id()
        if force or sid != self._cur_sid:
            self._cur_sid = sid
            self.sceneChanged.emit(sid)

    def flow_hint(self) -> str:
        el = self.current_element()
        b = self.textCursor().block()
        empty = not b.text().strip()
        enter = ENTER_EMPTY[el] if empty and el in ENTER_EMPTY else ENTER_NEXT[el]
        tab = f"Tab: {ELEMENTS[TAB_EMPTY[el]]}" if empty else f"Tab: new {ELEMENTS[TAB_NEXT[el]]}"
        if el == PAREN and not empty:
            tab = "Tab: new Dialogue"
        return f"{tab}   Enter: {ELEMENTS[enter]}"

    def keyPressEvent(self, e: QKeyEvent):
        key, mods = e.key(), e.modifiers()
        c = self.textCursor()
        b = c.block()
        el = self.element_of(b)
        if key in (Qt.Key_Return, Qt.Key_Enter) and not (mods & Qt.ShiftModifier):
            c.beginEditBlock()
            if not b.text().strip() and el in ENTER_EMPTY:
                self.apply_element(b, ENTER_EMPTY[el], c)
            else:
                at_end = c.atBlockEnd()
                nxt = ENTER_NEXT[el] if at_end else el
                c.insertBlock()
                self.apply_element(c.block(), nxt, c)
                if nxt == PAREN:
                    c.insertText("()")
                    c.movePosition(QTextCursor.Left)
                self.setTextCursor(c)
            c.endEditBlock()
            self._on_cursor(force=True)
            return
        if key == Qt.Key_Tab:
            text = b.text().strip()
            if el == PAREN and text.strip("() "):
                # finished parenthetical: Tab jumps out to a new Dialogue line
                c.beginEditBlock()
                c.movePosition(QTextCursor.EndOfBlock)
                c.insertBlock()
                self.apply_element(c.block(), DIALOGUE, c)
                c.endEditBlock()
                self.setTextCursor(c)
                self._on_cursor(force=True)
            elif text and el != PAREN and c.atBlockEnd():
                # finished line: Tab starts the next element on a new line
                c.beginEditBlock()
                c.insertBlock()
                nxt = TAB_NEXT[el]
                self.apply_element(c.block(), nxt, c)
                if nxt == PAREN:
                    c.insertText("()")
                    c.movePosition(QTextCursor.Left)
                c.endEditBlock()
                self.setTextCursor(c)
                self._on_cursor(force=True)
            else:
                # empty line (or mid-line): change what this line is
                if el == PAREN:
                    c.beginEditBlock()
                    cc = QTextCursor(b)
                    cc.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
                    cc.removeSelectedText()
                    c.endEditBlock()
                self.set_current_element(TAB_EMPTY[el] if not text or el == PAREN else TAB_NEXT[el])
            return
        if key == Qt.Key_Backtab:
            self.set_current_element((el - 1) % 7)
            return
        super().keyPressEvent(e)
        # auto-detect a scene heading typed into an action line
        if el == ACTION and e.text() in (".", " ") and HEADING_RE.match(b.text() + " "):
            self.set_current_element(HEADING)
        elif el == ACTION and e.text() == ":" and re.fullmatch(r"[A-Za-z .']+ TO:", b.text().strip(), re.I):
            self.set_current_element(TRANSITION)

    def contextMenuEvent(self, e):
        menu = self.createStandardContextMenu()
        if self.spell.enabled:
            add_spell_menu(menu, self, self.cursorForPosition(e.pos()), self.spell.rehighlight)
        sel = self.textCursor().selectedText().strip()
        menu.addSeparator()
        el_menu = menu.addMenu("Element")
        for i, name in enumerate(ELEMENTS):
            a = el_menu.addAction(name)
            a.triggered.connect(lambda _=False, i=i: self.set_current_element(i))
        if sel:
            label = sel[:28].replace("&", "&&")
            tag = menu.addMenu(f"Tag “{label}{'…' if len(sel) > 28 else ''}” as")
            for cat in CATEGORIES:
                a = tag.addAction(cat.replace("&", "&&"))
                a.triggered.connect(lambda _=False, cat=cat, s=sel: self.tagRequested.emit(cat, s))
        menu.exec(e.globalPos())

    def insertFromMimeData(self, source):
        # paste as plain text, one Action per line (Fountain-looking text is parsed)
        if source.hasText():
            from .model import parse_fountain
            text = source.text()
            if "\n" in text.strip():
                sd = parse_fountain(text)
                for sid, data in sd.scenes.items():
                    self.scene_data[sid] = data
                c = self.textCursor()
                c.beginEditBlock()
                for i, p in enumerate(sd.paras):
                    if i or c.block().text().strip():
                        c.insertBlock()
                    c.insertText(p["t"])
                    if p["e"] == HEADING:
                        bf = c.block().blockFormat()
                        bf.setProperty(SCENE_ID, p["sid"])
                        c.setBlockFormat(bf)
                    self.apply_element(c.block(), p["e"])
                c.endEditBlock()
                self.setTextCursor(c)
                return
            self.textCursor().insertText(text)
            return
        super().insertFromMimeData(source)


# ===================================================================== NOVEL
class MarkdownHeadings(QSyntaxHighlighter):
    enabled = True  # spellcheck on/off

    def set_enabled(self, on):
        self.enabled = on
        self.rehighlight()

    def highlightBlock(self, text):
        if self.enabled:
            sq = squiggle()
            for start, length in misspelt_ranges(text):
                self.setFormat(start, length, sq)
        if text.startswith("# "):
            f = QTextCharFormat()
            f.setFontWeight(QFont.Bold)
            f.setForeground(QColor("#b3121a"))
            f.setFontPointSize(self.document().defaultFont().pointSizeF() * 1.4)
            self.setFormat(0, len(text), f)
        elif text.startswith("## "):
            f = QTextCharFormat()
            f.setFontWeight(QFont.Bold)
            self.setFormat(0, len(text), f)
        for m in re.finditer(r"\*([^*]+)\*", text):
            f = QTextCharFormat()
            f.setFontItalic(True)
            self.setFormat(m.start(), m.end() - m.start(), f)


class NovelEdit(QPlainTextEdit):
    modified = Signal()
    chaptersUpdated = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("NovelPage")
        self.title: dict = {}
        f = QFont()
        f.setFamilies(["Georgia", "Libre Baskerville", "DejaVu Serif", "Times New Roman", "serif"])
        f.setPointSize(13)
        self.setFont(f)
        self.document().setDefaultFont(f)
        fm = QFontMetricsF(f)
        self.setFixedWidth(int(fm.horizontalAdvance("x") * 75 + 120))
        self.setViewportMargins(48, 48, 48, 48)
        self._hl = MarkdownHeadings(self.document())
        self.spell = self._hl
        self.setPlaceholderText("# Chapter One\n\nStart writing. Lines beginning with “# ” become chapters.")
        self._t = QTimer(self, singleShot=True, interval=500)
        self._t.timeout.connect(self.chaptersUpdated.emit)
        self.document().contentsChanged.connect(self._changed)

    def _changed(self):
        self.modified.emit()
        self._t.start()

    def chapters(self):
        out = []
        b = self.document().firstBlock()
        while b.isValid():
            if b.text().startswith("# "):
                out.append((b.text()[2:].strip(), b))
            b = b.next()
        return out

    def goto_block(self, block):
        c = QTextCursor(block)
        self.setTextCursor(c)
        self.centerCursor()
        self.setFocus()

    def word_count(self):
        return len(self.toPlainText().split())

    def contextMenuEvent(self, e):
        menu = self.createStandardContextMenu()
        if self.spell.enabled:
            add_spell_menu(menu, self, self.cursorForPosition(e.pos()), self.spell.rehighlight)
        menu.exec(e.globalPos())
