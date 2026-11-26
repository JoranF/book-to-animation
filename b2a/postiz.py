"""Send a finished Short to Postiz, which posts or schedules it on the
connected channels (YouTube, TikTok, Instagram, ...).

Needs POSTIZ_URL (e.g. https://postiz.example.com) and POSTIZ_API_KEY.
Nothing is posted by itself: only when the owner asks for it in the web app
or on the command line.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


def configured() -> bool:
    return bool(os.environ.get("POSTIZ_URL") and os.environ.get("POSTIZ_API_KEY"))


def _base() -> str:
    url = os.environ.get("POSTIZ_URL", "").rstrip("/")
    return url if url.endswith("/public/v1") else f"{url}/api/public/v1"


def _call(method: str, path: str, **kwargs: Any) -> Any:
    if not configured():
        raise RuntimeError("POSTIZ_URL and POSTIZ_API_KEY are not set")
    try:
        resp = requests.request(method, _base() + path, timeout=kwargs.pop("timeout", 60),
                                headers={"Authorization": os.environ["POSTIZ_API_KEY"]}, **kwargs)
    except requests.RequestException as exc:
        raise RuntimeError(f"Could not reach Postiz: {exc}") from exc
    if resp.status_code == 401:
        raise RuntimeError("Postiz did not accept POSTIZ_API_KEY")
    if resp.status_code == 429:
        raise RuntimeError("Postiz hourly limit reached, try again later")
    if resp.status_code >= 400:
        raise RuntimeError(f"Postiz error {resp.status_code}: {resp.text[:300]}")
    return resp.json()


def channels() -> list[dict[str, Any]]:
    """The connected accounts that can receive a post."""
    return [{"id": c["id"], "name": c.get("name"), "platform": c.get("identifier"),
             "profile": c.get("profile"), "picture": c.get("picture")}
            for c in _call("GET", "/integrations") if not c.get("disabled")]


def upload(video: Path) -> dict[str, Any]:
    with video.open("rb") as handle:
        media = _call("POST", "/upload", files={"file": (video.name, handle, "video/mp4")}, timeout=600)
    return {"id": media["id"], "path": media["path"]}


def caption(meta: dict[str, Any]) -> str:
    lines = [meta.get("description") or meta.get("title") or "", " ".join(meta.get("hashtags") or [])]
    if str(meta.get("voice", "")).startswith("piper"):
        lines.append("Voice: LibriTTS (CC BY 4.0).")
    return "\n\n".join(line for line in lines if line).strip()


def settings_for(platform: str, meta: dict[str, Any]) -> dict[str, Any]:
    title = (meta.get("title") or meta.get("hook") or "Short").strip()
    if platform == "youtube":
        return {"__type": "youtube", "title": title[:100], "type": os.environ.get("POSTIZ_YOUTUBE_PRIVACY", "public"),
                "selfDeclaredMadeForKids": "no",
                "tags": [{"value": t.lstrip("#"), "label": t.lstrip("#")} for t in (meta.get("hashtags") or [])[:8]]}
    if platform == "tiktok":
        return {"__type": "tiktok", "title": title[:90], "privacy_level": "PUBLIC_TO_EVERYONE",
                "duet": True, "stitch": True, "comment": True, "autoAddMusic": "no",
                "brand_content_toggle": False, "brand_organic_toggle": False,
                "content_posting_method": os.environ.get("POSTIZ_TIKTOK_METHOD", "DIRECT_POST"),
                # The voices and script are AI-made: say so, as TikTok asks.
                "video_made_with_ai": os.environ.get("POSTIZ_TIKTOK_AI_LABEL", "1") != "0"}
    if platform in ("instagram", "instagram-standalone"):
        return {"__type": platform, "post_type": "post"}
    return {"__type": platform}


def publish(meta: dict[str, Any], video: Path, channel_ids: list[str],
            when: datetime | None = None, draft: bool = False) -> dict[str, Any]:
    """Post now, schedule for `when`, or save as a draft in Postiz."""
    known = {c["id"]: c for c in channels()}
    missing = [c for c in channel_ids if c not in known]
    if missing or not channel_ids:
        raise RuntimeError(f"Unknown Postiz channel(s): {missing or 'none chosen'}")
    media = upload(video)
    text = caption(meta)
    date = (when or datetime.now(timezone.utc)).astimezone(timezone.utc)
    body = {
        "type": "draft" if draft else "schedule" if when else "now",
        "date": date.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "shortLink": False,
        "tags": [],
        "posts": [{"integration": {"id": cid},
                   "value": [{"content": text, "image": [media]}],
                   "settings": settings_for(known[cid]["platform"], meta)} for cid in channel_ids],
    }
    result = _call("POST", "/posts", json=body, timeout=120)
    return {"type": body["type"], "date": body["date"], "result": result,
            "channels": [{"id": cid, "platform": known[cid]["platform"], "name": known[cid]["name"]}
                         for cid in channel_ids]}
