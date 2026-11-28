"""Sound effects, ACE-Step music and trend research. Offline: every outside call is faked."""
import json
import wave
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

from b2a import config, llm, music, plan, render, script as script_mod, sfx, trends, visuals, voice

BOOK = script_mod.load_book("courage-to-be-disliked")
SCRIPT = script_mod.validate(json.loads(
    (config.BOOKS_DIR / "courage-to-be-disliked" / "examples" / "n2-06.json").read_text()), BOOK)


# --- sound effects ------------------------------------------------------------

def test_every_sound_is_short_and_clean(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    for kind in sfx.PRESETS:
        samples = sfx.sound(kind, 1)
        assert 0.05 < len(samples) / sfx.RATE < 1.5, kind
        assert np.isfinite(samples).all() and 0.05 < np.abs(samples).max() <= 1, kind
    # same preset + variant = the same sound on every server
    again = sfx.synth(sfx._params() | {"p_base_freq": 0.4}, seed=7)
    assert np.array_equal(again, sfx.synth(sfx._params() | {"p_base_freq": 0.4}, seed=7))


def test_cues_follow_the_script():
    words = voice.even_timings(voice.narration_text(SCRIPT), 40.0)
    times = voice.scene_times(SCRIPT, words, 40.5)
    cues = sfx.cues(SCRIPT, times)
    kinds = [c["kind"] for c in cues]
    assert cues[0] == {"at": 0.0, "kind": "sting"} and "chime" in kinds
    assert kinds.count("whoosh") == len(SCRIPT["scenes"]) - 2
    assert set(kinds) - {"sting", "whoosh", "chime"}, "reactions of the listener get a sound"
    assert all(0 <= c["at"] <= 40.5 for c in cues)


def test_sfx_track_and_render(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    script = {"scenes": SCRIPT["scenes"][:3]}
    seconds = 5.0
    words = voice.even_timings(voice.narration_text(script), seconds)
    times = voice.scene_times(script, words, seconds + config.TAIL_SECONDS)
    track, used = sfx.make_track(script, times, seconds, tmp_path / "sfx.wav", "x")
    with wave.open(str(track)) as w:
        assert w.getnframes() / w.getframerate() == pytest.approx(seconds + 1, abs=0.05)
    assert used[0] == "sting"

    voice_file = tmp_path / "voice.wav"
    render.ffmpeg("-f", "lavfi", "-i", f"sine=frequency=220:duration={seconds}", str(voice_file))
    image = tmp_path / "p.png"
    render.ffmpeg("-f", "lavfi", "-i", "testsrc2=s=768x1344", "-frames:v", "1", str(image))
    music_file = music.make_music(tmp_path / "m.wav", seconds=4, seed=1)
    out = render.render([{"image": image, "clip": None}] * 3, times, voice_file, words, music_file,
                        tmp_path / "work", tmp_path / "short.mp4", crt=False, sfx=track)
    assert render.duration(out) == pytest.approx(seconds + config.TAIL_SECONDS, abs=0.2)

    monkeypatch.setattr(config, "SFX_VOLUME", 0.0)
    assert sfx.make_track(script, times, seconds, tmp_path / "off.wav") == (None, [])


# --- music --------------------------------------------------------------------

class FakeAceStep:
    """Stands in for the ACE-Step REST API."""

    def __init__(self, tmp_path: Path, fail: bool = False):
        self.sent, self.polls, self.fail = [], 0, fail
        self.mp3 = tmp_path / "gen.mp3"
        render.ffmpeg("-f", "lavfi", "-i", "sine=frequency=440:duration=2", str(self.mp3))

    def reply(self, data):
        return type("R", (), {"raise_for_status": lambda s: None, "json": lambda s: {"code": 200, "data": data},
                              "content": self.mp3.read_bytes()})()

    def post(self, url, headers, timeout, json):
        assert headers == {"Authorization": "Bearer k"}
        if url.endswith("/release_task"):
            self.sent.append(json)
            return self.reply({"task_id": "t1", "status": "queued"})
        self.polls += 1
        if self.fail:
            return self.reply([{"task_id": "t1", "status": 2, "result": "out of memory"}])
        status = 1 if self.polls > 1 else 0
        files = '[{"file": "/v1/audio?path=%2Fapp%2Foutput%2Fa.mp3"}]'
        return self.reply([{"task_id": "t1", "status": status, "result": files}])

    def get(self, url, headers, timeout):
        assert url == "http://acestep:8001/v1/audio?path=%2Fapp%2Foutput%2Fa.mp3"
        return self.reply(None)


def _use_acestep(monkeypatch, tmp_path, fake):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "ACESTEP_URL", "http://acestep:8001")
    monkeypatch.setattr(config, "ACESTEP_API_KEY", "k")
    monkeypatch.setattr(config, "MUSIC_PER_MOOD", 2)
    monkeypatch.setattr(music.time, "sleep", lambda s: None)
    monkeypatch.setattr(music.requests, "post", fake.post)
    monkeypatch.setattr(music.requests, "get", fake.get)


def test_acestep_library_fills_then_reuses(tmp_path, monkeypatch):
    fake = FakeAceStep(tmp_path)
    _use_acestep(monkeypatch, tmp_path, fake)
    first, info = visuals.make_music(tmp_path, 40, "a", "tense")
    assert info["source"] == "acestep" and info["mood"] == "tense" and first.exists()
    sent = fake.sent[0]
    assert sent["lyrics"] == "[Instrumental]" and sent["thinking"] is False and sent["bpm"] == 88
    assert "late-1990s" in sent["prompt"] and "tense" in sent["prompt"]
    visuals.make_music(tmp_path, 40, "b", "tense")
    assert len(fake.sent) == 2
    again, _ = visuals.make_music(tmp_path, 40, "c", "tense")   # library full: no GPU work
    assert len(fake.sent) == 2 and again.parent == music.library_dir("tense")


def test_acestep_failure_falls_back_to_chiptune(tmp_path, monkeypatch):
    _use_acestep(monkeypatch, tmp_path, FakeAceStep(tmp_path, fail=True))
    track, info = visuals.make_music(tmp_path, 5, "a", "nonsense")
    assert info["source"] == "chiptune" and info["mood"] in music.MOODS and track.exists()
    monkeypatch.setattr(config, "ACESTEP_URL", "")
    assert visuals.make_music(tmp_path, 5, "a")[1]["source"] == "chiptune"


def test_script_asks_for_a_music_mood(monkeypatch):
    seen = {}

    def fake_ask(system, messages, max_tokens=16000, **kw):
        seen["system"], seen["user"] = system, messages[0]["content"]
        return json.dumps({**SCRIPT, "music_mood": "warm"})

    monkeypatch.setattr(llm, "ask", fake_ask)
    episode = plan.find_episode("courage-to-be-disliked", "n2-06")
    out = script_mod.write_script(BOOK, episode, trends_brief="Topics that work: people pleasing")
    assert out["music_mood"] == "warm" and "music_mood" in seen["system"]
    assert "people pleasing" in seen["user"] and "never copy a hook" in seen["user"]
    assert "music_mood" not in script_mod.validate({**SCRIPT, "music_mood": "disco"}, BOOK)


# --- trends -------------------------------------------------------------------

def test_scrapecreators_posts_are_found_in_any_shape():
    reply = {"search_item_list": [
        {"aweme_info": {"desc": "Stop people pleasing", "statistics": {"play_count": 120000, "digg_count": 900},
                        "share_url": "https://tiktok.com/1", "author": {"unique_id": "a"}}},
        {"aweme_info": {"desc": "Adler in 30 seconds", "statistics": {"play_count": 8000}}},
        {"ad": True},
    ]}
    posts = trends._posts(reply)
    assert len(posts) == 2
    assert trends._find(posts[0], trends.VIEW_KEYS) == 120000


def test_score_is_lift_over_the_median():
    items = [trends._item("youtube", "q", f"t{i}", views=v) for i, v in enumerate([100, 200, 300, 3000])]
    ranked = trends.score(items)
    assert ranked[0]["title"] == "t3" and ranked[0]["lift"] == 12.0


def test_trend_run_brief_and_next_episode(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(trends, "youtube", lambda q: [trends._item("youtube", q, f"{q} {i}", views=100 * (i + 1))
                                                      for i in range(4)])
    monkeypatch.setattr(trends, "reddit", lambda s: (_ for _ in ()).throw(RuntimeError("blocked")))
    monkeypatch.setattr(trends, "scrapecreators", lambda p, q: [])
    seen = {}

    def fake_ask(system, messages, max_tokens=16000, **kw):
        seen["user"] = messages[0]["content"]
        return json.dumps({"summary": "People pleasing is hot.", "topics": [{"topic": "people pleasing", "why": "3 posts 5x"}],
                           "hook_patterns": [{"pattern": "you-statement about a habit"}],
                           "episode_scores": {"n1-04": 9, "n1-02": 3, "zz-1": 10, "n2-01": "x"}})

    monkeypatch.setattr(llm, "ask", fake_ask)
    result = trends.run("courage-to-be-disliked")
    assert result["episode_scores"] == {"n1-04": 9.0, "n1-02": 3.0}
    assert result["sources"] == ["youtube"] and any("reddit" in e for e in result["errors"])
    assert "lift" in seen["user"] and "n3-03" in seen["user"]
    assert "people pleasing" in trends.prompt_text(trends.latest("courage-to-be-disliked"))
    # the chapter whose turn it is stays the same, the best-fitting episode in it goes first
    scores = trends.episode_scores("courage-to-be-disliked")
    assert plan.next_episode("courage-to-be-disliked", set(), scores)["id"] == "n1-04"
    assert plan.next_episode("courage-to-be-disliked", set())["id"] == "n1-01"


def test_old_brief_is_ignored(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    folder = trends.trends_dir("courage-to-be-disliked")
    folder.mkdir(parents=True)
    old = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    (folder / "latest.json").write_text(json.dumps({"date": old, "summary": "old", "episode_scores": {"n1-04": 9}}))
    assert trends.latest("courage-to-be-disliked") is None
    assert trends.episode_scores("courage-to-be-disliked") == {}
    assert trends.prompt_text(None) == ""


def test_trends_api(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from b2a import server

    monkeypatch.setenv("APP_PASSWORD", "secret")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(trends, "run", lambda book: {"date": "2026-11-27T10:00:00+00:00"})
    client = TestClient(server.app)
    assert client.post("/api/trends?book=nope", auth=("me", "secret")).status_code == 404
    started = client.post("/api/trends", auth=("me", "secret")).json()
    assert started["status"] in ("running", "done")
    assert client.get("/api/trends", auth=("me", "secret")).json()["brief"] is None
