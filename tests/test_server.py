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
