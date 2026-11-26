"""Step 1: write the script. Own words, original examples, no book quotes."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from . import config, fal

SYSTEM = """You write scripts for a YouTube Shorts channel that explains ideas \
from philosophy and psychology books as short animated stories.

Hard rules:
- Explain the IDEA in your own words. Never quote or closely paraphrase the \
book. No sentences from the book, no chapter structure, no character lines \
from the book. Do not mention the book title or authors in the narration.
- Use fresh, concrete, modern examples that are NOT in the book.
- Spoken English, simple words, short sentences, second person ("you").
- 95 to 125 words of narration in total (about 40 to 50 seconds).
- The first sentence is the hook: under 14 words, creates tension or \
curiosity, no greeting, no "did you know".
- End with one question or one line that makes people comment or rewatch.
- 8 to 10 scenes. Each scene is 1 or 2 short sentences of narration.

Visuals: a late-90s low-poly 3D game world with two recurring characters:
{characters}
Each scene needs:
- "image": one clear, simple picture (who, doing what, where, mood). Visual \
metaphors work well. No text or signs in the picture. Mention characters by \
their key (e.g. "the youth").
- "motion": one sentence describing small movement for a 5 second animation \
(character action plus a slow camera move).
- "characters": which recurring characters appear (may be empty).

Return ONLY JSON:
{{"title": "YouTube title under 60 chars", "hook": "the first sentence", \
"hook_type": "question|bold_claim|contradiction|story|you_statement", \
"description": "2 sentence YouTube description, may name the book", \
"hashtags": ["#shorts", "..."], \
"scenes": [{{"narration": "...", "image": "...", "motion": "...", \
"characters": ["youth"]}}]}}"""


def _extract_json(text: str) -> dict[str, Any]:
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise ValueError("The model did not return JSON")
    return json.loads(match.group(0))


def validate(script: dict[str, Any], book: dict[str, Any]) -> dict[str, Any]:
    scenes = script.get("scenes") or []
    if not 5 <= len(scenes) <= 12:
        raise ValueError(f"Expected 5-12 scenes, got {len(scenes)}")
    known = set(book["characters"])
    for scene in scenes:
        for field in ("narration", "image"):
            if not str(scene.get(field, "")).strip():
                raise ValueError(f"A scene is missing '{field}'")
        scene.setdefault("motion", "Slow camera push in, gentle idle movement.")
        scene["characters"] = [c for c in scene.get("characters", []) if c in known]
    words = sum(len(s["narration"].split()) for s in scenes)
    if not 60 <= words <= 160:
        raise ValueError(f"Narration has {words} words, expected 60-160")
    script.setdefault("hook", scenes[0]["narration"])
    script.setdefault("title", script["hook"][:60])
    script.setdefault("hook_type", "unknown")
    script.setdefault("description", "")
    script.setdefault("hashtags", ["#shorts"])
    return script


def write_script(book: dict[str, Any], topic: str, idea: str = "",
                 learnings: str = "") -> dict[str, Any]:
    characters = "\n".join(
        f'- "{key}": {c["prompt"]}' for key, c in book["characters"].items()
    )
    user = (
        f"Book: {book['title']} ({book.get('school', '')}).\n"
        f"What the book is about: {book['summary']}\n"
        f"Topic for this Short: {topic}\n"
    )
    if idea:
        user += f"Angle / idea from the channel owner: {idea}\n"
    if learnings:
        user += (
            "\nWhat worked and did not work on this channel so far "
            f"(use it):\n{learnings}\n"
        )
    messages = [
        {"role": "system", "content": SYSTEM.format(characters=characters)},
        {"role": "user", "content": user},
    ]
    error: Exception | None = None
    for _ in range(3):
        try:
            return validate(_extract_json(fal.chat(config.SCRIPT_MODEL, messages)), book)
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            error = exc
            messages.append({"role": "user", "content": f"Invalid: {exc}. Return the corrected JSON only."})
    raise RuntimeError(f"Could not get a valid script: {error}")


def load_book(slug: str) -> dict[str, Any]:
    path = config.BOOKS_DIR / slug / "book.json"
    if not path.exists():
        raise FileNotFoundError(f"Unknown book '{slug}' (no {path})")
    return json.loads(path.read_text())


def load_learnings() -> str:
    path: Path = config.DATA_DIR / "learnings.md"
    return path.read_text() if path.exists() else ""
