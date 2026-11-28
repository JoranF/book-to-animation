"""The asset library: characters, props and backgrounds (sets) kept between Shorts.

Two kinds of assets live side by side:
- built-in: the fixed kit written as code in world.py (the youth, the
  philosopher, 7 sets, 23 props). Always there, always the same.
- generated: made by Claude when a script needs something the kit does not
  have (a phone, a classroom, a teacher). Each one is a small JSON "recipe"
  of low-poly parts, saved in DATA_DIR/assets/<kind>/<name>.json, so every
  later Short reuses the exact same thing.

Reuse first: a requested asset is matched by name, alias and tags before
anything new is made. An asset can be marked for rebuild (with a note such as
"make it taller"); it is made again the next time a Short uses it, or right
away. A rebuild of a built-in prop or set saves a generated version that
replaces it until it is reset. The recurring characters are locked: they never
change, so every episode looks like the same show.

This module does not need Blender. world.py builds the recipes.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import config, llm

KINDS = ("prop", "set", "character")
SHAPES = ("box", "tube", "ball", "head", "ring", "plane")
MOTIONS = ("bob", "spin", "sway", "pulse", "none")
HAIR_STYLES = ("spikes", "flat", "bun", "bald")
MOODS = ("happy", "calm", "worried", "sad", "angry", "tired", "smirk", "plain")
LOCKED = {"youth", "philosopher"}      # the recurring characters never change
MAX_PARTS = 48
_lock = threading.RLock()

# What the built-in kit holds, with tags so a request like "phone booth" or
# "mentor" can be matched to something that is already there.
BUILTIN: dict[str, dict[str, dict[str, Any]]] = {
    "character": {
        "youth": {"description": "the impatient young man in a red top with spiky blue hair, a recurring character",
                  "tags": ["young", "student", "man", "boy", "main"]},
        "philosopher": {"description": "the calm old bald philosopher with a white beard, glasses and a cane, a recurring character",
                        "tags": ["old", "wise", "mentor", "elder", "sage"]},
        "father": {"description": "a strict father in a grey suit and red tie", "tags": ["dad", "parent", "adult"]},
        "grey": {"description": "a faceless grey person for crowds and other people", "tags": ["crowd", "people", "stranger", "person"]},
    },
    "set": {
        "bedroom_night": {"description": "dark bedroom at night with window and bed", "tags": ["bedroom", "night", "room", "home"]},
        "study": {"description": "the philosopher's warm study with bookshelves", "tags": ["study", "library", "office", "books", "room"]},
        "workshop": {"description": "bright room with windows", "tags": ["room", "bright", "studio", "workshop"]},
        "town": {"description": "town square with houses and trees", "tags": ["town", "street", "city", "outside", "square"]},
        "field": {"description": "green meadow with hills and trees", "tags": ["field", "meadow", "grass", "outside", "nature"]},
        "island": {"description": "floating grass island in the sky", "tags": ["island", "sky", "dream", "floating"]},
        "hill_sunrise": {"description": "hilltop at sunrise", "tags": ["hill", "sunrise", "morning", "top"]},
    },
    "prop": {
        "desk": {"tags": ["table", "desk", "work"]}, "paper_tower": {"tags": ["papers", "stack", "work", "pile"]},
        "falling_paper": {"tags": ["papers", "falling"]}, "lamp": {"tags": ["light", "lamp"]},
        "floating_head": {"tags": ["head", "judge", "opinion"]}, "bookshelf": {"tags": ["books", "shelf"]},
        "fireplace": {"tags": ["fire", "fireplace", "warm"]}, "door": {"tags": ["door", "exit", "portal"]},
        "path": {"tags": ["road", "path", "way"]}, "cube": {"tags": ["cube", "block", "glowing"]},
        "easel": {"tags": ["painting", "canvas", "art"]}, "briefcase": {"tags": ["bag", "case", "work", "job"]},
        "big_backpack": {"tags": ["bag", "backpack", "burden", "load"]}, "tree": {"tags": ["tree", "nature"]},
        "house": {"tags": ["house", "home", "building"]}, "cloud": {"tags": ["cloud", "sky"]},
        "sun": {"tags": ["sun", "sky"]}, "hill": {"tags": ["hill"]}, "island": {"tags": ["island"]},
        "bed": {"tags": ["bed", "sleep"]}, "window": {"tags": ["window"]}, "rug": {"tags": ["rug", "carpet"]},
        "chair": {"tags": ["chair", "seat", "armchair"]},
    },
}


# --- names and storage -----------------------------------------------------

def slug(name: Any) -> str:
    """'Smart Phone' -> 'smart_phone'."""
    text = re.sub(r"[^a-z0-9]+", "_", str(name or "").lower()).strip("_")
    return text[:40]


def _words(text: str) -> set[str]:
    out = set()
    for w in re.split(r"[^a-z0-9]+", text.lower()):
        if len(w) < 3:
            continue
        out.add(w[:-1] if w.endswith("s") and len(w) > 3 else w)
    return out


def root() -> Path:
    return config.DATA_DIR / "assets"


def _file(kind: str, name: str) -> Path:
    return root() / kind / f"{name}.json"


def preview_path(kind: str, name: str) -> Path:
    return root() / "previews" / f"{kind}-{name}.png"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load(kind: str, name: str) -> dict[str, Any] | None:
    """A generated asset (or the override of a built-in one), or None."""
    try:
        data = json.loads(_file(kind, name).read_text())
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def save(asset: dict[str, Any]) -> dict[str, Any]:
    path = _file(asset["kind"], asset["name"])
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(asset, indent=1, ensure_ascii=False))
    tmp.replace(path)
    return asset


def generated(kind: str | None = None) -> list[dict[str, Any]]:
    out = []
    for k in ([kind] if kind else KINDS):
        for path in sorted((root() / k).glob("*.json")):
            asset = load(k, path.stem)
            if asset:
                out.append(asset)
    return out


def _builtin_record(kind: str, name: str) -> dict[str, Any]:
    info = BUILTIN[kind][name]
    return {"name": name, "kind": kind, "source": "builtin", "description": info.get("description", name.replace("_", " ")),
            "tags": list(info.get("tags", [])), "aliases": [], "locked": name in LOCKED, "rebuild": False}


def get(kind: str, name: str) -> dict[str, Any] | None:
    """The asset that is used for this name: a generated one wins over the built-in."""
    asset = load(kind, name)
    if asset:
        return asset
    if name in BUILTIN.get(kind, {}):
        return _builtin_record(kind, name)
    return None


def catalog() -> list[dict[str, Any]]:
    """Every asset there is: built-in ones (unless overridden) and generated ones."""
    with _lock:
        made = {(a["kind"], a["name"]): a for a in generated()}
        out = []
        for kind in KINDS:
            for name in BUILTIN[kind]:
                asset = made.pop((kind, name), None)
                out.append({**asset, "overrides_builtin": True} if asset else _builtin_record(kind, name))
        out.extend(made.values())
        for asset in out:
            asset["has_preview"] = preview_path(asset["kind"], asset["name"]).exists()
        return out


def known() -> dict[str, Any]:
    """Names the stage checker accepts, plus the height of every character."""
    names: dict[str, set[str]] = {k: set(BUILTIN[k]) for k in KINDS}
    heights: dict[str, float] = {}
    for asset in generated():
        names[asset["kind"]].add(asset["name"])
        if asset["kind"] == "character":
            heights[asset["name"]] = round(1.6 * float(asset.get("recipe", {}).get("scale", 1.0)), 2)
    return {"prop": names["prop"], "set": names["set"], "character": names["character"], "heights": heights}


# --- finding something that is already there -------------------------------

def find(kind: str, name: str, description: str = "", tags: list[str] | None = None) -> dict[str, Any] | None:
    """Reuse first: exact name, alias, then a close match on name, tags and description."""
    name = slug(name)
    hit = get(kind, name)
    if hit:
        return hit
    pool = [a for a in catalog() if a["kind"] == kind]
    if kind == "character":     # a new person is never swapped for one of the fixed cast
        pool = [a for a in pool if a.get("source") != "builtin"]
    squashed = name.replace("_", "")
    for asset in pool:               # an alias, or the same name written apart ("smart_phone")
        names = [asset["name"], *asset.get("aliases", [])]
        if name in names or squashed in (n.replace("_", "") for n in names):
            return asset
    want_name = _words(name.replace("_", " "))
    want = want_name | _words(" ".join(tags or [])) | _words(description)
    if not want_name:
        return None
    best, score = None, 0.0
    for asset in pool:
        have_name = _words(asset["name"].replace("_", " ")) | _words(" ".join(asset.get("aliases", [])))
        have = have_name | _words(" ".join(asset.get("tags", []))) | _words(asset.get("description", ""))
        # the request's name must be (part of) the asset's name/aliases/tags,
        # and the rest must mostly agree, so a "phone" never becomes a "phone booth"
        # every word of the requested name must be the asset's name, an alias
        # or a tag ("phone" finds the smartphone tagged phone, but a "phone
        # booth" is not a smartphone); an asset whose own name is fully in
        # the request ranks first
        if len(want_name & have) < len(want_name):
            continue
        overlap = len(want & have) / max(len(want | have), 1)
        both_ways = have_name <= want
        value = overlap + (1.0 if both_ways else 0.0)
        if value > score:
            best, score = asset, value
    return best


# --- recipes -----------------------------------------------------------------

def _hex(value: Any, what: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        raise ValueError(f"{what} must be a colour like #a1b2c3")
    return value.lower()


def _nums(value: Any, n: int, what: str, low: float, high: float) -> list[float]:
    if not (isinstance(value, (list, tuple)) and len(value) == n
            and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value)):
        raise ValueError(f"{what} must be a list of {n} numbers")
    if any(not low <= v <= high for v in value):
        raise ValueError(f"{what} numbers must be between {low} and {high}")
    return [round(float(v), 3) for v in value]


def _num(value: Any, what: str, low: float, high: float, default: float) -> float:
    if value is None:
        return default
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not low <= value <= high:
        raise ValueError(f"{what} must be a number between {low} and {high}")
    return round(float(value), 3)


def _parts(parts: Any, reach: float) -> list[dict[str, Any]]:
    if not isinstance(parts, list) or not 1 <= len(parts) <= MAX_PARTS:
        raise ValueError(f"'parts' must be a list of 1 to {MAX_PARTS} parts")
    out = []
    for i, part in enumerate(parts, 1):
        if not isinstance(part, dict):
            raise ValueError(f"part {i} must be an object")
        if part.get("shape") not in SHAPES:
            raise ValueError(f"part {i}: shape must be one of {list(SHAPES)}")
        clean = {"shape": part["shape"], "color": _hex(part.get("color"), f"part {i} color"),
                 "size": _nums(part.get("size"), 3, f"part {i} size", 0.005, reach),
                 "at": _nums(part.get("at", [0, 0, 0]), 3, f"part {i} at", -reach, reach),
                 "rot": _nums(part.get("rot", [0, 0, 0]), 3, f"part {i} rot", -360, 360)}
        if part["shape"] == "tube":
            clean["sides"] = int(_num(part.get("sides"), f"part {i} sides", 3, 12, 6))
            clean["top"] = _num(part.get("top"), f"part {i} top", 0, 2, 1.0)
        if part.get("glow"):
            clean["glow"] = _num(part.get("glow"), f"part {i} glow", 0, 4, 0)
        if part.get("moves"):
            clean["moves"] = True
        out.append(clean)
    return out


def check_recipe(kind: str, recipe: Any) -> dict[str, Any]:
    """Raise ValueError with a clear message when a recipe cannot be built."""
    if not isinstance(recipe, dict):
        raise ValueError("'recipe' must be an object")
    if kind == "prop":
        out: dict[str, Any] = {"parts": _parts(recipe.get("parts"), 6.0)}
        motion = recipe.get("motion") or {"type": "none"}
        if not isinstance(motion, dict) or motion.get("type", "none") not in MOTIONS:
            raise ValueError(f"motion.type must be one of {list(MOTIONS)}")
        if motion.get("type", "none") != "none":
            out["motion"] = {"type": motion["type"], "speed": _num(motion.get("speed"), "motion.speed", 0.1, 6, 1.5),
                             "amount": _num(motion.get("amount"), "motion.amount", 0.01, 1.5, 0.1)}
        height = max(p["at"][2] + p["size"][2] / 2 for p in out["parts"])
        if height > 6:
            raise ValueError("a prop must stay under 6 metres tall")
        return out
    if kind == "set":
        out = {"sky": _hex(recipe.get("sky"), "sky"),
               "light": {"angle": _nums((recipe.get("light") or {}).get("angle", [50, 0, 30]), 3, "light.angle", -360, 360),
                         "color": _hex((recipe.get("light") or {}).get("color", "#fff6dd"), "light.color"),
                         "power": _num((recipe.get("light") or {}).get("power"), "light.power", 0.2, 4, 2.4)}}
        if recipe.get("room"):
            room = recipe["room"]
            if not isinstance(room, dict):
                raise ValueError("'room' must be an object with floor, floor2 and wall colours")
            out["room"] = {k: _hex(room.get(k), f"room.{k}") for k in ("floor", "floor2", "wall")}
        else:
            ground = recipe.get("ground") or {}
            out["ground"] = {"color": _hex(ground.get("color"), "ground.color")}
            if ground.get("checker"):
                out["ground"]["checker"] = _hex(ground["checker"], "ground.checker")
        out["parts"] = _parts(recipe.get("parts") or [{"shape": "box", "color": out["sky"], "size": [0.01, 0.01, 0.01],
                                                       "at": [0, 30, 0]}], 40.0)
        props = recipe.get("props") or []
        if not isinstance(props, list) or len(props) > 12:
            raise ValueError("'props' must be a list of at most 12 built-in props")
        for spec in props:
            if not isinstance(spec, dict) or spec.get("type") not in BUILTIN["prop"]:
                raise ValueError(f"set props must be built-in props: {sorted(BUILTIN['prop'])}")
        out["props"] = props
        return out
    if kind == "character":
        out = {"scale": _num(recipe.get("scale"), "scale", 0.6, 1.2, 1.0),
               "wide": _num(recipe.get("wide"), "wide", 0.8, 1.5, 1.0),
               "head": _num(recipe.get("head"), "head", 0.85, 1.3, 1.0)}
        for key in ("skin", "top", "legs", "shorts", "shoes"):
            out[key] = _hex(recipe.get(key), key)
        out["shoe_tip"] = _hex(recipe.get("shoe_tip", out["shoes"]), "shoe_tip")
        style = recipe.get("hair_style", "flat")
        if style not in HAIR_STYLES:
            raise ValueError(f"hair_style must be one of {list(HAIR_STYLES)}")
        out["hair_style"] = style
        out["hair"] = None if style == "bald" else _hex(recipe.get("hair"), "hair")
        for key in ("beard", "tie", "shirt", "stripe", "pack"):
            if recipe.get(key):
                out[key] = _hex(recipe[key], key)
        if recipe.get("coat"):
            out["coat"] = True
            out.setdefault("shirt", out["top"])
        if recipe.get("glasses"):
            out["glasses"] = True
        mood = recipe.get("mood", "plain")
        out["mood"] = mood if mood in MOODS else "plain"
        return out
    raise ValueError(f"kind must be one of {list(KINDS)}")


# --- making assets with Claude ----------------------------------------------

DESIGN_SYSTEM = """You are the 3D modeller of an animated YouTube Shorts \
channel in a late-90s low-poly console game style (chunky shapes, few \
polygons, flat bright colours, a bit toy-like). Everything you make is \
original. You build one asset as JSON from simple shapes; it is saved and \
reused in every later episode, so make it clear, readable from a distance \
and in the same style as the rest of the world.

Units are metres. x: left (-) to right (+), y: depth (bigger is further \
away), z: up. The youth is 1.6 tall, the philosopher 1.2; a desk top is at \
0.66. Make things their real size (a phone about 0.15 tall, a mug 0.1, a \
car 1.5); small things may be up to twice as big so they read on a phone \
screen. Use strong, simple silhouettes, 4 to 30 parts, and 2 to 5 colours \
from a cheerful retro palette.

PART: {"shape": "box"|"tube"|"ball"|"head"|"ring"|"plane", "color": "#rrggbb", \
"size": [width, depth, height], "at": [x, y, z] (centre of the part), \
"rot": [x, y, z] degrees, "sides": 3-12 and "top": 0-2 (tube only: number of \
sides, top radius ratio; top 0 is a cone), "glow": 0-4 (glowing screens, \
lights, magic), "moves": true (only the parts the motion should move)}
"ball" is a chunky low-poly sphere, "head" a smoother one, "ring" a torus \
lying flat (rotate 90 on x to stand it up), "plane" a flat square.

%s

Return ONLY JSON: {"description": "one line, what it is and looks like", \
"tags": ["4 to 8 single words people might call it"], "recipe": RECIPE}"""

KIND_RULES = {
    "prop": """RECIPE for a PROP: {"parts": [PART...], "motion": {"type": \
"bob"|"spin"|"sway"|"pulse"|"none", "speed": 0.1-6, "amount": 0.01-1.5}}
The prop stands on the floor at its own origin: [0, 0, 0] is the middle of \
its base, so z of the lowest part is about half its height. Keep it within \
x and y -1.5..1.5 unless it is a big thing (a car, a wall). Motion moves the \
parts with "moves": true (a phone screen that pulses, a fan that spins); \
leave it "none" for still objects.""",
    "set": """RECIPE for a SET (a background where a scene happens): \
{"sky": "#rrggbb", "light": {"angle": [x, y, z] degrees, "color": "#rrggbb", \
"power": 0.2-4}, "room": {"floor": "#..", "floor2": "#..", "wall": "#.."} \
for indoor places OR "ground": {"color": "#..", "checker": "#.."} for \
outdoor places, "parts": [PART...], "props": [{"type": BUILTIN_PROP, "pos": \
[x, y]...}]}
Actors stand around x -1.5..1.5, y 0..1.5 looking at the camera, which is \
in front (negative y). Keep that area free. A room is 7 wide with its back \
wall at y 4.5: put furniture against the walls (y 3..4.3, or x beyond +-2). \
Outdoors, put scenery from y 4 to y 30. Parts use world coordinates. \
Built-in props you may place: %s.""" % ", ".join(sorted(BUILTIN["prop"])),
    "character": """RECIPE for a CHARACTER (a body built like the other \
characters, so they all move the same): {"scale": 0.6-1.2 (1.0 is 1.6 m \
tall), "wide": 0.8-1.5, "head": 0.85-1.3, "skin": "#..", "top": "#..", \
"legs": "#..", "shorts": "#.." (trousers or skirt top), "shoes": "#..", \
"shoe_tip": "#..", "hair_style": "spikes"|"flat"|"bun"|"bald", "hair": "#..", \
"beard": "#.." (optional), "glasses": true (optional), "tie": "#.." \
(optional), "coat": true + "shirt": "#.." (optional long coat), "stripe": \
"#.." (optional sleeve stripe), "mood": "happy"|"calm"|"worried"|"sad"| \
"angry"|"tired"|"smirk"|"plain" (their usual face)}
Make them clearly different from the youth (red top, blue spiky hair) and \
the philosopher (yellow coat, bald, white beard).""",
}


def design(kind: str, name: str, description: str, note: str = "",
           old: dict[str, Any] | None = None) -> dict[str, Any]:
    """Ask Claude for a recipe and check it. Returns description, tags and recipe."""
    from .script import _ask_json      # the shared ask-until-valid loop

    def check(data: dict[str, Any]) -> dict[str, Any]:
        recipe = check_recipe(kind, data.get("recipe"))
        tags = [slug(t) for t in (data.get("tags") or []) if slug(t)][:10]
        return {"description": str(data.get("description") or description)[:200], "tags": tags, "recipe": recipe}

    ask = f"Make the {kind} \"{name}\": {description or name.replace('_', ' ')}."
    if old:
        ask += f"\nThe current version (JSON), to improve on:\n{json.dumps(old.get('recipe'), ensure_ascii=False)}"
    if note:
        ask += f"\nWhat must change: {note}"
    system = DESIGN_SYSTEM % KIND_RULES[kind]
    result, _ = _ask_json(system, [{"role": "user", "content": ask}], check,
                          model=config.ASSET_MODEL, effort=config.ASSET_EFFORT, step="assets", max_tokens=12000)
    return result


def create(kind: str, name: str, description: str = "", tags: list[str] | None = None,
           short_id: str | None = None) -> dict[str, Any]:
    """Make a new generated asset and save it (with a preview when Blender is there)."""
    name = slug(name)
    if not name:
        raise ValueError("an asset needs a name")
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {list(KINDS)}")
    if kind == "character" and name in LOCKED:
        raise ValueError(f"'{name}' is a recurring character and cannot be replaced")
    made = design(kind, name, description)
    asset = {"name": name, "kind": kind, "source": "generated", "description": made["description"],
             "tags": sorted(set(made["tags"]) | {slug(t) for t in tags or [] if slug(t)}), "aliases": [],
             "recipe": made["recipe"], "version": 1, "created": _now(), "updated": _now(),
             "created_for": short_id, "rebuild": False, "rebuild_note": "", "used": 0, "used_in": [], "history": []}
    with _lock:
        save(asset)
    make_preview(asset)
    return asset


def ensure(kind: str, name: str, description: str = "", tags: list[str] | None = None,
           short_id: str | None = None) -> tuple[dict[str, Any], bool]:
    """Reuse a matching asset, or make it. Returns (asset, made_now)."""
    with _lock:
        hit = find(kind, name, description, tags)
        if hit:
            wanted = slug(name)
            if wanted != hit["name"] and hit.get("source") == "generated" and wanted not in hit.get("aliases", []):
                hit.setdefault("aliases", []).append(wanted)
                save(hit)
            return hit, False
    return create(kind, name, description, tags, short_id), True


def mark_rebuild(kind: str, name: str, note: str = "", on: bool = True) -> dict[str, Any]:
    """Flag an asset so it is made again the next time a Short uses it."""
    with _lock:
        asset = get(kind, name)
        if not asset:
            raise KeyError(f"no {kind} called '{name}'")
        if asset.get("locked"):
            raise ValueError(f"'{name}' is a recurring character and is locked, so every episode looks the same")
        if asset["source"] == "builtin":     # a built-in one gets a generated stand-in later
            asset = {**asset, "source": "builtin_pending", "recipe": None, "version": 0, "created": _now(),
                     "used": 0, "used_in": [], "history": []}
        asset.update(rebuild=on, rebuild_note=note if on else "", updated=_now())
        if asset["source"] == "builtin_pending" and not on:
            _file(kind, name).unlink(missing_ok=True)
            return get(kind, name) or asset
        return save(asset)


def rebuild(kind: str, name: str, note: str | None = None) -> dict[str, Any]:
    """Make the asset again now. The old version is kept in its history."""
    with _lock:
        asset = get(kind, name)
    if not asset:
        raise KeyError(f"no {kind} called '{name}'")
    if asset.get("locked"):
        raise ValueError(f"'{name}' is a recurring character and is locked")
    note = asset.get("rebuild_note", "") if note is None else note
    old = asset if asset.get("recipe") else None
    made = design(kind, name, asset.get("description", ""), note, old)
    with _lock:
        current = load(kind, name) or {**asset, "used": 0, "used_in": [], "history": []}
        if current.get("recipe"):
            current.setdefault("history", []).append({"version": current.get("version", 1), "recipe": current["recipe"],
                                                      "updated": current.get("updated")})
            current["history"] = current["history"][-5:]
        current.update(source="generated", description=made["description"], recipe=made["recipe"],
                       tags=sorted(set(current.get("tags", [])) | set(made["tags"])),
                       version=int(current.get("version") or 0) + 1, updated=_now(), rebuild=False, rebuild_note="",
                       last_note=note)
        save(current)
    make_preview(current)
    return current


def reset(kind: str, name: str) -> dict[str, Any] | None:
    """Delete a generated asset. For a built-in name this brings the original back."""
    with _lock:
        _file(kind, name).unlink(missing_ok=True)
        preview_path(kind, name).unlink(missing_ok=True)
        return get(kind, name)


def edit(kind: str, name: str, tags: list[str] | None = None, aliases: list[str] | None = None,
         description: str | None = None) -> dict[str, Any]:
    with _lock:
        asset = load(kind, name)
        if not asset:
            raise KeyError(f"no generated {kind} called '{name}'")
        if tags is not None:
            asset["tags"] = sorted({slug(t) for t in tags if slug(t)})
        if aliases is not None:
            asset["aliases"] = sorted({slug(a) for a in aliases if slug(a) and slug(a) != name})
        if description is not None:
            asset["description"] = str(description)[:200]
        asset["updated"] = _now()
        return save(asset)


# --- using assets in a Short ---------------------------------------------------

def used_names(stage: dict[str, Any]) -> list[tuple[str, str]]:
    names = [("set", stage.get("set", ""))]
    names += [("prop", p.get("type", "")) for p in stage.get("props", []) if isinstance(p, dict)]
    names += [("character", a.get("who", "")) for a in stage.get("actors", []) if isinstance(a, dict)]
    return list(dict.fromkeys(names))


def prepare(stages: list[dict[str, Any]], short_id: str | None = None,
            progress=None) -> dict[str, dict[str, Any]]:
    """Before rendering: rebuild what is marked for rebuild, count the use, and
    return the recipes every scene needs ({name: {kind, recipe, version}})."""
    wanted = list(dict.fromkeys(n for s in stages for n in used_names(s)))
    out: dict[str, dict[str, Any]] = {}
    for kind, name in wanted:
        asset = get(kind, name)
        if not asset:
            continue
        if asset.get("rebuild") and not asset.get("locked"):
            if progress:
                progress(f"Rebuilding {kind} '{name}'")
            try:
                asset = rebuild(kind, name)
            except Exception as exc:  # noqa: BLE001 - an old version is better than no Short
                print(f"[b2a] rebuild of {kind} '{name}' failed, using the current one: {exc}")
        if asset.get("source") == "generated":
            with _lock:
                fresh = load(kind, name) or asset
                fresh["used"] = int(fresh.get("used", 0)) + 1
                if short_id and short_id not in fresh.setdefault("used_in", []):
                    fresh["used_in"] = (fresh["used_in"] + [short_id])[-50:]
                save(fresh)
            out[name] = {"kind": kind, "recipe": asset["recipe"], "version": asset.get("version", 1)}
    return out


def for_stage(stage: dict[str, Any], recipes: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """The recipes one scene needs, by name (handed to Blender inside the stage)."""
    names = {n for _, n in used_names(stage)}
    return {n: r for n, r in recipes.items() if n in names}


def library_guide(limit: int = 60) -> str:
    """The generated assets, for the stage writer, so it reuses them."""
    made = [a for a in generated() if a.get("recipe")]
    if not made:
        return "LIBRARY (made earlier, reuse them): none yet."
    made.sort(key=lambda a: -int(a.get("used", 0)))
    lines = [f'- {a["kind"]} "{a["name"]}": {a.get("description", "")}' for a in made[:limit]]
    return "LIBRARY (made for earlier episodes; use them like the kit, by name):\n" + "\n".join(lines)


# --- previews --------------------------------------------------------------------

def preview_stage(asset: dict[str, Any]) -> dict[str, Any]:
    """A one-frame scene that shows the asset."""
    kind, name = asset["kind"], asset["name"]
    if kind == "set":
        stage = {"set": name, "props": [], "actors": [{"who": "youth", "pos": [0, 0.6], "action": "idle"}],
                 "camera": {"move": "static", "target": [0, 0.6, 1.2], "dist": 6, "height": 1.8}}
    elif kind == "character":
        stage = {"set": "workshop", "props": [], "actors": [{"who": name, "pos": [0, 0.4], "face": 15, "action": "idle"}],
                 "camera": {"move": "static", "target": [0, 0.4, 0.8], "dist": 3.4, "height": 1.3}}
    else:
        top = max(p["at"][2] + p["size"][2] / 2 for p in asset["recipe"]["parts"])
        stage = {"set": "workshop", "props": [{"type": name, "pos": [0, 0.5]}],
                 "actors": [{"who": "youth", "pos": [-1.2, 0.6], "face": 30, "action": "idle"}],
                 "camera": {"move": "static", "target": [0, 0.5, top * 0.5],
                            "dist": max(1.6, top * 2.6), "height": top * 0.8 + 0.4, "angle": 18}}
    stage["assets"] = {name: {"kind": kind, "recipe": asset["recipe"], "version": asset.get("version", 1)}}
    return stage


def make_preview(asset: dict[str, Any]) -> Path | None:
    """Render one frame of the asset to a PNG. Best effort: never stops a Short."""
    if os.environ.get("ASSET_PREVIEWS", "1") == "0" or not asset.get("recipe"):
        return None
    dest = preview_path(asset["kind"], asset["name"])
    work = dest.parent / f".{asset['kind']}-{asset['name']}"
    try:
        work.mkdir(parents=True, exist_ok=True)
        job = work / "job.json"
        job.write_text(json.dumps({"stage": preview_stage(asset), "seconds": 1, "out": str(work), "frame": 0}))
        proc = subprocess.run([sys.executable, "-m", "b2a.blender_render", str(job)], capture_output=True,
                              text=True, cwd=config.ROOT, timeout=300)
        frame = work / "f_0000.png"
        if proc.returncode != 0 or not frame.exists():
            print(f"[b2a] preview of {asset['name']} failed: {proc.stderr[-400:]}")
            return None
        frame.replace(dest)
        return dest
    except Exception as exc:  # noqa: BLE001
        print(f"[b2a] preview of {asset['name']} failed: {exc}")
        return None
    finally:
        shutil.rmtree(work, ignore_errors=True)
