"""Background music.

Two sources:
- ACE-Step 1.5 (open music model, runs on our own GPU server, see musicgen/):
  instrumental tracks in a late-90s console style, one prompt per mood. Tracks
  are kept in a library (DATA_DIR/music/<mood>/) and reused, so the GPU only
  works until every mood has MUSIC_PER_MOOD tracks.
- A calm chiptune loop composed in code: free, instant, the fallback when
  ACE-Step is not set up or fails.
"""
from __future__ import annotations

import json
import random
import time
import wave
from pathlib import Path
from urllib.parse import urljoin

import numpy as np
import requests

from . import config

# Mood of a Short -> how its music should feel. The script writer picks one.
MOODS = {
    "curious": ("curious, playful, light plucky synth arpeggios, soft drums", 96, "C major"),
    "tense": ("tense, mysterious, low pulsing synth bass, ticking hi-hats, minor key", 88, "A minor"),
    "warm": ("warm, hopeful, gentle electric piano and soft pads, relaxed beat", 84, "F major"),
    "playful": ("playful, bouncy, cheeky square-wave melody, light shuffle groove", 104, "G major"),
    "melancholy": ("melancholy, reflective, slow mellow pads and music box, quiet", 76, "D minor"),
    "triumphant": ("uplifting, triumphant but calm, bright synth brass and steady drums", 100, "D major"),
}
STYLE = ("instrumental video game soundtrack from a late-1990s 3D console platformer, "
         "lo-fi PS1 and N64 era sound font, {mood}, loopable background music under dialogue, "
         "no vocals, no singing")


def default_mood(seed: int) -> str:
    return list(MOODS)[seed % len(MOODS)]


def acestep_enabled() -> bool:
    if config.MUSIC_BACKEND == "chiptune":
        return False
    return bool(config.ACESTEP_URL)


def library_dir(mood: str) -> Path:
    return config.DATA_DIR / "music" / mood


def library_track(mood: str, seed: int, seconds: float) -> Path:
    """A track for this mood: a new one while the library is not full yet, else a reused one."""
    folder = library_dir(mood)
    tracks = sorted(folder.glob("*.mp3"))
    if len(tracks) >= config.MUSIC_PER_MOOD:
        return tracks[seed % len(tracks)]
    dest = folder / f"{mood}_{len(tracks) + 1:02d}.mp3"
    return generate(mood, max(seconds, 60.0), dest, seed)


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {config.ACESTEP_API_KEY}"} if config.ACESTEP_API_KEY else {}


def _data(reply: requests.Response) -> object:
    reply.raise_for_status()
    body = reply.json()
    if body.get("code", 200) != 200 or body.get("error"):
        raise RuntimeError(f"ACE-Step error: {body.get('error')}")
    return body.get("data")


def generate(mood: str, seconds: float, dest: Path, seed: int = 0) -> Path:
    """Ask the ACE-Step API for one instrumental track and save it as mp3."""
    words, bpm, key = MOODS[mood]
    task = _data(requests.post(f"{config.ACESTEP_URL}/release_task", headers=_headers(), timeout=60, json={
        "prompt": STYLE.format(mood=words),
        "lyrics": "[Instrumental]",
        "instrumental": True,
        "audio_duration": round(min(seconds, 180)),
        "bpm": bpm,
        "key_scale": key,
        "time_signature": "4",
        "thinking": False,             # no language model needed: we give every setting
        "use_cot_caption": False,
        "use_cot_language": False,
        "inference_steps": 8,
        "batch_size": 1,
        "use_random_seed": False,
        "seed": seed % 2**31,
        "audio_format": "mp3",
    }))
    task_id = task["task_id"]                                            # type: ignore[index]
    deadline = time.time() + config.ACESTEP_TIMEOUT
    while time.time() < deadline:
        time.sleep(5)
        rows = _data(requests.post(f"{config.ACESTEP_URL}/query_result", headers=_headers(), timeout=30,
                                   json={"task_id_list": [task_id]}))
        row = rows[0] if isinstance(rows, list) and rows else {}         # type: ignore[index]
        if row.get("status") == 2:
            raise RuntimeError(f"ACE-Step could not make the track: {str(row.get('result'))[:300]}")
        if row.get("status") == 1:
            result = row.get("result")
            files = json.loads(result) if isinstance(result, str) else result
            url = urljoin(config.ACESTEP_URL + "/", files[0]["file"].lstrip("/"))
            audio = requests.get(url, headers=_headers(), timeout=120)
            audio.raise_for_status()
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_suffix(".part")
            tmp.write_bytes(audio.content)
            tmp.replace(dest)
            dest.with_suffix(".json").write_text(json.dumps(
                {"mood": mood, "prompt": STYLE.format(mood=words), "bpm": bpm, "key": key,
                 "seed": seed % 2**31, "seconds": round(min(seconds, 180))}, indent=2))
            return dest
    raise RuntimeError(f"ACE-Step took longer than {config.ACESTEP_TIMEOUT:.0f} s")


def fill_library(moods: list[str] | None = None, seconds: float = 75.0) -> list[Path]:
    """Make every missing track at once (e.g. at night), instead of during a Short."""
    made = []
    for mood in moods or list(MOODS):
        while len(sorted(library_dir(mood).glob("*.mp3"))) < config.MUSIC_PER_MOOD:
            count = len(sorted(library_dir(mood).glob("*.mp3")))
            made.append(generate(mood, seconds, library_dir(mood) / f"{mood}_{count + 1:02d}.mp3", count + 1))
    return made


# --- chiptune made in code (free fallback) ----------------------------------

RATE = 44100
NOTES = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
# Mellow four-chord loops (root, chord tones as semitones above the root).
PROGRESSIONS = [
    [("C", (0, 4, 7, 11)), ("A", (0, 3, 7, 10)), ("F", (0, 4, 7, 11)), ("G", (0, 4, 7, 9))],
    [("F", (0, 4, 7, 11)), ("G", (0, 4, 7, 9)), ("E", (0, 3, 7, 10)), ("A", (0, 3, 7, 10))],
    [("D", (0, 3, 7, 10)), ("G", (0, 4, 7, 9)), ("C", (0, 4, 7, 11)), ("A", (0, 3, 7, 10))],
    [("A", (0, 3, 7, 10)), ("F", (0, 4, 7, 11)), ("C", (0, 4, 7, 11)), ("G", (0, 4, 7, 9))],
]


def _freq(note: str, octave: int, semis: int = 0) -> float:
    return 440.0 * 2 ** ((NOTES[note] + semis + (octave - 4) * 12 - 9) / 12)


def _tone(freq: float, seconds: float, shape: str, decay: float) -> np.ndarray:
    t = np.arange(int(seconds * RATE)) / RATE
    phase = (t * freq) % 1.0
    if shape == "pulse":
        sound = np.where(phase < 0.25, 1.0, -1.0)
    elif shape == "triangle":
        sound = 4 * np.abs(phase - 0.5) - 1
    else:
        sound = np.sin(2 * np.pi * freq * t)
    envelope = np.exp(-t * decay) * np.minimum(t / 0.005, 1.0)
    return sound * envelope


def _add(track: np.ndarray, sound: np.ndarray, at: float, volume: float) -> None:
    start = int(at * RATE)
    end = min(start + len(sound), len(track))
    if end > start:
        track[start:end] += sound[: end - start] * volume


def make_music(dest: Path, seconds: float = 64.0, seed: int = 0) -> Path:
    rng = random.Random(seed)
    bpm = rng.choice([84, 88, 92, 96])
    beat = 60.0 / bpm
    progression = rng.choice(PROGRESSIONS)
    pattern = rng.choice([(0, 1, 2, 3, 2, 1, 2, 1), (0, 2, 1, 3, 1, 2, 0, 2), (0, 1, 2, 1, 3, 2, 1, 2)])
    track = np.zeros(int(seconds * RATE))
    noise = np.random.default_rng(seed)

    bar, time = 0, 0.0
    while time < seconds:
        root, tones = progression[bar % len(progression)]
        for tone in tones[:3]:                                   # soft pad
            _add(track, _tone(_freq(root, 4, tone), beat * 4, "triangle", 0.5), time, 0.09)
        for step in range(8):                                    # arpeggio
            semis = tones[pattern[step]] + (12 if step % 4 == 3 else 0)
            _add(track, _tone(_freq(root, 5, semis), beat * 0.48, "pulse", 7.0), time + step * beat / 2, 0.055)
        for step in (0, 1.5, 2, 3.5):                            # bass
            _add(track, _tone(_freq(root, 2), beat * 0.9, "triangle", 2.5), time + step * beat, 0.30)
        for step in range(4):                                    # kick, snare and hats
            at = time + step * beat
            if step % 2 == 0:
                t = np.arange(int(0.16 * RATE)) / RATE
                _add(track, np.sin(2 * np.pi * (48 + 70 * np.exp(-t * 30)) * t) * np.exp(-t * 20), at, 0.32)
            else:
                hit = noise.uniform(-1, 1, int(0.12 * RATE)) * np.exp(-np.arange(int(0.12 * RATE)) / RATE * 32)
                _add(track, hit, at, 0.07)
            for half in (0, 0.5):
                tick = noise.uniform(-1, 1, int(0.03 * RATE)) * np.exp(-np.arange(int(0.03 * RATE)) / RATE * 140)
                _add(track, tick, at + half * beat, 0.03)
        time += beat * 4
        bar += 1

    # Gentle low-pass so it sits under the voice, then normalise.
    kernel = np.ones(6) / 6
    track = np.convolve(track, kernel, mode="same")
    track = track / max(np.abs(track).max(), 1e-6) * 0.8
    dest.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(dest), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes((track * 32767).astype(np.int16).tobytes())
    return dest
