"""Trend research: what is working in our niche on Shorts, TikTok and Reddit.

Built on the workflow of the ScrapeCreators "trend-discovery" and
"outlier-post-finder" skills (github.com/ScrapeCreators/social-media-research-skills):
pull posts for a few niche searches, keep the numbers, rank by evidence, and
turn it into angles we can actually use. Claude writes the brief.

Sources:
- YouTube search via yt-dlp: free, no key.
- Reddit top posts of the week: free, no key (best effort, Reddit may block servers).
- ScrapeCreators, only with SCRAPECREATORS_API_KEY: TikTok and YouTube keyword
  search, about 1 credit per search (so ~10 credits per run).

The brief goes into the script prompt and gives every episode a trend score,
which "next episode" uses to pick the best-fitting episode of the chapter
whose turn it is. Run it weekly: `python -m b2a.cli trends`.
"""
from __future__ import annotations

import json
import os
import re
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import requests

from . import config, llm, plan as plan_mod

UA = "book-to-animation-trends/1.0"
SC_BASE = "https://api.scrapecreators.com"
DEFAULT_QUERIES = ["philosophy shorts", "psychology shorts", "stop caring what people think",
                   "people pleasing", "self worth", "stoicism"]
DEFAULT_SUBREDDITS = ["philosophy", "Stoicism", "selfimprovement", "getdisciplined"]


def trends_dir(book_slug: str) -> Path:
    return config.DATA_DIR / "trends" / Path(book_slug).name


# --- collecting ---------------------------------------------------------------

def _item(platform: str, query: str, title: str, views: Any = None, likes: Any = None,
          comments: Any = None, url: str = "", author: str = "", seconds: Any = None) -> dict[str, Any]:
    def num(value: Any) -> int | None:
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None
    return {"platform": platform, "query": query, "title": re.sub(r"\s+", " ", title or "").strip()[:300],
            "views": num(views), "likes": num(likes), "comments": num(comments),
            "url": url, "author": author, "seconds": num(seconds)}


def youtube(query: str, count: int = 25) -> list[dict[str, Any]]:
    """YouTube search results (Shorts first) with view counts, via yt-dlp."""
    import yt_dlp  # imported here: only needed for trend runs

    with yt_dlp.YoutubeDL({"quiet": True, "skip_download": True, "extract_flat": True,
                           "noprogress": True, "no_warnings": True}) as ydl:
        info = ydl.extract_info(f"ytsearch{count}:{query} #shorts", download=False) or {}
    out = []
    for entry in info.get("entries") or []:
        url = entry.get("url") or ""
        seconds = entry.get("duration")
        if "/shorts/" not in url and not (seconds and seconds <= 75):
            continue
        out.append(_item("youtube", query, entry.get("title", ""), entry.get("view_count"), None, None,
                         url, entry.get("channel") or entry.get("uploader") or "", seconds))
    return out


def reddit(subreddit: str, count: int = 25) -> list[dict[str, Any]]:
    """Top posts of the week in a subreddit: what people struggle with right now."""
    reply = requests.get(f"https://www.reddit.com/r/{subreddit}/top.json",
                         params={"t": "week", "limit": count}, headers={"User-Agent": UA}, timeout=20)
    reply.raise_for_status()
    out = []
    for child in reply.json().get("data", {}).get("children", []):
        post = child.get("data", {})
        out.append(_item("reddit", f"r/{subreddit}", post.get("title", ""), None, post.get("score"),
                         post.get("num_comments"), "https://www.reddit.com" + post.get("permalink", ""),
                         post.get("author", "")))
    return out


VIEW_KEYS = ("play_count", "playCount", "view_count", "viewCount", "views", "plays")
LIKE_KEYS = ("digg_count", "diggCount", "like_count", "likeCount", "likes")
COMMENT_KEYS = ("comment_count", "commentCount", "comments")
TEXT_KEYS = ("desc", "title", "caption", "text", "description")
URL_KEYS = ("url", "share_url", "webVideoUrl", "link")


def _find(obj: dict[str, Any], keys: Iterable[str], depth: int = 0) -> Any:
    """First value for any of these keys, also inside nested 'stats'-like objects."""
    for key in keys:
        value = obj.get(key)
        if value is not None and not isinstance(value, (dict, list)):
            return value
    if depth < 2:
        for value in obj.values():
            if isinstance(value, dict):
                found = _find(value, keys, depth + 1)
                if found is not None:
                    return found
    return None


def _posts(data: Any) -> list[dict[str, Any]]:
    """Every dict in a ScrapeCreators reply that looks like a post (text + a number)."""
    found: list[dict[str, Any]] = []

    def walk(node: Any, depth: int) -> None:
        if depth > 5:
            return
        if isinstance(node, list):
            for child in node:
                walk(child, depth + 1)
        elif isinstance(node, dict):
            if _find(node, TEXT_KEYS) and (_find(node, VIEW_KEYS) is not None or _find(node, LIKE_KEYS) is not None):
                found.append(node)
                return
            for child in node.values():
                walk(child, depth + 1)
    walk(data, 0)
    return found


def scrapecreators(platform: str, query: str) -> list[dict[str, Any]]:
    """TikTok or YouTube keyword search through ScrapeCreators (needs the key)."""
    key = os.environ.get("SCRAPECREATORS_API_KEY", "")
    if not key:
        return []
    path = {"tiktok": "/v1/tiktok/search/keyword", "youtube": "/v1/youtube/search"}[platform]
    reply = requests.get(SC_BASE + path, params={"query": query}, headers={"x-api-key": key}, timeout=60)
    if reply.status_code == 402:
        raise RuntimeError("ScrapeCreators credits are used up")
    reply.raise_for_status()
    out = []
    for post in _posts(reply.json()):
        out.append(_item(platform, query, str(_find(post, TEXT_KEYS)), _find(post, VIEW_KEYS),
                         _find(post, LIKE_KEYS), _find(post, COMMENT_KEYS), str(_find(post, URL_KEYS) or ""),
                         str(_find(post, ("unique_id", "uniqueId", "author", "channel", "username")) or "")))
    return out


def collect(queries: list[str], subreddits: list[str]) -> tuple[list[dict[str, Any]], list[str]]:
    """Run every source; a failing source is noted and skipped, never fatal."""
    items: list[dict[str, Any]] = []
    errors: list[str] = []

    def attempt(name: str, fn: Any, *args: Any) -> None:
        try:
            items.extend(fn(*args))
        except Exception as exc:  # noqa: BLE001 - one broken source must not stop the run
            errors.append(f"{name}: {str(exc)[:200]}")

    for query in queries:
        attempt(f"youtube '{query}'", youtube, query)
        attempt(f"tiktok '{query}'", scrapecreators, "tiktok", query)
    for subreddit in subreddits:
        attempt(f"reddit r/{subreddit}", reddit, subreddit)
    seen, unique = set(), []
    for item in items:
        key = item["url"] or (item["platform"], item["title"])
        if item["title"] and key not in seen:
            seen.add(key)
            unique.append(item)
    return unique, errors


def score(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Lift over the median of the same search, like the outlier-post-finder skill:
    a post that does 10x its neighbours says more than raw views."""
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for item in items:
        groups.setdefault((item["platform"], item["query"]), []).append(item)
    for group in groups.values():
        metric = "views" if any(i["views"] for i in group) else "likes"
        values = [i[metric] for i in group if i[metric]]
        median = statistics.median(values) if values else 0
        for item in group:
            item["lift"] = round((item[metric] or 0) / median, 2) if median else 0.0
    return sorted(items, key=lambda i: (i["lift"], i["views"] or i["likes"] or 0), reverse=True)


# --- the brief ------------------------------------------------------------------

BRIEF_SYSTEM = """You research trends for a YouTube Shorts and TikTok channel that turns \
philosophy and psychology books into short animated conversations between a calm \
philosopher and a sarcastic youth, in a late-90s low-poly game style.

You get public posts from the last weeks with their numbers ("lift" = how many times \
better than the median post of the same search). Find what is really working: topics, \
viewer problems, hook patterns, formats. Separate evidence from guesses: a pattern \
needs at least 2 posts. Ignore what does not fit the channel.

Then score how well every planned episode fits what is working now, 0 to 10.

Return ONLY JSON:
{"summary": "3 sentences",
 "topics": [{"topic": "...", "why": "evidence in a few words", "posts": 3}],
 "hook_patterns": [{"pattern": "describe the pattern, never copy a hook", "example_lift": 4.2}],
 "formats": ["..."],
 "viewer_problems": ["what people struggle with, in their own words"],
 "avoid": ["what is saturated or not working"],
 "episode_scores": {"<episode id>": 7}}"""


def brief(book: dict[str, Any], episodes: list[dict[str, Any]], items: list[dict[str, Any]]) -> dict[str, Any]:
    top = items[:120]
    lines = [f"- [{i['platform']}] lift {i['lift']} | views {i['views']} likes {i['likes']} "
             f"comments {i['comments']} | search '{i['query']}' | {i['title']}" for i in top]
    plan = [f"- {e['id']} ({e.get('format')}): {e['title']}. Hook: {e.get('hook', '')}" for e in episodes]
    user = (f"Book of this season: {book['title']}. About: {book['summary']}\n\n"
            f"Posts ({len(top)} of {len(items)}, best lift first):\n" + "\n".join(lines) +
            "\n\nPlanned episodes:\n" + "\n".join(plan))
    text = llm.ask(BRIEF_SYSTEM, [{"role": "user", "content": user}], 16000,
                   model=config.ANALYSIS_MODEL, effort=config.ANALYSIS_EFFORT, step="trends")
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise RuntimeError("Claude did not return a trend brief")
    data = json.loads(match.group(0))
    known = {e["id"] for e in episodes}
    scores = {}
    for key, value in (data.get("episode_scores") or {}).items():
        if key in known and isinstance(value, (int, float)):
            scores[key] = max(0.0, min(float(value), 10.0))
    data["episode_scores"] = scores
    return data


def run(book_slug: str) -> dict[str, Any]:
    """Collect, score, brief and save. Returns the saved brief."""
    from .script import load_book

    book = load_book(book_slug)
    settings = book.get("trends") or {}
    queries = settings.get("queries") or DEFAULT_QUERIES
    subreddits = settings.get("subreddits") or DEFAULT_SUBREDDITS
    items, errors = collect(queries, subreddits)
    if not items:
        raise RuntimeError("No trend data from any source: " + "; ".join(errors))
    items = score(items)
    result = brief(book, plan_mod.episodes(book_slug), items)
    now = datetime.now(timezone.utc)
    result.update({
        "date": now.isoformat(timespec="seconds"), "book": book_slug,
        "sources": sorted({i["platform"] for i in items}), "post_count": len(items),
        "errors": errors, "top_posts": items[:25], "queries": queries, "subreddits": subreddits,
    })
    folder = trends_dir(book_slug)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{now:%Y%m%d-%H%M%S}.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))
    (folder / "latest.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))
    return result


# --- reading it back ----------------------------------------------------------

def latest(book_slug: str, max_age_days: int | None = None) -> dict[str, Any] | None:
    """The newest brief, or None when there is none or it is too old to trust."""
    path = trends_dir(book_slug) / "latest.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    age = timedelta(days=config.TRENDS_MAX_AGE_DAYS if max_age_days is None else max_age_days)
    try:
        when = datetime.fromisoformat(data["date"])
    except (KeyError, ValueError):
        return None
    return data if datetime.now(timezone.utc) - when <= age else None


def prompt_text(data: dict[str, Any] | None) -> str:
    """The part of the brief the script writer gets."""
    if not data:
        return ""
    parts = [data.get("summary", "")]
    if data.get("topics"):
        parts.append("Topics that work: " + "; ".join(f"{t.get('topic')} ({t.get('why')})" for t in data["topics"][:6]))
    if data.get("hook_patterns"):
        parts.append("Hook patterns that work: " + "; ".join(str(h.get("pattern")) for h in data["hook_patterns"][:5]))
    if data.get("viewer_problems"):
        parts.append("What viewers struggle with: " + "; ".join(map(str, data["viewer_problems"][:6])))
    if data.get("avoid"):
        parts.append("Saturated, avoid: " + "; ".join(map(str, data["avoid"][:5])))
    return "\n".join(p for p in parts if p)


def episode_scores(book_slug: str) -> dict[str, float]:
    data = latest(book_slug)
    return dict(data.get("episode_scores") or {}) if data else {}
