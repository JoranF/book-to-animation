"""Step 3: scenes. Each scene's "stage" is rendered as low-poly 3D animation by
headless Blender (see world.py), one process per scene, a few at a time."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import zlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from . import config, music, stage as stage_mod

FPS = 15  # keep in sync with world.FPS; low on purpose for the old-console feel


def render_stage(stage: dict[str, Any], seconds: float, dest: Path) -> Path:
    """Render one scene to a small silent mp4."""
    if dest.exists():
        return dest
    frames = dest.with_suffix(".frames")
    job = dest.with_suffix(".job.json")
    job.write_text(json.dumps({"stage": stage, "seconds": seconds, "out": str(frames)}))
    proc = subprocess.run([sys.executable, "-m", "b2a.blender_render", str(job)],
                          capture_output=True, text=True, cwd=config.ROOT)
    if proc.returncode != 0:
        raise RuntimeError(f"Blender failed on {dest.name}: {proc.stderr[-1200:]}")
    tmp = dest.with_suffix(".tmp.mp4")
    encode = subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-framerate", str(FPS),
         "-i", str(frames / "f_%04d.png"), "-c:v", "libx264", "-crf", "10",
         "-preset", "veryfast", "-pix_fmt", "yuv420p", str(tmp)],
        capture_output=True, text=True)
    if encode.returncode != 0:
        raise RuntimeError(f"ffmpeg failed on {dest.name}: {encode.stderr[-800:]}")
    tmp.replace(dest)
    shutil.rmtree(frames, ignore_errors=True)
    job.unlink(missing_ok=True)
    return dest


def make_visuals(script: dict[str, Any], times: list[tuple[float, float]],
                 out_dir: Path) -> list[dict[str, Path | None]]:
    scenes = script["scenes"]

    def work(i: int) -> dict[str, Path | None]:
        stage = scenes[i].get("stage") or stage_mod.DEFAULT
        clip = render_stage(stage, times[i][1] - times[i][0], out_dir / f"scene_{i:02d}.mp4")
        return {"image": None, "clip": clip}

    workers = int(os.environ.get("RENDER_WORKERS", max(min((os.cpu_count() or 2) // 2, 4), 1)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(work, range(len(scenes))))


def make_music(out_dir: Path, seconds: float, seed_text: str) -> Path:
    """Use a track from assets/music if there is one, else compose a chiptune."""
    library = sorted((config.ASSETS_DIR / "music").glob("*.mp3")) + sorted((config.ASSETS_DIR / "music").glob("*.wav"))
    seed = zlib.crc32(seed_text.encode())
    if library:
        return library[seed % len(library)]
    dest = out_dir / "music.wav"
    if not dest.exists():
        music.make_music(dest, seconds + 2, seed)
    return dest
