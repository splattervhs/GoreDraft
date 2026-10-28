"""
GORE DRAFT - data model and file formats.

Everything here is plain Python (no Qt) so it can be tested on its own.

A screenplay is held as a ScriptData:
    title  : dict of title-page fields
    paras  : list of {"e": element, "t": text, "sid": scene id (headings only)}
    scenes : {scene id: {"synopsis": str, "items": [breakdown items]}}

A breakdown item is {"cat": category, "item": text, "char": character, "note": text}.

On disk a screenplay is a normal Fountain file. Breakdown items and
synopses live inside the script as Fountain notes / synopsis lines, so the
file still opens in any Fountain app (or Notepad) and nothing is lost.
"""
from __future__ import annotations

import html
import json
import re
import uuid
import zipfile
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree as ET

APP_NAME = "GORE DRAFT"
APP_VERSION = "0.2.1"
PROJECT_EXT = ".goredraft"

# ---------------------------------------------------------------- elements
HEADING, ACTION, CHARACTER, PAREN, DIALOGUE, TRANSITION, SHOT, BEAT = range(8)
ELEMENTS = ["Scene Heading", "Action", "Character", "Parenthetical",
            "Dialogue", "Transition", "Shot", "Beat"]
NON_PRINTING = {BEAT}  # beat markers are a writing guide; never printed

# What Enter gives you next (Celtx-style flow)
ENTER_NEXT = {HEADING: ACTION, ACTION: ACTION, CHARACTER: DIALOGUE,
              PAREN: DIALOGUE, DIALOGUE: CHARACTER, TRANSITION: HEADING,
              SHOT: ACTION, BEAT: HEADING}
# Enter on an EMPTY line converts it instead of adding another
ENTER_EMPTY = {HEADING: ACTION, CHARACTER: ACTION, DIALOGUE: ACTION,
               PAREN: DIALOGUE, TRANSITION: HEADING, SHOT: ACTION, BEAT: HEADING}
# Tab changes the element of the current line
TAB_NEXT = {HEADING: ACTION, ACTION: CHARACTER, CHARACTER: PAREN,
            PAREN: DIALOGUE, DIALOGUE: PAREN, TRANSITION: HEADING,
            SHOT: ACTION, BEAT: HEADING}

# Tab on an EMPTY line cycles through every element (Final Draft-style)
TAB_EMPTY = {ACTION: CHARACTER, CHARACTER: TRANSITION, TRANSITION: SHOT,
             SHOT: HEADING, HEADING: ACTION, DIALOGUE: PAREN, PAREN: DIALOGUE,
             BEAT: HEADING}

UPPERCASE_ELEMENTS = {HEADING, CHARACTER, TRANSITION, SHOT, BEAT}

# ---------------------------------------------------------------- breakdown
# Makeup / practical effects come first. This is the point of the app.
SPFX_CATEGORIES = [
    "Special Makeup FX",
    "Prosthetics & Appliances",
    "Blood & Gore",
    "Wounds & Continuity",
    "Creature FX",
    "Dummies & Body Parts",
    "Animatronics",
    "Practical / Mechanical FX",
    "Fog & Haze",
    "Drones",
    "Pyro",
]
OTHER_CATEGORIES = [
    "Props", "Weapons", "Wardrobe", "Hair & Makeup",
    "Cast", "Extras", "Stunts", "Vehicles", "Animals", "Set Dressing",
    "Locations", "Sound FX", "Music", "Visual FX", "Special Equipment",
    "Production Notes",
]
CATEGORIES = SPFX_CATEGORIES + OTHER_CATEGORIES
MAKEUP_CATEGORIES = {"Special Makeup FX", "Prosthetics & Appliances", "Blood & Gore",
                     "Wounds & Continuity", "Creature FX", "Dummies & Body Parts"}

CATEGORY_COLOURS = {
    "Special Makeup FX": "#e0242b", "Prosthetics & Appliances": "#ff5a36",
    "Blood & Gore": "#a3000b", "Wounds & Continuity": "#ff8c42",
    "Creature FX": "#3fb950", "Dummies & Body Parts": "#c678dd",
    "Practical / Mechanical FX": "#d19a66", "Animatronics": "#00d4ff",
    "Fog & Haze": "#9fb4c7", "Drones": "#7c5cff", "Pyro": "#ffb000",
    "Props": "#61afef", "Weapons": "#9da5b4", "Wardrobe": "#56b6c2",
    "Hair & Makeup": "#f78fb3", "Cast": "#ffffff", "Extras": "#bbbbbb",
    "Stunts": "#ff79c6", "Vehicles": "#8be9fd", "Animals": "#a6e22e",
    "Set Dressing": "#b48ead", "Locations": "#88c0d0", "Sound FX": "#ebcb8b",
    "Music": "#d08770", "Visual FX": "#5e81ac", "Special Equipment": "#a3be8c",
    "Production Notes": "#d8dee9",
}

# ---------------------------------------------------------------- beat sheet
# Blake Snyder's "Save the Cat" beat structure. Position = fraction of the
# script's length. Guide text is our own wording, with a horror angle.
SAVE_THE_CAT = [
    ("Opening Image", 0.0, 0.01,
     "A snapshot of the world and the hero before the story changes them.",
     "Horror: show the normal world, or a cold-open kill that sets the rules."),
    ("Theme Stated", 0.045, 0.05,
     "Someone says the lesson the hero needs, and the hero doesn't hear it yet.",
     "Horror: the warning nobody listens to."),
    ("Set-Up", 0.01, 0.09,
     "Introduce the hero, their flaws, their people, and what's missing in their life.",
     "Horror: plant the dread, the location, and the things that will matter later."),
    ("Catalyst", 0.10, 0.11,
     "The event that knocks the hero's world off its axis.",
     "Horror: the tape gets played, the door gets opened, the first body turns up."),
    ("Debate", 0.11, 0.23,
     "The hero hesitates. Should I go? Can I? What will it cost?",
     "Horror: rationalising the weird stuff. 'It's probably nothing.'"),
    ("Break into Two", 0.23, 0.25,
     "The hero chooses to enter the new world. A clear step forward.",
     "Horror: they go in, stay the night, or decide to investigate."),
    ("B Story", 0.27, 0.30,
     "A new character or relationship that carries the theme.",
     "Horror: the ally, the love interest, or the person who knows the history."),
    ("Fun and Games", 0.27, 0.50,
     "The promise of the premise. The set pieces the poster sold.",
     "Horror: the scares, the stalking, the gags your effects team is building."),
    ("Midpoint", 0.50, 0.52,
     "A false victory or false defeat. The stakes go up and the clock starts.",
     "Horror: the creature is revealed, or they learn it can't be escaped."),
    ("Bad Guys Close In", 0.52, 0.68,
     "Pressure from outside and cracks from inside. Everything gets harder.",
     "Horror: the body count climbs and the group turns on itself."),
    ("All Is Lost", 0.68, 0.70,
     "The lowest point. Something or someone dies, literally or symbolically.",
     "Horror: the ally dies, the escape fails, the hero is alone."),
    ("Dark Night of the Soul", 0.70, 0.77,
     "The hero sits in the loss, then finds the truth they've been avoiding.",
     "Horror: the quiet before the final stand."),
    ("Break into Three", 0.77, 0.78,
     "A new idea, often from the B Story, gives the hero a way forward.",
     "Horror: they figure out the rule, the weakness, or the ritual."),
    ("Finale", 0.78, 0.99,
     "The hero applies what they've learned and confronts the problem head-on.",
     "Horror: the final girl moment. Your biggest gag lives here."),
    ("Final Image", 0.99, 1.0,
     "The mirror of the opening image. Proof that change has happened.",
     "Horror: or the sting. It's not over."),
]
BEAT_NAMES = [b[0] for b in SAVE_THE_CAT]


def beat_info(name: str):
    key = name.split("(")[0].strip().lower()
    for b in SAVE_THE_CAT:
        if b[0].lower() == key:
            return b
    return None


def beat_sheet_paras(target_pages: int = 100) -> list:
    """Pre-filled guide: one beat marker per Save the Cat beat, with an empty
    action line under each to start writing."""
    out = []
    for name, start, end, *_ in SAVE_THE_CAT:
        lo, hi = max(1, round(start * target_pages)), max(1, round(end * target_pages))
        page = f"p.{lo}" if lo == hi else f"pp.{lo}-{hi}"
        out.append({"e": BEAT, "t": f"{name} ({page})"})
        out.append({"e": ACTION, "t": ""})
    return out


TITLE_FIELDS = [("title", "Title"), ("credit", "Credit"), ("author", "Author"),
                ("source", "Based on"), ("draft", "Draft"),
                ("copyright", "Copyright"), ("contact", "Contact")]
FOUNTAIN_TITLE_KEYS = {"title": "Title", "credit": "Credit", "author": "Author",
                       "source": "Source", "draft": "Draft date",
                       "copyright": "Copyright", "contact": "Contact",
                       "target": "Target Pages"}


def new_id() -> str:
    return uuid.uuid4().hex[:10]


@dataclass
class ScriptData:
    title: dict = field(default_factory=dict)
    paras: list = field(default_factory=list)
    scenes: dict = field(default_factory=dict)

    def scene_list(self):
        """[(number, heading text, sid, para index)]"""
        out, n = [], 0
        for i, p in enumerate(self.paras):
            if p["e"] == HEADING:
                n += 1
                if not p.get("sid"):
                    p["sid"] = new_id()
                out.append((n, p["t"].upper(), p["sid"], i))
        return out


# ================================================================ FOUNTAIN
HEADING_RE = re.compile(r"^(INT\.?/EXT|INT/EXT|I/E|INT|EXT|EST)[\.\s]", re.I)
BD_RE = re.compile(r"^\[\[BD (?P<cat>[^:\]]+):\s*(?P<item>.*?)"
                   r"(?:\s+@(?P<char>[^/\]]+?))?(?:\s+//\s*(?P<note>.*?))?\]\]$")
TITLE_KEY_RE = re.compile(r"^([A-Za-z ]+):\s*(.*)$")


def _clean(s: str) -> str:
    return (s or "").replace("]]", "] ]").replace("\n", " ").strip()


def write_fountain(sd: ScriptData) -> str:
    out = []
    # title page
    tp = [(FOUNTAIN_TITLE_KEYS[k], str(sd.title.get(k, ""))) for k in FOUNTAIN_TITLE_KEYS]
    tp = [(k, v) for k, v in tp if v.strip()]
    if tp:
        for k, v in tp:
            lines = v.strip().splitlines()
            if len(lines) == 1:
                out.append(f"{k}: {lines[0]}")
            else:
                out.append(f"{k}:")
                out.extend("    " + ln for ln in lines)
        out.append("")
    prev = None
    for p in sd.paras:
        e, t = p["e"], p["t"].rstrip()
        in_dialogue_chain = e in (PAREN, DIALOGUE) and prev in (CHARACTER, PAREN, DIALOGUE)
        if out and not in_dialogue_chain:
            if out[-1] != "":
                out.append("")
        if e == HEADING:
            up = t.upper()
            out.append(up if HEADING_RE.match(up) else "." + up)
            sc = sd.scenes.get(p.get("sid"), {})
            if sc.get("synopsis", "").strip():
                out.append("= " + sc["synopsis"].strip().replace("\n", " "))
            for it in sc.get("items", []):
                line = f"[[BD {it['cat']}: {_clean(it['item'])}"
                if it.get("char", "").strip():
                    line += f" @{_clean(it['char'])}"
                if it.get("note", "").strip():
                    line += f" // {_clean(it['note'])}"
                out.append(line + "]]")
        elif e == CHARACTER:
            up = t.upper().strip()
            out.append(up if re.search(r"[A-Z]", up) else "@" + up)
        elif e == PAREN:
            s = t.strip()
            if not s.startswith("("):
                s = "(" + s
            if not s.endswith(")"):
                s += ")"
            out.append(s)
        elif e == DIALOGUE:
            out.append(t if t.strip() else "  ")
        elif e == TRANSITION:
            up = t.upper().strip()
            out.append(up if up.endswith("TO:") else "> " + up)
        elif e == SHOT:
            out.append("!" + t.upper() + " [[shot]]")
        elif e == BEAT:
            out.append("# " + t.strip())
        else:  # ACTION
            needs_force = (t.strip() and (t.isupper() or HEADING_RE.match(t)
                           or t.startswith((".", "!", "@", ">", "=", "#", "~"))
                           or t.strip().endswith("TO:")))
            out.append(("!" + t) if needs_force else t)
        prev = e
    return "\n".join(out).rstrip() + "\n"


def parse_fountain(text: str) -> ScriptData:
    sd = ScriptData()
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # strip /* boneyard */
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    lines = text.split("\n")
    i = 0
    # ---- title page
    if lines and TITLE_KEY_RE.match(lines[0]) and not HEADING_RE.match(lines[0]):
        rev = {v.lower(): k for k, v in FOUNTAIN_TITLE_KEYS.items()}
        rev.update({"based on": "source", "draft": "draft", "notes": "contact"})
        key = None
        while i < len(lines) and lines[i].strip():
            ln = lines[i]
            m = TITLE_KEY_RE.match(ln)
            if m and not ln.startswith((" ", "\t")):
                key = rev.get(m.group(1).strip().lower())
                if key:
                    sd.title[key] = m.group(2).strip()
            elif key:
                sd.title[key] = (sd.title.get(key, "") + "\n" + ln.strip()).strip()
            i += 1
    cur_sid = None
    in_dialogue = False

    def add(e, t):
        p = {"e": e, "t": t}
        if e == HEADING:
            p["sid"] = new_id()
            sd.scenes[p["sid"]] = {"synopsis": "", "items": []}
        sd.paras.append(p)
        return p

    n = len(lines)
    while i < n:
        raw = lines[i]
        s = raw.strip()
        prev_blank = i == 0 or not lines[i - 1].strip()
        next_blank = i + 1 >= n or not lines[i + 1].strip()
        if not s:
            in_dialogue = False
            i += 1
            continue
        # breakdown note
        m = BD_RE.match(s)
        if m:
            if cur_sid is None:  # breakdown before any heading: make a scene holder
                p = add(HEADING, "UNTITLED SCENE")
                cur_sid = p["sid"]
            sd.scenes[cur_sid]["items"].append({
                "cat": m.group("cat").strip(), "item": (m.group("item") or "").strip(),
                "char": (m.group("char") or "").strip(),
                "note": (m.group("note") or "").strip()})
            i += 1
            continue
        if s.startswith("= ") or (s.startswith("=") and not s.startswith("===")):
            if cur_sid:
                syn = sd.scenes[cur_sid]["synopsis"]
                sd.scenes[cur_sid]["synopsis"] = (syn + " " + s[1:].strip()).strip()
            i += 1
            continue
        if s.startswith("#") and not s.startswith("##"):
            add(BEAT, s.lstrip("#").strip())
            i += 1
            continue
        if s.startswith("#") or s.startswith("===") or (s.startswith("[[") and s.endswith("]]") and "]]" not in s[2:-2]):
            i += 1  # sections, page breaks, ordinary notes: skip
            continue
        if in_dialogue:
            if s.startswith("(") and s.endswith(")"):
                add(PAREN, s)
            else:
                add(DIALOGUE, s)
            i += 1
            continue
        # headings
        if prev_blank and ((s.startswith(".") and not s.startswith("..")) or HEADING_RE.match(s)):
            h = s[1:] if s.startswith(".") else s
            h = re.sub(r"\s+#[^#]+#\s*$", "", h)  # strip scene numbers
            p = add(HEADING, h.strip())
            cur_sid = p["sid"]
            i += 1
            continue
        if s.lower().endswith("[[shot]]"):
            add(SHOT, s[:-8].lstrip("!").strip())
            i += 1
            continue
        if s.startswith("!"):
            add(ACTION, s[1:])
            i += 1
            continue
        if s.startswith(">") and not s.endswith("<"):
            add(TRANSITION, s[1:].strip())
            i += 1
            continue
        if s.startswith(">") and s.endswith("<"):
            add(ACTION, s[1:-1].strip())
            i += 1
            continue
        if prev_blank and next_blank and s.isupper() and s.endswith("TO:"):
            add(TRANSITION, s)
            i += 1
            continue
        if prev_blank and not next_blank and (s.startswith("@") or (s.isupper() and re.search(r"[A-Z]", s))):
            add(CHARACTER, s.lstrip("@").strip())
            in_dialogue = True
            i += 1
            continue
        add(ACTION, raw.rstrip().lstrip("\t"))
        i += 1
    return sd


# ================================================================ FDX (Final Draft)
FDX_MAP = {"Scene Heading": HEADING, "Action": ACTION, "Character": CHARACTER,
           "Parenthetical": PAREN, "Dialogue": DIALOGUE, "Transition": TRANSITION,
           "Shot": SHOT, "General": ACTION}  # beats are not exported to FDX


def parse_fdx(data: bytes) -> ScriptData:
    sd = ScriptData()
    root = ET.fromstring(data)
    content = root.find("Content")
    if content is None:
        return sd
    for para in content.findall("Paragraph"):
        e = FDX_MAP.get(para.get("Type", "Action"), ACTION)
        t = "".join((tx.text or "") for tx in para.findall("Text")).strip()
        p = {"e": e, "t": t}
        if e == HEADING:
            p["sid"] = new_id()
            sd.scenes[p["sid"]] = {"synopsis": "", "items": []}
        sd.paras.append(p)
    tp = root.find("TitlePage")
    if tp is not None:
        texts = [" ".join((t.text or "") for t in p.findall("Text")).strip()
                 for p in tp.iter("Paragraph")]
        texts = [t for t in texts if t]
        if texts:
            sd.title["title"] = texts[0]
    return sd


def write_fdx(sd: ScriptData) -> str:
    rev = {v: k for k, v in FDX_MAP.items() if k != "General"}
    out = ['<?xml version="1.0" encoding="UTF-8" standalone="no" ?>',
           '<FinalDraft DocumentType="Script" Template="No" Version="5">', '  <Content>']
    for p in sd.paras:
        if p["e"] in NON_PRINTING or not p["t"].strip():
            continue
        t = p["t"].upper() if p["e"] in UPPERCASE_ELEMENTS else p["t"]
        out.append(f'    <Paragraph Type="{rev[p["e"]]}"><Text>{html.escape(t)}</Text></Paragraph>')
    out.append("  </Content>")
    if sd.title.get("title"):
        out.append("  <TitlePage><Content>")
        for k in ("title", "credit", "author", "source", "contact"):
            if sd.title.get(k):
                out.append(f'    <Paragraph Alignment="Center"><Text>{html.escape(sd.title[k])}</Text></Paragraph>')
        out.append("  </Content></TitlePage>")
    out.append("</FinalDraft>")
    return "\n".join(out) + "\n"


# ================================================================ OLD CELTX (2.x desktop)
# A .celtx file is a zip: project.rdf (the index: document names, types,
# scenes, catalog/breakdown) plus one HTML file per document and one
# "scratch-*.html" scratchpad per script.
CELTX_MAP = {"sceneheading": HEADING, "action": ACTION, "character": CHARACTER,
             "parenthetical": PAREN, "dialog": DIALOGUE, "dialogue": DIALOGUE,
             "transition": TRANSITION, "shot": SHOT}
# Celtx breakdown departments -> our categories
CELTX_DEPTS = {
    "cast": "Cast", "extras": "Extras", "props": "Props", "wardrobe": "Wardrobe",
    "makeup": "Hair & Makeup", "specialeffects": "Practical / Mechanical FX",
    "opticalfx": "Visual FX", "soundfx": "Sound FX", "sound": "Sound FX",
    "music": "Music", "stunts": "Stunts", "vehicles": "Vehicles", "weapons": "Weapons",
    "animals": "Animals", "livestock": "Animals", "setdressing": "Set Dressing",
    "painting": "Set Dressing", "greenery": "Set Dressing", "set": "Locations",
    "location": "Locations", "scenery": "Set Dressing", "specialequipment": "Special Equipment",
    "productionnotes": "Production Notes", "security": "Production Notes",
    "construction": "Set Dressing", "electrics": "Special Equipment",
    "camera": "Special Equipment", "lightequipment": "Special Equipment",
    "miscellaneous": "Production Notes", "additionallabour": "Extras",
}
_RDF = "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}"
_CX = "{http://celtx.com/NS/v1/}"
_DC = "{http://purl.org/dc/elements/1.1/}"


class _CeltxHTML(HTMLParser):
    """Collects <p class=...> paragraphs (scripts) and headings (text docs)."""

    def __init__(self):
        super().__init__()
        self.paras, self.meta = [], {}
        self.title = ""
        self._cls, self._buf, self._in_title = None, [], False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("p", "h1", "h2", "h3", "li", "div"):
            self._flush()
            self._cls = (a.get("class") or ("#" + tag if tag.startswith("h") else "action")).lower()
            self._id = a.get("id", "")
            self._buf = []
        elif tag == "br" and self._cls is not None:
            self._buf.append("\n")
        elif tag == "meta" and a.get("name"):
            self.meta[a["name"]] = a.get("content", "")
        elif tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag in ("p", "h1", "h2", "h3", "li", "div"):
            self._flush()
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif self._cls is not None:
            self._buf.append(data)

    def _flush(self):
        if self._cls is not None:
            raw = "".join(self._buf)
            self.paras.append((self._cls, raw, getattr(self, "_id", "")))
        self._cls, self._buf = None, []


def _one_line(t: str) -> str:
    return re.sub(r"\s+", " ", t).strip()


def _html_text(body: str) -> str:
    """Scratchpad / plain HTML -> text."""
    body = re.sub(r"(?is)<(head|style|script)[^>]*>.*?</\1>", "", body)
    body = re.sub(r"(?i)<br\s*/?>", "\n", body)
    body = re.sub(r"(?i)</(p|div|h\d|li)>", "\n\n", body)
    text = html.unescape(re.sub(r"<[^>]+>", "", body))
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _celtx_index(z: zipfile.ZipFile):
    """Read project.rdf -> (project title, [doc dicts in library order], lookup helpers)."""
    rdf = next((n for n in z.namelist() if n.endswith("project.rdf")), None)
    if not rdf:
        return "", [], {}, {}
    root = ET.fromstring(z.read(rdf))
    by_about, seqs = {}, {}
    for e in root:
        about = e.get(_RDF + "about")
        if e.tag == _RDF + "Seq":
            seqs.setdefault(about, []).extend(
                (li.get(_RDF + "resource") or (li.text or "").strip()) for li in e.findall(_RDF + "li"))
        elif about:
            # a resource can appear as both a Seq and a typed node; keep the typed node
            by_about.setdefault(about, e) if e.tag != _RDF + "Description" or about not in by_about else None
            if e.tag != _RDF + "Seq" and (about not in by_about or by_about[about].tag == _RDF + "Description"):
                by_about[about] = e
    proj_title, order = "", []
    for e in root:
        if e.tag == _CX + "Project":
            proj_title = e.get(_DC + "title", "")
            comp = e.find(_CX + "components")
            if comp is not None:
                seen = set()

                def walk(res):
                    if res in seen:
                        return
                    seen.add(res)
                    node = by_about.get(res)
                    if node is not None and node.tag == _CX + "Document":
                        order.append(res)
                    for child in seqs.get(res, []):
                        walk(child)
                walk(comp.get(_RDF + "resource"))
    docs = []
    all_docs = [e.get(_RDF + "about") for e in root if e.tag == _CX + "Document"]
    for res in order + [d for d in all_docs if d not in order]:
        e = by_about[res]
        dt = e.find(_CX + "doctype")
        docs.append({
            "res": res, "title": e.get(_DC + "title") or "Untitled",
            "file": e.get(_CX + "localFile"), "aux": e.get(_CX + "auxFile"),
            "type": (dt.get(_RDF + "resource") if dt is not None else "").rsplit("/", 1)[-1],
            "node": e})
    return proj_title, docs, by_about, seqs


def _celtx_breakdown(doc_node, by_about, seqs):
    """{scene id in the HTML: [breakdown items]} from the Celtx scene catalog."""
    out = {}
    sc = doc_node.find(_CX + "scenes")
    if sc is None:
        return out
    for res in seqs.get(sc.get(_RDF + "resource"), []):
        scene = by_about.get(res)
        if scene is None:
            continue
        sid = scene.get(_CX + "sceneid")
        items = []
        m = scene.find(_CX + "members")
        for dl_res in seqs.get(m.get(_RDF + "resource"), []) if m is not None else []:
            dl = by_about.get(dl_res)
            dept = ""
            if dl is not None and dl.find(_CX + "department") is not None:
                dept = dl.find(_CX + "department").get(_RDF + "resource", "").rsplit("/", 1)[-1]
            for item_res in seqs.get(dl_res, []):
                item = by_about.get(item_res)
                if item is None:
                    continue
                kind = dept or item.tag.split("}")[-1]
                cat = CELTX_DEPTS.get(kind.lower(), "Production Notes")
                name = item.get(_DC + "title") or ""
                if name:
                    items.append({"cat": cat, "item": name,
                                  "char": name.upper() if cat == "Cast" else "", "note": ""})
        if sid:
            out[sid] = items
    return out


def import_celtx(path: str | Path):
    """Read an old Celtx 2.x desktop project.

    Returns (project title, [dict(name, kind, data, scratch)]), where kind is
    'screenplay' (data = ScriptData) or 'novel' (data = markdown text).
    """
    docs = []
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        proj_title, index, by_about, seqs = _celtx_index(z)
        if not index:  # no usable index: fall back to every script file
            index = [{"title": Path(n).stem, "file": n, "aux": None,
                      "type": "ScriptDocument" if "script" in n else "TextDocument", "node": None}
                     for n in sorted(names) if n.endswith((".html", ".htm")) and not n.startswith("scratch")]
        for d in index:
            f = d["file"]
            if not f or f not in names:
                continue  # catalog, sketch, calendar etc. have no text to import
            body = z.read(f).decode("utf-8", "replace")
            parser = _CeltxHTML()
            parser.feed(body)
            parser._flush()
            scratch = ""
            if d.get("aux") and d["aux"] in names:
                scratch = _html_text(z.read(d["aux"]).decode("utf-8", "replace"))
            if d["type"] == "ScriptDocument" or (d["type"] == "" and
                                                 any(c == "sceneheading" for c, _, _ in parser.paras)):
                sd = ScriptData()
                bd = _celtx_breakdown(d["node"], by_about, seqs) if d["node"] is not None else {}
                for cls, raw, pid in parser.paras:
                    t = _one_line(raw)
                    if not t:
                        continue
                    e = CELTX_MAP.get(cls, ACTION)
                    p = {"e": e, "t": t}
                    if e == HEADING:
                        p["sid"] = new_id()
                        sd.scenes[p["sid"]] = {"synopsis": "", "items": list(bd.get(pid, []))}
                    sd.paras.append(p)
                m = parser.meta
                sd.title = {k: v for k, v in {
                    "title": d["title"],
                    "credit": "Written by" if m.get("Author") else "",
                    "author": m.get("Author", ""), "source": m.get("DC.source", ""),
                    "copyright": m.get("DC.rights", ""), "contact": m.get("CX.contact", ""),
                }.items() if v}
                docs.append({"name": d["title"], "kind": "screenplay", "data": sd, "scratch": scratch})
            else:
                lines = []
                for cls, raw, _ in parser.paras:
                    t = raw.strip()
                    if not t:
                        continue
                    if cls.startswith("#h"):
                        lines.append("#" * int(cls[2]) + " " + _one_line(t))
                    else:
                        lines.append(re.sub(r"[ \t]+", " ", t).strip())
                text = "\n\n".join(lines) if lines else _html_text(body)
                docs.append({"name": d["title"], "kind": "novel", "data": text, "scratch": scratch})
    return proj_title, docs


# ================================================================ PROJECT
@dataclass
class Doc:
    id: str
    name: str
    kind: str  # 'screenplay' | 'novel'
    script: ScriptData | None = None
    text: str = ""          # novel markdown
    scratch: str = ""
    title: dict = field(default_factory=dict)  # novel title page

    @property
    def ext(self):
        return ".fountain" if self.kind == "screenplay" else ".md"


def safe_name(s: str) -> str:
    s = re.sub(r"[^\w\- ]+", "", s).strip().replace(" ", "_")
    return s or "untitled"


class Project:
    def __init__(self, name="Untitled"):
        self.name = name
        self.path: Path | None = None   # path to the .goredraft manifest
        self.docs: list[Doc] = []

    @property
    def folder(self) -> Path | None:
        return self.path.parent if self.path else None

    def add_doc(self, name, kind) -> Doc:
        d = Doc(new_id(), name, kind)
        if kind == "screenplay":
            d.script = ScriptData()
            d.script.title["title"] = name
        else:
            d.title = {"title": name}
        self.docs.append(d)
        return d

    # -- save: plain text files, one per document, plus a small JSON manifest
    def save(self, path: Path | None = None):
        if path:
            self.path = Path(path)
        assert self.path
        folder = self.folder
        (folder / "docs").mkdir(parents=True, exist_ok=True)
        (folder / "scratch").mkdir(exist_ok=True)
        used = set()
        manifest = {"app": APP_NAME, "version": APP_VERSION, "name": self.name, "docs": []}
        for d in self.docs:
            base = safe_name(d.name)
            fname, k = base, 2
            while fname.lower() in used:
                fname, k = f"{base}_{k}", k + 1
            used.add(fname.lower())
            file = f"docs/{fname}{d.ext}"
            if d.kind == "screenplay":
                (folder / file).write_text(write_fountain(d.script), encoding="utf-8")
            else:
                (folder / file).write_text(d.text, encoding="utf-8")
            entry = {"id": d.id, "name": d.name, "kind": d.kind, "file": file}
            if d.scratch.strip():
                sfile = f"scratch/{fname}.txt"
                (folder / sfile).write_text(d.scratch, encoding="utf-8")
                entry["scratch"] = sfile
            if d.kind == "novel":
                entry["title"] = d.title
            manifest["docs"].append(entry)
        self.path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path) -> "Project":
        path = Path(path)
        m = json.loads(path.read_text(encoding="utf-8"))
        p = cls(m.get("name", path.stem))
        p.path = path
        for e in m.get("docs", []):
            d = Doc(e.get("id") or new_id(), e["name"], e["kind"])
            f = path.parent / e["file"]
            text = f.read_text(encoding="utf-8") if f.exists() else ""
            if d.kind == "screenplay":
                d.script = parse_fountain(text)
            else:
                d.text = text
                d.title = e.get("title", {"title": d.name})
            if e.get("scratch"):
                sf = path.parent / e["scratch"]
                if sf.exists():
                    d.scratch = sf.read_text(encoding="utf-8")
            p.docs.append(d)
        return p
