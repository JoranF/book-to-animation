"""Small web app for Dokploy: start a Short, follow it, watch and download it."""
from __future__ import annotations

import contextlib
import html
import json
import os
import queue
import secrets
import threading
import traceback
from pathlib import Path
from typing import Any, Literal

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, Field

from . import config, music, pipeline, plan as plan_mod, script as script_mod, trends

@contextlib.asynccontextmanager
async def lifespan(_: FastAPI):
    threading.Thread(target=worker, daemon=True).start()
    yield


app = FastAPI(title="book-to-animation", lifespan=lifespan)
security = HTTPBasic()
jobs: dict[str, dict[str, Any]] = {}
todo: "queue.Queue[str]" = queue.Queue()
FILES = {"short.mp4", "thumb.jpg", "script.json", "meta.json"}


def auth(credentials: HTTPBasicCredentials = Depends(security)) -> None:
    password = os.environ.get("APP_PASSWORD", "")
    if not password or not secrets.compare_digest(credentials.password, password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong password",
                            headers={"WWW-Authenticate": "Basic"})


class NewShort(BaseModel):
    book: str = "courage-to-be-disliked"
    episode: str = Field(default="", max_length=40)   # id from the plan, or "next"
    topic: str = Field(default="", max_length=200)   # free topic when no episode
    idea: str = Field(default="", max_length=1000)


def worker() -> None:
    """One Short at a time, so costs and CPU stay predictable."""
    while True:
        short_id = todo.get()
        job = jobs[short_id]
        try:
            job["status"] = "running"
            pipeline.make_short(job["book"], job["topic"], job["idea"], short_id,
                                progress=lambda step, job=job: job.update(step=step),
                                episode_id=job["episode"] or None)
            job["status"] = "done"
        except Exception as exc:  # noqa: BLE001 - report every failure to the UI
            traceback.print_exc()
            job.update(status="failed", error=str(exc)[:500])


def short_path(short_id: str, name: str) -> Path:
    return pipeline.shorts_dir() / Path(short_id).name / name


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "claude_key_set": bool(os.environ.get("ANTHROPIC_API_KEY")),
            "elevenlabs_key_set": bool(os.environ.get("ELEVENLABS_API_KEY")),
            "acestep_url_set": music.acestep_enabled(),
            "scrapecreators_key_set": bool(os.environ.get("SCRAPECREATORS_API_KEY"))}


# --- trend research (weekly; see trends.py) ---

trend_runs: dict[str, dict[str, Any]] = {}


def _run_trends(book: str) -> None:
    try:
        result = trends.run(book)
        trend_runs[book] = {"status": "done", "date": result["date"]}
    except Exception as exc:  # noqa: BLE001 - shown in the API
        traceback.print_exc()
        trend_runs[book] = {"status": "failed", "error": str(exc)[:500]}


@app.post("/api/trends", dependencies=[Depends(auth)])
def start_trends(book: str = "courage-to-be-disliked") -> dict[str, Any]:
    """Start a trend research run in the background (Claude + optional ScrapeCreators credits)."""
    book = Path(book).name
    try:
        script_mod.load_book(book)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    if trend_runs.get(book, {}).get("status") == "running":
        return trend_runs[book]
    trend_runs[book] = {"status": "running"}
    threading.Thread(target=_run_trends, args=(book,), daemon=True).start()
    return trend_runs[book]


@app.get("/api/trends", dependencies=[Depends(auth)])
def get_trends(book: str = "courage-to-be-disliked") -> dict[str, Any]:
    book = Path(book).name
    return {"run": trend_runs.get(book), "brief": trends.latest(book, max_age_days=3650)}


@app.post("/api/shorts", dependencies=[Depends(auth)])
def create_short(body: NewShort) -> dict[str, Any]:
    try:
        script_mod.load_book(body.book)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    data = body.model_dump()
    if body.episode:
        busy = {j["episode"] for j in jobs.values() if j["status"] in ("queued", "running")}
        try:
            episode = (plan_mod.next_episode(body.book, pipeline.made_episodes(body.book) | busy,
                                             trends.episode_scores(body.book))
                       if body.episode == "next" else plan_mod.find_episode(body.book, body.episode))
        except KeyError as exc:
            raise HTTPException(404, str(exc.args[0])) from exc
        data.update(episode=episode["id"], topic=episode["title"])
    elif len(body.topic.strip()) < 3:
        raise HTTPException(422, "Give an episode or a topic")
    short_id = pipeline.new_id(f"{data['episode']}-{data['topic']}" if data["episode"] else data["topic"])
    jobs[short_id] = {"id": short_id, "status": "queued", "step": "queued", **data}
    todo.put(short_id)
    return jobs[short_id]


@app.get("/api/episodes", dependencies=[Depends(auth)])
def get_episodes(book: str = "courage-to-be-disliked") -> dict[str, Any]:
    """The episode plan of a book, with which episodes already have a Short."""
    plan = plan_mod.load_plan(Path(book).name) or {"chapters": []}
    made = pipeline.made_episodes(book)
    return {"book": book, "chapters": [
        {**ch, "episodes": [{**ep, "made": ep["id"] in made} for ep in ch["episodes"]]}
        for ch in plan["chapters"]]}


@app.get("/api/shorts", dependencies=[Depends(auth)])
def get_shorts() -> dict[str, Any]:
    active = [j for j in jobs.values() if j["status"] != "done"]
    return {"jobs": active, "shorts": pipeline.list_shorts()}


@app.get("/api/shorts/{short_id}", dependencies=[Depends(auth)])
def get_short(short_id: str) -> dict[str, Any]:
    meta = short_path(short_id, "meta.json")
    if meta.exists():
        return json.loads(meta.read_text())
    if short_id in jobs:
        return jobs[short_id]
    raise HTTPException(404, "Unknown Short")


class Feedback(BaseModel):
    youtube: dict[str, Any] = {}
    analytics: dict[str, Any] = {}


@app.patch("/api/shorts/{short_id}/feedback", dependencies=[Depends(auth)])
def update_feedback(short_id: str, body: Feedback) -> dict[str, Any]:
    """Feedback loop: store YouTube id and numbers next to hook, topic and length."""
    path = short_path(short_id, "meta.json")
    if not path.exists():
        raise HTTPException(404, "Unknown Short")
    meta = json.loads(path.read_text())
    meta["youtube"].update(body.youtube)
    meta["analytics"].update(body.analytics)
    path.write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    return meta


# --- what a shared dashboard (see studio/) reads: the same small contract every pipeline offers ---

class ItemStatus(BaseModel):
    status: Literal["pending", "approved", "rejected"]


class Sent(BaseModel):
    """What the dashboard sent to Postiz for one Short."""
    type: str = "now"                    # now | schedule | draft
    date: str | None = None
    channels: list[dict[str, Any]] = []
    result: Any = None


def caption(meta: dict[str, Any]) -> str:
    lines = [meta.get("description") or meta.get("title") or "", " ".join(meta.get("hashtags") or [])]
    if str(meta.get("voice", "")).startswith("piper"):
        lines.append("Voice: LibriTTS (CC BY 4.0).")     # required credit for the free voice
    return "\n\n".join(line for line in lines if line).strip()


def item(meta: dict[str, Any]) -> dict[str, Any]:
    return {"id": meta["id"], "title": meta["title"], "caption": caption(meta), "hashtags": [],
            "seconds": meta.get("duration_seconds"), "status": meta.get("review", "pending"),
            "video": f"/files/{meta['id']}/short.mp4",
            "label": " ".join(str(x) for x in (meta.get("episode"), meta.get("format")) if x) or meta.get("topic"),
            "error": None, "posted": meta.get("posts")}


def _meta(short_id: str) -> tuple[Path, dict[str, Any]]:
    path = short_path(short_id, "meta.json")
    if not path.exists():
        raise HTTPException(404, "Unknown Short")
    return path, json.loads(path.read_text())


@app.get("/api/items", dependencies=[Depends(auth)])
def api_items(status: Literal["pending", "approved", "posted", "rejected"] = "approved") -> dict[str, Any]:
    return {"items": [item(m) for m in pipeline.list_shorts() if m.get("review", "pending") == status]}


@app.post("/api/items/{short_id}/status", dependencies=[Depends(auth)])
def api_set_status(short_id: str, body: ItemStatus) -> dict[str, Any]:
    path, meta = _meta(short_id)
    meta["review"] = body.status
    path.write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    return {"ok": True, "item": item(meta)}


@app.post("/api/items/{short_id}/sent", dependencies=[Depends(auth)])
def api_sent(short_id: str, body: Sent) -> dict[str, Any]:
    """The dashboard reports what it sent to Postiz; kept with the Short for the feedback loop."""
    path, meta = _meta(short_id)
    meta.setdefault("posts", []).append(body.model_dump())
    meta["review"] = "posted"
    path.write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    return {"ok": True, "item": item(meta)}


@app.get("/files/{short_id}/{name}", dependencies=[Depends(auth)])
def get_file(short_id: str, name: str) -> FileResponse:
    path = short_path(short_id, name)
    if name not in FILES or not path.exists():
        raise HTTPException(404)
    return FileResponse(path)


PAGE = """<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>book-to-animation</title>
<style>body{font:16px system-ui;margin:0 auto;max-width:980px;padding:16px;background:#14121f;color:#eee}
input,select,textarea,button{font:inherit;padding:8px;border-radius:6px;border:1px solid #555;background:#221f33;color:#eee;width:100%;box-sizing:border-box;margin:4px 0}
button{background:#ffe500;color:#111;font-weight:700;cursor:pointer}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:16px}
video{width:100%;border-radius:8px;background:#000}small{color:#aaa}.job{padding:8px;background:#221f33;border-radius:6px;margin:6px 0}</style>
<h1>book-to-animation</h1>__STUDIO__
<form onsubmit="go(event)"><select name=book>__BOOKS__</select>
<select name=episode id=episode onchange="pick()"></select><div id=angle class=job hidden></div>
<div id=own hidden><input name=topic placeholder="Your own topic">
<textarea name=idea placeholder="Optional idea or angle"></textarea></div><button>Make Short</button></form>
<div id=jobs></div><h2>Shorts</h2><div class=grid id=shorts></div>
<script>
const jobsEl=document.getElementById('jobs'),shortsEl=document.getElementById('shorts'),epEl=document.getElementById('episode');
let eps={},madeKey='';
function pick(){const e=eps[epEl.value],a=document.getElementById('angle');document.getElementById('own').hidden=epEl.value!=='';
a.hidden=!e;if(e)a.innerHTML=`<b>${esc(e.hook)}</b><br><small>${esc(e.format)}: ${esc(e.angle)}</small>`}
async function plan(){const book=document.querySelector('[name=book]').value;
const d=await (await fetch('/api/episodes?book='+encodeURIComponent(book))).json();
const key=JSON.stringify(d.chapters.map(c=>c.episodes.map(e=>e.made)));if(key===madeKey)return;madeKey=key;eps={};const keep=epEl.value;
epEl.innerHTML='<option value=next>Next episode that is not made yet</option>'+d.chapters.map(c=>`<optgroup label="${esc(c.title)}">`+
c.episodes.map(e=>{eps[e.id]=e;return `<option value="${esc(e.id)}">${e.made?'\u2713 ':''}${esc(e.id)} ${esc(e.title)}</option>`}).join('')+'</optgroup>').join('')+
'<option value="">Own topic...</option>';if(keep)epEl.value=keep;pick()}
document.querySelector('[name=book]').onchange=()=>{madeKey='';plan()};
async function go(e){e.preventDefault();const f=new FormData(e.target);
await fetch('/api/shorts',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(Object.fromEntries(f))});load()}
function esc(s){return String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
const esc0=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
async function load(){const d=await (await fetch('/api/shorts')).json();
jobsEl.innerHTML=d.jobs.map(j=>`<div class=job>${esc(j.topic)}: <b>${esc(j.status)}</b> (${esc(j.step)}) ${esc(j.error)}</div>`).join('');
const html=d.shorts.map(s=>`<div><video controls preload=none poster="/files/${esc(s.id)}/thumb.jpg" src="/files/${esc(s.id)}/short.mp4"></video>
<b>${esc(s.title)}</b><br><small>${esc(s.episode||'')} ${esc(s.topic)}, ${esc(s.duration_seconds)}s, $${esc(s.estimated_cost_usd)}, ${esc(s.review||'pending')}</small></div>`).join('');
if(shortsEl.dataset.h!==html){shortsEl.innerHTML=html;shortsEl.dataset.h=html}}
plan();load();setInterval(()=>{load();plan()},5000)</script>"""


@app.get("/", response_class=HTMLResponse, dependencies=[Depends(auth)])
def index() -> str:
    books = [script_mod.load_book(p.parent.name) for p in sorted(config.BOOKS_DIR.glob("*/book.json"))]
    options = "".join(f'<option value="{html.escape(b["slug"])}">{html.escape(b["title"])}</option>' for b in books)
    studio = os.environ.get("STUDIO_URL", "")
    link = (f'<p><a style="color:#ffe500" href="{html.escape(studio)}">Review and post in Studio</a></p>'
            if studio.startswith("https://") else "")
    return PAGE.replace("__BOOKS__", options).replace("__STUDIO__", link)
