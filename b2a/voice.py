"""Step 2: voiceover with one consistent voice, plus word timings.

Two ways to get a voice:
- "elevenlabs": ElevenLabs with your own ELEVENLABS_API_KEY. Best quality, and
  the narrator, the philosopher and the youth each get their own voice.
- "piper": a free voice that runs on our own server. No key, no cost.
TTS_BACKEND=auto (default) picks the best one that has a key and falls back to
piper when a paid voice is not available.

A scene may say who speaks with "speaker": narrator (default), philosopher or
youth.
"""
from __future__ import annotations

import base64
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

import requests

from . import config

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
    """Accept the shapes ElevenLabs returns for timestamps."""
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


def even_timings(text: str, duration: float, offset: float = 0.0) -> list[Word]:
    """Spread words over a stretch of audio by their length."""
    tokens = text.split()
    total = sum(len(t) + 1 for t in tokens) or 1
    words, cursor = [], offset
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


# --- piper (free, local) ------------------------------------------------------

def piper_model() -> Path:
    path = Path(config.PIPER_MODEL)
    if not path.exists():
        raise RuntimeError(f"Piper voice model not found at {path}")
    return path


def speaker_of(scene: dict[str, Any]) -> str:
    speaker = scene.get("speaker") or "narrator"
    return speaker if speaker in config.SPEAKERS else "narrator"


def join_parts(parts: list[Path], gap: float | list[float], audio: Path) -> Path:
    """Glue the per-scene recordings together with a short pause in between."""
    inputs: list[str] = []
    for part in parts:
        inputs += ["-i", str(part)]
    gaps = gap if isinstance(gap, list) else [gap] * len(parts)
    chain = "".join(f"[{i}:a]apad=pad_dur={gaps[i]}[a{i}];" for i in range(len(parts)))
    chain += "".join(f"[a{i}]" for i in range(len(parts))) + f"concat=n={len(parts)}:v=0:a=1[a]"
    proc = subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *inputs,
                           "-filter_complex", chain, "-map", "[a]", str(audio)],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed joining the voice: {proc.stderr[-500:]}")
    return audio


def voice_piper(script: dict[str, Any], out_dir: Path, audio_duration: Callable[[Path], float]) -> tuple[Path, list[Word]]:
    """One audio file per scene, so scene cuts and captions line up exactly."""
    parts_dir = out_dir / "voice_parts"
    parts_dir.mkdir(parents=True, exist_ok=True)
    words: list[Word] = []
    parts: list[Path] = []
    cursor, gap = 0.0, 0.22
    for i, scene in enumerate(script["scenes"]):
        part = parts_dir / f"{i:02d}.wav"
        cmd = [sys.executable, "-m", "piper", "-m", str(piper_model()), "-f", str(part),
               "--length-scale", str(config.PIPER_LENGTH_SCALE), "--sentence-silence", "0.18"]
        speaker = config.PIPER_SPEAKERS.get(speaker_of(scene))
        speaker = config.PIPER_SPEAKER if speaker is None else speaker
        if speaker is not None:
            cmd += ["-s", str(speaker)]
        proc = subprocess.run(cmd, input=scene["narration"].strip(), capture_output=True, text=True)
        if proc.returncode != 0 or not part.exists():
            raise RuntimeError(f"piper failed: {proc.stderr[-500:]}")
        seconds = audio_duration(part)
        words += even_timings(scene["narration"], seconds, cursor)
        cursor += seconds + gap
        parts.append(part)
    return join_parts(parts, gap, out_dir / "voice.wav"), words


# --- ElevenLabs (own key) -----------------------------------------------------

TAG = re.compile(r"\s*\[[^\]\n]{1,40}\]\s*")


def strip_tags(text: str) -> str:
    """Remove delivery tags like [sighs] or [pause]: they are spoken as acting, not as words."""
    return re.sub(r"\s+", " ", TAG.sub(" ", text)).strip()


def drop_tag_characters(alignment: dict[str, Any] | None) -> dict[str, Any] | None:
    """Timings may include the characters of the tags; captions must not."""
    if not alignment or "characters" not in alignment:
        return alignment
    starts = alignment.get("character_start_times_seconds") or []
    ends = alignment.get("character_end_times_seconds") or []
    keep, depth = [], 0
    for i, ch in enumerate(alignment["characters"]):
        depth += ch == "["
        if depth == 0:
            keep.append(i)
        depth -= ch == "]" and depth > 0
    return {"characters": [alignment["characters"][i] for i in keep],
            "character_start_times_seconds": [starts[i] for i in keep if i < len(starts)],
            "character_end_times_seconds": [ends[i] for i in keep if i < len(ends)]}


def acts(model: str) -> bool:
    """Models that understand delivery tags such as [sighs] and [pause]."""
    return model.startswith(("eleven_v3", "eleven_v4"))


class ModelRejected(RuntimeError):
    pass


def _elevenlabs_run(script: dict[str, Any], out_dir: Path, audio_duration: Callable[[Path], float],
                    key: str, model: str) -> tuple[Path, list[Word]]:
    parts_dir = out_dir / "voice_parts"
    parts_dir.mkdir(parents=True, exist_ok=True)
    scenes = script["scenes"]
    words: list[Word] = []
    parts: list[Path] = []
    gaps: list[float] = []
    cursor = 0.0
    for i, scene in enumerate(scenes):
        text = scene["narration"].strip()
        body: dict[str, Any] = {"model_id": model, "voice_settings": {
            "stability": config.ELEVENLABS_STABILITY, "similarity_boost": 0.75}}
        if acts(model):
            # The acting model gets the line with its delivery tags and pauses.
            body["text"] = (scene.get("voice_text") or text).strip()
        else:
            body["text"] = text
            # Neighbouring lines keep the melody natural across scene cuts.
            if i > 0 and speaker_of(scenes[i - 1]) == speaker_of(scene):
                body["previous_text"] = scenes[i - 1]["narration"].strip()
            if i + 1 < len(scenes) and speaker_of(scenes[i + 1]) == speaker_of(scene):
                body["next_text"] = scenes[i + 1]["narration"].strip()
        voice_id = config.ELEVENLABS_VOICES[speaker_of(scene)]
        resp = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps",
            params={"output_format": "mp3_44100_128"},
            headers={"xi-api-key": key}, json=body, timeout=180)
        if resp.status_code in (400, 404, 422):
            raise ModelRejected(f"ElevenLabs refused model {model} ({resp.status_code}): {resp.text[:300]}")
        if resp.status_code >= 400:
            raise RuntimeError(f"ElevenLabs failed ({resp.status_code}): {resp.text[:300]}")
        data = resp.json()
        part = parts_dir / f"{i:02d}.mp3"
        part.write_bytes(base64.b64decode(data["audio_base64"]))
        seconds = audio_duration(part)
        timed = parse_timestamps(drop_tag_characters(data.get("alignment")))
        timed = align_to_script(text, timed) if len(timed) == len(text.split()) else even_timings(text, seconds)
        words += [{"text": w["text"], "start": w["start"] + cursor, "end": w["end"] + cursor} for w in timed]
        # A beat of silence when the other person answers, less inside one turn.
        gap = 0.16 if i + 1 < len(scenes) and speaker_of(scenes[i + 1]) != speaker_of(scene) else 0.08
        gaps.append(gap)
        cursor += seconds + gap
        parts.append(part)
    return join_parts(parts, gaps, out_dir / "voice.wav"), words


def voice_elevenlabs(script: dict[str, Any], out_dir: Path, audio_duration: Callable[[Path], float]) -> tuple[Path, list[Word]]:
    """One request per scene with exact timings; each speaker has a voice.

    Tries the configured model first (the expressive one that follows delivery
    tags) and falls back to the older model when the account or the endpoint
    does not accept it."""
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        raise RuntimeError("ELEVENLABS_API_KEY is not set")
    models = list(dict.fromkeys([config.ELEVENLABS_MODEL, config.ELEVENLABS_FALLBACK_MODEL]))
    for model in models:
        try:
            result = _elevenlabs_run(script, out_dir, audio_duration, key, model)
            used_model.update(name=model)
            return result
        except ModelRejected as exc:
            if model == models[-1]:
                raise RuntimeError(str(exc)) from exc
            print(f"[voice] {exc}; trying {models[-1]}")
    raise RuntimeError("no ElevenLabs model available")


used_model: dict[str, str] = {}


def make_voice(script: dict[str, Any], out_dir: Path,
               audio_duration: Callable[[Path], float]) -> tuple[Path, list[Word], str]:
    """Returns the audio file, word timings and which voice was used."""
    backends = {"elevenlabs": voice_elevenlabs, "piper": voice_piper}
    if config.TTS_BACKEND != "auto":
        order = [config.TTS_BACKEND]
    else:
        order = (["elevenlabs"] if os.environ.get("ELEVENLABS_API_KEY") else []) + ["piper"]
    for name in order:
        try:
            return (*backends[name](script, out_dir, audio_duration), name)
        except (RuntimeError, requests.RequestException) as exc:
            if name == order[-1]:
                raise
            print(f"[voice] {name} voice not available, trying the next one ({exc})")
    raise RuntimeError("no voice backend available")
