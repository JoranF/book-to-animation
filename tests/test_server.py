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


def test_publish_to_postiz(monkeypatch, tmp_path):
    """Channels are listed, the video is uploaded, and each platform gets its settings."""
    import json

    from b2a import postiz

    monkeypatch.setenv("APP_PASSWORD", "secret")
    monkeypatch.setattr(server.config, "DATA_DIR", tmp_path)
    client = TestClient(server.app)
    monkeypatch.delenv("POSTIZ_URL", raising=False)
    assert client.get("/api/postiz/channels", auth=ME).json() == {"configured": False, "channels": []}

    job = tmp_path / "shorts" / "abc"
    job.mkdir(parents=True)
    (job / "short.mp4").write_bytes(b"video")
    (job / "meta.json").write_text(json.dumps({"id": "abc", "title": "No race", "description": "About racing.",
                                               "hashtags": ["#shorts", "#philosophy"], "voice": "piper:x#8"}))
    calls = []

    class Reply:
        status_code = 200

        def __init__(self, data):
            self.data = data

        def json(self):
            return self.data

    def fake_request(method, url, timeout, headers, **kwargs):
        assert headers == {"Authorization": "k"} and url.startswith("https://postiz.test/api/public/v1/")
        calls.append((method, url.rsplit("/", 1)[-1], kwargs.get("json")))
        if url.endswith("/integrations"):
            return Reply([{"id": "yt1", "name": "Chan", "identifier": "youtube", "disabled": False},
                          {"id": "tt1", "name": "Tok", "identifier": "tiktok", "disabled": False},
                          {"id": "old", "name": "Off", "identifier": "x", "disabled": True}])
        if url.endswith("/upload"):
            return Reply({"id": "m1", "path": "https://postiz.test/uploads/m1.mp4"})
        return Reply([{"postId": "p1", "integration": "yt1"}])

    monkeypatch.setenv("POSTIZ_URL", "https://postiz.test/")
    monkeypatch.setenv("POSTIZ_API_KEY", "k")
    monkeypatch.setattr(postiz.requests, "request", fake_request)
    assert [c["id"] for c in client.get("/api/postiz/channels", auth=ME).json()["channels"]] == ["yt1", "tt1"]
    assert client.post("/api/shorts/abc/publish", auth=ME, json={"channels": ["old"]}).status_code == 502
    sent = client.post("/api/shorts/abc/publish", auth=ME,
                       json={"channels": ["yt1", "tt1"], "when": "2026-12-01T18:00:00+01:00"})
    assert sent.status_code == 200 and sent.json()["type"] == "schedule"
    body = calls[-1][2]
    assert body["date"] == "2026-12-01T17:00:00.000Z" and len(body["posts"]) == 2
    yt, tt = body["posts"]
    assert yt["settings"]["__type"] == "youtube" and yt["settings"]["title"] == "No race"
    assert tt["settings"]["content_posting_method"] == "DIRECT_POST"
    assert yt["value"][0]["image"] == [{"id": "m1", "path": "https://postiz.test/uploads/m1.mp4"}]
    assert "LibriTTS" in yt["value"][0]["content"] and "#philosophy" in yt["value"][0]["content"]
    assert json.loads((job / "meta.json").read_text())["posts"][0]["channels"][0]["platform"] == "youtube"
    assert client.post("/api/shorts/nope/publish", auth=ME, json={"channels": ["yt1"]}).status_code == 404
