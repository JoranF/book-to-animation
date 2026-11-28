"""The feedback loop: what the script writer is told about earlier Shorts.

Three inputs, all kept in DATA_DIR:
- notes.json: the owner's standing notes ("never open with a question"). Added on the dashboard,
  or ticked "also for future Shorts" when a Short is redone with feedback.
- the numbers of posted Shorts (meta.json "analytics", reported by the dashboard every hour from
  Postiz and YouTube Analytics), compared per creative choice: format, hook type, length, how much of
  it is dialogue, music mood, book. With YouTube connected on the dashboard they include retention:
  average % watched, the share still watching after 3 s (the hook) and the drop-off points, which
  are traced back to the scene and the words spoken at that moment.
- playbook.json: a short list of rules Claude writes from those numbers and notes once there are
  enough posted Shorts. Refreshed at most once a day, so it costs a few cents a week.

text() puts them together; script.load_learnings() hands that to every new script. A legacy
DATA_DIR/learnings.md written by hand is included too.
"""
from __future__ import annotations

import json
import re
import threading
import time
import uuid
from pathlib import Path
from statistics import median
from typing import Any

from . import config

MIN_POSTS = 5          # posted Shorts with views before the numbers are used at all
PLAYBOOK_POSTS = 8     # ... before Claude writes a playbook from them
PLAYBOOK_EVERY = 86400
MAX_NOTES = 40
_lock = threading.Lock()


def _path(name: str) -> Path:
    return config.DATA_DIR / name


def _read(name: str, default: Any) -> Any:
    try:
        return json.loads(_path(name).read_text())
    except (OSError, ValueError):
        return default


def _write(name: str, data: Any) -> None:
    p = _path(name)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False))
    tmp.replace(p)


# --- the owner's notes ------------------------------------------------------------

def notes() -> list[dict[str, Any]]:
    return _read("notes.json", [])


def add_note(text: str, source: str = "") -> list[dict[str, Any]]:
    text = re.sub(r"\s+", " ", text or "").strip()[:1000]
    if len(text) < 3:
        raise ValueError("A note needs a few words")
    with _lock:
        current = [n for n in notes() if n.get("text") != text]
        current.insert(0, {"id": uuid.uuid4().hex[:10], "text": text, "at": time.time(), "source": source})
        _write("notes.json", current[:MAX_NOTES])
        return current[:MAX_NOTES]


def delete_note(note_id: str) -> list[dict[str, Any]]:
    with _lock:
        current = [n for n in notes() if n.get("id") != note_id]
        _write("notes.json", current)
        return current


# --- the numbers -------------------------------------------------------------------

def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _short_file(meta: dict[str, Any], name: str) -> Any:
    try:
        return json.loads((config.DATA_DIR / "shorts" / str(meta.get("id")) / name).read_text())
    except (OSError, ValueError):
        return None


def drop_offs(meta: dict[str, Any]) -> list[dict[str, Any]]:
    """The dashboard's drop-off points of a Short, with the scene and the words at that moment."""
    drops = (meta.get("analytics") or {}).get("drop_offs") or []
    if not drops:
        return []
    times = meta.get("scene_times")
    script_json = _short_file(meta, "script.json") or {}
    scenes = script_json.get("scenes") or []
    words = _short_file(meta, "words.json") or []
    if not times and scenes and words:
        from .voice import scene_times
        try:
            times = scene_times(script_json, words, float(meta.get("duration_seconds") or 0))
        except (KeyError, TypeError, ValueError, IndexError):
            times = None
    out = []
    for d in drops:
        at = _num(d.get("at"))
        if at is None:
            continue
        item = {"at": at, "lost": _num(d.get("lost"))}
        for i, (a, b) in enumerate(times or []):
            if a <= at < b:
                item["scene"] = i + 1
                if i < len(scenes):
                    item["speaker"] = scenes[i].get("speaker")
                    item["line"] = str(scenes[i].get("narration") or "")[:120]
                break
        said = [str(w.get("text") or w.get("word") or "").strip() for w in words if isinstance(w, dict)
                and isinstance(w.get("start"), (int, float)) and at - 2 <= w["start"] <= at + 0.5]
        if said:
            item["said"] = " ".join(said)[:120]
        out.append(item)
    return out


def _length(seconds: Any) -> str:
    s = float(seconds or 0)
    return "under 30s" if s < 30 else "30-45s" if s < 45 else "over 45s"


def _talk(meta: dict[str, Any]) -> str:
    speakers = set(meta.get("speakers") or [])
    return "dialogue" if {"philosopher", "youth"} <= speakers else "mostly narrator"


def performance(shorts: list[dict[str, Any]]) -> dict[str, Any]:
    """Views per creative choice, for the Shorts that have numbers."""
    rows = [m for m in shorts if isinstance((m.get("analytics") or {}).get("views"), (int, float))]
    if not rows:
        return {"posts": 0}
    views = lambda m: m["analytics"]["views"]
    typical = median(views(m) for m in rows) or 1

    def group(key):
        out: dict[str, list[float]] = {}
        for m in rows:
            out.setdefault(str(key(m) or "?"), []).append(views(m))
        return sorted(({"name": k, "posts": len(v), "median_views": int(median(v)),
                        "vs_typical": round(median(v) / typical, 2)} for k, v in out.items()),
                      key=lambda g: -g["median_views"])

    def eng(m):
        a = m["analytics"]
        v = max(views(m), 1)
        return round(100 * ((a.get("likes") or 0) + 2 * (a.get("comments") or 0) + 3 * (a.get("shares") or 0)) / v, 1)

    pick = lambda m: {"id": m["id"], "hook": m.get("hook"), "title": m.get("title"), "views": int(views(m)),
                      "engagement": eng(m), "format": m.get("format"), "seconds": m.get("duration_seconds"),
                      "watched": _num(m["analytics"].get("avg_view_percentage")), "hold_3s": _num(m["analytics"].get("hold_3s"))}
    ranked = sorted(rows, key=views, reverse=True)
    return {
        "posts": len(rows), "median_views": int(typical),
        "format": group(lambda m: m.get("format")),
        "hook_type": group(lambda m: m.get("hook_type")),
        "length": group(lambda m: _length(m.get("duration_seconds"))),
        "talk": group(_talk),
        "music": group(lambda m: (m.get("music") or {}).get("mood") if isinstance(m.get("music"), dict) else None),
        "book": group(lambda m: m.get("book")),
        "best": [pick(m) for m in ranked[:5]],
        "worst": [pick(m) for m in ranked[-5:][::-1]] if len(ranked) > 5 else [],
        "retention": retention(rows),
    }


def retention(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Watch % and hook hold per creative choice, and where viewers leave, for Shorts with YouTube data."""
    have = [m for m in rows if _num(m["analytics"].get("avg_view_percentage")) is not None]
    if not have:
        return {"posts": 0}
    watched = lambda m: _num(m["analytics"].get("avg_view_percentage"))

    def group(key):
        out: dict[str, list[dict[str, Any]]] = {}
        for m in have:
            out.setdefault(str(key(m) or "?"), []).append(m)
        res = []
        for k, v in out.items():
            g = {"name": k, "posts": len(v), "watched": round(median(watched(m) for m in v), 1)}
            h = [x for m in v if (x := _num(m["analytics"].get("hold_3s"))) is not None]
            if h:
                g["hold_3s"] = round(median(h), 1)
            res.append(g)
        return sorted(res, key=lambda g: -g["watched"])

    holds = [x for m in have if (x := _num(m["analytics"].get("hold_3s"))) is not None]
    half = [x for m in have if (x := _num(m["analytics"].get("half_gone_at"))) is not None]
    drops = sorted(({"id": m["id"], "hook": m.get("hook"), "format": m.get("format"), **d}
                    for m in have for d in drop_offs(m)), key=lambda d: -(d.get("lost") or 0))
    scene_drops: dict[str, list[float]] = {}
    for d in drops:
        if d.get("scene"):
            scene_drops.setdefault("scene 1 (opening)" if d["scene"] == 1 else "scene 2" if d["scene"] == 2
                                   else "scene 3+", []).append(d.get("lost") or 0)
    by_hold = sorted((m for m in have if _num(m["analytics"].get("hold_3s")) is not None),
                     key=lambda m: -_num(m["analytics"]["hold_3s"]))
    return {
        "posts": len(have),
        "watched": round(median(watched(m) for m in have), 1),
        "hold_3s": round(median(holds), 1) if holds else None,
        "half_gone_at": round(median(half), 1) if half else None,
        "format": group(lambda m: m.get("format")),
        "hook_type": group(lambda m: m.get("hook_type")),
        "length": group(lambda m: _length(m.get("duration_seconds"))),
        "talk": group(_talk),
        "drops": drops[:10],
        "drops_by_scene": {k: {"drops": len(v), "lost": round(sum(v) / len(v), 1)} for k, v in scene_drops.items()},
        "held_best": [{"hook": m.get("hook"), "hold_3s": _num(m["analytics"]["hold_3s"])} for m in by_hold[:4]],
        "held_worst": [{"hook": m.get("hook"), "hold_3s": _num(m["analytics"]["hold_3s"])} for m in by_hold[-4:][::-1]]
        if len(by_hold) > 4 else [],
    }


def _retention_text(ret: dict[str, Any]) -> list[str]:
    if ret.get("posts", 0) < 3:
        return []
    lines = [f"Retention on YouTube ({ret['posts']} Shorts with data): viewers watch a median {ret['watched']:.0f}%."
             + (f" {ret['hold_3s']:.0f}% are still there after 3 seconds, so the hook and the first line decide most "
                "of the result." if ret.get("hold_3s") is not None else "")
             + (f" Half of the viewers are gone by {ret['half_gone_at']:.0f}s: land the key idea before then."
                if ret.get("half_gone_at") else "")]
    for key, title in (("format", "Watched by format"), ("hook_type", "Watched by hook type"), ("length", "Watched by length"),
                       ("talk", "Watched: dialogue vs narrator")):
        groups = [g for g in ret.get(key) or [] if g["name"] != "?"]
        if len(groups) > 1:
            lines.append(f"{title}: " + ", ".join(
                f"{g['name']} {g['watched']:.0f}%" + (f" ({g['hold_3s']:.0f}% past 3s)" if g.get("hold_3s") is not None else "")
                + f" [{g['posts']}]" for g in groups))
    if ret.get("drops_by_scene"):
        lines.append("Where the drop-offs happen: " + ", ".join(
            f"{k}: {v['drops']}x, -{v['lost']:.0f}% on average" for k, v in sorted(ret["drops_by_scene"].items())))
    if ret.get("drops"):
        lines.append("Biggest drop-offs (cut or tighten lines like these; avoid slow set-up before the point):\n" + "\n".join(
            f"- at {d['at']:.0f}s, -{d.get('lost') or 0:.0f}%"
            + (f", scene {d['scene']} ({d.get('speaker') or '?'}): \"{d.get('line', '')}\"" if d.get("scene") else "")
            + (f", words: \"{d['said']}\"" if d.get("said") and not d.get("line") else "")
            + f" [hook: \"{d.get('hook')}\"]" for d in ret["drops"][:6]))
    if ret.get("held_best"):
        lines.append("Hooks that kept the most viewers past 3s: " + "; ".join(
            f"\"{h['hook']}\" ({h['hold_3s']:.0f}%)" for h in ret["held_best"]))
    if ret.get("held_worst"):
        lines.append("Hooks that lost the most in the first 3s: " + "; ".join(
            f"\"{h['hook']}\" ({h['hold_3s']:.0f}%)" for h in ret["held_worst"]))
    return lines


def _numbers_text(perf: dict[str, Any]) -> str:
    lines = [f"Results of our own posted Shorts ({perf['posts']} Shorts, median {perf['median_views']} views). "
             "They are a signal, not a rule: groups with 1 or 2 Shorts can be luck."]
    for key, title in (("format", "By format"), ("hook_type", "By hook type"), ("length", "By length"),
                       ("talk", "Dialogue vs narrator"), ("music", "By music mood")):
        groups = [g for g in perf.get(key) or [] if g["name"] != "?"]
        if len(groups) > 1:
            lines.append(f"{title}: " + ", ".join(f"{g['name']} {g['vs_typical']}x ({g['posts']})" for g in groups))
    lines += _retention_text(perf.get("retention") or {})
    lines.append("Hooks that did best:\n" + "\n".join(
        f"- \"{b['hook']}\" ({b['views']} views, {b['format']}, engagement {b['engagement']}%"
        + (f", watched {b['watched']:.0f}%" if b.get("watched") is not None else "") + ")" for b in perf["best"]))
    if perf.get("worst"):
        lines.append("Hooks that did worst:\n" + "\n".join(
            f"- \"{w['hook']}\" ({w['views']} views, {w['format']})" for w in perf["worst"]))
    return "\n".join(lines)


# --- Claude's playbook ---------------------------------------------------------------

PLAYBOOK_SYSTEM = """You coach the script writer of an animated YouTube Shorts / TikTok channel \
about philosophy and psychology books (two recurring characters, a calm philosopher and an \
impatient youth). From the channel's own numbers and the owner's notes, write at most 8 short, \
concrete rules for the next scripts: what to do more, what to stop. Retention matters as much as \
views: say how to open (the first 3 seconds), how long to make it and which kind of scene or line \
makes viewers leave. Only claim what the numbers support; say "test" for weak signals (groups of 1 or 2). The owner's notes always win over the \
numbers. Return only the rules, one per line, each starting with "- "."""


def playbook() -> dict[str, Any]:
    return _read("playbook.json", {})


def refresh_playbook(shorts: list[dict[str, Any]], force: bool = False) -> dict[str, Any] | None:
    """Ask Claude for new rules when there are enough numbers and the last ones are a day old
    (or at least 3 more Shorts have numbers). Returns the new playbook, or None when skipped."""
    perf = performance(shorts)
    old = playbook()
    if perf["posts"] < PLAYBOOK_POSTS:
        return None
    if not force and old and time.time() - old.get("at", 0) < PLAYBOOK_EVERY and perf["posts"] < old.get("posts", 0) + 3:
        return None
    from . import llm
    owner = "\n".join(f"- {n['text']}" for n in notes()) or "(none)"
    text = llm.ask(PLAYBOOK_SYSTEM, [{"role": "user", "content":
                   f"{_numbers_text(perf)}\n\nThe owner's notes:\n{owner}"}], 4000,
                   model=config.ANALYSIS_MODEL, effort=config.ANALYSIS_EFFORT, step="playbook")
    rules = [line.strip() for line in text.splitlines() if line.strip().startswith("- ")][:8]
    if not rules:
        return None
    new = {"at": time.time(), "posts": perf["posts"], "rules": rules}
    _write("playbook.json", new)
    return new


def refresh_in_background(shorts_fn) -> None:
    """After new numbers arrive: refresh the playbook without blocking the request."""
    def run():
        try:
            refresh_playbook(shorts_fn())
        except Exception as exc:  # noqa: BLE001 - a missing key or a failed call only skips this round
            print(f"playbook refresh skipped: {exc}")
    threading.Thread(target=run, daemon=True).start()


# --- what the script writer gets ------------------------------------------------------

def text(shorts: list[dict[str, Any]]) -> str:
    parts = []
    owner = notes()
    if owner:
        parts.append("The channel owner's notes (always follow these):\n"
                     + "\n".join(f"- {n['text']}" for n in owner[:25]))
    legacy = _path("learnings.md")
    if legacy.exists() and legacy.read_text().strip():
        parts.append(legacy.read_text().strip())
    perf = performance(shorts)
    if perf["posts"] >= MIN_POSTS:
        pb = playbook()
        if pb.get("rules"):
            parts.append(f"Rules from the results of our last {pb['posts']} Shorts:\n" + "\n".join(pb["rules"]))
        parts.append(_numbers_text(perf))
    return "\n\n".join(parts)


def summary(shorts: list[dict[str, Any]]) -> dict[str, Any]:
    return {"text": text(shorts), "notes": notes(), "performance": performance(shorts),
            "playbook": playbook(), "min_posts": MIN_POSTS, "playbook_posts": PLAYBOOK_POSTS}
