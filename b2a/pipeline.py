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

from . import config, render, script as script_mod, visuals, voice as voice_mod


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


def estimate_cost(script: dict[str, Any], wrote_script: bool, voice_backend: str) -> float:
    """Pictures and music are made on our own server, so only fal calls cost money."""
    p = config.PRICES
    chars = len(voice_mod.narration_text(script))
    cost = (p["llm_script"] if wrote_script else 0.0)
    cost += chars / 1000 * p["tts_per_1k_chars"] if voice_backend == "fal" else 0.0
    return round(cost, 2)


def make_short(book_slug: str, topic: str, idea: str = "", short_id: str | None = None,
               script: dict[str, Any] | None = None,
               progress: Callable[[str], None] = print) -> dict[str, Any]:
    book = script_mod.load_book(book_slug)
    short_id = short_id or new_id(topic)
    job = shorts_dir() / short_id
    job.mkdir(parents=True, exist_ok=True)
    started = time.time()

    progress("script")
    script = script or _load(job / "script.json")
    state = _load(job / "state.json") or {"wrote_script": False, "voice": None}
    example = config.BOOKS_DIR / book_slug / "examples" / f"{_slug(topic)}.json"
    if script is None and example.exists() and not idea:
        script = _load(example)     # hand-checked script for this exact topic
    if script is None:
        script = script_mod.write_script(book, topic, idea, script_mod.load_learnings())
        state["wrote_script"] = True
    script = script_mod.validate(script, book)
    _save(job / "script.json", script)

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
        "topic": topic,
        "idea": idea,
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
        "voice": {"elevenlabs": "elevenlabs:" + config.ELEVENLABS_VOICES["narrator"],
                  "fal": f"elevenlabs-via-fal:{config.TTS_VOICE}"}.get(
                      state["voice"], f"piper:{Path(config.PIPER_MODEL).stem}#{config.PIPER_SPEAKER}"),
        "speakers": sorted({voice_mod.speaker_of(s) for s in script["scenes"]}),
        "visuals": "blender",
        "script_model": config.SCRIPT_MODEL if state["wrote_script"] else "manual",
        "estimated_cost_usd": estimate_cost(script, state["wrote_script"], state["voice"] or "piper"),
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
