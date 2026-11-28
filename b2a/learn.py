"""The feedback loop: what the script writer is told about earlier Shorts.

Three inputs, all kept in DATA_DIR:
- notes.json: the owner's standing notes ("never open with a question"). Added on the dashboard,
  or ticked "also for future Shorts" when a Short is redone with feedback.
- the numbers of posted Shorts (meta.json "analytics", reported by the dashboard every hour from
  Postiz), compared per creative choice: format, hook type, length, how much of it is dialogue,
  music mood, book.
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
                      "engagement": eng(m), "format": m.get("format"), "seconds": m.get("duration_seconds")}
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
    }


def _numbers_text(perf: dict[str, Any]) -> str:
    lines = [f"Results of our own posted Shorts ({perf['posts']} Shorts, median {perf['median_views']} views). "
             "They are a signal, not a rule: groups with 1 or 2 Shorts can be luck."]
    for key, title in (("format", "By format"), ("hook_type", "By hook type"), ("length", "By length"),
                       ("talk", "Dialogue vs narrator"), ("music", "By music mood")):
        groups = [g for g in perf.get(key) or [] if g["name"] != "?"]
        if len(groups) > 1:
            lines.append(f"{title}: " + ", ".join(f"{g['name']} {g['vs_typical']}x ({g['posts']})" for g in groups))
    lines.append("Hooks that did best:\n" + "\n".join(
        f"- \"{b['hook']}\" ({b['views']} views, {b['format']}, engagement {b['engagement']}%)" for b in perf["best"]))
    if perf.get("worst"):
        lines.append("Hooks that did worst:\n" + "\n".join(
            f"- \"{w['hook']}\" ({w['views']} views, {w['format']})" for w in perf["worst"]))
    return "\n".join(lines)


# --- Claude's playbook ---------------------------------------------------------------

PLAYBOOK_SYSTEM = """You coach the script writer of an animated YouTube Shorts / TikTok channel \
about philosophy and psychology books (two recurring characters, a calm philosopher and an \
impatient youth). From the channel's own numbers and the owner's notes, write at most 8 short, \
concrete rules for the next scripts: what to do more, what to stop. Only claim what the numbers \
support; say "test" for weak signals (groups of 1 or 2). The owner's notes always win over the \
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
                   f"{_numbers_text(perf)}\n\nThe owner's notes:\n{owner}"}], 4000)
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
