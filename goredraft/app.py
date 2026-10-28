"""GORE DRAFT main window."""
from __future__ import annotations

import sys
import time
from pathlib import Path

from PySide6.QtCore import QSettings, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QFontDatabase, QIcon, QKeySequence, QPixmap
from PySide6.QtWidgets import (QApplication, QButtonGroup, QComboBox, QDialog,
                               QDialogButtonBox, QDockWidget, QFileDialog, QFormLayout,
                               QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMainWindow, QMessageBox, QPlainTextEdit,
                               QPushButton, QRadioButton, QScrollArea, QSpinBox, QSplashScreen,
                               QStackedWidget, QTabWidget, QToolBar, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget)

from . import model, reports
from .editor import NovelEdit, ScriptEdit
from .model import (APP_NAME, APP_VERSION, ELEMENTS, PROJECT_EXT, Doc, Project,
                    ScriptData, beat_sheet_paras)
from .panels import (BreakdownPanel, IndexCardsView, ReportsView, TitlePageView,
                     section)
from .theme import QSS
from . import support

HERE = Path(__file__).parent
TAB_SCRIPT, TAB_TITLE, TAB_CARDS, TAB_SCRATCH, TAB_REPORTS = range(5)


class NewDocDialog(QDialog):
    def __init__(self, parent, kind="screenplay"):
        super().__init__(parent)
        self.setWindowTitle("Add to project")
        v = QVBoxLayout(self)
        v.addWidget(section("What are you writing?"))
        self.kind_screen = QRadioButton("Screenplay")
        self.kind_novel = QRadioButton("Novel / prose")
        (self.kind_screen if kind == "screenplay" else self.kind_novel).setChecked(True)
        h = QHBoxLayout()
        h.addWidget(self.kind_screen)
        h.addWidget(self.kind_novel)
        v.addLayout(h)
        f = QFormLayout()
        self.name = QLineEdit("Untitled")
        self.name.selectAll()
        f.addRow("Name", self.name)
        self.template = QComboBox()
        self.template.addItems(["Blank page", "Save the Cat beat sheet (pre-filled guide)"])
        f.addRow("Start from", self.template)
        self.target = QSpinBox()
        self.target.setRange(5, 200)
        self.target.setValue(100)
        self.target.setSuffix(" pages")
        f.addRow("Target length", self.target)
        v.addLayout(f)
        self.kind_novel.toggled.connect(lambda on: (self.template.setEnabled(not on), self.target.setEnabled(not on)))
        self.kind_novel.toggled.emit(self.kind_novel.isChecked())
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def values(self):
        return ("screenplay" if self.kind_screen.isChecked() else "novel",
                self.name.text().strip() or "Untitled",
                self.template.currentIndex() == 1, self.target.value())


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("Splatter VHS", "GORE DRAFT")
        reports.MINUTES_PER_PAGE = float(self.settings.value("min_per_page", 1.0))
        self.project = Project()
        self.editors: dict[str, QWidget] = {}
        self.current: Doc | None = None
        self.dirty = False
        self._build_ui()
        self._build_actions()
        self.resize(1500, 950)
        g = self.settings.value("geometry")
        if g:
            self.restoreGeometry(g)
        self.autosave = QTimer(self, interval=180_000)
        self.autosave.timeout.connect(self._backup)
        self.autosave.start()
        self.new_project(ask=False)

    # =============================================================== UI
    def _build_ui(self):
        self.setWindowIcon(QIcon(str(HERE / "icon.png")))
        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.South)
        self.tabs.setDocumentMode(True)
        self.setCentralWidget(self.tabs)

        # script tab: a desk with the page centred on it
        self.page_stack = QStackedWidget()
        desk = QWidget()
        desk.setObjectName("DeskInner")
        dl = QHBoxLayout(desk)
        dl.setContentsMargins(0, 16, 0, 0)
        dl.addStretch(1)
        dl.addWidget(self.page_stack)
        dl.addStretch(1)
        self.tabs.addTab(desk, "SCRIPT")

        self.title_view = TitlePageView()
        self.title_view.changed.connect(self.mark_dirty)
        self.tabs.addTab(self.title_view, "TITLE PAGE")

        self.cards = IndexCardsView()
        self.cards.changed.connect(self.mark_dirty)
        self.cards.goto.connect(self._goto_from_cards)
        self.cards.reordered.connect(lambda: (self.mark_dirty(), self._refresh_outline()))
        self.tabs.addTab(self.cards, "INDEX CARDS")

        self.scratch = QPlainTextEdit()
        self.scratch.setObjectName("Scratch")
        self.scratch.setPlaceholderText("Scratchpad — ideas, gag notes, research, shopping lists. Saved with the document.")
        self.scratch.textChanged.connect(self.mark_dirty)
        self.tabs.addTab(self.scratch, "SCRATCHPAD")

        self.reports = ReportsView()
        self.reports.source = self._report_source
        self.reports.page_size = self.page_size
        self.tabs.addTab(self.reports, "REPORTS")
        self.tabs.currentChanged.connect(self._tab_changed)

        # left dock: library + scenes
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(6, 6, 6, 6)
        lv.addWidget(section("Project Library"))
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.itemSelectionChanged.connect(self._tree_selected)
        self.tree.itemDoubleClicked.connect(lambda *_: self.rename_doc())
        lv.addWidget(self.tree, 2)
        hb = QHBoxLayout()
        for label, tip, fn in (("+ Add", "Add a screenplay or novel", self.add_doc),
                               ("Rename", "Rename document", self.rename_doc),
                               ("Delete", "Remove document from project", self.delete_doc)):
            b = QPushButton(label)
            b.setToolTip(tip)
            b.clicked.connect(fn)
            hb.addWidget(b)
        lv.addLayout(hb)
        self.outline_label = section("Scenes")
        lv.addWidget(self.outline_label)
        self.outline = QListWidget()
        self.outline.setToolTip("Click to jump · drag to reorder scenes and beats")
        self.outline.setDragDropMode(QListWidget.InternalMove)
        self.outline.setDefaultDropAction(Qt.MoveAction)
        self.outline.itemClicked.connect(self._outline_clicked)
        self.outline.model().rowsMoved.connect(lambda *_: QTimer.singleShot(0, self._outline_reordered))
        lv.addWidget(self.outline, 3)
        self.left_dock = QDockWidget("Library", self)
        self.left_dock.setObjectName("LeftDock")
        self.left_dock.setWidget(left)
        self.left_dock.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetClosable)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.left_dock)

        # right dock: beat guide + breakdown
        self.breakdown = BreakdownPanel()
        self.breakdown.changed.connect(self.mark_dirty)
        self.breakdown.beat.targetChanged.connect(self._target_changed)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.breakdown)
        self.right_dock = QDockWidget("Breakdown", self)
        self.right_dock.setObjectName("RightDock")
        self.right_dock.setWidget(scroll)
        self.right_dock.setMinimumWidth(340)
        self.right_dock.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetClosable)
        self.addDockWidget(Qt.RightDockWidgetArea, self.right_dock)

        # status bar
        self.hint = QLabel("")
        self.stats = QLabel("")
        self.statusBar().addWidget(self.hint, 1)
        self.statusBar().addPermanentWidget(self.stats)

        self._beat_timer = QTimer(self, singleShot=True, interval=350)
        self._beat_timer.timeout.connect(self._update_beat_and_stats)

    def _build_actions(self):
        A = lambda text, fn, key=None, tip=None: self._act(text, fn, key, tip)
        self.a_new = A("&New Project", lambda: self.new_project(), QKeySequence.New)
        self.a_open = A("&Open Project…", self.open_project, QKeySequence.Open)
        self.a_save = A("&Save", self.save, QKeySequence.Save)
        self.a_saveas = A("Save &As…", lambda: self.save(as_=True), QKeySequence.SaveAs)
        self.a_import = A("&Import Fountain / Final Draft…", self.import_script)
        self.a_celtx = A("Import Old &Celtx (.celtx)…", self.import_celtx)
        self.a_exp_pdf = A("Export &PDF…", self.export_pdf, "Ctrl+P")
        self.a_exp_fountain = A("Export &Fountain…", lambda: self.export_text("fountain"))
        self.a_exp_fdx = A("Export Final &Draft (.fdx)…", lambda: self.export_text("fdx"))
        self.a_exp_md = A("Export &Markdown…", lambda: self.export_text("md"))
        self.a_quit = A("&Quit", self.close, QKeySequence.Quit)
        self.a_add = A("Add Document…", self.add_doc, "Ctrl+Shift+N")
        self.a_beats = A("Insert Save the Cat Beats", self.insert_beats)
        self.a_next_beat = A("Next Beat", lambda: self.jump_beat(1), "Ctrl+]")
        self.a_prev_beat = A("Previous Beat", lambda: self.jump_beat(-1), "Ctrl+[")
        self.a_scene_up = A("Move Scene Up", lambda: self._move_scene(-1), "Ctrl+Shift+Up")
        self.a_scene_down = A("Move Scene Down", lambda: self._move_scene(1), "Ctrl+Shift+Down")
        self.a_spell = QAction("Check Spelling", self, checkable=True)
        self.a_spell.setShortcut("F7")
        self.a_spell.setChecked(self.settings.value("spell", "true") in (True, "true"))
        self.a_spell.toggled.connect(self._toggle_spell)
        self.a_mpp = A("Minutes per Page…", self._set_minutes_per_page)

        mb = self.menuBar()
        m = mb.addMenu("&File")
        for a in (self.a_new, self.a_open, self.a_save, self.a_saveas, None, self.a_import,
                  self.a_celtx, None, self.a_exp_pdf, self.a_exp_fountain, self.a_exp_fdx,
                  self.a_exp_md):
            m.addSeparator() if a is None else m.addAction(a)
        ps = m.addMenu("PDF Page Size")
        grp = QActionGroup(self)
        for size in ("A4", "Letter"):
            a = ps.addAction(size)
            a.setCheckable(True)
            a.setChecked(self.page_size() == size)
            a.triggered.connect(lambda _=False, s=size: self.settings.setValue("page", s))
            grp.addAction(a)
        m.addSeparator()
        m.addAction(self.a_quit)

        e = mb.addMenu("&Edit")
        for text, key, slot in (("Undo", QKeySequence.Undo, "undo"), ("Redo", QKeySequence.Redo, "redo"),
                                (None, None, None), ("Cut", QKeySequence.Cut, "cut"),
                                ("Copy", QKeySequence.Copy, "copy"), ("Paste", QKeySequence.Paste, "paste"),
                                ("Select All", QKeySequence.SelectAll, "selectAll")):
            if text is None:
                e.addSeparator()
                continue
            a = e.addAction(text)
            a.setShortcut(key)
            a.triggered.connect(lambda _=False, s=slot: self._editor_call(s))

        s = mb.addMenu("&Script")
        self.el_actions = []
        for i, name in enumerate(ELEMENTS):
            a = s.addAction(name)
            a.setShortcut(f"Ctrl+{i + 1}")
            a.triggered.connect(lambda _=False, i=i: self._set_element(i))
            self.el_actions.append(a)
        s.addSeparator()
        for a in (self.a_scene_up, self.a_scene_down, None, self.a_beats, self.a_next_beat, self.a_prev_beat):
            if a is None:
                s.addSeparator()
                continue
            s.addAction(a)

        v = mb.addMenu("&View")
        v.addAction(self.left_dock.toggleViewAction())
        v.addAction(self.right_dock.toggleViewAction())
        v.addSeparator()
        v.addAction(self.a_spell)
        v.addAction(self.a_mpp)
        zm = v.addMenu("Zoom")
        for z in (75, 100, 125, 150, 175, 200):
            a = zm.addAction(f"{z}%")
            a.triggered.connect(lambda _=False, z=z: self.set_zoom(z))

        h = mb.addMenu("&Help")
        h.addAction(A("Keyboard Flow", self.show_keys))
        h.addAction(A("Report a Problem…", lambda: support.report_problem(self)))
        h.addAction(A("Open Log Folder", support.open_log_folder))
        h.addSeparator()
        h.addAction(A("About GORE DRAFT", self.about))

        tb = QToolBar("Main")
        tb.setObjectName("MainToolbar")
        tb.setMovable(False)
        tb.setIconSize(QSize(16, 16))
        self.addToolBar(tb)
        brand = QLabel("  GORE<span style='color:#d11a22'>DRAFT</span>  ")
        brand.setStyleSheet("font-weight:900; font-size:14pt; letter-spacing:3px; background:transparent;")
        brand.setTextFormat(Qt.RichText)
        tb.addWidget(brand)
        for a in (self.a_new, self.a_open, self.a_save):
            tb.addAction(a)
        tb.addSeparator()
        tb.addAction(self.a_add)
        tb.addSeparator()
        tb.addWidget(QLabel(" Element "))
        self.el_combo = QComboBox()
        self.el_combo.addItems(ELEMENTS)
        self.el_combo.setMinimumWidth(150)
        self.el_combo.activated.connect(self._set_element)
        tb.addWidget(self.el_combo)
        tb.addSeparator()
        self.zoom_combo = QComboBox()
        self.zoom_combo.addItems([f"{z}%" for z in (75, 100, 125, 150, 175, 200)])
        self.zoom_combo.setCurrentText("100%")
        self.zoom_combo.activated.connect(lambda _: self.set_zoom(int(self.zoom_combo.currentText()[:-1])))
        tb.addWidget(self.zoom_combo)
        tb.addSeparator()
        tb.addAction(self.a_exp_pdf)

    def _act(self, text, fn, key=None, tip=None):
        a = QAction(text, self)
        if key:
            a.setShortcut(key)
        if tip:
            a.setToolTip(tip)
        a.triggered.connect(lambda _=False: fn())
        return a

    # =============================================================== helpers
    def page_size(self):
        return self.settings.value("page", "A4")

    def ed(self):
        return self.editors.get(self.current.id) if self.current else None

    def script_ed(self) -> ScriptEdit | None:
        e = self.ed()
        return e if isinstance(e, ScriptEdit) else None

    def _editor_call(self, slot):
        w = QApplication.focusWidget()
        if w is not None and hasattr(w, slot):
            getattr(w, slot)()

    def mark_dirty(self):
        self.dirty = True
        self._update_title()

    def _update_title(self):
        name = self.project.path.stem if self.project.path else "Untitled project"
        beta = " BETA" if support.BETA else ""
        self.setWindowTitle(f"{'• ' if self.dirty else ''}{name} — {APP_NAME} {APP_VERSION}{beta}")

    # =============================================================== project
    def confirm_discard(self) -> bool:
        if not self.dirty:
            return True
        r = QMessageBox.question(self, "Unsaved changes", "Save changes to this project first?",
                                 QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if r == QMessageBox.Save:
            return self.save()
        return r == QMessageBox.Discard

    def _clear_editors(self):
        for w in self.editors.values():
            self.page_stack.removeWidget(w)
            w.deleteLater()
        self.editors.clear()
        self.current = None

    def new_project(self, ask=True):
        if ask and not self.confirm_discard():
            return
        self._clear_editors()
        self.project = Project("Untitled")
        d = self.project.add_doc("Screenplay", "screenplay")
        self._load_project_ui(select=d)
        self.dirty = False
        self._update_title()

    def open_project(self, path=None):
        if not self.confirm_discard():
            return
        if not path:
            start = self.settings.value("lastdir", str(Path.home()))
            path, _ = QFileDialog.getOpenFileName(self, "Open GORE DRAFT project", start,
                                                  f"GORE DRAFT project (*{PROJECT_EXT})")
            if not path:
                return
        try:
            p = Project.load(path)
        except Exception as ex:  # noqa: BLE001
            QMessageBox.critical(self, "Couldn't open", f"{path}\n\n{ex}")
            return
        self._clear_editors()
        self.project = p
        if not p.docs:
            p.add_doc("Screenplay", "screenplay")
        self._load_project_ui(select=p.docs[0])
        self.settings.setValue("lastdir", str(Path(path).parent.parent))
        self.settings.setValue("last", str(path))
        self.dirty = False
        self._update_title()

    def _flush(self, d: Doc | None = None):
        """Copy editor contents back into the Doc objects."""
        docs = [d] if d else self.project.docs
        for doc in docs:
            if doc is None:
                continue
            w = self.editors.get(doc.id)
            if isinstance(w, ScriptEdit):
                doc.script = w.to_script()
            elif isinstance(w, NovelEdit):
                doc.text = w.toPlainText()
        if self.current:
            self.current.scratch = self.scratch.toPlainText()

    def save(self, as_=False) -> bool:
        if as_ or not self.project.path:
            start = self.settings.value("lastdir", str(Path.home()))
            path, _ = QFileDialog.getSaveFileName(
                self, "Save project — a folder with this name will be created",
                str(Path(start) / "My Film"), f"GORE DRAFT project (*{PROJECT_EXT})")
            if not path:
                return False
            p = Path(path)
            stem = p.stem if p.suffix == PROJECT_EXT else p.name
            folder = p.parent / stem
            if p.parent.name == stem:  # user picked inside an existing project folder
                folder = p.parent
            self.project.path = folder / f"{stem}{PROJECT_EXT}"
            self.project.name = stem
            self.settings.setValue("lastdir", str(folder.parent))
        self._flush()
        try:
            self.project.save()
        except Exception as ex:  # noqa: BLE001
            QMessageBox.critical(self, "Save failed", str(ex))
            return False
        self.settings.setValue("last", str(self.project.path))
        self.dirty = False
        self._update_title()
        self.statusBar().showMessage(f"Saved to {self.project.folder}", 4000)
        support.log.info("saved %d docs", len(self.project.docs))
        self._rebuild_tree()
        return True

    def _backup(self):
        if not (self.dirty and self.project.folder):
            return
        self._flush()
        bdir = self.project.folder / "backups"
        bdir.mkdir(exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M")
        for d in self.project.docs:
            name = model.safe_name(d.name)
            text = model.write_fountain(d.script) if d.kind == "screenplay" else d.text
            (bdir / f"{name}-autosave{d.ext}").write_text(text, encoding="utf-8")
        self.statusBar().showMessage(f"Backup written {stamp}", 3000)

    # =============================================================== documents
    def _make_editor(self, d: Doc):
        if d.kind == "screenplay":
            w = ScriptEdit()
            w.set_script(d.script or ScriptData())
            w.modified.connect(self.mark_dirty)
            w.elementChanged.connect(self._element_changed)
            w.sceneChanged.connect(self.breakdown.set_scene)
            w.scenesUpdated.connect(self._refresh_outline)
            w.cursorPositionChanged.connect(self._beat_timer.start)
            w.tagRequested.connect(lambda cat, text: self.breakdown.add_item(cat, text))
            w.selectionChanged.connect(self._beat_timer.start)
            z = int(self.zoom_combo.currentText()[:-1]) / 100 if hasattr(self, "zoom_combo") else 1
            if z != 1:
                w.set_zoom(z)
        else:
            w = NovelEdit()
            w.title = d.title
            w.setPlainText(d.text)
            w.document().setModified(False)
            w.modified.connect(self.mark_dirty)
            w.chaptersUpdated.connect(self._refresh_outline)
            w.selectionChanged.connect(self._beat_timer.start)
            w.cursorPositionChanged.connect(self._beat_timer.start)
        if hasattr(self, "a_spell") and not self.a_spell.isChecked():
            w.spell.set_enabled(False)
        self.editors[d.id] = w
        self.page_stack.addWidget(w)
        return w

    def _load_project_ui(self, select: Doc):
        for d in self.project.docs:
            self._make_editor(d)
        self._rebuild_tree(select)
        self.switch_doc(select)

    def _rebuild_tree(self, select: Doc | None = None):
        select = select or self.current
        self.tree.blockSignals(True)
        self.tree.clear()
        root = QTreeWidgetItem([self.project.name.upper()])
        f = root.font(0)
        f.setBold(True)
        root.setFont(0, f)
        self.tree.addTopLevelItem(root)
        for d in self.project.docs:
            icon = "🎬" if d.kind == "screenplay" else "📖"
            it = QTreeWidgetItem([f"{icon}  {d.name}"])
            it.setData(0, Qt.UserRole, d.id)
            root.addChild(it)
            if select and d.id == select.id:
                it.setSelected(True)
        root.setExpanded(True)
        self.tree.blockSignals(False)

    def _tree_selected(self):
        items = self.tree.selectedItems()
        if not items:
            return
        did = items[0].data(0, Qt.UserRole)
        d = next((x for x in self.project.docs if x.id == did), None)
        if d and d is not self.current:
            self.switch_doc(d)

    def switch_doc(self, d: Doc):
        if self.current:
            self.current.scratch = self.scratch.toPlainText()
        self.current = d
        w = self.editors[d.id]
        self.page_stack.setCurrentWidget(w)
        self.page_stack.setFixedWidth(w.width())
        is_script = isinstance(w, ScriptEdit)
        self.scratch.blockSignals(True)
        self.scratch.setPlainText(d.scratch)
        self.scratch.blockSignals(False)
        self.title_view.load(w.title if is_script else d.title)
        self.tabs.setTabEnabled(TAB_CARDS, is_script)
        self.el_combo.setEnabled(is_script)
        for a in self.el_actions + [self.a_beats, self.a_next_beat, self.a_prev_beat,
                                    self.a_scene_up, self.a_scene_down,
                                    self.a_exp_fdx, self.a_exp_fountain]:
            a.setEnabled(is_script)
        self.a_exp_md.setEnabled(not is_script)
        self.right_dock.setVisible(is_script)
        self.breakdown.set_editor(w if is_script else None)
        if is_script:
            try:
                self.breakdown.beat.target.blockSignals(True)
                self.breakdown.beat.target.setValue(int(w.title.get("target") or 100))
            except ValueError:
                pass
            finally:
                self.breakdown.beat.target.blockSignals(False)
        self.outline_label.setText("SCENES" if is_script else "CHAPTERS")
        self.reports.set_kind(d.kind)
        self._refresh_outline()
        self._update_beat_and_stats()
        if self.tabs.currentIndex() == TAB_CARDS and not is_script:
            self.tabs.setCurrentIndex(TAB_SCRIPT)
        self._tab_changed(self.tabs.currentIndex())
        w.setFocus()

    def add_doc(self):
        dlg = NewDocDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        kind, name, beats, target = dlg.values()
        d = self.project.add_doc(name, kind)
        if kind == "screenplay":
            d.script.title["target"] = str(target)
            if beats:
                d.script.paras = beat_sheet_paras(target)
        self._make_editor(d)
        self._rebuild_tree(d)
        self.switch_doc(d)
        self.mark_dirty()

    def rename_doc(self):
        if not self.current:
            return
        name, ok = QInputDialog.getText(self, "Rename", "Document name:", text=self.current.name)
        if ok and name.strip():
            self.current.name = name.strip()
            self._rebuild_tree()
            self.mark_dirty()

    def delete_doc(self):
        if not self.current or len(self.project.docs) <= 1:
            QMessageBox.information(self, "Can't delete", "A project needs at least one document.")
            return
        if QMessageBox.question(self, "Remove document",
                                f"Remove “{self.current.name}” from the project?\n\n"
                                "The file stays on disk until you save.") != QMessageBox.Yes:
            return
        d = self.current
        self.project.docs.remove(d)
        w = self.editors.pop(d.id)
        self.page_stack.removeWidget(w)
        w.deleteLater()
        self.current = None
        self._rebuild_tree(self.project.docs[0])
        self.switch_doc(self.project.docs[0])
        self.mark_dirty()

    # =============================================================== outline / status
    def _refresh_outline(self):
        w = self.ed()
        self.outline.blockSignals(True)
        self.outline.model().blockSignals(True)
        self.outline.clear()
        if isinstance(w, ScriptEdit):
            self.outline.setDragDropMode(QListWidget.InternalMove)
            beats = {b.blockNumber(): t for t, b in w.beat_blocks()}
            heads = {b.blockNumber(): (n, t, b) for n, t, _s, b in w.scene_blocks()}
            for ci, bn in enumerate(sorted(set(beats) | set(heads))):
                if bn in beats:
                    it = QListWidgetItem("◆ " + beats[bn].upper())
                    it.setForeground(Qt.red)
                    f = it.font()
                    f.setBold(True)
                    it.setFont(f)
                else:
                    n, t, b = heads[bn]
                    it = QListWidgetItem(f"  {n:>3}  {t}")
                it.setData(Qt.UserRole, bn)
                it.setData(Qt.UserRole + 1, ci)   # chunk index for drag-reorder
                self.outline.addItem(it)
            self.breakdown.refresh_characters()
            self._ignore_character_names(w)
        elif isinstance(w, NovelEdit):
            self.outline.setDragDropMode(QListWidget.NoDragDrop)
            for name, b in w.chapters():
                it = QListWidgetItem(name)
                it.setData(Qt.UserRole, b.blockNumber())
                self.outline.addItem(it)
        self.outline.model().blockSignals(False)
        self.outline.blockSignals(False)
        self._beat_timer.start()

    def _outline_reordered(self):
        w = self.script_ed()
        if not w:
            return
        order = [self.outline.item(i).data(Qt.UserRole + 1) for i in range(self.outline.count())]
        if None in order:
            return
        if w.reorder_chunks(order):
            self.mark_dirty()
            self.statusBar().showMessage("Scenes reordered · Ctrl+Z to undo", 4000)
        self._refresh_outline()

    def _move_scene(self, delta):
        w = self.script_ed()
        if w:
            w.move_current_scene(delta)
            self.mark_dirty()
            self._refresh_outline()

    def _ignore_character_names(self, w):
        from .spell import Speller
        sp = Speller.get()
        before = len(sp.ignore)
        b = w.document().firstBlock()
        while b.isValid():
            if w.element_of(b) == model.CHARACTER:
                for part in reports._clean_char(b.text()).split():
                    sp.ignore.add(part.lower())
            b = b.next()
        if len(sp.ignore) != before:
            sp._cache.clear()
            w.spell.rehighlight()

    def _toggle_spell(self, on):
        self.settings.setValue("spell", "true" if on else "false")
        for w in self.editors.values():
            w.spell.set_enabled(on)

    def _set_minutes_per_page(self):
        v, ok = QInputDialog.getDouble(
            self, "Minutes per page",
            "Screen minutes per script page.\n1.0 is the standard rule of thumb; FX-heavy horror often runs 1.2–1.5.",
            reports.MINUTES_PER_PAGE, 0.3, 3.0, 2)
        if ok:
            reports.MINUTES_PER_PAGE = v
            self.settings.setValue("min_per_page", v)
            self._update_beat_and_stats()

    def _outline_clicked(self, item):
        w = self.ed()
        if not w:
            return
        b = w.document().findBlockByNumber(item.data(Qt.UserRole))
        if b.isValid():
            self.tabs.setCurrentIndex(TAB_SCRIPT)
            w.goto_block(b)

    def _goto_from_cards(self, block):
        self.tabs.setCurrentIndex(TAB_SCRIPT)
        w = self.script_ed()
        if w and block.isValid():
            w.goto_block(block)

    def _element_changed(self, el):
        self.el_combo.setCurrentIndex(el)
        w = self.script_ed()
        if w:
            self.hint.setText(w.flow_hint())

    def _set_element(self, el):
        w = self.script_ed()
        if w:
            w.set_current_element(el)
            w.setFocus()

    def _update_beat_and_stats(self):
        w = self.ed()
        if isinstance(w, ScriptEdit):
            sd = w.to_script() if w.document().blockCount() < 20000 else ScriptData()
            target = self.breakdown.beat.target.value()
            page_now = reports.page_at(sd, w.current_para_index()) if sd.paras else 1
            self.breakdown.beat.update_for(w.current_beat(), page_now, target)
            pages = reports.estimate_pages(sd) if sd.paras else 0
            runtime = reports.fmt_runtime(pages * reports.MINUTES_PER_PAGE)
            sel = len(w.textCursor().selectedText().split())
            self.stats.setText(f"{f'{sel:,} selected · ' if sel else ''}{reports.word_count(sd):,} words · "
                               f"{len(w.scene_blocks())} scenes · ~{pages:.1f} / {target} pages · ≈ {runtime}")
            self.hint.setText(w.flow_hint())
        elif isinstance(w, NovelEdit):
            words = w.word_count()
            sel = len(w.textCursor().selectedText().split())
            self.stats.setText(f"{f'{sel:,} selected · ' if sel else ''}{words:,} words · "
                               f"~{max(1, round(words / 250))} ms pages · ~{reports.fmt_runtime(words / 250)} read")
            self.hint.setText("Novel mode · lines starting with “# ” become chapters · *italic*")

    def _target_changed(self, v):
        w = self.script_ed()
        if w:
            w.title["target"] = str(v)
            self.mark_dirty()
            self._update_beat_and_stats()

    def _tab_changed(self, i):
        w = self.ed()
        if i == TAB_CARDS:
            self.cards.refresh(self.script_ed())
        elif i == TAB_REPORTS:
            self.reports.render()
        elif i == TAB_TITLE and w is not None:
            self.title_view.load(w.title if isinstance(w, ScriptEdit) else self.current.title)

    def _report_source(self):
        w = self.ed()
        if isinstance(w, ScriptEdit):
            return "screenplay", w.to_script()
        return "novel", (self.current.title.get("title", self.current.name), w.toPlainText() if w else "")

    def set_zoom(self, z):
        self.zoom_combo.setCurrentText(f"{z}%")
        for w in self.editors.values():
            if isinstance(w, ScriptEdit):
                w.set_zoom(z / 100)
        w = self.ed()
        if w:
            self.page_stack.setFixedWidth(w.width())

    # =============================================================== beats
    def insert_beats(self):
        w = self.script_ed()
        if not w:
            return
        if w.beat_blocks():
            if QMessageBox.question(self, "Beats already there",
                                    "This script already has beat markers. Insert another full set at the cursor?") \
                    != QMessageBox.Yes:
                return
        w.insert_paras(beat_sheet_paras(self.breakdown.beat.target.value()))
        self._refresh_outline()

    def jump_beat(self, direction):
        w = self.script_ed()
        if not w:
            return
        here = w.textCursor().blockNumber()
        beats = [b for _t, b in w.beat_blocks()]
        if direction > 0:
            nxt = next((b for b in beats if b.blockNumber() > here), None)
        else:
            nxt = next((b for b in reversed(beats) if b.blockNumber() < here), None)
        if nxt:
            w.goto_block(nxt)

    # =============================================================== import / export
    def import_script(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import screenplay", self.settings.value("lastdir", ""),
                                              "Screenplays (*.fountain *.spmd *.txt *.fdx)")
        if not path:
            return
        p = Path(path)
        try:
            sd = model.parse_fdx(p.read_bytes()) if p.suffix.lower() == ".fdx" \
                else model.parse_fountain(p.read_text(encoding="utf-8", errors="replace"))
        except Exception as ex:  # noqa: BLE001
            QMessageBox.critical(self, "Import failed", str(ex))
            return
        d = self.project.add_doc(sd.title.get("title") or p.stem, "screenplay")
        d.script = sd
        self._make_editor(d)
        self._rebuild_tree(d)
        self.switch_doc(d)
        self.mark_dirty()

    def _project_is_blank(self) -> bool:
        """A fresh, untouched project: one empty screenplay, never saved."""
        if self.project.path or len(self.project.docs) != 1:
            return False
        self._flush()
        d = self.project.docs[0]
        return d.kind == "screenplay" and not any(p["t"].strip() for p in d.script.paras)

    def import_celtx(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import old Celtx project", self.settings.value("lastdir", ""),
                                              "Celtx project (*.celtx)")
        if not path:
            return
        try:
            proj_title, docs = model.import_celtx(path)
        except Exception as ex:  # noqa: BLE001
            QMessageBox.critical(self, "Import failed", f"Couldn't read that .celtx file.\n\n{ex}")
            return
        if not docs:
            QMessageBox.information(self, "Nothing found", "No scripts or text documents were found in that file.")
            return
        if self._project_is_blank():
            # start fresh, named after the Celtx project
            self._clear_editors()
            self.project = Project(proj_title or Path(path).stem)
        best = None
        for item in docs:
            d = self.project.add_doc(item["name"], item["kind"])
            if item["kind"] == "screenplay":
                d.script = item["data"]
                size = len(d.script.paras)
                if best is None or (best[1] < size):
                    best = (d, size)
            else:
                d.text = item["data"]
            d.scratch = item.get("scratch", "")
            self._make_editor(d)
        target = best[0] if best else self.project.docs[-1]
        self._rebuild_tree(target)
        self.switch_doc(target)
        self.mark_dirty()
        n_items = sum(len(s["items"]) for i in docs if i["kind"] == "screenplay"
                      for s in i["data"].scenes.values())
        QMessageBox.information(
            self, "Celtx import",
            f"Imported “{proj_title or Path(path).stem}”: {len(docs)} document(s)"
            f"{f', {n_items} breakdown item(s)' if n_items else ''}.\n\n"
            "Celtx's Sketch, Calendar and Storyboard items have no text, so they're skipped. "
            "Save the project to keep it as plain files.")

    def export_pdf(self):
        from .pdfexport import export_novel, export_screenplay
        if not self.current:
            return
        self._flush(self.current)
        path, _ = QFileDialog.getSaveFileName(self, "Export PDF", f"{model.safe_name(self.current.name)}.pdf",
                                              "PDF (*.pdf)")
        if not path:
            return
        try:
            if self.current.kind == "screenplay":
                n = export_screenplay(self.current.script, path, self.page_size())
            else:
                n = export_novel(self.current.title, self.current.text, path, self.page_size())
        except Exception as ex:  # noqa: BLE001
            QMessageBox.critical(self, "Export failed", str(ex))
            return
        self.statusBar().showMessage(f"Exported {n} pages ({self.page_size()}) → {path}", 6000)

    def export_text(self, fmt):
        if not self.current:
            return
        self._flush(self.current)
        ext = {"fountain": "fountain", "fdx": "fdx", "md": "md"}[fmt]
        path, _ = QFileDialog.getSaveFileName(self, "Export", f"{model.safe_name(self.current.name)}.{ext}",
                                              f"*.{ext}")
        if not path:
            return
        if fmt == "fountain":
            text = model.write_fountain(self.current.script)
        elif fmt == "fdx":
            text = model.write_fdx(self.current.script)
        else:
            text = self.current.text
        Path(path).write_text(text, encoding="utf-8")
        self.statusBar().showMessage(f"Exported → {path}", 5000)

    # =============================================================== misc
    def show_keys(self):
        rows = "".join(f"<tr><td><b>{ELEMENTS[e]}</b></td><td>{ELEMENTS[model.TAB_NEXT[e]]}</td>"
                       f"<td>{ELEMENTS[model.ENTER_NEXT[e]]}</td><td>Ctrl+{e + 1}</td></tr>"
                       for e in range(len(ELEMENTS)))
        QMessageBox.information(self, "Keyboard flow", f"""
            <p>Tab changes the current line. Enter starts the next line.
            Enter on an empty line converts it (empty Character → Action).</p>
            <table cellpadding=4><tr><th align=left>On</th><th align=left>Tab →</th>
            <th align=left>Enter →</th><th align=left>Jump</th></tr>{rows}</table>
            <p>Type <b>INT.</b> or <b>EXT.</b> on an Action line and it becomes a Scene Heading.<br>
            Select text → right-click → <b>Tag as</b> to add it to the scene breakdown.<br>
            Ctrl+] / Ctrl+[ jump between beats.</p>""")

    def about(self):
        art = (HERE / "splash.jpg").as_uri()
        QMessageBox.about(self, "About GORE DRAFT", f"""
            <img src="{art}" width="480"><br>
            <h3>Version {APP_VERSION}{' <span style="color:#d11a22">BETA</span>' if support.BETA else ''}</h3>
            <p>A Splatter VHS screenwriting tool, built around practical and makeup effects.</p>
            <p>Your work is saved as plain Fountain and Markdown files in a folder you own.
            No accounts, no cloud, no subscription. If this app disappears tomorrow,
            your scripts still open in Notepad.</p>
            <p>Script font: Courier Prime (SIL Open Font License).<br>
            Beat structure after Blake Snyder's <i>Save the Cat</i>.</p>
            <p style="color:#888"><small>Celtx and Final Draft are trademarks of their respective owners.
            GORE DRAFT is independent and not affiliated with or endorsed by them.</small></p>""")

    def closeEvent(self, e):
        if not self.confirm_discard():
            e.ignore()
            return
        self.settings.setValue("geometry", self.saveGeometry())
        e.accept()


def beta_stamp(pix: QPixmap) -> QPixmap:
    """Paint a rubber-stamp style BETA badge + version onto the splash."""
    if not support.BETA:
        return pix
    from PySide6.QtGui import QColor, QFont, QPainter, QPen
    from PySide6.QtCore import QRectF
    out = QPixmap(pix)
    p = QPainter(out)
    p.setRenderHint(QPainter.Antialiasing)
    w, h = out.width(), out.height()
    bw, bh = w * 0.20, h * 0.11
    p.translate(w * 0.86, h * 0.13)
    p.rotate(-12)
    r = QRectF(-bw / 2, -bh / 2, bw, bh)
    p.setPen(QPen(QColor(209, 26, 34, 235), max(3, w / 220)))
    p.setBrush(QColor(12, 10, 14, 170))
    p.drawRoundedRect(r, 6, 6)
    f = QFont()
    f.setFamilies(["Courier Prime", "Courier New"])
    f.setBold(True)
    f.setPixelSize(int(bh * 0.46))
    f.setLetterSpacing(QFont.AbsoluteSpacing, bh * 0.08)
    p.setFont(f)
    p.setPen(QColor("#ff3b3b"))
    p.drawText(QRectF(r.left(), r.top() + bh * 0.05, bw, bh * 0.62), Qt.AlignCenter, "BETA")
    f.setPixelSize(int(bh * 0.2))
    f.setLetterSpacing(QFont.AbsoluteSpacing, 1)
    p.setFont(f)
    p.setPen(QColor("#f1e6c8"))
    p.drawText(QRectF(r.left(), r.top() + bh * 0.62, bw, bh * 0.32), Qt.AlignCenter, f"VERSION {APP_VERSION}")
    p.end()
    return out


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("Splatter VHS")
    support.setup_logging()
    for f in (HERE / "fonts").glob("*.ttf"):
        QFontDatabase.addApplicationFont(str(f))
    app.setStyle("Fusion")
    app.setWindowIcon(QIcon(str(HERE / "icon.png")))
    splash = None
    if (HERE / "splash.jpg").exists() and "--no-splash" not in sys.argv:
        pix = QPixmap(str(HERE / "splash.jpg"))
        screen = app.primaryScreen().availableGeometry()
        width = min(960, int(screen.width() * 0.6))
        splash = QSplashScreen(beta_stamp(pix.scaledToWidth(width, Qt.SmoothTransformation)))
        splash.show()
        app.processEvents()
    started = time.monotonic()
    app.setStyleSheet(QSS)
    w = MainWindow()
    if splash:
        # keep the splash up for at least ~1.5s so it doesn't just flicker
        wait = max(0, 1500 - int((time.monotonic() - started) * 1000))
        QTimer.singleShot(wait, lambda: (w.show(), splash.finish(w)))
    else:
        w.show()
    arg = next((a for a in sys.argv[1:] if a.endswith(PROJECT_EXT)), None)
    if arg:
        w.open_project(arg)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
