"""Step 3: character references, scene images and short animations."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from . import config, fal, style


def character_refs(book: dict[str, Any]) -> dict[str, Path]:
    """One fixed reference image per recurring character, made once per book."""
    refs: dict[str, Path] = {}
    for key, char in book["characters"].items():
        repo = config.BOOKS_DIR / book["slug"] / "characters" / f"{key}.png"
        data = config.DATA_DIR / "books" / book["slug"] / "characters" / f"{key}.png"
        if repo.exists():
            refs[key] = repo
            continue
        if not data.exists():
            result = fal.run(config.IMAGE_MODEL, {
                "prompt": style.CHARACTER_SHEET.format(character=char["prompt"]),
                "aspect_ratio": "1:1", "resolution": "1K", "output_format": "png",
            })
            fal.download(result["images"][0]["url"], data)
        refs[key] = data
    return refs


def scene_image(scene: dict[str, Any], ref_urls: dict[str, str], dest: Path) -> Path:
    if dest.exists():
        return dest
    prompt = style.SCENE.format(scene=scene["image"])
    refs = [ref_urls[c] for c in scene.get("characters", []) if c in ref_urls]
    # Without a character in frame we still pass the references so the world
    # keeps the same look.
    refs = refs or list(ref_urls.values())[:1]
    args = {"prompt": prompt, "aspect_ratio": "9:16", "resolution": "1K", "output_format": "png"}
    if refs:
        result = fal.run(config.IMAGE_EDIT_MODEL, {**args, "image_urls": refs})
    else:
        result = fal.run(config.IMAGE_MODEL, args)
    return fal.download(result["images"][0]["url"], dest)


def scene_clip(scene: dict[str, Any], image: Path, seconds: float, dest: Path) -> Path:
    if dest.exists():
        return dest
    result = fal.run(config.VIDEO_MODEL, {
        "prompt": style.MOTION.format(motion=scene["motion"]),
        "image_url": fal.upload(image),
        "duration": round(min(max(seconds, 2.0), 15.0), 1),
        "resolution": config.VIDEO_RESOLUTION,
        "prompt_expansion_mode": "balanced",
    })
    return fal.download(result["video"]["url"], dest)


def animated_indexes(n_scenes: int) -> set[int]:
    mode = config.ANIMATE.strip().lower()
    if mode == "all":
        return set(range(n_scenes))
    if mode == "none":
        return set()
    return set(range(min(int(mode), n_scenes)))


def make_visuals(book: dict[str, Any], script: dict[str, Any],
                 times: list[tuple[float, float]], out_dir: Path) -> list[dict[str, Path | None]]:
    refs = character_refs(book)
    ref_urls = {key: fal.upload(path) for key, path in refs.items()}
    scenes = script["scenes"]
    animate = animated_indexes(len(scenes))

    def work(i: int) -> dict[str, Path | None]:
        image = scene_image(scenes[i], ref_urls, out_dir / f"scene_{i:02d}.png")
        clip = None
        if i in animate:
            try:
                clip = scene_clip(scenes[i], image, times[i][1] - times[i][0],
                                  out_dir / f"scene_{i:02d}.mp4")
            except RuntimeError as exc:  # fall back to a camera move on the still
                print(f"[visuals] scene {i}: animation failed, using still ({exc})")
        return {"image": image, "clip": clip}

    with ThreadPoolExecutor(max_workers=4) as pool:
        return list(pool.map(work, range(len(scenes))))


def make_music(out_dir: Path) -> Path | None:
    """Reuse a track from assets/music if there is one, else generate one."""
    library = sorted((config.ASSETS_DIR / "music").glob("*.mp3"))
    if library:
        return library[0]
    dest = out_dir / "music.mp3"
    if not dest.exists():
        try:
            result = fal.run(config.MUSIC_MODEL, {"prompt": style.MUSIC})
            fal.download(result["audio"]["url"], dest)
        except RuntimeError as exc:
            print(f"[music] skipped: {exc}")
            return None
    return dest
