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
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, Field

from . import config, pipeline, script as script_mod

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
    topic: str = Field(min_length=3, max_length=200)
    idea: str = Field(default="", max_length=1000)


def worker() -> None:
    """One Short at a time, so costs and CPU stay predictable."""
    while True:
        short_id = todo.get()
        job = jobs[short_id]
        try:
            job["status"] = "running"
            pipeline.make_short(job["book"], job["topic"], job["idea"], short_id,
                                progress=lambda step, job=job: job.update(step=step))
            job["status"] = "done"
        except Exception as exc:  # noqa: BLE001 - report every failure to the UI
            traceback.print_exc()
            job.update(status="failed", error=str(exc)[:500])


def short_path(short_id: str, name: str) -> Path:
    return pipeline.shorts_dir() / Path(short_id).name / name


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "fal_key_set": bool(os.environ.get("FAL_KEY"))}


@app.post("/api/shorts", dependencies=[Depends(auth)])
def create_short(body: NewShort) -> dict[str, Any]:
    try:
        script_mod.load_book(body.book)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    short_id = pipeline.new_id(body.topic)
    jobs[short_id] = {"id": short_id, "status": "queued", "step": "queued", **body.model_dump()}
    todo.put(short_id)
    return jobs[short_id]


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
<input name=topic list=topics placeholder="Topic, e.g. Separation of tasks" required><datalist id=topics>__TOPICS__</datalist>
<textarea name=idea placeholder="Optional idea or angle"></textarea><button>Make Short</button></form>
<div id=jobs></div><h2>Shorts</h2><div class=grid id=shorts></div>
<script>
const jobsEl=document.getElementById('jobs'),shortsEl=document.getElementById('shorts');
async function go(e){e.preventDefault();const f=new FormData(e.target);
await fetch('/api/shorts',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(Object.fromEntries(f))});load()}
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
async function load(){const d=await (await fetch('/api/shorts')).json();
jobsEl.innerHTML=d.jobs.map(j=>`<div class=job>${esc(j.topic)}: <b>${esc(j.status)}</b> (${esc(j.step)}) ${esc(j.error)}</div>`).join('');
const html=d.shorts.map(s=>`<div><video controls preload=none poster="/files/${esc(s.id)}/thumb.jpg" src="/files/${esc(s.id)}/short.mp4"></video>
<b>${esc(s.title)}</b><br><small>${esc(s.duration_seconds)}s, $${esc(s.estimated_cost_usd)}, ${esc(s.topic)}</small></div>`).join('');
if(shortsEl.dataset.h!==html){shortsEl.innerHTML=html;shortsEl.dataset.h=html}}
load();setInterval(load,5000)</script>"""


@app.get("/", response_class=HTMLResponse, dependencies=[Depends(auth)])
def index() -> str:
    books = [script_mod.load_book(p.parent.name) for p in sorted(config.BOOKS_DIR.glob("*/book.json"))]
    options = "".join(f'<option value="{html.escape(b["slug"])}">{html.escape(b["title"])}</option>' for b in books)
    topics = "".join(f'<option value="{html.escape(t)}">' for b in books for t in b.get("topics", []))
    return PAGE.replace("__BOOKS__", options).replace("__TOPICS__", topics)
