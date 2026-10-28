"""Reports: plain HTML built from a ScriptData. No Qt needed."""
from __future__ import annotations

import math
import re
from collections import OrderedDict, defaultdict
from html import escape as esc

from .model import (ACTION, BEAT, CATEGORIES, CATEGORY_COLOURS, CHARACTER,
                    DIALOGUE, HEADING, MAKEUP_CATEGORIES, NON_PRINTING, PAREN,
                    SHOT, SPFX_CATEGORIES, TRANSITION, ScriptData, beat_info,
                    SAVE_THE_CAT)

LINES_PER_PAGE = 55
MINUTES_PER_PAGE = 1.0   # the industry rule of thumb; adjustable in the app


def fmt_runtime(minutes: float) -> str:
    """1.5 -> '1m 30s'; 95 -> '1h 35m'"""
    secs = int(round(minutes * 60))
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m:02d}m"
    return f"{m}m {s:02d}s" if m else f"{s}s"


def timecode(minutes: float) -> str:
    secs = int(round(minutes * 60))
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}"


def word_count(sd: ScriptData) -> int:
    return sum(len(p["t"].split()) for p in sd.paras if p["e"] not in NON_PRINTING)
WIDTH = {HEADING: 61, ACTION: 61, SHOT: 61, TRANSITION: 61,
         CHARACTER: 38, DIALOGUE: 35, PAREN: 25}

CSS = """
<style>
body { font-family: 'Courier Prime', 'Courier New', monospace; color:#111; }
h1 { color:#b3121a; font-size:20pt; margin:0; letter-spacing:2px; }
h2 { color:#b3121a; font-size:13pt; margin-top:18px; border-bottom:2px solid #b3121a; }
h3 { font-size:11pt; margin:10px 0 2px 0; }
.sub { color:#666; font-size:9pt; }
table { border-collapse:collapse; }
th { background:#1a1418; color:#fff; padding:4px 6px; text-align:left; font-size:9pt; }
td { padding:3px 6px; border-bottom:1px solid #ddd; font-size:9pt; vertical-align:top; }
.tag { font-weight:bold; }
.box { font-size:12pt; }
.empty { color:#888; font-style:italic; }
</style>
"""


def _clean_char(name: str) -> str:
    """JENNY (V.O.) -> JENNY ; JENNY (CONT'D) -> JENNY"""
    return re.sub(r"\s*\(.*?\)\s*", " ", name.upper()).replace("^", "").strip()


def para_lines(p) -> int:
    w = WIDTH.get(p["e"], 61)
    n = max(1, math.ceil(len(p["t"]) / w))
    return n


def estimate_pages(sd: ScriptData) -> float:
    lines, prev = 0, None
    for p in sd.paras:
        if p["e"] in NON_PRINTING or not p["t"].strip():
            continue
        if not (p["e"] in (PAREN, DIALOGUE) and prev in (CHARACTER, PAREN, DIALOGUE)):
            lines += 1
        lines += para_lines(p)
        prev = p["e"]
    return lines / LINES_PER_PAGE


def scenes(sd: ScriptData):
    """List of dicts with everything a report wants to know about each scene."""
    out, cur, prev, lines = [], None, None, 0
    beat = ""
    for p in sd.paras:
        if p["e"] == BEAT:
            beat = p["t"]
            continue
        if p["e"] == HEADING:
            cur = {"n": len(out) + 1, "heading": p["t"].upper(), "sid": p.get("sid"),
                   "chars": OrderedDict(), "lines": 0, "dialogue": []}
            data = sd.scenes.get(p.get("sid"), {})
            cur["synopsis"] = data.get("synopsis", "")
            cur["items"] = data.get("items", [])
            cur["beat"] = beat
            out.append(cur)
        if cur is None:
            cur = {"n": 0, "heading": "(BEFORE FIRST SCENE)", "sid": None, "chars": OrderedDict(),
                   "lines": 0, "dialogue": [], "synopsis": "", "items": [], "beat": beat}
            out.append(cur)
        add = para_lines(p) + (0 if (p["e"] in (PAREN, DIALOGUE) and prev in (CHARACTER, PAREN, DIALOGUE)) else 1)
        cur["lines"] += add
        if p["e"] == CHARACTER:
            c = _clean_char(p["t"])
            if c:
                cur["chars"][c] = cur["chars"].get(c, 0) + 1
                cur["dialogue"].append([c, "", ""])
        elif p["e"] == PAREN and cur["dialogue"]:
            cur["dialogue"][-1][1] = p["t"]
        elif p["e"] == DIALOGUE and cur["dialogue"]:
            d = cur["dialogue"][-1]
            d[2] = (d[2] + " " + p["t"]).strip()
        prev = p["e"]
    return out


def _eighths(lines: int) -> str:
    e = max(1, round(lines / LINES_PER_PAGE * 8))
    whole, rem = divmod(e, 8)
    if whole and rem:
        return f"{whole} {rem}/8"
    return f"{whole}" if whole else f"{rem}/8"


def _header(title: str, sd: ScriptData, extra="") -> str:
    t = sd.title.get("title", "Untitled")
    return (f"{CSS}<h1>{esc(title)}</h1><div class='sub'>{esc(t)} &middot; "
            f"{len(scenes(sd))} scenes &middot; ~{estimate_pages(sd):.1f} pages {extra}</div>")


def _chip(cat: str) -> str:
    c = CATEGORY_COLOURS.get(cat, "#999")
    return f"<span class='tag' style='color:{c}'>&#9632;</span> {esc(cat)}"


# ---------------------------------------------------------------- reports
def scene_breakdown(sd: ScriptData, with_description=True) -> str:
    h = [_header("SCENE BREAKDOWN", sd)]
    h.append("<table width='100%'><tr><th>#</th><th>Scene</th><th>Length</th>"
             "<th>Cast</th><th>Breakdown</th></tr>")
    for s in scenes(sd):
        cast = ", ".join(s["chars"].keys()) or "<span class='empty'>-</span>"
        items = "<br>".join(f"{_chip(i['cat'])}: {esc(i['item'])}" for i in s["items"]) \
            or "<span class='empty'>-</span>"
        desc = f"<br><i>{esc(s['synopsis'])}</i>" if with_description and s["synopsis"] else ""
        h.append(f"<tr><td><b>{s['n']}</b></td><td><b>{esc(s['heading'])}</b>{desc}</td>"
                 f"<td>{_eighths(s['lines'])}</td><td>{esc(cast) if s['chars'] else cast}</td><td>{items}</td></tr>")
    h.append("</table>")
    return "".join(h)


def dialogue(sd: ScriptData, character: str | None = None) -> str:
    h = [_header("DIALOGUE", sd, f"&middot; {esc(character)}" if character else "")]
    per = defaultdict(list)
    for s in scenes(sd):
        for c, paren, line in s["dialogue"]:
            per[c].append((s["n"], paren, line))
    if not per:
        return "".join(h) + "<p class='empty'>No dialogue yet.</p>"
    h.append("<h2>Line count</h2><table><tr><th>Character</th><th>Speeches</th><th>Words</th></tr>")
    for c, lines in sorted(per.items(), key=lambda kv: -len(kv[1])):
        words = sum(len(l[2].split()) for l in lines)
        h.append(f"<tr><td><b>{esc(c)}</b></td><td>{len(lines)}</td><td>{words}</td></tr>")
    h.append("</table>")
    for c, lines in sorted(per.items()):
        if character and c != character:
            continue
        h.append(f"<h2>{esc(c)}</h2><table width='100%'>")
        for n, paren, line in lines:
            h.append(f"<tr><td width='40'>Sc {n}</td><td>{esc(paren)} {esc(line)}</td></tr>")
        h.append("</table>")
    return "".join(h)


def elements(sd: ScriptData) -> str:
    h = [_header("ELEMENTS BY CATEGORY", sd)]
    per = OrderedDict((c, []) for c in CATEGORIES)
    for s in scenes(sd):
        for i in s["items"]:
            per.setdefault(i["cat"], []).append((s["n"], i))
    any_ = False
    for cat, rows in per.items():
        if not rows:
            continue
        any_ = True
        h.append(f"<h2>{_chip(cat)} ({len(rows)})</h2><table width='100%'>"
                 "<tr><th>Sc</th><th>Item</th><th>Character</th><th>Notes</th></tr>")
        for n, i in rows:
            h.append(f"<tr><td>{n}</td><td>{esc(i['item'])}</td><td>{esc(i.get('char',''))}</td>"
                     f"<td>{esc(i.get('note',''))}</td></tr>")
        h.append("</table>")
    if not any_:
        h.append("<p class='empty'>Nothing tagged yet. Select text in the script, right-click, "
                 "and tag it — or use the Breakdown panel.</p>")
    return "".join(h)


def makeup_continuity(sd: ScriptData) -> str:
    """The SPFX makeup tracker: per character, in scene order, so you can see
    a wound progress through the film and build the right number of repeats."""
    h = [_header("SFX MAKEUP CONTINUITY", sd)]
    per = OrderedDict()
    unassigned = []
    total = 0
    blood_scenes = set()
    for s in scenes(sd):
        for i in s["items"]:
            if i["cat"] not in MAKEUP_CATEGORIES:
                continue
            total += 1
            if i["cat"] == "Blood & Gore":
                blood_scenes.add(s["n"])
            who = _clean_char(i.get("char", ""))
            if who:
                per.setdefault(who, []).append((s, i))
            else:
                unassigned.append((s, i))
    h.append(f"<p><b>{total}</b> makeup effects &middot; <b>{len(per)}</b> characters in makeup "
             f"&middot; blood in <b>{len(blood_scenes)}</b> scenes</p>")
    if not total:
        return "".join(h) + "<p class='empty'>No makeup effects tagged yet.</p>"
    for who, rows in per.items():
        h.append(f"<h2>{esc(who)}</h2><table width='100%'><tr><th>Sc</th><th>Scene</th>"
                 "<th>Effect</th><th>Category</th><th>Notes / repeats</th></tr>")
        for s, i in rows:
            h.append(f"<tr><td>{s['n']}</td><td>{esc(s['heading'])}</td><td><b>{esc(i['item'])}</b></td>"
                     f"<td>{_chip(i['cat'])}</td><td>{esc(i.get('note',''))}</td></tr>")
        h.append("</table>")
    if unassigned:
        h.append("<h2>NOT ASSIGNED TO A CHARACTER</h2><table width='100%'><tr><th>Sc</th>"
                 "<th>Scene</th><th>Effect</th><th>Category</th><th>Notes</th></tr>")
        for s, i in unassigned:
            h.append(f"<tr><td>{s['n']}</td><td>{esc(s['heading'])}</td><td><b>{esc(i['item'])}</b></td>"
                     f"<td>{_chip(i['cat'])}</td><td>{esc(i.get('note',''))}</td></tr>")
        h.append("</table>")
    return "".join(h)


def gag_sheet(sd: ScriptData) -> str:
    """Workshop checklist: every practical/makeup gag in shooting-script order
    with boxes to tick off as it's built, tested, and on set."""
    h = [_header("GAG SHEET", sd, "&middot; workshop checklist")]
    h.append("<table width='100%'><tr><th>Sc</th><th>Gag</th><th>Type</th><th>Who</th>"
             "<th>Notes</th><th>Built</th><th>Tested</th><th>On set</th></tr>")
    n = 0
    for s in scenes(sd):
        for i in s["items"]:
            if i["cat"] not in SPFX_CATEGORIES:
                continue
            n += 1
            h.append(f"<tr><td>{s['n']}</td><td><b>{esc(i['item'])}</b></td><td>{_chip(i['cat'])}</td>"
                     f"<td>{esc(i.get('char',''))}</td><td>{esc(i.get('note',''))}</td>"
                     "<td class='box'>&#9744;</td><td class='box'>&#9744;</td><td class='box'>&#9744;</td></tr>")
    h.append("</table>")
    if not n:
        h.append("<p class='empty'>No practical or makeup gags tagged yet.</p>")
    return "".join(h)


def cast_report(sd: ScriptData) -> str:
    h = [_header("CAST & SCENES", sd)]
    per = OrderedDict()
    for s in scenes(sd):
        names = set(s["chars"].keys())
        names |= {_clean_char(i["item"]) for i in s["items"] if i["cat"] == "Cast"}
        for c in names:
            if c:
                per.setdefault(c, []).append(s["n"])
    if not per:
        return "".join(h) + "<p class='empty'>No characters yet.</p>"
    h.append("<table width='100%'><tr><th>Character</th><th>Scenes</th><th>Count</th></tr>")
    for c, ns in sorted(per.items(), key=lambda kv: -len(kv[1])):
        h.append(f"<tr><td><b>{esc(c)}</b></td><td>{', '.join(map(str, ns))}</td><td>{len(ns)}</td></tr>")
    h.append("</table>")
    return "".join(h)


def page_at(sd: ScriptData, para_index: int) -> float:
    """Estimated page number where paragraph `para_index` falls."""
    lines, prev = 0, None
    for p in sd.paras[:para_index]:
        if p["e"] in NON_PRINTING or not p["t"].strip():
            continue
        if not (p["e"] in (PAREN, DIALOGUE) and prev in (CHARACTER, PAREN, DIALOGUE)):
            lines += 1
        lines += para_lines(p)
        prev = p["e"]
    return 1 + lines / LINES_PER_PAGE


def beat_report(sd: ScriptData) -> str:
    try:
        target = int(str(sd.title.get("target", "")).strip() or 100)
    except ValueError:
        target = 100
    h = [_header("BEAT SHEET", sd, f"&middot; target {target} pages")]
    beats = [(i, p["t"]) for i, p in enumerate(sd.paras) if p["e"] == BEAT]
    if not beats:
        return "".join(h) + ("<p class='empty'>No beat markers in this script. Use Script &rarr; "
                             "Insert Save the Cat Beats to add the guide.</p>")
    sc_by_beat = defaultdict(list)
    for s in scenes(sd):
        sc_by_beat[s.get("beat", "")].append(s)
    h.append("<table width='100%'><tr><th>Beat</th><th>Aim</th><th>Yours</th><th>Status</th>"
             "<th>Scenes</th></tr>")
    for idx, name in beats:
        info = beat_info(name)
        yours = page_at(sd, idx)
        if info:
            lo, hi = max(1.0, info[1] * target), max(1.0, info[2] * target)
            aim = f"p.{round(lo)}" if round(lo) == round(hi) else f"pp.{round(lo)}-{round(hi)}"
            slack = max(2, target * 0.03)
            if yours < lo - slack:
                status = "<span style='color:#1f6feb'>early</span>"
            elif yours > hi + slack:
                status = "<span style='color:#b3121a'><b>late</b></span>"
            else:
                status = "<span style='color:#2da44e'>on track</span>"
        else:
            aim, status = "-", "-"
        scs = ", ".join(str(s["n"]) for s in sc_by_beat.get(name, [])) or "<span class='empty'>-</span>"
        h.append(f"<tr><td><b>{esc(name.split('(')[0].strip())}</b>"
                 f"{'<br><i>' + esc(info[3]) + '</i>' if info else ''}</td>"
                 f"<td>{aim}</td><td>p.{yours:.0f}</td><td>{status}</td><td>{scs}</td></tr>")
    h.append("</table><p class='sub'>Beat structure after Blake Snyder's <i>Save the Cat</i>. "
             "Pages are estimates; treat early/late as a nudge, not a rule.</p>")
    return "".join(h)


def runtime_report(sd: ScriptData) -> str:
    pages = estimate_pages(sd)
    total = pages * MINUTES_PER_PAGE
    h = [_header("RUNTIME", sd, f"&middot; ≈ <b>{fmt_runtime(total)}</b> at "
                                f"{MINUTES_PER_PAGE:g} min/page")]
    h.append(f"<p>Estimated screen time <b>{fmt_runtime(total)}</b> from ~{pages:.1f} pages "
             f"&middot; {word_count(sd):,} words.</p>")
    rows = scenes(sd)
    if not rows:
        return "".join(h) + "<p class='empty'>No scenes yet.</p>"
    h.append("<table width='100%'><tr><th>#</th><th>Scene</th><th>Beat</th><th>Length</th>"
             "<th>Est. time</th><th>Starts at</th><th>FX</th></tr>")
    t = 0.0
    longest = max(rows, key=lambda r: r["lines"])
    for r in rows:
        mins = r["lines"] / LINES_PER_PAGE * MINUTES_PER_PAGE
        fx = sum(1 for i in r["items"] if i["cat"] in SPFX_CATEGORIES)
        mark = " style='background:#fbe9ea'" if r is longest and len(rows) > 2 else ""
        h.append(f"<tr{mark}><td>{r['n']}</td><td><b>{esc(r['heading'])}</b></td>"
                 f"<td>{esc(r.get('beat','').split('(')[0].strip())}</td>"
                 f"<td>{_eighths(r['lines'])} pg</td><td>{fmt_runtime(mins)}</td>"
                 f"<td>{timecode(t)}</td><td>{fx or ''}</td></tr>")
        t += mins
    h.append(f"<tr><td></td><td><b>TOTAL</b></td><td></td><td><b>{pages:.1f} pg</b></td>"
             f"<td><b>{fmt_runtime(total)}</b></td><td>{timecode(t)}</td><td></td></tr></table>")
    h.append("<p class='sub'>Page-a-minute is a rule of thumb. Dialogue-heavy scenes usually play "
             "faster; action, stalking and FX set pieces usually play slower. Change minutes per page "
             "under View if your scripts tend to run long.</p>")
    return "".join(h)


SCREENPLAY_REPORTS = OrderedDict([
    ("Runtime", runtime_report),
    ("Beat Sheet", beat_report),
    ("SFX Makeup Continuity", makeup_continuity),
    ("Gag Sheet", gag_sheet),
    ("Scene Breakdown", lambda sd: scene_breakdown(sd, False)),
    ("Scene Breakdown with Description", scene_breakdown),
    ("Elements", elements),
    ("Dialogue", dialogue),
    ("Cast & Scenes", cast_report),
])


def novel_stats(title: str, text: str) -> str:
    chapters, cur = [], None
    for line in text.splitlines():
        if line.startswith("# "):
            cur = [line[2:].strip(), 0]
            chapters.append(cur)
        else:
            if cur is None:
                cur = ["(Opening)", 0]
                chapters.append(cur)
            cur[1] += len(line.split())
    total = sum(c[1] for c in chapters)
    read_min = total / 250  # average adult reading speed, words per minute
    h = [CSS, f"<h1>MANUSCRIPT STATS</h1><div class='sub'>{esc(title)} &middot; {total:,} words "
         f"&middot; ~{max(1, round(total / 250))} manuscript pages &middot; "
         f"~{fmt_runtime(read_min)} reading time</div>"]
    h.append("<table width='100%'><tr><th>#</th><th>Chapter</th><th>Words</th></tr>")
    for n, (name, w) in enumerate(chapters, 1):
        h.append(f"<tr><td>{n}</td><td>{esc(name)}</td><td>{w:,}</td></tr>")
    h.append("</table>")
    return "".join(h)
