"""Studio: one login to review the videos of every pipeline and send them to Postiz.

Its own small app, next to the pipelines. It knows no pipeline by name: each
one is plugged in with SOURCE_<NAME>_URL and SOURCE_<NAME>_PASSWORD and offers
the contract described in sources.py. Nothing is posted by itself.
"""
from __future__ import annotations

import os
import secrets
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, Field

from . import postiz, sources

app = FastAPI(title="Studio")
security = HTTPBasic()


def auth(credentials: HTTPBasicCredentials = Depends(security)) -> None:
    password = os.environ.get("STUDIO_PASSWORD", "")
    if not password or not secrets.compare_digest(credentials.password.encode(), password.encode()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong password",
                            headers={"WWW-Authenticate": "Basic"})


class ItemStatus(BaseModel):
    status: str


class Publish(BaseModel):
    channels: list[str] = Field(min_length=1, max_length=20)
    when: datetime | None = None     # empty = post now
    draft: bool = False


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "password_set": bool(os.environ.get("STUDIO_PASSWORD")),
            "postiz_set": postiz.configured(), "sources": sources.names()}


@app.get("/api/sources", dependencies=[Depends(auth)])
def get_sources() -> dict[str, Any]:
    return {"sources": sources.names(), "postiz": postiz.configured()}


@app.get("/api/postiz/channels", dependencies=[Depends(auth)])
def postiz_channels() -> dict[str, Any]:
    if not postiz.configured():
        return {"configured": False, "channels": []}
    try:
        return {"configured": True, "channels": postiz.channels()}
    except RuntimeError as exc:
        return {"configured": True, "channels": [], "error": str(exc)}


@app.get("/api/sources/{name}/items", dependencies=[Depends(auth)])
def source_items(name: str, status: str = "approved") -> dict[str, Any]:
    try:
        return {"items": sources.items(name, status if status in sources.STATUSES else "approved")}
    except RuntimeError as exc:
        return {"items": [], "error": str(exc)}


@app.post("/api/sources/{name}/items/{item_id}/status", dependencies=[Depends(auth)])
def source_status(name: str, item_id: str, body: ItemStatus) -> dict[str, Any]:
    try:
        sources.set_status(name, item_id, body.status)
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc
    return {"ok": True}


@app.post("/api/sources/{name}/items/{item_id}/publish", dependencies=[Depends(auth)])
def source_publish(name: str, item_id: str, body: Publish) -> dict[str, Any]:
    """Fetch the video from the pipeline, send it to Postiz, tell the pipeline."""
    try:
        found = sources.item(name, item_id)
        with tempfile.TemporaryDirectory() as tmp:
            video = sources.download(name, found["video"], Path(tmp) / f"{name}-{Path(str(item_id)).name}.mp4")
            meta = {"title": found.get("title"), "description": found.get("caption"),
                    "hashtags": ["#" + str(t).lstrip("#") for t in found.get("hashtags") or []]}
            sent = postiz.publish(meta, video, body.channels, body.when, body.draft)
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc
    sent["recorded_by_source"] = sources.mark_sent(name, item_id, sent)
    return sent


@app.get("/sources/{name}/video/{item_id}", dependencies=[Depends(auth)])
def source_video(name: str, item_id: str, request: Request) -> StreamingResponse:
    try:
        upstream = sources.video(name, sources.item(name, item_id)["video"], request.headers.get("range"))
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc
    if upstream.status_code >= 400:
        upstream.close()
        raise HTTPException(404)
    keep = {k: v for k, v in upstream.headers.items()
            if k.lower() in ("content-length", "content-range", "accept-ranges", "content-type")}
    return StreamingResponse(upstream.iter_content(1 << 16), status_code=upstream.status_code, headers=keep)


PAGE = """<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Studio</title>
<style>body{font:16px system-ui;margin:0 auto;max-width:980px;padding:16px;background:#14121f;color:#eee}
input,button{font:inherit;padding:8px;border-radius:6px;border:1px solid #555;background:#221f33;color:#eee;width:100%;box-sizing:border-box;margin:4px 0}
button{background:#ffe500;color:#111;font-weight:700;cursor:pointer}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:16px}
.tabs a{display:inline-block;padding:6px 14px;border-radius:6px;background:#221f33;color:#eee;text-decoration:none;margin:0 6px 6px 0}
.tabs a.on{background:#ffe500;color:#111;font-weight:700}
video{width:100%;border-radius:8px;background:#000}small{color:#aaa}.note{padding:8px;background:#221f33;border-radius:6px;margin:6px 0}</style>
<h1>Studio</h1>
<p class=tabs id=tabs></p><p class=tabs id=stat></p><div id=note class=note hidden></div><div class=grid id=items></div>
<script>
const itemsEl=document.getElementById('items'),noteEl=document.getElementById('note');let view='pending',srcs=[],chans=[],chanNote='';
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const src=()=>srcs.includes(location.hash.slice(1))?location.hash.slice(1):srcs[0]||'';
const json=(url,body)=>fetch(url,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(body)});
function tab(){const n=src();document.getElementById('tabs').innerHTML=srcs.map(t=>`<a href="#${t}" class="${t===n?'on':''}">${t[0].toUpperCase()+t.slice(1)}</a>`).join('');
itemsEl.dataset.h='';itemsEl.innerHTML='';load()}
function show(s){view=s;itemsEl.dataset.h='';load()}
async function load(){const n=src();if(!n){noteEl.hidden=false;noteEl.textContent='No pipelines connected yet. Set SOURCE_<NAME>_URL and SOURCE_<NAME>_PASSWORD.';return}
document.getElementById('stat').innerHTML=['pending','approved','posted','rejected'].map(s=>`<a href="#${n}" class="${s===view?'on':''}" onclick="show('${s}')">${s==='posted'?'sent':s}</a>`).join('');
const d=await (await fetch('/api/sources/'+n+'/items?status='+view)).json();if(n!==src())return;
const note=d.error||(d.items.length?chanNote:'No '+(view==='posted'?'sent':view)+' videos.');noteEl.hidden=!note;noteEl.textContent=note;
const html=d.items.map(c=>{const id=encodeURIComponent(c.id);return `<div><video controls preload=none src="/sources/${n}/video/${id}"></video><b>${esc(c.title)}</b><br>
<small>${esc(c.label)}${c.seconds?', '+Math.round(c.seconds)+'s':''}</small><br><small>${esc(c.caption)} ${esc((c.hashtags||[]).map(t=>'#'+String(t).replace(/^#/,'')).join(' '))}</small>
${c.error?`<br><small>Not sent: ${esc(c.error)}</small>`:''}
${(Array.isArray(c.posted)?c.posted:[]).map(p=>`<br><small>${esc(p.type)} ${esc(String(p.date||'').slice(0,16).replace('T',' '))} UTC: ${esc((p.channels||[]).map(h=>h.platform).join(', '))}</small>`).join('')}
<div>${[['approved','Approve'],['rejected','Reject'],['pending','Back to pending']].filter(x=>x[0]!==c.status&&c.status!=='posted').map(x=>
`<button style="width:auto;margin-right:4px" onclick="setStatus('${id}','${x[0]}')">${x[1]}</button>`).join('')}</div>
${c.status==='approved'&&chans.length?`<details><summary>Post with Postiz</summary><form onsubmit="post(event,'${id}')">`+chans.map(h=>`<label><input type=checkbox name=c value="${esc(h.id)}" style="width:auto"> ${esc(h.platform)}: ${esc(h.name)}</label><br>`).join('')+
`<input type=datetime-local name=when title="Leave empty to post now"><button>Post or schedule</button><small class=msg></small></form></details>`:''}</div>`}).join('');
if(itemsEl.dataset.h!==html&&!itemsEl.querySelector('details[open]')){itemsEl.innerHTML=html;itemsEl.dataset.h=html}}
async function setStatus(id,status){const r=await json('/api/sources/'+src()+'/items/'+id+'/status',{status});
if(!r.ok){noteEl.hidden=false;noteEl.textContent=(await r.json()).detail||'Could not change the status'}itemsEl.dataset.h='';load()}
async function post(e,id){e.preventDefault();const f=new FormData(e.target),msg=e.target.querySelector('.msg'),when=f.get('when'),channels=f.getAll('c');
if(!channels.length){msg.textContent=' Choose a channel';return}
if(!confirm((when?'Schedule':'Post NOW')+' on '+channels.length+' channel(s)?'))return;msg.textContent=' Sending...';
const r=await json('/api/sources/'+src()+'/items/'+id+'/publish',{channels,when:when?new Date(when).toISOString():null});
if(r.ok){e.target.closest('details').open=false;itemsEl.dataset.h='';load()}else msg.textContent=' Failed: '+((await r.json()).detail||r.status)}
window.onhashchange=tab;
Promise.all([fetch('/api/sources').then(r=>r.json()),fetch('/api/postiz/channels').then(r=>r.json())]).then(([s,p])=>{srcs=s.sources;chans=p.channels;
chanNote=p.error||(p.configured?'':'Postiz is not set up yet (POSTIZ_URL and POSTIZ_API_KEY), so videos can be reviewed but not posted.');tab()});
setInterval(load,8000)</script>"""


@app.get("/", response_class=HTMLResponse, dependencies=[Depends(auth)])
def index() -> str:
    return PAGE
