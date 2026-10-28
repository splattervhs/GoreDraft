"""Offline spellchecking with Australian/British spelling and film vocabulary.

Uses pyspellchecker's English word list, then accepts AU/UK forms by mapping
them to their US spelling (colour -> color, realise -> realize, theatre ->
theater ...). Words in ALL CAPS (character names, headings, SFX callouts) and
words you've added to your dictionary are never flagged.
"""
from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import QStandardPaths
from PySide6.QtGui import QColor, QSyntaxHighlighter, QTextCharFormat

try:
    from spellchecker import SpellChecker
except ImportError:  # app still runs; spellcheck just switches off
    SpellChecker = None

WORD_RE = re.compile(r"[A-Za-z][A-Za-z']*[A-Za-z]|[A-Za-z]")

EXTRA_WORDS = """
animatronic animatronics prosthetic prosthetics squib squibs hazer hazers gaffer gaffers
mocap vfx sfx fx pyro pyrotechnic pyrotechnics latex silicone foam gelatine gelatin
appliance appliances bladder bladders pumpkin fluorescents fluoro storyboard storyboards
splatterpunk splatter gore gory slasher slashers giallo zombie zombies werewolf ghoul ghouls
undead demonic possessed possession exorcism cryptid cryptids yowie bunyip drop bear
voiceover offscreen o.s v.o cont'd intercut montage flashback flashforward jumpcut
smartphone livestream livestreams livestreamer webcam vhs camcorder dvd blu-ray
arvo ute utes servo bogan bogans mozzie mozzies brekkie barbie esky thongs dunny
footy maccas sheila sheilas crikey drongo dag daggy stubby stubbies bottle-o
okay ok uh um hmm huh yeah nah mum mums
""".split()

# AU/UK -> US rewrites tried when a word isn't in the dictionary
UK_RULES = [
    (r"our(s|ed|ing|ite|ites|able|er|ers|ful|less)?$", r"or\1"),
    (r"our", "or"),
    (r"isation(s)?$", r"ization\1"), (r"ise(s|d|r|rs)?$", r"ize\1"), (r"ising$", "izing"),
    (r"yse(s|d)?$", r"yze\1"), (r"ysing$", "yzing"),
    (r"tre(s)?$", r"ter\1"), (r"ogue(s)?$", r"og\1"),
    (r"lled$", "led"), (r"lling$", "ling"), (r"ller(s)?$", r"ler\1"),
    (r"ence$", "ense"), (r"mme(s)?$", r"m\1"), (r"ae", "e"), (r"oe", "e"),
    (r"eable$", "able"), (r"ement$", "ment"),
]


class Speller:
    _inst = None

    @classmethod
    def get(cls) -> "Speller":
        if cls._inst is None:
            cls._inst = Speller()
        return cls._inst

    def __init__(self):
        self.ok = SpellChecker is not None
        self.sc = SpellChecker(language="en", distance=2) if self.ok else None
        self.user_path = Path(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)) / "dictionary.txt"
        self.user: set[str] = set()
        self.ignore: set[str] = set()       # per-session (character names etc.)
        if self.user_path.exists():
            self.user = {w.strip().lower() for w in self.user_path.read_text(encoding="utf-8").splitlines() if w.strip()}
        if self.ok:
            self.sc.word_frequency.load_words(EXTRA_WORDS)
        self._cache: dict[str, bool] = {}

    def known(self, word: str) -> bool:
        if not self.ok or len(word) < 2 or word.isupper():
            return True
        w = word.lower().strip("'")
        if w.endswith("'s"):
            w = w[:-2]
        if w in self.user or w in self.ignore:
            return True
        hit = self._cache.get(w)
        if hit is not None:
            return hit
        res = w in self.sc
        if not res:
            for pat, rep in UK_RULES:
                alt = re.sub(pat, rep, w)
                if alt != w and alt in self.sc:
                    res = True
                    break
        self._cache[w] = res
        return res

    def suggestions(self, word: str, n=6) -> list[str]:
        if not self.ok:
            return []
        cands = self.sc.candidates(word.lower()) or set()
        ranked = sorted(cands, key=lambda c: -self.sc.word_frequency[c])[:n]
        if word[:1].isupper():
            ranked = [c.capitalize() for c in ranked]
        return ranked

    def add(self, word: str):
        w = word.lower()
        self.user.add(w)
        self._cache[w] = True
        try:
            self.user_path.parent.mkdir(parents=True, exist_ok=True)
            self.user_path.write_text("\n".join(sorted(self.user)) + "\n", encoding="utf-8")
        except OSError:
            pass

    def ignore_all(self, word: str):
        self.ignore.add(word.lower())
        self._cache[word.lower()] = True


def misspelt_ranges(text: str):
    sp = Speller.get()
    for m in WORD_RE.finditer(text):
        if not sp.known(m.group()):
            yield m.start(), m.end() - m.start()


def squiggle() -> QTextCharFormat:
    f = QTextCharFormat()
    f.setUnderlineStyle(QTextCharFormat.SpellCheckUnderline)
    f.setUnderlineColor(QColor("#e0242b"))
    return f


class SpellHighlighter(QSyntaxHighlighter):
    """Overlay-only highlighter: never touches block state (the script editor
    stores each line's element there)."""

    def __init__(self, doc, enabled=True):
        super().__init__(doc)
        self.enabled = enabled
        self.fmt = squiggle()

    def set_enabled(self, on: bool):
        self.enabled = on
        self.rehighlight()

    # element ids that are shown in capitals or are notes: never spellchecked
    SKIP_STATES = {0, 2, 5, 6, 7}  # heading, character, transition, shot, beat

    def highlightBlock(self, text):
        if not self.enabled:
            return
        block = self.currentBlock()
        el = block.blockFormat().property(0x100000 + 2)  # editor.ELEMENT
        if el is None:
            el = block.userState()
        if el in self.SKIP_STATES:
            return
        for start, length in misspelt_ranges(text):
            self.setFormat(start, length, self.fmt)


def word_at(cursor):
    """(word, QTextCursor selecting it) under a text cursor, or (None, None)."""
    from PySide6.QtGui import QTextCursor
    block = cursor.block()
    pos = cursor.position() - block.position()
    for m in WORD_RE.finditer(block.text()):
        if m.start() <= pos <= m.end():
            c = QTextCursor(block)
            c.setPosition(block.position() + m.start())
            c.setPosition(block.position() + m.end(), QTextCursor.KeepAnchor)
            return m.group(), c
    return None, None


def add_spell_menu(menu, editor, pos_cursor, on_change=None):
    """Prepend suggestions / Add to dictionary to a context menu."""
    sp = Speller.get()
    word, wc = word_at(pos_cursor)
    if not (word and sp.ok and not sp.known(word)):
        return
    first = menu.actions()[0] if menu.actions() else None
    sugg = sp.suggestions(word)
    acts = []
    for s in sugg or []:
        a = menu.addAction(s)
        f = a.font()
        f.setBold(True)
        a.setFont(f)
        a.triggered.connect(lambda _=False, s=s, wc=wc: wc.insertText(s))
        acts.append(a)
    if not sugg:
        a = menu.addAction("(no suggestions)")
        a.setEnabled(False)
        acts.append(a)
    add = menu.addAction(f"Add “{word}” to dictionary")
    add.triggered.connect(lambda: (sp.add(word), on_change and on_change()))
    ign = menu.addAction("Ignore all")
    ign.triggered.connect(lambda: (sp.ignore_all(word), on_change and on_change()))
    acts += [add, ign]
    sep = menu.addSeparator()
    acts.append(sep)
    for a in acts:
        menu.removeAction(a)
    menu.insertActions(first, acts) if first else menu.addActions(acts)
