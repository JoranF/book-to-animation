"""Small web app for Dokploy: start a Short, follow it, watch and download it."""
from __future__ import annotations

import contextlib
from datetime import datetime
import html
import json
import os
import queue
import secrets
import threading
import traceback
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, Field

from . import config, pipeline, plan as plan_mod, postiz, script as script_mod

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
            "postiz_set": postiz.configured()}


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
            episode = (plan_mod.next_episode(body.book, pipeline.made_episodes(body.book) | busy)
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


class Publish(BaseModel):
    channels: list[str] = Field(min_length=1, max_length=20)
    when: datetime | None = None     # empty = post now
    draft: bool = False


@app.get("/api/postiz/channels", dependencies=[Depends(auth)])
def postiz_channels() -> dict[str, Any]:
    if not postiz.configured():
        return {"configured": False, "channels": []}
    try:
        return {"configured": True, "channels": postiz.channels()}
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.post("/api/shorts/{short_id}/publish", dependencies=[Depends(auth)])
def publish_short(short_id: str, body: Publish) -> dict[str, Any]:
    """Send a finished Short to Postiz: post now, schedule, or save as draft."""
    path = short_path(short_id, "meta.json")
    video = short_path(short_id, "short.mp4")
    if not (path.exists() and video.exists()):
        raise HTTPException(404, "Unknown Short")
    meta = json.loads(path.read_text())
    try:
        sent = postiz.publish(meta, video, body.channels, body.when, body.draft)
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc
    meta = json.loads(path.read_text())
    meta.setdefault("posts", []).append(sent)
    path.write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    return sent


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
<h1>book-to-animation</h1>
<form onsubmit="go(event)"><select name=book>__BOOKS__</select>
<select name=episode id=episode onchange="pick()"></select><div id=angle class=job hidden></div>
<div id=own hidden><input name=topic placeholder="Your own topic">
<textarea name=idea placeholder="Optional idea or angle"></textarea></div><button>Make Short</button></form>
<div id=jobs></div><h2>Shorts</h2><div class=grid id=shorts></div>
<script>
const jobsEl=document.getElementById('jobs'),shortsEl=document.getElementById('shorts'),epEl=document.getElementById('episode');
let eps={},madeKey='',chans=[];
fetch('/api/postiz/channels').then(r=>r.ok?r.json():{channels:[]}).then(d=>{chans=d.channels;shortsEl.dataset.h='';load()});
async function post(e,id){e.preventDefault();const f=new FormData(e.target),msg=e.target.querySelector('.msg'),when=f.get('when');
const channels=f.getAll('c');if(!channels.length){msg.textContent=' Choose a channel';return}
if(!confirm((when?'Schedule':'Post NOW')+' on '+channels.length+' channel(s)?'))return;msg.textContent=' Sending...';
const r=await fetch('/api/shorts/'+id+'/publish',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({channels,when:when?new Date(when).toISOString():null})});
msg.textContent=r.ok?' Sent to Postiz':' Failed: '+((await r.json()).detail||r.status);if(r.ok){shortsEl.dataset.h='';load()}}
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
<b>${esc(s.title)}</b><br><small>${esc(s.episode||'')} ${esc(s.topic)}, ${esc(s.duration_seconds)}s, $${esc(s.estimated_cost_usd)}</small>
${(s.posts||[]).map(p=>`<br><small>${esc(p.type)} ${esc(p.date.slice(0,16).replace('T',' '))} UTC: ${esc(p.channels.map(c=>c.platform).join(', '))}</small>`).join('')}
${chans.length?`<details><summary>Post with Postiz</summary><form onsubmit="post(event,'${esc(s.id)}')">`+chans.map(c=>`<label><input type=checkbox name=c value="${esc(c.id)}" style="width:auto"> ${esc(c.platform)}: ${esc(c.name)}</label><br>`).join('')+
`<input type=datetime-local name=when title="Leave empty to post now"><button>Post or schedule</button><small class=msg></small></form></details>`:''}</div>`).join('');
if(shortsEl.dataset.h!==html&&!shortsEl.querySelector('details[open]')){shortsEl.innerHTML=html;shortsEl.dataset.h=html}}
plan();load();setInterval(()=>{load();plan()},5000)</script>"""


@app.get("/", response_class=HTMLResponse, dependencies=[Depends(auth)])
def index() -> str:
    books = [script_mod.load_book(p.parent.name) for p in sorted(config.BOOKS_DIR.glob("*/book.json"))]
    options = "".join(f'<option value="{html.escape(b["slug"])}">{html.escape(b["title"])}</option>' for b in books)
    return PAGE.replace("__BOOKS__", options)
