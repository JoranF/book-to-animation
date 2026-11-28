"""Feedback loop: owner notes, redo with feedback, numbers and the playbook in the script prompt."""
import json

from fastapi.testclient import TestClient

from b2a import learn, llm, pipeline, script, server

ME = ("me", "secret")


def short(tmp_path, sid, views=None, fmt="dialogue", hook="hook", speakers=("philosopher", "youth"), **extra):
    job = tmp_path / "shorts" / sid
    job.mkdir(parents=True, exist_ok=True)
    meta = {"id": sid, "book": "courage-to-be-disliked", "episode": "n2-06", "topic": "No race", "title": f"T {sid}",
            "hook": hook, "hook_type": "question", "format": fmt, "duration_seconds": 38, "speakers": list(speakers),
            "music": {"mood": "calm"}, "review": "pending", "youtube": {}, "analytics": {"views": views}, **extra}
    (job / "meta.json").write_text(json.dumps(meta))
    (job / "script.json").write_text(json.dumps({"title": "Old", "hook": hook, "scenes": [
        {"speaker": "youth", "narration": "Old line", "voice_text": "[sighs] Old line", "stage": {}}]}))
    return meta


def test_notes_and_numbers_reach_the_script_prompt(monkeypatch, tmp_path):
    monkeypatch.setattr(learn.config, "DATA_DIR", tmp_path)
    assert script.load_learnings() == ""
    learn.add_note("Never open with a question")
    learn.add_note("Never open with a question")             # no duplicates
    assert len(learn.notes()) == 1
    for i in range(4):
        short(tmp_path, f"s{i}", views=100 * (i + 1), fmt="dialogue" if i % 2 else "myth_buster", hook=f"hook {i}")
    text = script.load_learnings()
    assert "Never open with a question" in text and "Results of our own" not in text     # 4 < MIN_POSTS
    short(tmp_path, "s4", views=5000, hook="the winner")
    text = script.load_learnings()
    assert "Results of our own posted Shorts (5 Shorts" in text and '"the winner" (5000 views' in text
    assert "By format:" in text
    perf = learn.performance(pipeline.list_shorts())
    assert perf["format"][0]["name"] == "dialogue" and perf["talk"][0]["name"] == "dialogue"
    learn.delete_note(learn.notes()[0]["id"])
    assert learn.notes() == []


def test_playbook_waits_for_enough_posts_and_a_day(monkeypatch, tmp_path):
    monkeypatch.setattr(learn.config, "DATA_DIR", tmp_path)
    calls = []
    monkeypatch.setattr(llm, "ask", lambda system, messages, max_tokens=0: calls.append(messages) or
                        "Here you go:\n- Open with the youth's complaint\n- Keep it under 40 seconds")
    for i in range(7):
        short(tmp_path, f"s{i}", views=10 * i)
    assert learn.refresh_playbook(pipeline.list_shorts()) is None and not calls
    short(tmp_path, "s7", views=999)
    pb = learn.refresh_playbook(pipeline.list_shorts())
    assert pb["rules"] == ["- Open with the youth's complaint", "- Keep it under 40 seconds"] and len(calls) == 1
    assert learn.refresh_playbook(pipeline.list_shorts()) is None and len(calls) == 1     # not again the same day
    assert "Open with the youth's complaint" in script.load_learnings()


def test_redo_api_queues_a_new_version_and_remembers(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_PASSWORD", "secret")
    monkeypatch.setattr(server.config, "DATA_DIR", tmp_path)
    short(tmp_path, "old1")
    monkeypatch.setattr(server.todo, "put", lambda _id: None)        # no real render
    client = TestClient(server.app)
    assert client.post("/api/shorts/nope/redo", auth=ME, json={"feedback": "faster"}).status_code == 404
    job = client.post("/api/shorts/old1/redo", auth=ME, json={"feedback": "The hook is too slow", "remember": True}).json()
    assert job["redo_of"] == "old1" and job["episode"] == "n2-06" and job["status"] == "queued"
    again = client.post("/api/shorts/old1/redo", auth=ME, json={"feedback": "other"}).json()
    assert again["id"] == job["id"]                                  # one redo at a time
    notes = client.get("/api/notes", auth=ME).json()["notes"]
    assert notes[0]["text"] == "The hook is too slow" and "n2-06" in notes[0]["source"]
    assert client.post("/api/notes", auth=ME, json={"text": "Shorter lines"}).json()["notes"][0]["text"] == "Shorter lines"
    learned = client.get("/api/learnings", auth=ME).json()
    assert "Shorter lines" in learned["text"] and learned["performance"]["posts"] == 0
    server.replaced("old1", job["id"])
    meta = client.get("/api/shorts/old1", auth=ME).json()
    assert meta["redone_as"] == job["id"] and meta["review"] == "rejected"
    server.jobs.clear()


def test_feedback_patch_keeps_numbers(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_PASSWORD", "secret")
    monkeypatch.setattr(server.config, "DATA_DIR", tmp_path)
    short(tmp_path, "p1")
    seen = []
    monkeypatch.setattr(learn, "refresh_in_background", lambda fn: seen.append(fn))
    client = TestClient(server.app)
    meta = client.patch("/api/shorts/p1/feedback", auth=ME, json={"analytics": {"views": 1234, "likes": 50}}).json()
    assert meta["analytics"]["views"] == 1234 and seen


def test_redo_prompt_carries_the_old_script_and_feedback(monkeypatch):
    sent = []

    def fake_ask(system, messages, max_tokens=0):
        sent.append(messages[0]["content"])
        raise RuntimeError("stop here")
    monkeypatch.setattr(llm, "ask", fake_ask)
    book = script.load_book("courage-to-be-disliked")
    from b2a import plan
    episode = plan.find_episode("courage-to-be-disliked", "n2-06")
    old = {"title": "Old title", "hook": "Old hook", "scenes": [{"speaker": "youth", "narration": "x", "voice_text": "[sighs] x"}]}
    try:
        script.write_script(book, episode, previous=old, feedback="make the youth angrier")
    except RuntimeError:
        pass
    assert "This is a REDO" in sent[0] and "make the youth angrier" in sent[0] and "Old hook" in sent[0]
