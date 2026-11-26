"""Book + idea in, finished Short out. Every step is cached in the job folder,
so a failed run continues where it stopped."""
from __future__ import annotations

import json
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from . import config, llm, plan as plan_mod, render, script as script_mod, visuals, voice as voice_mod


def shorts_dir() -> Path:
    return config.DATA_DIR / "shorts"


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "short"


def _load(path: Path) -> Any:
    return json.loads(path.read_text()) if path.exists() else None


def _save(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def new_id(topic: str) -> str:
    return f"{datetime.now(timezone.utc):%Y%m%d-%H%M%S}-{_slug(topic)}-{uuid.uuid4().hex[:4]}"


def estimate_cost(script: dict[str, Any], tokens: dict[str, int] | None, voice_backend: str) -> float:
    """Pictures and music are made on our own server, so only Claude and ElevenLabs cost money."""
    p = config.PRICES
    tokens = tokens or {}
    cost = (tokens.get("input_tokens", 0) * p["llm_in_per_mtok"]
            + tokens.get("output_tokens", 0) * p["llm_out_per_mtok"]) / 1e6
    if voice_backend == "elevenlabs":
        cost += len(voice_mod.narration_text(script)) / 1000 * p["tts_per_1k_chars"]
    return round(cost, 2)


def made_episodes(book_slug: str) -> set[str]:
    return {m["episode"] for m in list_shorts() if m.get("book") == book_slug and m.get("episode")}


def make_short(book_slug: str, topic: str = "", idea: str = "", short_id: str | None = None,
               script: dict[str, Any] | None = None,
               progress: Callable[[str], None] = print,
               episode_id: str | None = None) -> dict[str, Any]:
    """Make one Short: from an episode of the plan ("next" = first one not made
    yet), or from a free topic and idea."""
    book = script_mod.load_book(book_slug)
    earlier = list_shorts()
    job = shorts_dir() / short_id if short_id else None
    state = (job and _load(job / "state.json")) or {"tokens": None, "voice": None, "episode": None}
    if state.get("episode"):                       # continuing an earlier run
        episode = state["episode"]
    elif episode_id == "next":
        episode = plan_mod.next_episode(book_slug, made_episodes(book_slug))
    elif episode_id:
        episode = plan_mod.find_episode(book_slug, episode_id)
    elif topic:
        episode = plan_mod.adhoc_episode(topic, idea, len(earlier))
    else:
        raise ValueError("Give an episode or a topic")
    state["episode"] = episode
    topic = episode["title"]
    short_id = short_id or new_id(f"{episode['id']}-{topic}" if episode["id"] else topic)
    job = shorts_dir() / short_id
    job.mkdir(parents=True, exist_ok=True)
    started = time.time()

    progress("script")
    script = script or _load(job / "script.json")
    example = config.BOOKS_DIR / book_slug / "examples" / f"{episode['id']}.json"
    if script is None and example.exists():
        script = _load(example)     # hand-checked script for this exact episode
    if script is None:
        before = dict(llm.usage)
        avoid = [m["hook"] for m in earlier[:15] if m.get("hook")]
        script = script_mod.write_script(book, episode, script_mod.load_learnings(), avoid)
        state["tokens"] = {k: llm.usage[k] - before[k] for k in before}
    script = script_mod.validate(script, book)
    _save(job / "script.json", script)
    _save(job / "state.json", state)

    progress("voice")
    words = _load(job / "words.json")
    voice = next(iter(job.glob("voice.*")), None)
    if not (words and voice):
        voice, words, state["voice"] = voice_mod.make_voice(script, job, render.duration)
        _save(job / "words.json", words)
    _save(job / "state.json", state)
    total = render.duration(voice) + config.TAIL_SECONDS
    times = voice_mod.scene_times(script, words, total)

    progress("visuals")
    scenes = visuals.make_visuals(script, times, job)
    music = visuals.make_music(job, total, short_id)

    progress("render")
    video = render.render(scenes, times, voice, words, music, job / "work", job / "short.mp4")
    render.thumbnail(video, job / "thumb.jpg")

    meta = {
        "id": short_id,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "book": book_slug,
        "episode": episode["id"],
        "chapter": episode.get("chapter"),
        "format": episode.get("format"),
        "topic": topic,
        "idea": idea or episode.get("angle") or "",
        "title": script["title"],
        "hook": script["hook"],
        "hook_type": script.get("hook_type"),
        "description": script.get("description"),
        "hashtags": script.get("hashtags"),
        "language": "en",
        "duration_seconds": round(total, 1),
        "word_count": len(voice_mod.narration_text(script).split()),
        "scene_count": len(scenes),
        "sets": [s.get("stage", {}).get("set") for s in script["scenes"]],
        "voice": ("elevenlabs:" + config.ELEVENLABS_VOICES["narrator"] if state["voice"] == "elevenlabs"
                  else f"piper:{Path(config.PIPER_MODEL).stem}#{config.PIPER_SPEAKER}"),
        "speakers": sorted({voice_mod.speaker_of(s) for s in script["scenes"]}),
        "visuals": "blender",
        "script_model": config.SCRIPT_MODEL if state.get("tokens") else "manual",
        "script_tokens": state.get("tokens"),
        "estimated_cost_usd": estimate_cost(script, state.get("tokens"), state["voice"] or "piper"),
        "render_seconds": round(time.time() - started),
        "files": {"video": "short.mp4", "thumbnail": "thumb.jpg", "script": "script.json"},
        # Filled in later by the upload + analytics steps (feedback loop).
        "youtube": {"video_id": None, "published_at": None},
        "analytics": {"views": None, "avg_view_percentage": None, "likes": None,
                      "comments": None, "subscribers_gained": None, "updated_at": None},
    }
    _save(job / "meta.json", meta)
    progress("done")
    return meta


def list_shorts() -> list[dict[str, Any]]:
    metas = [_load(p) for p in sorted(shorts_dir().glob("*/meta.json"), reverse=True)]
    return [m for m in metas if m]
