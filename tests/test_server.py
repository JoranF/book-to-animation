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
