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


def test_other_pipelines_plug_in(monkeypatch, tmp_path):
    """A pipeline that offers /api/items shows up as a tab and can be sent to Postiz."""
    from b2a import postiz, sources

    monkeypatch.setenv("APP_PASSWORD", "secret")
    monkeypatch.setattr(server.config, "DATA_DIR", tmp_path)
    client = TestClient(server.app)
    assert client.get("/api/sources", auth=ME).json() == {"sources": []}
    assert client.get("/api/items", auth=ME).json() == {"items": []}      # we offer the same contract
    calls = []

    class Reply:
        def __init__(self, code=200, data=None, headers=None):
            self.status_code, self.data, self.headers = code, data, headers or {}

        def json(self):
            return self.data

        def iter_content(self, size):
            yield b"mp4"

        def close(self):
            pass

    def fake_request(method, url, allow_redirects, auth, timeout, **kwargs):
        assert auth[1] == "pw" and url.startswith("https://clipper.test/") and allow_redirects is False
        path = url.split("clipper.test")[1]
        calls.append((method, path, kwargs.get("json")))
        if path == "/api/items":
            ok = kwargs["params"]["status"] == "approved"
            return Reply(data={"items": [{"id": 7, "title": "Clutch", "caption": "What a play", "hashtags": ["fps"],
                                          "status": "approved", "video": "/clips/7/video"}] if ok else []})
        if path == "/clips/7/video":
            return Reply(206, headers={"Content-Type": "video/mp4", "Content-Range": "bytes 0-2/3", "X-Other": "x"})
        return Reply(404 if path.endswith("/sent") else 200)

    sent_meta = {}

    def fake_publish(meta, video, channels, when, draft):
        sent_meta.update(meta, bytes=video.read_bytes())
        return {"type": "schedule", "channels": channels}

    monkeypatch.setenv("SOURCE_CLIPS_URL", "https://clipper.test/")
    monkeypatch.setenv("SOURCE_CLIPS_PASSWORD", "pw")
    monkeypatch.setattr(sources.requests, "request", fake_request)
    monkeypatch.setattr(postiz, "publish", fake_publish)
    assert client.get("/api/sources", auth=ME).json() == {"sources": ["clips"]}
    assert client.get("/api/sources/clips/items", auth=ME).json()["items"][0]["title"] == "Clutch"
    assert "error" in client.get("/api/sources/nope/items", auth=ME).json()
    assert client.post("/api/sources/clips/items/7/status", auth=ME, json={"status": "rejected"}).status_code == 200
    assert calls[-1] == ("POST", "/api/items/7/status", {"status": "rejected"})
    assert client.post("/api/sources/clips/items/7/status", auth=ME, json={"status": "posted"}).status_code == 502
    sent = client.post("/api/sources/clips/items/7/publish", auth=ME,
                       json={"channels": ["yt1"], "when": "2026-12-01T18:00:00Z"})
    assert sent.json() == {"type": "schedule", "channels": ["yt1"], "recorded_by_source": False}
    assert sent_meta == {"title": "Clutch", "description": "What a play", "hashtags": ["#fps"], "bytes": b"mp4"}
    video = client.get("/sources/clips/video/7", auth=ME, headers={"Range": "bytes=0-"})
    assert video.status_code == 206 and video.content == b"mp4" and "x-other" not in video.headers
    assert client.get("/sources/clips/video/7").status_code == 401
    with __import__("pytest").raises(RuntimeError):
        sources.video("clips", "//evil.test/x")
