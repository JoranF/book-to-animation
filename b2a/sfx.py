"""Retro sound effects, made in code like the old 8-bit games.

The synth is a Python port of the sfxr algorithm as found in jsfxr
(https://github.com/chr15m/jsfxr, public domain). Every sound comes from a
named preset plus a seed, so the library is the same on every server and a
channel keeps one recognisable "sound" while each Short can still vary.

The editor places them on the timeline from the script: a sting on the hook,
a soft whoosh on cuts, a sound for every reaction (a startle, a facepalm,
a laugh) and a chime on the last line.
"""
from __future__ import annotations

import math
import random
import wave
import zlib
from pathlib import Path
from typing import Any

import numpy as np

from . import config

RATE = 44100
OVERSAMPLING = 8
SQUARE, SAWTOOTH, SINE, NOISE = 0, 1, 2, 3

# How many seeded variants of every kind live in the library.
VARIANTS = 3


def _params() -> dict[str, float]:
    return {
        "wave_type": SQUARE, "p_env_attack": 0.0, "p_env_sustain": 0.3, "p_env_punch": 0.0,
        "p_env_decay": 0.4, "p_base_freq": 0.3, "p_freq_limit": 0.0, "p_freq_ramp": 0.0,
        "p_freq_dramp": 0.0, "p_vib_strength": 0.0, "p_vib_speed": 0.0, "p_arp_mod": 0.0,
        "p_arp_speed": 0.0, "p_duty": 0.0, "p_duty_ramp": 0.0, "p_repeat_speed": 0.0,
        "p_pha_offset": 0.0, "p_pha_ramp": 0.0, "p_lpf_freq": 1.0, "p_lpf_ramp": 0.0,
        "p_lpf_resonance": 0.0, "p_hpf_freq": 0.0, "p_hpf_ramp": 0.0, "sound_vol": 0.5,
    }


# --- presets: what each kind of moment sounds like ---------------------------
# Kept calm on purpose: they sit under a voice, so short, soft and low-passed.

def _sting(r: random.Random, p: dict[str, float]) -> None:
    """Rising power-up for the hook at 0.0 s."""
    p.update(wave_type=SQUARE, p_duty=r.uniform(0.2, 0.5), p_base_freq=0.25 + r.uniform(0, 0.1),
             p_freq_ramp=0.12 + r.uniform(0, 0.08), p_repeat_speed=0.45 + r.uniform(0, 0.2),
             p_env_sustain=0.25 + r.uniform(0, 0.1), p_env_decay=0.3 + r.uniform(0, 0.15),
             p_lpf_freq=0.65)


def _whoosh(r: random.Random, p: dict[str, float]) -> None:
    """Soft filtered noise sweep on a cut."""
    p.update(wave_type=NOISE, p_base_freq=0.35 + r.uniform(0, 0.15), p_freq_ramp=-0.08,
             p_env_attack=0.3 + r.uniform(0, 0.06), p_env_sustain=0.15, p_env_decay=0.35,
             p_lpf_freq=0.32 + r.uniform(0, 0.1), p_lpf_ramp=0.25, p_hpf_freq=0.12)


def _blip(r: random.Random, p: dict[str, float]) -> None:
    """Menu blip, for a point or a small beat."""
    p.update(wave_type=r.choice([SQUARE, SAWTOOTH]), p_duty=r.uniform(0.2, 0.5),
             p_base_freq=0.42 + r.uniform(0, 0.12), p_env_sustain=0.15, p_env_decay=0.2,
             p_hpf_freq=0.1, p_lpf_freq=0.7)
    if p["wave_type"] == SAWTOOTH:
        p["p_duty"] = 1.0


def _jump(r: random.Random, p: dict[str, float]) -> None:
    """Startle: a quick upward boing."""
    p.update(wave_type=SQUARE, p_duty=r.uniform(0.1, 0.5), p_base_freq=0.32 + r.uniform(0, 0.1),
             p_freq_ramp=0.22 + r.uniform(0, 0.08), p_env_sustain=0.25, p_env_decay=0.25,
             p_lpf_freq=0.75)


def _thud(r: random.Random, p: dict[str, float]) -> None:
    """Facepalm: a low dull hit."""
    p.update(wave_type=NOISE, p_base_freq=0.12 + r.uniform(0, 0.06), p_freq_ramp=-0.3,
             p_env_sustain=0.1, p_env_decay=0.3 + r.uniform(0, 0.05), p_env_punch=0.5,
             p_lpf_freq=0.3)


def _laugh(r: random.Random, p: dict[str, float]) -> None:
    """Laugh: a bouncy repeated arpeggio."""
    p.update(wave_type=SQUARE, p_duty=0.4, p_base_freq=0.45 + r.uniform(0, 0.08),
             p_arp_mod=0.3 + r.uniform(0, 0.15), p_arp_speed=0.6, p_repeat_speed=0.62 + r.uniform(0, 0.08),
             p_env_sustain=0.45, p_env_decay=0.25, p_lpf_freq=0.7)


def _no(r: random.Random, p: dict[str, float]) -> None:
    """Shake head: a wobbling low buzz."""
    p.update(wave_type=SAWTOOTH, p_duty=1.0, p_base_freq=0.2 + r.uniform(0, 0.05),
             p_vib_strength=0.45, p_vib_speed=0.55 + r.uniform(0, 0.1),
             p_env_sustain=0.35, p_env_decay=0.2, p_lpf_freq=0.45)


def _down(r: random.Random, p: dict[str, float]) -> None:
    """Slump or shrug: a falling 'aww'."""
    p.update(wave_type=SQUARE, p_duty=0.5, p_base_freq=0.4 + r.uniform(0, 0.08),
             p_freq_ramp=-0.2 - r.uniform(0, 0.06), p_env_sustain=0.35, p_env_decay=0.35,
             p_lpf_freq=0.6)


def _chime(r: random.Random, p: dict[str, float]) -> None:
    """Coin pickup: the idea lands (last line)."""
    p.update(wave_type=SAWTOOTH, p_duty=1.0, p_base_freq=0.5 + r.uniform(0, 0.1),
             p_env_sustain=0.12, p_env_decay=0.4 + r.uniform(0, 0.1), p_env_punch=0.4,
             p_arp_speed=0.55 + r.uniform(0, 0.1), p_arp_mod=0.3 + r.uniform(0, 0.1),
             p_lpf_freq=0.75)


PRESETS = {"sting": _sting, "whoosh": _whoosh, "blip": _blip, "jump": _jump, "thud": _thud,
           "laugh": _laugh, "no": _no, "down": _down, "chime": _chime}

# Which sound goes with which movement of the listener.
REACTIONS = {"startle": "jump", "facepalm": "thud", "laugh": "laugh", "shake_head": "no",
             "slump": "down", "shrug": "down", "point_viewer": "blip", "arms_up": "jump"}

# Loudness per kind, relative to SFX_VOLUME (whooshes stay in the back).
LEVELS = {"sting": 0.7, "whoosh": 0.35, "blip": 0.6, "jump": 0.8, "thud": 0.9,
          "laugh": 0.6, "no": 0.6, "down": 0.7, "chime": 0.85}


def synth(p: dict[str, float], seed: int = 0) -> np.ndarray:
    """Render sfxr parameters to float samples in [-1, 1] at 44.1 kHz."""
    noise_rng = random.Random(seed)
    noise = [noise_rng.uniform(-1, 1) for _ in range(32)]

    def restart() -> dict[str, float]:
        s: dict[str, float] = {}
        s["period"] = 100 / (p["p_base_freq"] ** 2 + 0.001)
        s["period_max"] = 100 / (p["p_freq_limit"] ** 2 + 0.001)
        s["period_mult"] = 1 - p["p_freq_ramp"] ** 3 * 0.01
        s["period_mult_slide"] = -p["p_freq_dramp"] ** 3 * 0.000001
        s["duty"] = 0.5 - p["p_duty"] * 0.5
        s["duty_slide"] = -p["p_duty_ramp"] * 0.00005
        s["arp_mult"] = (1 - p["p_arp_mod"] ** 2 * 0.9) if p["p_arp_mod"] >= 0 else (1 + p["p_arp_mod"] ** 2 * 10)
        s["arp_time"] = 0 if p["p_arp_speed"] == 1 else int((1 - p["p_arp_speed"]) ** 2 * 20000 + 32)
        return s

    s = restart()
    wave_type = int(p["wave_type"])
    fltw = p["p_lpf_freq"] ** 3 * 0.1
    lpf_on = p["p_lpf_freq"] != 1
    fltw_d = 1 + p["p_lpf_ramp"] * 0.0001
    fltdmp = min(5 / (1 + p["p_lpf_resonance"] ** 2 * 20) * (0.01 + fltw), 0.8)
    flthp = p["p_hpf_freq"] ** 2 * 0.1
    flthp_d = 1 + p["p_hpf_ramp"] * 0.0003
    vib_speed = p["p_vib_speed"] ** 2 * 0.01
    vib_amp = p["p_vib_strength"] * 0.5
    env_len = [max(int(p["p_env_attack"] ** 2 * 100000), 1), max(int(p["p_env_sustain"] ** 2 * 100000), 1),
               max(int(p["p_env_decay"] ** 2 * 100000), 1)]
    punch = p["p_env_punch"]
    fl_off = p["p_pha_offset"] ** 2 * 1020 * (-1 if p["p_pha_offset"] < 0 else 1)
    fl_slide = p["p_pha_ramp"] ** 2 * (-1 if p["p_pha_ramp"] < 0 else 1)
    repeat = 0 if p["p_repeat_speed"] == 0 else int((1 - p["p_repeat_speed"]) ** 2 * 20000 + 32)
    gain = math.exp(p["sound_vol"]) - 1
    freq_cutoff = p["p_freq_limit"] > 0

    fltp = fltdp = fltphp = 0.0
    stage = elapsed = 0
    since_repeat = 0
    vib_phase = 0.0
    phase = ipp = 0
    flanger = [0.0] * 1024
    out: list[float] = []
    t = 0
    while len(out) < RATE * 4:                     # safety cap: 4 seconds
        if repeat and (since_repeat := since_repeat + 1) >= repeat:
            since_repeat = 0
            s = restart()
        if s["arp_time"] and t >= s["arp_time"]:
            s["arp_time"] = 0
            s["period"] *= s["arp_mult"]
        t += 1
        s["period_mult"] += s["period_mult_slide"]
        s["period"] *= s["period_mult"]
        if s["period"] > s["period_max"]:
            s["period"] = s["period_max"]
            if freq_cutoff:
                break
        rfperiod = s["period"]
        if vib_amp > 0:
            vib_phase += vib_speed
            rfperiod = s["period"] * (1 + math.sin(vib_phase) * vib_amp)
        iperiod = max(int(rfperiod), OVERSAMPLING)
        s["duty"] = min(max(s["duty"] + s["duty_slide"], 0.0), 0.5)

        elapsed += 1
        if elapsed > env_len[stage]:
            elapsed = 0
            stage += 1
            if stage > 2:
                break
        envf = elapsed / env_len[stage]
        env = envf if stage == 0 else (1 + (1 - envf) * 2 * punch if stage == 1 else 1 - envf)

        fl_off += fl_slide
        iphase = min(abs(int(fl_off)), 1023)
        if flthp_d != 0:
            flthp = min(max(flthp * flthp_d, 0.00001), 0.1)

        sample = 0.0
        duty = s["duty"]
        for _ in range(OVERSAMPLING):
            phase += 1
            if phase >= iperiod:
                phase %= iperiod
                if wave_type == NOISE:
                    noise = [noise_rng.uniform(-1, 1) for _ in range(32)]
            fp = phase / iperiod
            if wave_type == SQUARE:
                sub = 0.5 if fp < duty else -0.5
            elif wave_type == SAWTOOTH:
                sub = (-1 + 2 * fp / duty) if fp < duty else (1 - 2 * (fp - duty) / (1 - duty))
            elif wave_type == SINE:
                sub = math.sin(fp * 2 * math.pi)
            else:
                sub = noise[int(phase * 32 / iperiod) % 32]
            pp = fltp
            fltw = min(max(fltw * fltw_d, 0.0), 0.1)
            if lpf_on:
                fltdp += (sub - fltp) * fltw
                fltdp -= fltdp * fltdmp
            else:
                fltp = sub
                fltdp = 0.0
            fltp += fltdp
            fltphp += fltp - pp
            fltphp -= fltphp * flthp
            sub = fltphp
            flanger[ipp & 1023] = sub
            sub += flanger[(ipp - iphase + 1024) & 1023]
            ipp = (ipp + 1) & 1023
            sample += sub * env
        out.append(sample / OVERSAMPLING * gain)
    samples = np.clip(np.array(out, dtype=np.float64), -1, 1)
    fade = min(len(samples), int(0.004 * RATE))    # no clicks at either end
    if fade:
        ramp = np.linspace(0, 1, fade)
        samples[:fade] *= ramp
        samples[-fade:] *= ramp[::-1]
    return samples


def _write(dest: Path, samples: np.ndarray) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp")
    with wave.open(str(tmp), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes((np.clip(samples, -1, 1) * 32767).astype(np.int16).tobytes())
    tmp.replace(dest)
    return dest


def library_dir() -> Path:
    return config.DATA_DIR / "sfx"


def sound(kind: str, variant: int = 0) -> np.ndarray:
    """One sound from the library, made and cached on first use."""
    if kind not in PRESETS:
        raise KeyError(f"Unknown sound '{kind}', choose from {sorted(PRESETS)}")
    path = library_dir() / f"{kind}_{variant % VARIANTS}.wav"
    if not path.exists():
        seed = zlib.crc32(f"{kind}:{variant % VARIANTS}".encode())
        params = _params()
        PRESETS[kind](random.Random(seed), params)
        _write(path, synth(params, seed))
    with wave.open(str(path), "rb") as src:
        data = np.frombuffer(src.readframes(src.getnframes()), dtype=np.int16)
    return data.astype(np.float64) / 32767


def build_library() -> list[Path]:
    """Make every sound once (also handy to listen to them all)."""
    for kind in PRESETS:
        for variant in range(VARIANTS):
            sound(kind, variant)
    return sorted(library_dir().glob("*.wav"))


def cues(script: dict[str, Any], times: list[tuple[float, float]]) -> list[dict[str, Any]]:
    """Where a sound goes, read from the script. At most two per scene, so it never gets busy."""
    scenes = script["scenes"]
    out: list[dict[str, Any]] = []
    for i, (scene, (start, end)) in enumerate(zip(scenes, times)):
        here: list[dict[str, Any]] = []
        if i == 0:
            here.append({"at": 0.0, "kind": "sting"})
        elif i == len(scenes) - 1:
            here.append({"at": start, "kind": "chime"})
        else:
            here.append({"at": max(start - 0.12, 0.0), "kind": "whoosh"})
        speaker = scene.get("speaker")
        for actor in (scene.get("stage") or {}).get("actors", []):
            kind = REACTIONS.get(actor.get("action", ""))
            # the listener's reaction gets a sound, the speaker's gesture does not
            if kind and actor.get("who") != speaker:
                here.append({"at": min(start + 0.3, max(end - 0.3, start)), "kind": kind})
                break
        out += here[:2]
    return out


def make_track(script: dict[str, Any], times: list[tuple[float, float]], seconds: float,
               dest: Path, seed_text: str = "") -> tuple[Path | None, list[str]]:
    """Mix every cue into one wav as long as the Short. Returns the file and the kinds used."""
    if config.SFX_VOLUME <= 0:
        return None, []
    variant = zlib.crc32(seed_text.encode()) % VARIANTS if config.SFX_VARY else 0
    track = np.zeros(int((seconds + 1) * RATE))
    used: list[str] = []
    for cue in cues(script, times):
        samples = sound(cue["kind"], variant) * LEVELS[cue["kind"]]
        start = int(cue["at"] * RATE)
        end = min(start + len(samples), len(track))
        if end > start:
            track[start:end] += samples[: end - start]
            used.append(cue["kind"])
    peak = np.abs(track).max()
    if peak > 1:
        track /= peak
    return _write(dest, track * config.SFX_VOLUME), used
