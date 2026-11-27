"""Pose-to-pose character animation, without needing Blender.

How a 2D or 3D animator would block a shot, done in code:

1. Key poses. Every action is a short sequence of strong, readable poses from
   POSES (hand on chest, palms up, finger raised, arms crossed, ...), never one
   endless sine wave. A seeded random choice picks which poses, in which order,
   mirrored or not, so the same action looks different in every shot.
2. Inbetweens. Each pose is reached with an easing curve that fits the move:
   "smooth" (slow in and slow out), "snap" (fast with a small overshoot, for a
   gesture stroke), "heavy" (accelerating, for a drop), "soft" (decelerating).
3. Anticipation. Big moves start with a short opposite move (a dip before a
   jump, an arm pulled back before a point).
4. Overlapping action and follow-through. The head and forearms sample the
   curves a little later than the body, so they drag behind and overshoot
   after the main move has stopped.
5. Moving holds. While a pose is held, the body keeps breathing and drifting a
   little, so a hold never freezes.
6. Layers. Arms, body (weight shifts) and head (glances) have their own keys,
   so the arms can gesture while the weight shifts on its own rhythm.
7. Speech beats. A speaker's gesture strokes land on stressed words (the
   timing of the voice is passed in as "beats"), the way people gesture.

`track(action_or_actions, seconds, params, seed)` returns a Track; Track.sample(t)
gives a full pose (a dict of CHANNELS) that world.py puts on the character.
"""
from __future__ import annotations

import bisect
import math
import random
from typing import Any, Callable

# body: lean (+ forward), side (tilt sideways), twist, lift (metres, up), shift (metres, sideways)
# head: pitch (+ down), tilt, turn (+ to screen right), brow (raise 0..1)
# arms, l_ is screen left: fwd (raise forward), out (raise sideways), elbow (bend),
#       in (turn the forearm towards the chest)
BODY = ("lean", "side", "twist", "lift", "shift", "leg_l", "leg_r")
HEAD = ("pitch", "tilt", "turn", "brow")
ARMS = ("l_fwd", "l_out", "l_elbow", "l_in", "r_fwd", "r_out", "r_elbow", "r_in")
CHANNELS = BODY + HEAD + ARMS
LINEAR = ("lift", "shift", "brow")       # not angles

NEUTRAL: dict[str, float] = {ch: 0.0 for ch in CHANNELS}
NEUTRAL.update(l_out=7.0, r_out=7.0, l_elbow=12.0, r_elbow=12.0)

# follow-through: how many seconds a channel lags behind the body
DELAY = {**{ch: 0.0 for ch in BODY}, **{ch: 0.06 for ch in HEAD},
         "l_fwd": 0.03, "l_out": 0.03, "r_fwd": 0.03, "r_out": 0.03,
         "l_elbow": 0.09, "l_in": 0.09, "r_elbow": 0.09, "r_in": 0.09, "brow": 0.0}

# how lively a mood is: faster and bigger when angry, slow and small when tired
ENERGY = {"angry": 1.3, "happy": 1.15, "worried": 1.05, "smirk": 0.9, "plain": 0.9,
          "calm": 0.8, "sad": 0.65, "tired": 0.6}
# a mood also bends the whole body a little
MOOD_OFFSET = {
    "sad": {"pitch": 12, "lean": 5, "l_out": -3, "r_out": -3},
    "tired": {"pitch": 9, "lean": 4, "lift": -0.01},
    "angry": {"lean": 3, "pitch": 4},
    "happy": {"pitch": -4, "lift": 0.006},
    "worried": {"pitch": 4, "tilt": 3},
    "smirk": {"tilt": -5, "pitch": -2},
}


def arm(side: str, fwd: float, out: float, elbow: float, inward: float = 0.0) -> dict[str, float]:
    return {f"{side}_fwd": fwd, f"{side}_out": out, f"{side}_elbow": elbow, f"{side}_in": inward}


def both(fwd: float, out: float, elbow: float, inward: float = 0.0) -> dict[str, float]:
    return {**arm("l", fwd, out, elbow, inward), **arm("r", fwd, out, elbow, inward)}


HANG = both(0, 7, 12)

# Key poses. One-armed poses use the right arm; mirror() makes the left version.
POSES: dict[str, dict[str, float]] = {
    # arms
    "hang": HANG,
    "hang_loose": {**arm("l", 4, 9, 22, 10), **arm("r", 2, 6, 16, 6)},
    "hips": both(-12, 42, 108, 88),
    "hip_r": {**arm("l", 2, 7, 14), **arm("r", -12, 42, 108, 88)},
    "crossed": {**arm("l", 44, -20, 108, 72), **arm("r", 50, -16, 100, 72)},
    "hands_together": both(30, -6, 70, 58),
    "open_both": both(40, 24, 58, -22),
    "palms_up": both(24, 32, 86, -48),
    "palm_up_r": {**arm("l", 3, 8, 16), **arm("r", 30, 18, 82, -45)},
    "beat_r": {**arm("l", 6, 9, 24, 12), **arm("r", 40, 10, 72, 12)},
    "chest_r": {**arm("l", 4, 8, 18), **arm("r", 32, -6, 128, 76)},
    "point_soft_r": {**arm("l", 6, 8, 20), **arm("r", 66, 8, 22, 0)},
    "count_r": {**arm("l", 8, 9, 30, 15), **arm("r", 44, 2, 122, 22)},
    "steeple": both(46, -8, 96, 56),
    "chop_r": {**arm("l", 10, 9, 40, 20), **arm("r", 56, 6, 62, 32)},
    "sweep_r": {**arm("l", 6, 9, 22), **arm("r", 24, 62, 28, -20)},
    "size_both": both(36, 26, 72, 40),
    "wave_off_r": {**arm("l", 4, 9, 18), **arm("r", 30, 36, 92, -30)},
    "think_r": {**arm("l", 30, -4, 100, 70), **arm("r", 40, -10, 150, 34)},
    "scratch_r": {**arm("l", 2, 8, 14), **arm("r", 32, 96, 140, 72)},
    "stop_r": {**arm("l", 3, 8, 16), **arm("r", 82, 14, 70, 0)},
    "stop_both": both(78, 18, 66, 0),
    "point_r": {**arm("l", 4, 8, 18), **arm("r", 86, 10, 4, 0)},
    "point_up_r": {**arm("l", 4, 8, 18), **arm("r", 150, 12, 10, 0)},
    "reach_both": both(74, 10, 8, 0),
    "give_r": {**arm("l", 38, -6, 110, 70), **arm("r", 62, 18, 30, -30)},
    "arms_wide": both(18, 118, 12, 0),
    "arms_v": both(28, 140, 18, 0),
    "fist_pump_r": {**arm("l", 20, 20, 70, 30), **arm("r", 160, 16, 40, 0)},
    "facepalm_r": {**arm("l", 6, 6, 20), **arm("r", 80, -10, 150, 26)},
    "cover_face": both(76, -12, 148, 30),
    "recoil": both(36, 46, 78, -18),
    "guard": both(30, 24, 96, 30),
    "belly": both(22, -6, 96, 70),
    "whisper_r": {**arm("l", 6, 8, 20), **arm("r", 48, -4, 140, 50)},
    "brush_up_r": {**arm("l", 24, -4, 100, 70), **arm("r", 92, 12, 40, 0)},
    "brush_down_r": {**arm("l", 24, -4, 100, 70), **arm("r", 64, 24, 64, 0)},
    "dangle": both(8, 3, 6, 0),
}

TALK = ["open_both", "palm_up_r", "beat_r", "chest_r", "point_soft_r", "count_r", "steeple",
        "chop_r", "sweep_r", "size_both", "wave_off_r", "palms_up"]
REST = ["hang", "hang_loose", "hands_together", "hip_r"]
LISTEN = ["hang", "hang_loose", "hands_together", "crossed", "hips", "think_r", "hip_r"]


def mirror(pose: dict[str, float]) -> dict[str, float]:
    out: dict[str, float] = {}
    for ch, v in pose.items():
        if ch[:2] in ("l_", "r_"):
            out[("r_" if ch[0] == "l" else "l_") + ch[2:]] = v
        elif ch == "leg_l":
            out["leg_r"] = v
        elif ch == "leg_r":
            out["leg_l"] = v
        elif ch in ("side", "twist", "shift", "tilt", "turn"):
            out[ch] = -v
        else:
            out[ch] = v
    return out


# --- easing (the inbetweens) ------------------------------------------------

def _smooth(x: float) -> float:          # slow in, slow out
    return 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def _snap(x: float) -> float:            # fast out, small overshoot, settle
    c1 = 1.2
    return 1 + (c1 + 1) * (x - 1) ** 3 + c1 * (x - 1) ** 2


def _soft(x: float) -> float:            # decelerate into the pose
    return 1 - (1 - x) ** 2.4


def _heavy(x: float) -> float:           # accelerate, like falling
    return x ** 2.2


EASE: dict[str, Callable[[float], float]] = {
    "smooth": _smooth, "snap": _snap, "soft": _soft, "heavy": _heavy, "linear": lambda x: x,
}


# --- keys -----------------------------------------------------------------

class Seq:
    """Keyframes per channel. move() sets a pose to be reached between two times."""

    def __init__(self, rng: random.Random, energy: float, start: dict[str, float] | None = None,
                 cane: bool = False):
        self.rng = rng
        self.cane = cane
        self.energy = energy
        self.speed = energy ** 0.6
        self.amp = 0.8 + 0.2 * energy
        base = {**NEUTRAL, **(start or {})}
        self.keys: dict[str, list[tuple[float, float, str]]] = {ch: [(0.0, base[ch], "smooth")] for ch in CHANNELS}
        self.times: dict[str, list[float]] = {ch: [0.0] for ch in CHANNELS}

    def d(self, seconds: float) -> float:
        """A duration, quicker for lively moods."""
        return seconds / self.speed

    def value(self, ch: str, t: float) -> float:
        keys, times = self.keys[ch], self.times[ch]
        i = bisect.bisect_right(times, t)
        if i == 0:
            return keys[0][1]
        if i >= len(keys):
            return keys[-1][1]
        t0, v0, _ = keys[i - 1]
        t1, v1, ease = keys[i]
        x = (t - t0) / max(t1 - t0, 1e-6)
        return v0 + (v1 - v0) * EASE[ease](min(max(x, 0.0), 1.0))

    def move(self, t0: float, dur: float, pose: dict[str, float], ease: str = "smooth",
             vary: float = 0.12) -> float:
        """Hold every channel in `pose` until t0, then reach the pose at t0 + dur."""
        dur = max(dur, 0.05)
        for ch, v in self.vary(pose, vary).items():
            cur = self.value(ch, t0)
            keys, times = self.keys[ch], self.times[ch]
            while len(keys) > 1 and times[-1] > t0:    # a new instruction replaces later keys
                keys.pop(); times.pop()
            if t0 > times[-1]:
                keys.append((t0, cur, "smooth")); times.append(t0)
            else:
                keys[-1] = (times[-1], cur, keys[-1][2])
            keys.append((t0 + dur, v, ease)); times.append(t0 + dur)
        return t0 + dur

    def vary(self, pose: dict[str, float], amount: float) -> dict[str, float]:
        """Exaggerate or tone down a pose for the mood, and never repeat it exactly."""
        out = {}
        for ch, v in pose.items():
            n = NEUTRAL[ch]
            if amount:
                k = self.amp * self.rng.uniform(1 - amount, 1 + amount)
                jitter = 0.0 if ch in LINEAR else self.rng.uniform(-2.5, 2.5) * amount / 0.12
            else:
                k, jitter = 1.0, 0.0
            out[ch] = n + (v - n) * k + jitter
        return out

    def pose(self, name: str, flip: bool | None = None) -> dict[str, float]:
        p = POSES[name]
        if self.cane:      # the cane hand (right) stays low: gesture with the free hand
            busy = sum(abs(v - NEUTRAL[ch]) * (1 if ch[0] == "r" else -1) for ch, v in p.items() if ch in ARMS)
            flip = busy > 0
        elif flip is None:
            flip = self.rng.random() < 0.5
        return mirror(p) if flip else dict(p)


# --- layers that keep a body alive ------------------------------------------

def weight_layer(s: Seq, t0: float, t1: float) -> None:
    """Shift the weight from leg to leg now and then (contrapposto)."""
    t = t0 + s.rng.uniform(0.3, 1.4)
    side = s.rng.choice((-1, 1))
    while t < t1 - 0.4:
        k = s.rng.uniform(0.5, 1.0)
        s.move(t, s.d(s.rng.uniform(0.5, 0.8)),
               {"shift": 0.022 * side * k, "side": 2.6 * side * k, "twist": s.rng.uniform(-4, 4),
                "leg_l": 4 * k if side > 0 else 0, "leg_r": 4 * k if side < 0 else 0}, vary=0)
        side = -side if s.rng.random() < 0.8 else 0
        t += s.d(s.rng.uniform(1.8, 3.4))


def gaze_layer(s: Seq, t0: float, t1: float, keep_pitch: bool = False) -> None:
    """Quick glances away and back (eyes lead, so the head moves fast and holds)."""
    t = t0 + s.rng.uniform(0.6, 1.8)
    while t < t1 - 0.5:
        glance = {"turn": s.rng.uniform(-18, 18), "tilt": s.rng.uniform(-6, 6)}
        if not keep_pitch:
            glance["pitch"] = s.rng.uniform(-5, 7)
        t = s.move(t, s.d(0.18), glance, "snap", vary=0)
        t = s.move(t + s.d(s.rng.uniform(0.5, 1.3)), s.d(0.3), {"turn": s.rng.uniform(-4, 4), "tilt": 0}, "smooth", vary=0)
        t += s.d(s.rng.uniform(1.0, 2.6))


def rest_arms(s: Seq, t0: float, names=REST) -> float:
    return s.move(t0, s.d(s.rng.uniform(0.45, 0.7)), s.pose(s.rng.choice(names)), "smooth")


# --- actions --------------------------------------------------------------
# Each action writes keys between t0 and t1. `p` are the actor's stage settings.

def act_idle(s, t0, t1, p):
    t = rest_arms(s, t0)
    while t < t1 - 1.0:      # change how the arms rest once or twice per shot
        t += s.d(s.rng.uniform(2.2, 4.0))
        if t < t1 - 0.6:
            t = rest_arms(s, t)


def _strokes(s: Seq, t0: float, t1: float, p: dict[str, Any]) -> list[float]:
    gap = 0.62 / s.speed
    beats = sorted(b for b in p.get("beats", []) if t0 + 0.25 <= b < t1 - 0.25)
    if len(beats) < 2:
        beats, t = [], t0 + s.rng.uniform(0.25, 0.55)
        while t < t1 - 0.3:
            beats.append(t)
            t += s.d(s.rng.uniform(0.75, 1.5))
    out: list[float] = []
    for b in beats:
        if not out or b - out[-1] >= gap:
            out.append(b)
    return out


def act_talk(s, t0, t1, p):
    """Gesture phrases: preparation, a stroke on the stressed word, a hold, a retraction."""
    recent: list[str] = []
    strokes = _strokes(s, t0, t1, p)
    for i, b in enumerate(strokes):
        nxt = strokes[i + 1] if i + 1 < len(strokes) else t1
        name = s.rng.choice([g for g in TALK if g not in recent[-2:]])
        recent.append(name)
        prep = min(s.d(0.3), max(b - t0, 0.08))
        s.move(b - prep, prep, s.pose(name), "snap")
        # head accent on the stroke: a small nod and raised brows
        s.move(b - prep * 0.6, prep * 0.6, {"pitch": s.rng.uniform(3, 8), "brow": s.rng.uniform(0.3, 1.0),
                                             "tilt": s.rng.uniform(-6, 6)}, "snap", vary=0)
        s.move(b + s.d(0.25), s.d(0.4), {"pitch": s.rng.uniform(-3, 2), "brow": 0.0}, "soft", vary=0)
        if s.rng.random() < 0.45 and nxt - b > 0.7:          # baton: a second small beat
            beat = {ch: v - (10 if ch.endswith("_fwd") else 0) for ch, v in s.pose(name, False).items()}
            s.move(b + s.d(0.3), s.d(0.12), beat, "snap", vary=0.05)
            s.move(b + s.d(0.44), s.d(0.2), s.pose(name, False), "soft", vary=0.05)
        if nxt - b > 1.9 and s.rng.random() < 0.5:           # retract between phrases
            rest_arms(s, b + s.d(0.9))
        lean = s.rng.uniform(-2, 6)
        s.move(b - prep, s.d(0.5), {"lean": lean}, "smooth", vary=0)


def act_nod(s, t0, t1, p):
    """Listening: arms in a resting pose, nods in small groups at irregular moments."""
    t = s.move(t0, s.d(0.6), s.pose(s.rng.choice(LISTEN)), "smooth")
    t = t0 + s.rng.uniform(0.3, 0.9)
    while t < t1 - 0.6:
        for _ in range(s.rng.choice((1, 2, 2, 3))):
            t = s.move(t, s.d(0.17), {"pitch": s.rng.uniform(9, 15)}, "snap", vary=0)
            t = s.move(t, s.d(0.22), {"pitch": s.rng.uniform(-2, 1)}, "soft", vary=0)
        s.move(t, s.d(0.4), {"tilt": s.rng.uniform(-7, 7), "turn": s.rng.uniform(-6, 6)}, vary=0)
        t += s.d(s.rng.uniform(0.9, 2.2))


def act_point(s, t0, t1, p):
    flip = bool(p.get("mirror"))
    sweep = float(p.get("sweep", 0.0))
    lift = float(p.get("lift", 86))
    point = {**POSES["point_r"], "r_fwd": lift}
    s.move(t0, s.d(0.2), {"r_fwd": 10, "r_out": 4, "r_elbow": 60}, "smooth", vary=0)   # anticipation
    t = s.move(t0 + s.d(0.2), s.d(0.22), mirror(point) if flip else point, "snap")
    s.move(t0 + s.d(0.15), s.d(0.3), {"lean": 6, "turn": (8 if not flip else -8)}, "snap", vary=0)
    while t < t1 - 0.8:
        t += s.d(s.rng.uniform(0.7, 1.4))
        if sweep:
            aim = s.rng.uniform(-1, 1) * sweep
            s.move(t, s.d(0.4), {("l_out" if flip else "r_out"): 10 + aim, "turn": aim * 0.6}, "smooth", vary=0)
        else:   # jab: emphasise the point again
            side = "l" if flip else "r"
            s.move(t, s.d(0.1), {f"{side}_fwd": lift - 14, f"{side}_elbow": 30}, "snap", vary=0)
            s.move(t + s.d(0.12), s.d(0.18), {f"{side}_fwd": lift, f"{side}_elbow": 4}, "snap", vary=0)
        t += s.d(0.3)


def act_point_viewer(s, t0, t1, p):
    s.move(t0, s.d(0.25), {"lean": -4, "l_fwd": 20, "l_elbow": 90}, "smooth", vary=0)
    s.move(t0 + s.d(0.25), s.d(0.25), {"lean": 12, "pitch": 4}, "snap", vary=0)
    t = s.move(t0 + s.d(0.25), s.d(0.22), {**arm("l", 80, 18, 6), **arm("r", 6, 10, 30)}, "snap")
    s.move(t + s.d(0.5), s.d(0.2), {"brow": 1.0}, "snap", vary=0)
    while t < t1 - 0.8:
        t += s.d(s.rng.uniform(0.8, 1.5))
        s.move(t, s.d(0.1), {"l_fwd": 66, "lean": 15}, "snap", vary=0)
        s.move(t + s.d(0.12), s.d(0.2), {"l_fwd": 80, "lean": 11}, "soft", vary=0)


def act_stop(s, t0, t1, p):
    name = s.rng.choice(("stop_r", "stop_r", "stop_both"))
    s.move(t0, s.d(0.18), {"r_fwd": 20, "r_elbow": 110, "l_elbow": 40}, "smooth", vary=0)
    t = s.move(t0 + s.d(0.18), s.d(0.2), s.pose(name, False), "snap")
    s.move(t0 + s.d(0.1), s.d(0.3), {"lean": -5, "pitch": -3}, "snap", vary=0)
    while t < t1 - 0.8:
        t += s.d(s.rng.uniform(0.9, 1.6))
        if s.rng.random() < 0.5:     # push the hand forward again
            s.move(t, s.d(0.1), {"r_fwd": 92, "r_elbow": 50, "lean": 2}, "snap", vary=0)
            s.move(t + s.d(0.12), s.d(0.25), {"r_fwd": 82, "r_elbow": 70, "lean": -4}, "soft", vary=0)
        else:                        # small shake of the head: no
            for k in (1, -1, 0.5):
                t = s.move(t, s.d(0.12), {"turn": 14 * k}, "smooth", vary=0)
            t = s.move(t, s.d(0.15), {"turn": 0}, "soft", vary=0)


def act_look_around(s, t0, t1, p):
    """Look, hold, look somewhere else: the head snaps, the body follows later."""
    rest_arms(s, t0, ("hang", "hang_loose", "hands_together", "scratch_r"))
    t, side = t0 + s.d(0.2), s.rng.choice((-1, 1))
    while t < t1 - 0.4:
        aim = side * s.rng.uniform(25, 45)
        t = s.move(t, s.d(0.2), {"turn": aim, "pitch": s.rng.uniform(-8, 6)}, "snap", vary=0)
        s.move(t - s.d(0.05), s.d(0.45), {"twist": aim * 0.3}, "smooth", vary=0)
        t += s.d(s.rng.uniform(0.5, 1.2))
        side = -side
        if s.rng.random() < 0.3 and t < t1 - 1.2:
            t = rest_arms(s, t, ("scratch_r", "think_r", "hang"))


def act_give(s, t0, t1, p):
    flip = p.get("side", 1) == 0
    give = POSES["give_r"]
    s.move(t0, s.d(0.3), {"r_fwd": 20, "r_elbow": 90, "l_fwd": 30, "l_elbow": 100, "l_in": 60}, "smooth", vary=0)
    t = s.move(t0 + s.d(0.35), s.d(0.6), mirror(give) if flip else give, "soft")
    s.move(t0 + s.d(0.3), s.d(0.6), {"lean": 9, "turn": -12 if flip else 12, "pitch": 6}, "smooth", vary=0)
    s.move(t + s.d(0.6), s.d(0.5), {"lean": 4, "pitch": -2}, "smooth", vary=0)


def act_reach(s, t0, t1, p):
    s.move(t0, s.d(0.3), {**both(20, 8, 70), "lean": -4}, "smooth", vary=0)
    t = s.move(t0 + s.d(0.3), s.d(0.6), {**POSES["reach_both"]}, "soft")
    s.move(t0 + s.d(0.3), s.d(0.7), {"lean": 12, "pitch": -4}, "soft", vary=0)
    while t < t1 - 0.8:      # stretch a little further, then a little less
        t += s.d(s.rng.uniform(0.6, 1.2))
        s.move(t, s.d(0.4), {"l_fwd": s.rng.uniform(70, 86), "r_fwd": s.rng.uniform(70, 86),
                             "lean": s.rng.uniform(10, 16)}, "smooth", vary=0)
        t += s.d(0.4)


def act_paint(s, t0, t1, p):
    t = s.move(t0, s.d(0.4), s.pose("brush_down_r", False), "smooth")
    s.move(t0, s.d(0.5), {"lean": 6, "pitch": 4}, "smooth", vary=0)
    while t < t1 - 0.3:
        stroke = "brush_up_r" if s.rng.random() < 0.5 else "brush_down_r"
        pose = {**s.pose(stroke, False), "r_out": s.rng.uniform(0, 34)}
        t = s.move(t, s.d(s.rng.uniform(0.2, 0.35)), pose, "snap")
        if s.rng.random() < 0.3:     # step back and look at it
            s.move(t, s.d(0.4), {"lean": -4, "tilt": s.rng.uniform(-10, 10), "pitch": -3}, "smooth", vary=0)
            t += s.d(0.9)
            s.move(t, s.d(0.3), {"lean": 6, "tilt": 0, "pitch": 4}, "smooth", vary=0)
        t += s.d(s.rng.uniform(0.05, 0.25))


def act_arms_crossed(s, t0, t1, p):
    t = s.move(t0 + s.d(0.1), s.d(0.45), s.pose("crossed", s.rng.random() < 0.5), "snap")
    s.move(t0, s.d(0.4), {"lean": -4, "pitch": -4}, "smooth", vary=0)
    t += s.d(0.5)
    while t < t1 - 0.6:
        if s.rng.random() < 0.5:     # impatient foot tap
            foot = s.rng.choice(("leg_l", "leg_r"))
            for _ in range(s.rng.choice((2, 3, 4))):
                t = s.move(t, s.d(0.1), {foot: -12}, "snap", vary=0)
                t = s.move(t, s.d(0.12), {foot: 0}, "heavy", vary=0)
        else:                        # slow shake of the head
            for k in (1, -1, 0.6, 0):
                t = s.move(t, s.d(0.2), {"turn": 16 * k}, "smooth", vary=0)
        t += s.d(s.rng.uniform(0.6, 1.4))


def act_whisper(s, t0, t1, p):
    lean = 1 if p.get("lean", 1) > 0 else -1
    flip = lean < 0
    s.move(t0, s.d(0.5), {"side": 9 * lean, "lean": 8, "turn": 22 * lean, "tilt": 8 * lean}, "smooth", vary=0)
    t = s.move(t0 + s.d(0.2), s.d(0.35), s.pose("whisper_r", flip), "snap")
    while t < t1 - 0.8:
        t += s.d(s.rng.uniform(0.6, 1.2))
        if s.rng.random() < 0.5:     # point at someone, then back to the mouth
            t = s.move(t, s.d(0.2), s.pose("point_soft_r", flip), "snap")
            s.move(t - s.d(0.1), s.d(0.2), {"turn": -10 * lean}, "snap", vary=0)
            t += s.d(0.6)
            t = s.move(t, s.d(0.3), s.pose("whisper_r", flip), "smooth")
            s.move(t - s.d(0.3), s.d(0.3), {"turn": 22 * lean}, "smooth", vary=0)
        else:
            s.move(t, s.d(0.3), {"side": s.rng.uniform(6, 11) * lean}, "smooth", vary=0)


def act_arms_up(s, t0, t1, p):
    # anticipation: crouch with the arms down and back, then spring up
    s.move(t0, s.d(0.3), {**both(-14, 10, 30), "lift": -0.05, "lean": 8, "pitch": 8}, "smooth", vary=0)
    name = s.rng.choice(("arms_v", "arms_wide", "fist_pump_r"))
    t = s.move(t0 + s.d(0.3), s.d(0.25), s.pose(name), "snap")
    s.move(t0 + s.d(0.3), s.d(0.25), {"lift": 0.05, "lean": -8, "pitch": -16}, "snap", vary=0)
    s.move(t, s.d(0.3), {"lift": 0.0}, "heavy", vary=0)
    while t < t1 - 0.6:
        t += s.d(s.rng.uniform(0.6, 1.1))
        s.move(t, s.d(0.15), {"lift": 0.03}, "snap", vary=0)
        s.move(t + s.d(0.15), s.d(0.2), {"lift": 0.0}, "heavy", vary=0)
        if s.rng.random() < 0.35:
            s.move(t, s.d(0.3), s.pose(s.rng.choice(("arms_v", "arms_wide", "fist_pump_r"))), "snap")
        t += s.d(0.4)


def act_shrug(s, t0, t1, p):
    t = t0 + s.d(0.1)
    while t < t1 - 0.6:
        big = s.rng.uniform(0.7, 1.0)
        s.move(t, s.d(0.15), {"lift": -0.015}, "smooth", vary=0)          # tiny dip first
        t = s.move(t + s.d(0.15), s.d(0.22), s.pose(s.rng.choice(("palms_up", "palm_up_r", "palms_up"))), "snap")
        s.move(t - s.d(0.22), s.d(0.22), {"lift": 0.035 * big, "tilt": s.rng.choice((-1, 1)) * 12 * big,
                                          "pitch": -3, "brow": 1.0}, "snap", vary=0)
        t += s.d(s.rng.uniform(0.5, 0.9))
        s.move(t, s.d(0.35), {"lift": 0.0, "tilt": 0, "brow": 0.2}, "heavy", vary=0)
        if s.rng.random() < 0.5:
            rest_arms(s, t)
        t += s.d(s.rng.uniform(0.7, 1.4))


def act_shake_head(s, t0, t1, p):
    rest_arms(s, t0, ("hang", "crossed", "hips", "hands_together", "wave_off_r"))
    t = t0 + s.d(0.2)
    while t < t1 - 0.5:
        size = s.rng.uniform(18, 28)
        for k in (1, -1, 0.7, -0.5, 0.2):
            t = s.move(t, s.d(0.13), {"turn": size * k}, "smooth", vary=0)
        s.move(t, s.d(0.3), {"turn": 0, "pitch": s.rng.uniform(2, 9)}, "soft", vary=0)
        t += s.d(s.rng.uniform(0.6, 1.4))


def act_facepalm(s, t0, t1, p):
    two = s.rng.random() < 0.3
    s.move(t0, s.d(0.25), {"pitch": -8, "brow": 1.0}, "smooth", vary=0)       # look up: "oh no"
    t = s.move(t0 + s.d(0.15), s.d(0.35), s.pose("cover_face" if two else "facepalm_r", False), "snap")
    s.move(t - s.d(0.1), s.d(0.3), {"pitch": 11, "lean": 5, "brow": 0.0}, "heavy", vary=0)  # head meets the hand
    t += s.d(0.5)
    while t < t1 - 0.6:      # slow shake inside the hand, or slide down
        if s.rng.random() < 0.6:
            for k in (1, -1, 0):
                t = s.move(t, s.d(0.3), {"turn": 9 * k}, "smooth", vary=0)
        else:
            t = s.move(t, s.d(0.6), {"pitch": 16, "lean": 8}, "smooth", vary=0)
        t += s.d(s.rng.uniform(0.4, 1.0))


def act_startle(s, t0, t1, p):
    # the shock: jump up and back, arms fly up, then settle into a wary pose
    t = s.move(t0 + 0.05, 0.12, {"lift": 0.12, "lean": -12, "pitch": -10, "brow": 1.0}, "snap", vary=0)
    s.move(t0 + 0.05, 0.14, s.pose("recoil"), "snap")
    t = s.move(t, 0.22, {"lift": -0.02, "lean": -6}, "heavy", vary=0)
    t = s.move(t, 0.2, {"lift": 0.0}, "soft", vary=0)
    t = s.move(t + s.d(0.3), s.d(0.6), s.pose(s.rng.choice(("guard", "recoil", "stop_both"))), "smooth")
    s.move(t, s.d(0.5), {"lean": -3, "pitch": -3}, "smooth", vary=0)
    while t < t1 - 0.6:
        t += s.d(s.rng.uniform(0.6, 1.2))
        s.move(t, s.d(0.12), {"turn": s.rng.uniform(-14, 14)}, "snap", vary=0)


def act_laugh(s, t0, t1, p):
    s.move(t0, s.d(0.25), {"lean": -10, "pitch": -14}, "snap", vary=0)        # head thrown back
    rest_arms(s, t0, ("belly", "hang_loose", "hips"))
    t = t0 + s.d(0.3)
    while t < t1 - 0.4:      # bursts of laughter that die down
        n = s.rng.choice((3, 4, 5))
        for i in range(n):
            k = 1 - i / (n + 1)
            t = s.move(t, s.d(0.09), {"lift": 0.03 * k, "lean": 10 * k, "pitch": 14 * k}, "snap", vary=0)
            t = s.move(t, s.d(0.1), {"lift": 0.0, "lean": 4 * k, "pitch": 4 * k}, "heavy", vary=0)
        t = s.move(t, s.d(0.4), {"lean": s.rng.uniform(-6, 2), "pitch": s.rng.uniform(-10, 0)}, "smooth", vary=0)
        if s.rng.random() < 0.4:
            rest_arms(s, t, ("belly", "hang_loose", "hips", "chest_r"))
        t += s.d(s.rng.uniform(0.3, 0.9))


def act_slump(s, t0, t1, p):
    # a sigh first (shoulders rise), then the body drops, the head follows, arms dangle
    s.move(t0, s.d(0.4), {"lift": 0.02, "pitch": -6, "lean": -2}, "smooth", vary=0)
    t = s.move(t0 + s.d(0.5), s.d(0.7), {"lift": -0.03, "lean": s.rng.uniform(20, 30)}, "heavy", vary=0)
    s.move(t0 + s.d(0.6), s.d(0.8), {"pitch": s.rng.uniform(26, 36), "tilt": s.rng.uniform(-8, 8)}, "heavy", vary=0)
    s.move(t0 + s.d(0.5), s.d(0.9), {**POSES["dangle"], "l_fwd": 22, "r_fwd": 22}, "heavy")
    while t < t1 - 0.8:      # occasional heavier sigh
        t += s.d(s.rng.uniform(1.2, 2.2))
        s.move(t, s.d(0.5), {"lean": s.rng.uniform(16, 22)}, "smooth", vary=0)
        s.move(t + s.d(0.5), s.d(0.7), {"lean": s.rng.uniform(24, 32)}, "heavy", vary=0)
        t += s.d(1.2)


# action: (function, layers it leaves to weight_layer / gaze_layer)
ROUTINES: dict[str, tuple[Callable, tuple[str, ...]]] = {
    "idle": (act_idle, ("weight", "gaze")),
    "talk": (act_talk, ("weight",)),
    "nod": (act_nod, ("weight",)),
    "point": (act_point, ("weight",)),
    "point_viewer": (act_point_viewer, ()),
    "stop": (act_stop, ("weight",)),
    "look_around": (act_look_around, ("weight",)),
    "give": (act_give, ("weight",)),
    "reach": (act_reach, ()),
    "paint": (act_paint, ("weight",)),
    "arms_crossed": (act_arms_crossed, ("weight", "gaze")),
    "whisper": (act_whisper, ()),
    "arms_up": (act_arms_up, ()),
    "shrug": (act_shrug, ("weight",)),
    "shake_head": (act_shake_head, ("weight",)),
    "facepalm": (act_facepalm, ()),
    "startle": (act_startle, ()),
    "laugh": (act_laugh, ()),
    "slump": (act_slump, ()),
}
LOCOMOTION = ("walk", "trudge")
CANE_LIMITS = (("r_fwd", -4, 10), ("r_out", 5, 9), ("r_elbow", 6, 14), ("r_in", -5, 5))


# --- the result -------------------------------------------------------------

class Track:
    """Samples the keys with follow-through, moving-hold drift, breathing and mood."""

    def __init__(self, seq: Seq, mood: str | None, free: list[tuple[float, float]] | None = None):
        self.seq = seq
        self.free = free or []      # times the cane hand may move (pointing with the cane)
        rng = seq.rng
        self.offset = MOOD_OFFSET.get(mood or "", {})
        self.lag = 1.0 / seq.speed
        self.breath = (rng.uniform(2.2, 3.0), rng.uniform(0, 6.28))
        amp = {"l_fwd": 1.6, "l_out": 1.2, "r_fwd": 1.6, "r_out": 1.2, "l_elbow": 2.0, "r_elbow": 2.0,
               "turn": 2.2, "pitch": 1.4, "tilt": 1.2, "lean": 0.7, "side": 0.5, "twist": 0.8}
        self.noise = {ch: (a, rng.uniform(0.17, 0.45), rng.uniform(0.5, 0.95), rng.uniform(0, 6.28),
                           rng.uniform(0, 6.28)) for ch, a in amp.items()}

    def sample(self, t: float) -> dict[str, float]:
        out = {}
        for ch in CHANNELS:
            v = self.seq.value(ch, t - DELAY[ch] * self.lag) + self.offset.get(ch, 0.0)
            n = self.noise.get(ch)
            if n:
                a, f1, f2, p1, p2 = n
                v += a * (0.6 * math.sin(6.283 * f1 * t + p1) + 0.4 * math.sin(6.283 * f2 * t + p2))
            out[ch] = v
        if self.seq.cane and not any(a <= t < b for a, b in self.free):
            for ch, lo, hi in CANE_LIMITS:
                out[ch] = min(max(out[ch], lo), hi)
        f, ph = self.breath
        out["lift"] += 0.008 * math.sin(t * f + ph)
        out["pitch"] -= 0.8 * math.sin(t * f + ph)
        return out


def track(actions: str | list[str], seconds: float, params: dict[str, Any] | None = None,
          seed: int = 0, mood: str | None = None, cane: bool = False) -> Track:
    """Key poses for one actor in one shot. Several actions play one after the other."""
    params = params or {}
    names = [a for a in ([actions] if isinstance(actions, str) else list(actions)) if a in ROUTINES] or ["idle"]
    rng = random.Random(seed)
    seq = Seq(rng, ENERGY.get(mood or "", 1.0), POSES[rng.choice(REST)], cane)
    at = params.get("at") or []
    bounds = [0.0]
    for i in range(1, len(names)):
        cut = at[i - 1] if i - 1 < len(at) else seconds * i / len(names)
        bounds.append(min(max(float(cut), bounds[-1] + 0.4), seconds))
    bounds.append(seconds + 1.0)
    weight, gaze, free = [], [], []
    for name, t0, t1 in zip(names, bounds, bounds[1:]):
        fn, layers = ROUTINES[name]
        if name == "point":
            free.append((t0, t1))
        fn(seq, t0, t1, params)
        if "weight" in layers:
            weight.append((t0, t1))
        if "gaze" in layers:
            gaze.append((t0, t1))
    # the layers go on after the action keys, only where the action left them free
    for t0, t1 in weight:
        _layer_in_gaps(seq, t0, t1, weight_layer, ("shift", "side", "twist", "leg_l", "leg_r"))
    for t0, t1 in gaze:
        _layer_in_gaps(seq, t0, t1, gaze_layer, ("turn", "tilt", "pitch"))
    return Track(seq, mood, free)


def _layer_in_gaps(seq: Seq, t0: float, t1: float, layer: Callable, channels: tuple[str, ...]) -> None:
    """Run a layer only after the last key the action itself set on those channels."""
    busy = max((seq.times[ch][-1] for ch in channels if len(seq.times[ch]) > 1 and seq.times[ch][-1] >= t0),
               default=t0)
    if busy < t1 - 0.8:
        layer(seq, busy, t1)
