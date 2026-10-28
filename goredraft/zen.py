"""Zen mode: just the page, a dark room, and a focus timer."""
from __future__ import annotations

from PySide6.QtCore import QPropertyAnimation, Qt, QTimer, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QApplication, QFrame, QGraphicsOpacityEffect, QHBoxLayout,
                               QLabel, QMenu, QPushButton, QVBoxLayout)

PRESETS = [("Classic · 25 on / 5 off", 25, 5, 15),
           ("Deep · 50 on / 10 off", 50, 10, 20),
           ("Sprint · 15 on / 3 off", 15, 3, 10)]


class FocusTimer(QFrame):
    """A pomodoro timer: work, short break, work... long break every 4th."""
    phaseFinished = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("FocusTimer")
        self.work, self.short, self.long = 25, 5, 15
        self.phase = "work"
        self.done = 0                     # completed work sessions
        self.remaining = self.work * 60
        self.running = False
        self.words_start = 0
        self.words_now = 0
        self._tick = QTimer(self, interval=1000)
        self._tick.timeout.connect(self._step)
        self._flash = QTimer(self, interval=350)
        self._flash.timeout.connect(self._flash_step)
        self._flashes = 0

        v = QVBoxLayout(self)
        v.setContentsMargins(14, 10, 14, 12)
        v.setSpacing(4)
        top = QHBoxLayout()
        self.label = QLabel("🍅  FOCUS")
        self.label.setObjectName("FocusPhase")
        top.addWidget(self.label, 1)
        self.dots = QLabel("○○○○")
        self.dots.setObjectName("FocusDots")
        self.dots.setToolTip("Focus sessions done. A long break comes after four.")
        top.addWidget(self.dots)
        v.addLayout(top)
        self.clock = QLabel("25:00")
        self.clock.setObjectName("FocusClock")
        self.clock.setAlignment(Qt.AlignCenter)
        v.addWidget(self.clock)
        self.words = QLabel("+0 words this session")
        self.words.setObjectName("FocusWords")
        self.words.setAlignment(Qt.AlignCenter)
        v.addWidget(self.words)
        row = QHBoxLayout()
        self.go = QPushButton("Start")
        self.go.setObjectName("Primary")
        self.go.clicked.connect(self.toggle)
        row.addWidget(self.go, 1)
        reset = QPushButton("↺")
        reset.setToolTip("Reset this timer")
        reset.setFixedWidth(34)
        reset.clicked.connect(self.reset)
        row.addWidget(reset)
        skip = QPushButton("⏭")
        skip.setToolTip("Skip to the next phase")
        skip.setFixedWidth(34)
        skip.clicked.connect(lambda: self._finish(silent=True))
        row.addWidget(skip)
        opts = QPushButton("⚙")
        opts.setFixedWidth(46)
        opts.setToolTip("Timer lengths")
        m = QMenu(opts)
        for name, w, s, l in PRESETS:
            a = m.addAction(name)
            a.triggered.connect(lambda _=False, w=w, s=s, l=l: self.set_lengths(w, s, l))
        opts.setMenu(m)
        row.addWidget(opts)
        v.addLayout(row)
        self.setFixedWidth(250)
        self._render()

    # -- control
    def set_lengths(self, w, s, l):
        self.work, self.short, self.long = w, s, l
        self.reset()

    def toggle(self):
        self.running = not self.running
        (self._tick.start if self.running else self._tick.stop)()
        self._render()

    def reset(self):
        self.running = False
        self._tick.stop()
        self.remaining = self._length() * 60
        self._render()

    def start_session(self, words: int):
        self.words_start = self.words_now = words
        self._render()

    def set_words(self, words: int):
        self.words_now = words
        self._render()

    # -- internals
    def _length(self):
        return {"work": self.work, "short": self.short, "long": self.long}[self.phase]

    def _step(self):
        self.remaining -= 1
        if self.remaining <= 0:
            self._finish()
        self._render()

    def _finish(self, silent=False):
        ended = self.phase
        if self.phase == "work":
            self.done += 1
            self.phase = "long" if self.done % 4 == 0 else "short"
        else:
            self.phase = "work"
        self.remaining = self._length() * 60
        self.running = False
        self._tick.stop()
        if not silent:
            QApplication.beep()
            self._flashes = 8
            self._flash.start()
            self.phaseFinished.emit(ended)
        self._render()

    def _flash_step(self):
        self._flashes -= 1
        self.setProperty("alarm", self._flashes % 2 == 1)
        self.style().unpolish(self)
        self.style().polish(self)
        if self._flashes <= 0:
            self._flash.stop()

    def _render(self):
        m, s = divmod(max(0, self.remaining), 60)
        self.clock.setText(f"{m:02d}:{s:02d}")
        names = {"work": "🍅  FOCUS", "short": "☕  SHORT BREAK", "long": "🛋  LONG BREAK"}
        self.label.setText(names[self.phase])
        self.label.setStyleSheet("color: %s;" % ("#ff3b3b" if self.phase == "work" else "#3fb950"))
        n = self.done % 4
        self.dots.setText("●" * n + "○" * (4 - n))
        self.go.setText("Pause" if self.running else ("Start" if self.phase == "work" else "Start break"))
        diff = self.words_now - self.words_start
        self.words.setText(f"{diff:+,} words this session")
        self.setProperty("phase", self.phase)
        self.style().unpolish(self)
        self.style().polish(self)


class ZenHint(QLabel):
    """'Esc to leave' — shows briefly, then fades."""

    def __init__(self, parent=None):
        super().__init__("ZEN MODE  ·  Esc or F11 to leave", parent)
        self.setObjectName("ZenHint")
        self.setAlignment(Qt.AlignCenter)
        self._fx = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._fx)
        self._anim = QPropertyAnimation(self._fx, b"opacity", self)
        self._anim.setDuration(1200)
        self._anim.setStartValue(1.0)
        self._anim.setEndValue(0.0)
        self._anim.finished.connect(self.hide)

    def flash(self):
        self._fx.setOpacity(1.0)
        self.show()
        self.raise_()
        QTimer.singleShot(2500, self._anim.start)


ZEN_QSS = """
QFrame#FocusTimer { background: rgba(22,18,26,235); border: 1px solid #2e2533;
                    border-top: 4px solid #d11a22; border-radius: 4px; }
QFrame#FocusTimer[phase="short"], QFrame#FocusTimer[phase="long"] { border-top-color: #3fb950; }
QFrame#FocusTimer[alarm="true"] { background: #d11a22; }
QFrame#FocusTimer QLabel { background: transparent; }
QLabel#FocusPhase { color: #ff3b3b; font-weight: bold; letter-spacing: 2px; font-size: 9pt; }
QFrame#FocusTimer[phase="short"] QLabel#FocusPhase, QFrame#FocusTimer[phase="long"] QLabel#FocusPhase { color: #3fb950; }
QLabel#FocusDots { color: #9a8f98; font-size: 10pt; }
QLabel#FocusClock { color: #f1e6c8; font-family: 'Courier Prime', 'Courier New'; font-size: 34pt; font-weight: bold; }
QLabel#FocusWords { color: #9a8f98; font-size: 9pt; }
QLabel#ZenHint { background: rgba(12,10,14,220); color: #f1e6c8; padding: 8px 18px; border-radius: 4px;
                 font-family: 'Courier Prime', 'Courier New'; font-weight: bold; letter-spacing: 2px; }
"""
