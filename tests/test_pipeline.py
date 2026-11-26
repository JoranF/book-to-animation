"""Offline tests: no fal calls. Rendering uses generated placeholder media."""
import json
import subprocess
from pathlib import Path

import pytest

from b2a import config, pipeline, render, script as script_mod, voice

BOOK = script_mod.load_book("courage-to-be-disliked")
SCRIPT = json.loads((config.BOOKS_DIR / "courage-to-be-disliked" / "examples" / "separation-of-tasks.json").read_text())


def test_example_script_is_valid():
    script = script_mod.validate(json.loads(json.dumps(SCRIPT)), BOOK)
    assert 95 <= sum(len(s["narration"].split()) for s in script["scenes"]) <= 125


def test_validate_rejects_too_short():
    with pytest.raises(ValueError):
        script_mod.validate({"scenes": [{"narration": "Hi.", "image": "x"}] * 6}, BOOK)


def test_character_timestamps_become_words():
    text = "Hi you. Ok?"
    starts = [i * 0.1 for i in range(len(text))]
    words = voice.parse_timestamps([{"characters": list(text),
                                     "character_start_times_seconds": starts,
                                     "character_end_times_seconds": [s + 0.1 for s in starts]}])
    assert [w["text"] for w in words] == ["Hi", "you.", "Ok?"]
    assert words[1]["start"] == pytest.approx(0.3)


def test_word_timestamps_and_fallback():
    words = voice.parse_timestamps([{"text": "Hi", "start": 0, "end": 0.2, "type": "word"},
                                    {"text": " ", "start": 0.2, "end": 0.3, "type": "spacing"}])
    assert len(words) == 1
    even = voice.even_timings("one two three", 3.0)
    assert even[-1]["end"] == pytest.approx(3.0)


def test_scene_times_cover_whole_video():
    words = voice.even_timings(voice.narration_text(SCRIPT), 40.0)
    times = voice.scene_times(SCRIPT, words, 40.5)
    assert times[0][0] == 0.0 and times[-1][1] == 40.5
    assert all(a[1] == b[0] for a, b in zip(times, times[1:]))
    assert all(end - start > 1.0 for start, end in times)


def test_caption_chunks_stop_at_sentence_end():
    words = voice.even_timings("Stop. Ask one question now please.", 4.0)
    chunks = render.caption_chunks(words)
    assert [w["text"] for w in chunks[0]] == ["Stop."]
    assert all(len(c) <= 3 for c in chunks)


def test_render_end_to_end(tmp_path: Path):
    """Full edit with placeholder pictures and a beep instead of a voice."""
    script = {"scenes": SCRIPT["scenes"][:3]}
    seconds = 6.0
    voice_file = tmp_path / "voice.mp3"
    render.ffmpeg("-f", "lavfi", "-i", f"sine=frequency=220:duration={seconds}", str(voice_file))
    words = voice.even_timings(voice.narration_text(script), seconds)
    times = voice.scene_times(script, words, seconds + config.TAIL_SECONDS)
    scenes = []
    for i, color in enumerate(["red", "green", "blue"]):
        image = tmp_path / f"{i}.png"
        render.ffmpeg("-f", "lavfi", "-i", f"testsrc2=s=768x1344,drawbox=c={color}:t=40", "-frames:v", "1", str(image))
        scenes.append({"image": image, "clip": None})
    clip = tmp_path / "0.mp4"
    render.ffmpeg("-f", "lavfi", "-i", "testsrc2=s=432x768:r=24:d=1.5", "-pix_fmt", "yuv420p", str(clip))
    scenes[0]["clip"] = clip

    out = render.render(scenes, times, voice_file, words, None, tmp_path / "work", tmp_path / "short.mp4")
    probe = json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(out)],
        capture_output=True, text=True, check=True).stdout)
    video = next(s for s in probe["streams"] if s["codec_type"] == "video")
    assert (video["width"], video["height"]) == (1080, 1920)
    assert any(s["codec_type"] == "audio" for s in probe["streams"])
    assert float(probe["format"]["duration"]) == pytest.approx(seconds + config.TAIL_SECONDS, abs=0.2)


def test_cost_estimate_only_counts_fal_calls():
    assert pipeline.estimate_cost(SCRIPT, wrote_script=False, voice_backend="piper") == 0
    assert 0.03 <= pipeline.estimate_cost(SCRIPT, wrote_script=True, voice_backend="fal") <= 0.5


def test_stage_validation_catches_unknown_parts():
    from b2a import stage

    good = stage.validate(json.loads(json.dumps(stage.DEFAULT)))
    assert good["camera"]["move"] == "push_in"
    for broken in ({"set": "moon"},
                   {"set": "field", "actors": [{"who": "wizard"}]},
                   {"set": "field", "actors": [{"who": "youth", "action": "fly"}]},
                   {"set": "field", "props": [{"type": "dragon"}]},
                   {"set": "field", "camera": {"move": "spin"}},
                   {"set": "field", "actors": [{"who": "youth", "pos": "left"}]}):
        with pytest.raises(ValueError):
            stage.validate(broken)


def test_music_is_generated(tmp_path: Path):
    from b2a import music

    track = music.make_music(tmp_path / "m.wav", seconds=6, seed=3)
    assert render.duration(track) == pytest.approx(6, abs=0.1)


def test_blender_draws_every_example_scene(tmp_path: Path):
    """One frame of each example scene: covers all sets and most props and moves."""
    pytest.importorskip("bpy")
    from b2a import stage, world

    assert set(world.SETS) == set(stage.SETS)
    assert set(world.PROPS) == set(stage.PROPS)
    assert set(world.ACTIONS) == set(stage.ACTIONS)
    assert set(world.LOOKS) == set(stage.WHO) and set(world.HEADS) == set(stage.HEADS)
    for i, scene in enumerate(SCRIPT["scenes"]):
        world.render_scene(scene["stage"], 4.0, str(tmp_path / str(i)), only_frame=20)
        assert (tmp_path / str(i) / "f_0020.png").stat().st_size > 2000


def test_make_short_with_fakes(tmp_path: Path, monkeypatch):
    """Whole pipeline with the fal voice and Blender replaced by placeholders."""
    from b2a import fal, visuals

    calls = []

    def fake_run(endpoint, arguments, retries=2):
        calls.append(endpoint)
        text = arguments["text"]
        starts = [i * 0.02 for i in range(len(text))]
        return {"audio": {"url": "fake://voice.mp3"},
                "timestamps": [{"characters": list(text),
                                "character_start_times_seconds": starts,
                                "character_end_times_seconds": [s + 0.02 for s in starts]}]}

    def fake_download(url, dest):
        seconds = len(voice.narration_text(SHORT_SCRIPT)) * 0.02
        render.ffmpeg("-f", "lavfi", "-i", f"sine=frequency=330:duration={seconds}", str(dest))
        return dest

    def fake_stage(stage, seconds, dest):
        calls.append("blender")
        render.ffmpeg("-f", "lavfi", "-i", f"testsrc2=s=360x640:r=15:d={seconds:.2f}", "-pix_fmt", "yuv420p", str(dest))
        return dest

    monkeypatch.setenv("FAL_KEY", "test")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(fal, "run", fake_run)
    monkeypatch.setattr(fal, "download", fake_download)
    monkeypatch.setattr(fal, "chat", lambda *a, **k: json.dumps(SHORT_SCRIPT))
    monkeypatch.setattr(visuals, "render_stage", fake_stage)

    meta = pipeline.make_short("courage-to-be-disliked", "Life is not a competition", progress=lambda s: None)
    job = tmp_path / "shorts" / meta["id"]
    assert (job / "short.mp4").exists() and (job / "thumb.jpg").exists()
    assert meta["hook"] == SHORT_SCRIPT["hook"] and meta["voice"].startswith("elevenlabs-via-fal")
    assert meta["scene_count"] == len(SHORT_SCRIPT["scenes"]) == calls.count("blender")
    assert meta["estimated_cost_usd"] > 0
    assert pipeline.list_shorts()[0]["id"] == meta["id"]


SHORT_SCRIPT = {**SCRIPT, "scenes": [
    {**s, "narration": "One two three four five six seven eight nine ten eleven twelve."}
    for s in SCRIPT["scenes"][:6]
]}


def test_elevenlabs_voice_per_speaker(tmp_path: Path, monkeypatch):
    """Each scene is one request, with the speaker's own voice and exact timings."""
    import base64

    sample = tmp_path / "s.mp3"
    render.ffmpeg("-f", "lavfi", "-i", "sine=frequency=300:duration=1", str(sample))
    seen = []

    class Reply:
        status_code = 200

        def __init__(self, text):
            self.text = text

        def json(self):
            starts = [i * 0.05 for i in range(len(self.text))]
            return {"audio_base64": base64.b64encode(sample.read_bytes()).decode(),
                    "alignment": {"characters": list(self.text),
                                  "character_start_times_seconds": starts,
                                  "character_end_times_seconds": [s + 0.05 for s in starts]}}

    def fake_post(url, params, headers, json, timeout):
        seen.append(url.split("/")[-2])
        assert headers["xi-api-key"] == "k"
        return Reply(json["text"])

    monkeypatch.setenv("ELEVENLABS_API_KEY", "k")
    monkeypatch.setattr(voice.requests, "post", fake_post)
    script = {"scenes": [{"narration": "Stop right there."},
                         {"narration": "Whose task is this?", "speaker": "philosopher"}]}
    audio, words, backend = voice.make_voice(script, tmp_path, render.duration)
    assert backend == "elevenlabs" and audio.exists()
    assert seen == [config.ELEVENLABS_VOICES["narrator"], config.ELEVENLABS_VOICES["philosopher"]]
    assert [w["text"] for w in words] == ["Stop", "right", "there.", "Whose", "task", "is", "this?"]
    assert words[3]["start"] > 1.0   # second scene starts after the first recording
