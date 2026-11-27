"""Episode plan: one narrow idea per Short, grouped by chapter of the book.

books/<slug>/episodes.json holds the plan. Every episode has its own hook,
angle and format, so the Shorts of one book do not all feel the same.
"""
from __future__ import annotations

import json
import re
from typing import Any

from . import config, llm

FORMATS = {
    "myth_buster": "Open with a belief most people hold, then flip it.",
    "mini_story": "Tell one tiny story about one person from start to finish; the idea lands in the last scenes.",
    "one_question": "Build the whole Short around one question the viewer has to answer for themselves.",
    "dialogue": "Pure back-and-forth: the youth arrives with a complaint and the philosopher takes it apart in quick lines. No narrator after the hook.",
    "challenge": "Give the viewer one small thing to try today.",
    "reframe": "Take an everyday situation and show it from a surprising second angle.",
}


def plan_path(book_slug: str):
    return config.BOOKS_DIR / book_slug / "episodes.json"


def load_plan(book_slug: str) -> dict[str, Any] | None:
    path = plan_path(book_slug)
    return json.loads(path.read_text()) if path.exists() else None


def episodes(book_slug: str) -> list[dict[str, Any]]:
    """All episodes in order, each with the chapter it belongs to."""
    plan = load_plan(book_slug) or {"chapters": []}
    return [{**ep, "chapter": ch["title"], "chapter_id": ch["id"]}
            for ch in plan["chapters"] for ep in ch["episodes"]]


def find_episode(book_slug: str, episode_id: str) -> dict[str, Any]:
    for episode in episodes(book_slug):
        if episode["id"] == episode_id:
            return episode
    raise KeyError(f"Unknown episode '{episode_id}' for book '{book_slug}'")


def next_episode(book_slug: str, made: set[str], scores: dict[str, float] | None = None) -> dict[str, Any]:
    """The next episode that has no Short yet, taking turns between chapters.
    Within the chapter whose turn it is, the episode that fits current trends best
    goes first (scores from trends.py); without scores it is plan order."""
    todo = [ep for ep in episodes(book_slug) if ep["id"] not in made]
    if not todo:
        raise KeyError(f"Every episode of '{book_slug}' has been made")
    counts: dict[str, int] = {}
    for ep in episodes(book_slug):
        counts.setdefault(ep["chapter_id"], 0)
        counts[ep["chapter_id"]] += ep["id"] in made
    scores = scores or {}
    return min(todo, key=lambda ep: (counts[ep["chapter_id"]], -scores.get(ep["id"], 0.0)))


def adhoc_episode(topic: str, idea: str, number: int) -> dict[str, Any]:
    """A free topic typed by the owner, shaped like an episode."""
    return {"id": None, "title": topic, "hook": "", "angle": idea, "chapter": None,
            "format": list(FORMATS)[number % len(FORMATS)]}


PLAN_SYSTEM = """You plan a YouTube Shorts series about one non-fiction book. \
Split the book into its chapters or parts and list 6 to 10 episodes per chapter. \
Each episode covers ONE narrow idea, never the whole book.

Rules:
- Everything in your own words. Never quote or closely paraphrase the book.
- "hook": the first spoken sentence, under 14 words, tension or curiosity.
- "angle": 1 to 3 sentences: the single idea plus one fresh modern example \
that is NOT from the book.
- "format": one of {formats}. Spread them evenly.
- No two episodes may share a hook pattern or an example.

Return ONLY JSON: {{"chapters": [{{"id": "c1", "title": "...", "episodes": \
[{{"id": "c1-01", "title": "...", "hook": "...", "angle": "...", "format": "..."}}]}}]}}"""


def generate_plan(book: dict[str, Any]) -> dict[str, Any]:
    """Let Claude draft the episode plan for a new book. Review it before use."""
    user = f"Book: {book['title']} by {book.get('authors', '?')}.\nAbout: {book['summary']}"
    text = llm.ask(PLAN_SYSTEM.format(formats=", ".join(FORMATS)), [{"role": "user", "content": user}], 32000)
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise RuntimeError("Claude did not return a plan")
    plan = json.loads(match.group(0))
    for chapter in plan["chapters"]:
        for episode in chapter["episodes"]:
            if episode.get("format") not in FORMATS:
                episode["format"] = "reframe"
    return {"book": book["slug"], **plan}
