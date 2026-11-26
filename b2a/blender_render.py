"""Render one scene with headless Blender. Runs as its own process:

    python -m b2a.blender_render job.json

job.json: {"stage": {...}, "seconds": 5.2, "out": "frames_dir", "frame": optional single frame}
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> None:
    job = json.loads(Path(sys.argv[1]).read_text())
    from . import world  # imports bpy, which is heavy

    Path(job["out"]).mkdir(parents=True, exist_ok=True)
    frames = world.render_scene(job["stage"], job["seconds"], job["out"], only_frame=job.get("frame"))
    print(f"[blender] rendered {1 if job.get('frame') is not None else frames} frame(s)")


if __name__ == "__main__":
    main()
