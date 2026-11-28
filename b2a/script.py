"""Step 1: write the script. Own words, original examples, no book quotes."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from . import config, llm, music, plan as plan_mod, stage as stage_mod
from .voice import strip_tags

SYSTEM = """You write scripts for a YouTube Shorts channel that explains ideas \
from philosophy and psychology books as short animated stories.

Hard rules:
- Explain the IDEA in your own words. Never quote or closely paraphrase the \
book. No sentences from the book, no chapter structure, no character lines \
from the book. Do not mention the book title or authors in the narration.
- Use fresh, concrete, modern examples that are NOT in the book.
- This Short covers ONE narrow idea (the episode below). Do not summarise the \
book or touch its other ideas. A viewer who has seen ten other Shorts from \
this series must still find this one new.
- Spoken English, simple words, short sentences, second person ("you").
- 95 to 125 words of narration in total (about 40 to 50 seconds).
- The first sentence is the hook: under 14 words, creates tension or \
curiosity, no greeting, no "did you know".
- End with one question or one line that makes people comment or rewatch.
- 9 to 14 scenes. Each scene is ONE line: 1 or 2 short sentences.

Visuals: a late-90s low-poly 3D game world with two recurring characters:
{characters}
Each scene needs:
- "speaker": who says this scene's line: "narrator", "philosopher" or \
"youth", each with their own voice. The Short is a CONVERSATION, not a \
lecture: at least half of the scenes are the youth and the philosopher \
talking to each other, and each line reacts to the line before it. The youth \
is impatient and a bit sarcastic: he objects, cuts in, jokes, gets it wrong. \
The philosopher stays calm and answers short, with a twist or a question \
back. A character line is at most 12 words. No speeches, no "As I said". The \
narrator only does quick set-ups and bridges (the hook may be said by a \
character instead). Whoever speaks must be an actor in that scene.
- Engagement comes first: tension in the first two seconds, a new beat every \
3 to 4 seconds, one moment of friction or humour between the two, and the \
answer to the hook only near the end.
- "narration" is acted by a voice model that follows delivery tags in square \
brackets. Direct it like an actor: start a line with one tag for the emotion \
when it helps ([sighs], [laughs], [whispers], [shouts], [curious], \
[mischievously], [annoyed], [deadpan]) and put [pause] or [long pause] \
exactly where a beat of silence makes the line land: before a punchline, \
after a hard question, before the last line. Use "..." for a trailing-off \
thought and a dash for a cut-off. At most 2 tags per line, none on most \
narrator lines. Tags are not shown in the captions and do not count as words.
- "image": one sentence describing the picture for a human reader.
- "stage": the 3D scene, built as described below.

{guide}

Return ONLY JSON:
{{"title": "YouTube title under 60 chars", "hook": "the first sentence", \
"hook_type": "question|bold_claim|contradiction|story|you_statement", \
"description": "2 sentence YouTube description, may name the book", \
"hashtags": ["#shorts", "..."], \
"music_mood": "one of {moods}", \
"scenes": [{{"narration": "...", "speaker": "narrator", "image": "...", "stage": {{...}}}}]}}"""


def _extract_json(text: str) -> dict[str, Any]:
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise ValueError("The model did not return JSON")
    return json.loads(match.group(0))


def validate(script: dict[str, Any], book: dict[str, Any]) -> dict[str, Any]:
    scenes = script.get("scenes") or []
    if not 5 <= len(scenes) <= 16:
        raise ValueError(f"Expected 5-16 scenes, got {len(scenes)}")
    for number, scene in enumerate(scenes, 1):
        spoken = str(scene.get("voice_text") or scene.get("narration") or "").strip()
        if not strip_tags(spoken):
            raise ValueError(f"Scene {number} is missing 'narration'")
        scene["voice_text"] = spoken                 # with [tags], for the voice
        scene["narration"] = strip_tags(spoken)      # clean, for captions and timing
        if scene.get("speaker") not in config.SPEAKERS:
            scene["speaker"] = "narrator"
        try:
            scene["stage"] = stage_mod.validate(scene.get("stage") or dict(stage_mod.DEFAULT))
        except ValueError as exc:
            raise ValueError(f"Scene {number} stage: {exc}") from exc
        for actor in scene["stage"]["actors"]:      # the speaker's mouth moves
            if actor["who"] == scene["speaker"]:
                actor["talking"] = True
    words = sum(len(s["narration"].split()) for s in scenes)
    if not 60 <= words <= 160:
        raise ValueError(f"Narration has {words} words, expected 60-160")
    script.setdefault("hook", scenes[0]["narration"])
    script.setdefault("title", script["hook"][:60])
    script.setdefault("hook_type", "unknown")
    script.setdefault("description", "")
    script.setdefault("hashtags", ["#shorts"])
    if script.get("music_mood") not in music.MOODS:
        script.pop("music_mood", None)            # the editor picks one
    return script


def write_script(book: dict[str, Any], episode: dict[str, Any], learnings: str = "",
                 avoid: list[str] | None = None, trends_brief: str = "",
                 previous: dict[str, Any] | None = None, feedback: str = "") -> dict[str, Any]:
    """Write the script for one episode (see plan.py for what an episode is)."""
    characters = "\n".join(
        f'- "{key}": {c["prompt"]}' for key, c in book["characters"].items()
    )
    fmt = episode.get("format") if episode.get("format") in plan_mod.FORMATS else "reframe"
    user = (
        f"Book: {book['title']} ({book.get('school', '')}).\n"
        f"What the book is about (background only): {book['summary']}\n\n"
        f"Episode: {episode['title']}\n"
    )
    if episode.get("chapter"):
        user += f"Part of the book: {episode['chapter']}\n"
    if episode.get("angle"):
        user += f"The one idea and angle: {episode['angle']}\n"
    if episode.get("hook"):
        user += f"Planned hook (keep it or make it sharper): {episode['hook']}\n"
    user += f"Format \"{fmt}\": {plan_mod.FORMATS[fmt]}\n"
    if avoid:
        user += ("\nHooks of Shorts we already made. Yours must sound and be built "
                 "differently, with a different example and opening scene:\n"
                 + "\n".join(f"- {h}" for h in avoid) + "\n")
    if learnings:
        user += (
            "\nWhat worked and did not work on this channel so far "
            f"(use it):\n{learnings}\n"
        )
    if trends_brief:
        user += (
            "\nWhat is working in this niche on Shorts and TikTok right now (research "
            "from the last weeks). Use what fits this one idea; never copy a hook or "
            f"a title:\n{trends_brief}\n"
        )
    if previous and feedback:
        old = {k: previous.get(k) for k in ("title", "hook", "hook_type", "description", "hashtags", "music_mood")}
        old["scenes"] = [{"speaker": sc.get("speaker"), "narration": sc.get("voice_text") or sc.get("narration"),
                          "image": sc.get("image"), "stage": sc.get("stage")} for sc in previous.get("scenes") or []]
        user += (
            "\nThis is a REDO. The earlier version of this Short (JSON):\n"
            f"{json.dumps(old, ensure_ascii=False)}\n\n"
            f"The channel owner watched it and wants this changed:\n{feedback.strip()}\n"
            "Write a new version that does what the feedback asks. Keep what the feedback does "
            "not mention when it worked; every hard rule above still applies.\n"
        )
    system = SYSTEM.format(characters=characters, guide=stage_mod.GUIDE,
                           moods="|".join(music.MOODS))
    messages: list[dict[str, Any]] = [{"role": "user", "content": user}]
    error: Exception | None = None
    for _ in range(3):
        text = llm.ask(system, messages)
        try:
            return validate(_extract_json(text), book)
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            error = exc
            messages += [{"role": "assistant", "content": text or "(empty)"},
                         {"role": "user", "content": f"Invalid: {exc}. Return the corrected JSON only."}]
    raise RuntimeError(f"Could not get a valid script: {error}")


def load_book(slug: str) -> dict[str, Any]:
    path = config.BOOKS_DIR / slug / "book.json"
    if not path.exists():
        raise FileNotFoundError(f"Unknown book '{slug}' (no {path})")
    return json.loads(path.read_text())


def load_learnings() -> str:
    """The owner's notes, the numbers of posted Shorts and Claude's playbook (see learn.py)."""
    from . import learn, pipeline
    return learn.text(pipeline.list_shorts())
