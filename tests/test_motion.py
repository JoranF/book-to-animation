"""Pose-to-pose animation: no Blender needed."""
import pytest

from b2a import motion, stage, visuals


def _arms(track, seconds=5.0):
    return [tuple(round(track.sample(i / 15)[ch], 1) for ch in motion.ARMS) for i in range(int(seconds * 15))]


def test_every_action_keys_cleanly():
    for name in motion.ROUTINES:
        for mood in (None, "sad", "angry"):
            track = motion.track(name, 4.0, {}, seed=3, mood=mood)
            for i in range(70):
                pose = track.sample(i / 15)
                assert set(pose) == set(motion.CHANNELS)
                assert all(abs(v) < 400 for v in pose.values())


def test_same_action_differs_per_shot_and_repeats_per_seed():
    a = _arms(motion.track("talk", 5.0, {}, seed=1))
    b = _arms(motion.track("talk", 5.0, {}, seed=2))
    assert a != b
    assert a == _arms(motion.track("talk", 5.0, {}, seed=1))


def test_talk_is_poses_not_a_loop():
    """The arms hold poses (few changes per second), unlike a sine wave."""
    frames = _arms(motion.track("talk", 6.0, {}, seed=5))
    moving = sum(1 for x, y in zip(frames, frames[1:]) if max(abs(p - q) for p, q in zip(x, y)) > 4)
    assert 5 < moving < len(frames) * 0.7


def test_gesture_strokes_land_on_beats():
    track = motion.track("talk", 6.0, {"beats": [1.0, 2.5, 4.0]}, seed=9)
    rest = track.sample(0.6)
    stroke = track.sample(1.05)
    assert max(abs(stroke[c] - rest[c]) for c in motion.ARMS) > 15


def test_cane_hand_stays_down_except_when_pointing():
    track = motion.track("talk", 5.0, {}, seed=4, cane=True)
    assert all(track.sample(i / 15)["r_fwd"] <= 10.01 for i in range(75))
    point = motion.track("point", 3.0, {}, seed=4, cane=True)
    assert max(point.sample(i / 15)["r_fwd"] for i in range(45)) > 60


def test_action_lists_play_in_order():
    track = motion.track(["startle", "arms_crossed"], 4.0, {"at": [1.5]}, seed=2)
    assert track.sample(0.15)["lift"] > 0.05            # jumps first
    late = track.sample(3.5)
    assert late["l_elbow"] > 80 and late["r_elbow"] > 80  # then arms crossed


def test_stage_accepts_action_lists():
    good = stage.validate({"set": "field", "actors": [{"who": "youth", "actions": ["talk", "shrug"], "at": [2]}]})
    assert good["actors"][0]["action"] == "talk"
    for bad in (["talk", "walk"], [], ["dance"]):
        with pytest.raises(ValueError):
            stage.validate({"set": "field", "actors": [{"who": "youth", "actions": bad}]})


def test_speech_beats_pick_stressed_words():
    words = [{"text": t, "start": s, "end": s + 0.2} for t, s in
             (("You", 0.0), ("are", 0.25), ("not", 0.5), ("responsible,", 0.7), ("for", 1.2),
              ("their", 1.4), ("feelings.", 1.6), ("Next", 9.0))]
    assert visuals.speech_beats(words, 0.0, 5.0) == [0.0, 0.7, 1.2, 1.6]
