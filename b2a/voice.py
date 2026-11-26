"""Step 2: voiceover with one consistent voice, plus word timings."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from . import config, fal

Word = dict[str, Any]  # {"text": str, "start": float, "end": float}


def narration_text(script: dict[str, Any]) -> str:
    return " ".join(s["narration"].strip() for s in script["scenes"])


def words_from_characters(chars: list[str], starts: list[float], ends: list[float]) -> list[Word]:
    """Group character-level timings into words."""
    words: list[Word] = []
    current: Word | None = None
    for ch, start, end in zip(chars, starts, ends):
        if ch.isspace():
            current = None
            continue
        if current is None:
            current = {"text": ch, "start": float(start), "end": float(end)}
            words.append(current)
        else:
            current["text"] += ch
            current["end"] = float(end)
    return words


def parse_timestamps(raw: Any) -> list[Word]:
    """Accept the shapes fal/ElevenLabs return for timestamps."""
    if not raw:
        return []
    if isinstance(raw, dict):
        raw = [raw]
    words: list[Word] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        item = item.get("alignment") or item
        if "characters" in item:
            words += words_from_characters(
                item["characters"],
                item.get("character_start_times_seconds") or item.get("start_times") or [],
                item.get("character_end_times_seconds") or item.get("end_times") or [],
            )
        elif "start" in item and "end" in item:
            text = str(item.get("text") or item.get("word") or "").strip()
            if text and item.get("type", "word") == "word":
                words.append({"text": text, "start": float(item["start"]), "end": float(item["end"])})
    return words


def even_timings(text: str, duration: float) -> list[Word]:
    """Last resort: spread words over the audio by their length."""
    tokens = text.split()
    total = sum(len(t) + 1 for t in tokens) or 1
    words, cursor = [], 0.0
    for token in tokens:
        span = duration * (len(token) + 1) / total
        words.append({"text": token, "start": cursor, "end": cursor + span})
        cursor += span
    return words


def align_to_script(script_text: str, timed: list[Word]) -> list[Word]:
    """Use the script's own spelling when the word counts line up."""
    tokens = script_text.split()
    if len(tokens) == len(timed):
        return [{**w, "text": t} for t, w in zip(tokens, timed)]
    return timed


def make_voice(script: dict[str, Any], out_dir: Path, audio_duration) -> tuple[Path, list[Word]]:
    text = narration_text(script)
    result = fal.run(config.TTS_MODEL, {"text": text, "voice": config.TTS_VOICE, "timestamps": True})
    url = result["audio"]["url"]
    ext = re.sub(r"[^a-z0-9]", "", url.rsplit(".", 1)[-1].lower())[:4] or "mp3"
    audio = fal.download(url, out_dir / f"voice.{ext}")

    words = parse_timestamps(result.get("timestamps"))
    if not words:
        try:
            stt = fal.run(config.STT_MODEL, {"audio_url": url, "language_code": "eng",
                                             "diarize": False, "tag_audio_events": False})
            words = parse_timestamps(stt.get("words"))
        except RuntimeError:
            words = []
    if not words:
        words = even_timings(text, audio_duration(audio))
    return audio, align_to_script(text, words)


def scene_times(script: dict[str, Any], words: list[Word], total: float) -> list[tuple[float, float]]:
    """Start and end of every scene, cut on the first word of its narration."""
    counts = [len(s["narration"].split()) for s in script["scenes"]]
    scale = len(words) / max(sum(counts), 1)
    starts, index = [], 0
    for count in counts:
        pos = min(int(round(index * scale)), len(words) - 1)
        starts.append(0.0 if index == 0 else max(words[pos]["start"] - 0.08, 0.0))
        index += count
    return [(s, (starts[i + 1] if i + 1 < len(starts) else total)) for i, s in enumerate(starts)]
