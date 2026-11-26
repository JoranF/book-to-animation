"""Other pipelines whose videos show up in this dashboard.

Every pipeline stays its own app. To appear here it only has to offer this
small contract over HTTP (basic auth, any username, its own password):

  GET  /api/items?status=pending|approved|posted|rejected
       -> {"items": [{"id", "title", "caption", "hashtags": [..], "seconds",
                      "status", "video": "/path/to/video.mp4", "label",
                      "error", "posted"}]}
       Only id, title, status and video are required.
  GET  <video>                      the mp4, Range requests welcome
  POST /api/items/{id}/status       {"status": "approved"|"rejected"|"pending"}   (optional)
  POST /api/items/{id}/sent         what was sent to Postiz, so the pipeline can
                                    mark the item as posted                      (optional)

A pipeline is plugged in with two settings, NAME being any word:
  SOURCE_<NAME>_URL=https://...     SOURCE_<NAME>_PASSWORD=...
The dashboard does the sending to Postiz itself, so a new pipeline never has
to know about Postiz.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import requests

STATUSES = ("pending", "approved", "posted", "rejected")


def names() -> list[str]:
    found = [m.group(1).lower() for key in os.environ
             if (m := re.fullmatch(r"SOURCE_([A-Z0-9]+)_URL", key)) and os.environ[key]]
    return sorted(found)


def _call(name: str, method: str, path: str, **kwargs: Any) -> requests.Response:
    url = os.environ.get(f"SOURCE_{name.upper()}_URL", "")
    if not re.fullmatch(r"[a-z0-9]+", name) or not url:
        raise RuntimeError(f"Unknown source '{name}'")
    if not path.startswith("/") or path.startswith("//"):
        raise RuntimeError("A source may only point to its own paths")
    try:
        resp = requests.request(method, url.rstrip("/") + path, allow_redirects=False,
                                auth=("dashboard", os.environ.get(f"SOURCE_{name.upper()}_PASSWORD", "")),
                                timeout=kwargs.pop("timeout", 30), **kwargs)
    except requests.RequestException as exc:
        raise RuntimeError(f"Could not reach {name} at its SOURCE_{name.upper()}_URL") from exc
    if resp.status_code == 401:
        raise RuntimeError(f"{name} did not accept SOURCE_{name.upper()}_PASSWORD")
    return resp


def items(name: str, status: str = "approved") -> list[dict[str, Any]]:
    resp = _call(name, "GET", "/api/items", params={"status": status})
    if resp.status_code == 404:
        raise RuntimeError(f"{name} does not offer its videos yet (GET /api/items); it needs an update")
    if resp.status_code >= 400:
        raise RuntimeError(f"{name} answered with error {resp.status_code}")
    data = resp.json()
    return [i for i in (data.get("items") or []) if isinstance(i, dict) and "id" in i and i.get("video")]


def item(name: str, item_id: str) -> dict[str, Any]:
    for status in ("approved", "pending", "posted"):
        for found in items(name, status):
            if str(found["id"]) == str(item_id):
                return found
    raise RuntimeError("Unknown item")


def set_status(name: str, item_id: str, status: str) -> None:
    if status not in ("pending", "approved", "rejected"):
        raise RuntimeError("Unknown status")
    resp = _call(name, "POST", f"/api/items/{item_id}/status", json={"status": status})
    if resp.status_code >= 400:
        raise RuntimeError(f"{name} could not change the status ({resp.status_code})")


def video(name: str, path: str, range_header: str | None = None) -> requests.Response:
    headers = {"Range": range_header} if range_header else {}
    return _call(name, "GET", path, headers=headers, stream=True, timeout=120)


def download(name: str, path: str, dest: Path) -> Path:
    resp = video(name, path)
    if resp.status_code >= 400:
        raise RuntimeError(f"{name} did not give the video ({resp.status_code})")
    with dest.open("wb") as handle:
        for chunk in resp.iter_content(1 << 20):
            handle.write(chunk)
    return dest


def mark_sent(name: str, item_id: str, sent: dict[str, Any]) -> bool:
    """Tell the pipeline what went out. Pipelines without this endpoint are fine."""
    try:
        return _call(name, "POST", f"/api/items/{item_id}/sent", json=sent).status_code < 400
    except RuntimeError:
        return False
