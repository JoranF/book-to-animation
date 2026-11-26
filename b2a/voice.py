"""Step 2: voiceover with one consistent voice, plus word timings.

Three ways to get a voice:
- "elevenlabs": ElevenLabs with your own ELEVENLABS_API_KEY. Best quality, and
  the narrator, the philosopher and the youth each get their own voice.
- "fal": ElevenLabs through fal (one narrator voice).
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


# --- fal (ElevenLabs) -------------------------------------------------------

def voice_fal(script: dict[str, Any], out_dir: Path, audio_duration: Callable[[Path], float]) -> tuple[Path, list[Word]]:
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


# --- piper (free, local) ------------------------------------------------------

def piper_model() -> Path:
    path = Path(config.PIPER_MODEL)
    if not path.exists():
        raise RuntimeError(f"Piper voice model not found at {path}")
    return path


def speaker_of(scene: dict[str, Any]) -> str:
    speaker = scene.get("speaker") or "narrator"
    return speaker if speaker in config.SPEAKERS else "narrator"


def join_parts(parts: list[Path], gap: float, audio: Path) -> Path:
    """Glue the per-scene recordings together with a short pause in between."""
    inputs: list[str] = []
    for part in parts:
        inputs += ["-i", str(part)]
    chain = "".join(f"[{i}:a]apad=pad_dur={gap}[a{i}];" for i in range(len(parts)))
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

def voice_elevenlabs(script: dict[str, Any], out_dir: Path, audio_duration: Callable[[Path], float]) -> tuple[Path, list[Word]]:
    """One request per scene with exact timings; each speaker has a voice."""
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        raise RuntimeError("ELEVENLABS_API_KEY is not set")
    parts_dir = out_dir / "voice_parts"
    parts_dir.mkdir(parents=True, exist_ok=True)
    scenes = script["scenes"]
    words: list[Word] = []
    parts: list[Path] = []
    cursor, gap = 0.0, 0.12
    for i, scene in enumerate(scenes):
        text = scene["narration"].strip()
        body: dict[str, Any] = {"text": text, "model_id": config.ELEVENLABS_MODEL}
        # Neighbouring lines keep the melody natural across scene cuts.
        if i > 0 and speaker_of(scenes[i - 1]) == speaker_of(scene):
            body["previous_text"] = scenes[i - 1]["narration"].strip()
        if i + 1 < len(scenes) and speaker_of(scenes[i + 1]) == speaker_of(scene):
            body["next_text"] = scenes[i + 1]["narration"].strip()
        voice_id = config.ELEVENLABS_VOICES[speaker_of(scene)]
        resp = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps",
            params={"output_format": "mp3_44100_128"},
            headers={"xi-api-key": key}, json=body, timeout=120)
        if resp.status_code >= 400:
            raise RuntimeError(f"ElevenLabs failed ({resp.status_code}): {resp.text[:300]}")
        data = resp.json()
        part = parts_dir / f"{i:02d}.mp3"
        part.write_bytes(base64.b64decode(data["audio_base64"]))
        seconds = audio_duration(part)
        timed = align_to_script(text, parse_timestamps(data.get("alignment"))) or even_timings(text, seconds)
        words += [{"text": w["text"], "start": w["start"] + cursor, "end": w["end"] + cursor} for w in timed]
        cursor += seconds + gap
        parts.append(part)
    return join_parts(parts, gap, out_dir / "voice.wav"), words


def make_voice(script: dict[str, Any], out_dir: Path,
               audio_duration: Callable[[Path], float]) -> tuple[Path, list[Word], str]:
    """Returns the audio file, word timings and which voice was used."""
    backends = {"elevenlabs": voice_elevenlabs, "fal": voice_fal, "piper": voice_piper}
    if config.TTS_BACKEND != "auto":
        order = [config.TTS_BACKEND]
    else:
        order = (["elevenlabs"] if os.environ.get("ELEVENLABS_API_KEY") else []) \
            + (["fal"] if os.environ.get("FAL_KEY") else []) + ["piper"]
    for name in order:
        try:
            return (*backends[name](script, out_dir, audio_duration), name)
        except (RuntimeError, requests.RequestException) as exc:
            if name == order[-1]:
                raise
            print(f"[voice] {name} voice not available, trying the next one ({exc})")
    raise RuntimeError("no voice backend available")
