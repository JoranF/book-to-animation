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


def test_cost_estimate_is_in_budget():
    cost = pipeline.estimate_cost(SCRIPT, clip_seconds=42, made_music=True)
    assert 0.5 <= cost <= 3.0


def test_make_short_with_fake_fal(tmp_path: Path, monkeypatch):
    """Whole pipeline, with fal replaced by local placeholder media."""
    from b2a import fal

    calls = []

    def fake_run(endpoint, arguments, retries=2):
        calls.append(endpoint)
        if endpoint == config.TTS_MODEL:
            text = arguments["text"]
            starts = [i * 0.02 for i in range(len(text))]
            return {"audio": {"url": "fake://voice.mp3"},
                    "timestamps": [{"characters": list(text),
                                    "character_start_times_seconds": starts,
                                    "character_end_times_seconds": [s + 0.02 for s in starts]}]}
        if endpoint == config.VIDEO_MODEL:
            return {"video": {"url": "fake://clip.mp4"}}
        if endpoint == config.MUSIC_MODEL:
            return {"audio": {"url": "fake://music.mp3"}}
        return {"images": [{"url": "fake://image.png"}]}

    def fake_download(url, dest):
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.suffix == ".png":
            render.ffmpeg("-f", "lavfi", "-i", "testsrc2=s=576x1024", "-frames:v", "1", str(dest))
        elif dest.suffix == ".mp4":
            render.ffmpeg("-f", "lavfi", "-i", "testsrc2=s=432x768:r=24:d=1", "-pix_fmt", "yuv420p", str(dest))
        else:
            seconds = len(voice.narration_text(SHORT_SCRIPT)) * 0.02
            render.ffmpeg("-f", "lavfi", "-i", f"sine=frequency=330:duration={seconds}", str(dest))
        return dest

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "ANIMATE", "1")
    monkeypatch.setattr(fal, "run", fake_run)
    monkeypatch.setattr(fal, "download", fake_download)
    monkeypatch.setattr(fal, "upload", lambda path: "fake://upload")
    monkeypatch.setattr(fal, "chat", lambda *a, **k: json.dumps(SHORT_SCRIPT))

    meta = pipeline.make_short("courage-to-be-disliked", "Separation of tasks", progress=lambda s: None)
    job = tmp_path / "shorts" / meta["id"]
    assert (job / "short.mp4").exists() and (job / "thumb.jpg").exists()
    assert meta["hook"] == SHORT_SCRIPT["hook"] and meta["animated_scenes"] == 1
    assert meta["scene_count"] == len(SHORT_SCRIPT["scenes"])
    assert calls.count(config.IMAGE_MODEL) == 2  # one reference per character
    assert pipeline.list_shorts()[0]["id"] == meta["id"]

    # A second run with the same id reuses everything that is already there.
    calls.clear()
    pipeline.make_short("courage-to-be-disliked", "Separation of tasks", short_id=meta["id"], progress=lambda s: None)
    assert calls == []


SHORT_SCRIPT = {**SCRIPT, "scenes": [
    {**s, "narration": "One two three four five six seven eight nine ten eleven twelve."}
    for s in SCRIPT["scenes"][:6]
]}
