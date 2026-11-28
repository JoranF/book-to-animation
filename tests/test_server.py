from fastapi.testclient import TestClient

from b2a import server

ME = ("me", "secret")


def test_auth_and_pages(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_PASSWORD", "secret")
    monkeypatch.setattr(server.config, "DATA_DIR", tmp_path)
    client = TestClient(server.app)
    assert client.get("/health").json()["ok"] is True
    assert client.get("/").status_code == 401
    assert client.get("/", auth=("me", "wrong")).status_code == 401
    page = client.get("/", auth=ME)
    assert page.status_code == 200 and "Make Short" in page.text
    plan = client.get("/api/episodes", auth=ME).json()
    assert len(plan["chapters"]) == 5 and plan["chapters"][0]["episodes"][0]["made"] is False
    assert client.post("/api/shorts", auth=ME, json={"episode": "zz-99"}).status_code == 404
    assert client.post("/api/shorts", auth=ME, json={"topic": ""}).status_code == 422
    assert client.get("/api/shorts", auth=ME).json() == {"jobs": [], "shorts": []}
    assert client.get("/files/nope/short.mp4", auth=ME).status_code == 404
    assert client.get("/files/nope/passwd", auth=ME).status_code == 404
    assert client.post("/api/shorts", auth=ME, json={"book": "nope", "topic": "abc"}).status_code == 404


def test_no_password_means_locked(monkeypatch):
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    assert TestClient(server.app).get("/", auth=("me", "")).status_code == 401


def test_items_contract_for_the_dashboard(monkeypatch, tmp_path):
    import json

    monkeypatch.setenv("APP_PASSWORD", "secret")
    monkeypatch.setattr(server.config, "DATA_DIR", tmp_path)
    client = TestClient(server.app)
    job = tmp_path / "shorts" / "abc"
    job.mkdir(parents=True)
    (job / "meta.json").write_text(json.dumps({"id": "abc", "title": "No race", "description": "About racing.",
                                               "hashtags": ["#shorts"], "voice": "piper:x#8", "episode": "n2-06",
                                               "duration_seconds": 34.8}))
    assert client.get("/api/items").status_code == 401
    assert client.get("/api/items", auth=ME).json() == {"items": []}
    found = client.get("/api/items?status=pending", auth=ME).json()["items"][0]
    assert found["video"] == "/files/abc/short.mp4" and "LibriTTS" in found["caption"] and found["label"] == "n2-06"
    assert client.post("/api/items/abc/status", auth=ME, json={"status": "posted"}).status_code == 422
    assert client.post("/api/items/abc/status", auth=ME, json={"status": "approved"}).json()["item"]["status"] == "approved"
    sent = client.post("/api/items/abc/sent", auth=ME, json={"type": "schedule", "date": "2026-12-01T17:00:00.000Z",
                                                             "channels": [{"id": "yt1", "platform": "youtube"}]})
    assert sent.json()["item"]["status"] == "posted"
    assert json.loads((job / "meta.json").read_text())["posts"][0]["channels"][0]["id"] == "yt1"
    assert client.post("/api/items/nope/sent", auth=ME, json={}).status_code == 404


def test_every_book_plan_is_valid():
    from b2a import plan, script

    slugs = server.all_books()
    assert len(slugs) >= 9 and "meditations" in slugs and "courage-to-be-disliked" in slugs
    seen = set()
    for slug in slugs:
        book = script.load_book(slug)
        assert book["slug"] == slug and set(book["characters"]) == {"philosopher", "youth"}
        eps = plan.episodes(slug)
        assert len(eps) >= 14
        for ep in eps:
            assert ep["format"] in plan.FORMATS and ep["hook"] and ep["angle"]
            assert len(ep["hook"].split()) <= 14
            assert (slug, ep["id"]) not in seen
            seen.add((slug, ep["id"]))


def test_books_list_and_auto_rotation(monkeypatch, tmp_path):
    from b2a import plan

    monkeypatch.setenv("APP_PASSWORD", "secret")
    monkeypatch.setattr(server.config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(server.todo, "put", lambda _id: None)    # no real render
    monkeypatch.setattr(server, "jobs", {})
    client = TestClient(server.app)
    books = client.get("/api/books", auth=ME).json()["books"]
    assert {b["slug"] for b in books} == set(server.all_books()) and all(b["made"] == 0 for b in books)
    picked = [client.post("/api/shorts", auth=ME, json={"book": "auto"}).json()["book"] for _ in range(3)]
    assert len(set(picked)) == 3                                 # takes turns between books
    shorts = [{"book": "art-of-war", "episode": ep["id"]} for ep in plan.episodes("art-of-war")]
    assert plan.next_book(["art-of-war", "meditations"], shorts) == "meditations"


def test_models_per_step_can_be_chosen_in_the_dashboard(monkeypatch, tmp_path):
    from b2a import config, settings

    monkeypatch.setenv("APP_PASSWORD", "secret")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    for attr in settings.DEFAULTS:              # restore whatever apply() changes
        monkeypatch.setattr(config, attr, getattr(config, attr))
    client = TestClient(server.app)
    view = client.get("/api/settings/models", auth=ME).json()
    assert [s["key"] for s in view["steps"]] == ["script", "staging", "clarity", "assets", "analysis"]
    assert {m["id"] for m in view["models"]} >= {"claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"}
    staging = next(s for s in view["steps"] if s["key"] == "staging")
    assert staging["model"] == staging["default_model"] == settings.DEFAULTS["STAGE_MODEL"]

    saved = client.put("/api/settings/models", auth=ME,
                       json={"staging": {"model": "claude-haiku-5-5", "effort": "low"}, "clarity_min": 0}).json()
    staging = next(s for s in saved["steps"] if s["key"] == "staging")
    assert staging["model"] == "claude-haiku-5-5" and saved["clarity_min"] == 0
    assert config.STAGE_MODEL == "claude-haiku-5-5" and config.STAGE_EFFORT == "low" and config.CLARITY_MIN == 0
    assert config.SCRIPT_MODEL == settings.DEFAULTS["SCRIPT_MODEL"]       # untouched step keeps its value
    assert client.put("/api/settings/models", auth=ME, json={"script": {"model": "gpt-9"}}).status_code == 422
    assert client.put("/api/settings/models", auth=ME, json={"clarity_min": 11}).status_code == 422

    back = client.put("/api/settings/models", auth=ME, json={"reset": True}).json()
    assert config.STAGE_MODEL == settings.DEFAULTS["STAGE_MODEL"] and back["clarity_min"] == settings.DEFAULTS["CLARITY_MIN"]
    assert "Claude models per step" in client.get("/", auth=ME).text
