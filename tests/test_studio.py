import pytest
from fastapi.testclient import TestClient

from studio import app as studio_app, postiz, sources

ME = ("me", "secret")


class Reply:
    def __init__(self, code=200, data=None, headers=None):
        self.status_code, self.data, self.headers, self.text = code, data, headers or {}, ""

    def json(self):
        return self.data

    def iter_content(self, size):
        yield b"mp4"

    def close(self):
        pass


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("STUDIO_PASSWORD", "secret")
    for key in ("POSTIZ_URL", "POSTIZ_API_KEY", "SOURCE_CLIPS_URL", "SOURCE_SHORTS_URL"):
        monkeypatch.delenv(key, raising=False)
    return TestClient(studio_app.app)


def test_login_and_empty_state(client, monkeypatch):
    assert client.get("/health").json() == {"ok": True, "password_set": True, "postiz_set": False, "sources": []}
    assert client.get("/").status_code == 401
    assert client.get("/", auth=("me", "wrong")).status_code == 401
    assert "Studio" in client.get("/", auth=ME).text
    assert client.get("/api/sources", auth=ME).json() == {"sources": [], "postiz": False}
    assert client.get("/api/postiz/channels", auth=ME).json() == {"configured": False, "channels": []}
    monkeypatch.delenv("STUDIO_PASSWORD")
    assert client.get("/", auth=("me", "")).status_code == 401


def test_postiz_gets_the_video_and_settings(monkeypatch, tmp_path):
    calls = []

    def fake_request(method, url, timeout, headers, **kwargs):
        assert headers == {"Authorization": "k"} and url.startswith("https://postiz.test/api/public/v1/")
        calls.append((method, url.rsplit("/", 1)[-1], kwargs.get("json")))
        if url.endswith("/integrations"):
            return Reply(data=[{"id": "yt1", "name": "Chan", "identifier": "youtube", "disabled": False},
                               {"id": "tt1", "name": "Tok", "identifier": "tiktok", "disabled": False},
                               {"id": "old", "name": "Off", "identifier": "x", "disabled": True}])
        if url.endswith("/upload"):
            return Reply(data={"id": "m1", "path": "https://postiz.test/uploads/m1.mp4"})
        return Reply(data=[{"postId": "p1", "integration": "yt1"}])

    monkeypatch.setenv("POSTIZ_URL", "https://postiz.test/")
    monkeypatch.setenv("POSTIZ_API_KEY", "k")
    monkeypatch.setattr(postiz.requests, "request", fake_request)
    video = tmp_path / "short.mp4"
    video.write_bytes(b"video")
    meta = {"title": "No race", "description": "About racing.", "hashtags": ["#shorts", "#philosophy"]}
    assert [c["id"] for c in postiz.channels()] == ["yt1", "tt1"]
    with pytest.raises(RuntimeError):
        postiz.publish(meta, video, ["old"])
    from datetime import datetime
    sent = postiz.publish(meta, video, ["yt1", "tt1"], datetime.fromisoformat("2026-12-01T18:00:00+01:00"))
    assert sent["type"] == "schedule" and sent["channels"][0] == {"id": "yt1", "platform": "youtube", "name": "Chan"}
    body = calls[-1][2]
    assert body["date"] == "2026-12-01T17:00:00.000Z" and len(body["posts"]) == 2
    yt, tt = body["posts"]
    assert yt["settings"]["__type"] == "youtube" and yt["settings"]["title"] == "No race"
    assert tt["settings"]["content_posting_method"] == "DIRECT_POST"
    assert yt["value"][0]["image"] == [{"id": "m1", "path": "https://postiz.test/uploads/m1.mp4"}]
    assert "#philosophy" in yt["value"][0]["content"]


def test_a_pipeline_plugs_in(client, monkeypatch):
    """A pipeline that offers /api/items shows up as a tab and can be sent to Postiz."""
    calls = []

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
    assert client.get("/api/sources", auth=ME).json()["sources"] == ["clips"]
    assert client.get("/api/sources/clips/items", auth=ME).json()["items"][0]["title"] == "Clutch"
    assert "error" in client.get("/api/sources/nope/items", auth=ME).json()
    assert client.post("/api/sources/clips/items/7/status", auth=ME, json={"status": "rejected"}).status_code == 200
    assert calls[-1] == ("POST", "/api/items/7/status", {"status": "rejected"})
    assert client.post("/api/sources/clips/items/7/status", auth=ME, json={"status": "posted"}).status_code == 502
    sent = client.post("/api/sources/clips/items/7/publish", auth=ME,
                       json={"channels": ["yt1"], "when": "2026-12-01T18:00:00Z"})
    assert sent.json() == {"type": "schedule", "channels": ["yt1"], "recorded_by_source": False}
    assert calls[-1][:2] == ("POST", "/api/items/7/sent")
    assert sent_meta == {"title": "Clutch", "description": "What a play", "hashtags": ["#fps"], "bytes": b"mp4"}
    video = client.get("/sources/clips/video/7", auth=ME, headers={"Range": "bytes=0-"})
    assert video.status_code == 206 and video.content == b"mp4" and "x-other" not in video.headers
    assert client.get("/sources/clips/video/7").status_code == 401
    with pytest.raises(RuntimeError):
        sources.video("clips", "//evil.test/x")


def test_studio_reads_the_shorts_app(client, monkeypatch, tmp_path):
    """The real book-to-animation app is a source like any other."""
    import json

    from b2a import server

    monkeypatch.setenv("APP_PASSWORD", "pw")
    monkeypatch.setattr(server.config, "DATA_DIR", tmp_path)
    job = tmp_path / "shorts" / "abc"
    job.mkdir(parents=True)
    (job / "short.mp4").write_bytes(b"mp4")
    (job / "meta.json").write_text(json.dumps({"id": "abc", "title": "No race", "description": "About racing.",
                                               "hashtags": ["#shorts"], "episode": "n2-06"}))
    shorts = TestClient(server.app)

    def through(method, url, allow_redirects, auth, timeout, **kwargs):
        kwargs.pop("stream", None)
        reply = shorts.request(method, url.split("shorts.test")[1], auth=auth, **kwargs)
        reply.iter_content = lambda size: [reply.content]      # requests' name for it
        return reply

    monkeypatch.setenv("SOURCE_SHORTS_URL", "https://shorts.test")
    monkeypatch.setenv("SOURCE_SHORTS_PASSWORD", "pw")
    monkeypatch.setattr(sources.requests, "request", through)
    monkeypatch.setattr(postiz, "publish", lambda meta, video, channels, when, draft: {
        "type": "now", "date": "2026-12-01T17:00:00.000Z", "caption": meta["description"],
        "channels": [{"id": "yt1", "platform": "youtube", "name": "Chan"}]})
    assert client.get("/api/sources/shorts/items?status=pending", auth=ME).json()["items"][0]["label"] == "n2-06"
    assert client.post("/api/sources/shorts/items/abc/status", auth=ME, json={"status": "approved"}).status_code == 200
    sent = client.post("/api/sources/shorts/items/abc/publish", auth=ME, json={"channels": ["yt1"]}).json()
    assert sent["recorded_by_source"] is True and "#shorts" in sent["caption"]
    meta = json.loads((job / "meta.json").read_text())
    assert meta["review"] == "posted" and meta["posts"][0]["channels"][0]["platform"] == "youtube"
    assert client.get("/api/sources/shorts/items?status=posted", auth=ME).json()["items"][0]["id"] == "abc"
