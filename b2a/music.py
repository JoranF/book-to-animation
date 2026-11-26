"""Background music made in code: a calm chiptune loop in the spirit of old
console games. Original, free and different for every seed."""
from __future__ import annotations

import random
import wave
from pathlib import Path

import numpy as np

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
