"""What a scene can contain, without needing Blender.

The script writer gets GUIDE as its instruction manual and every scene's
"stage" is checked with validate() before anything is rendered. The actual
shapes and movements live in world.py.
"""
from __future__ import annotations

from typing import Any

SETS = ["bedroom_night", "study", "workshop", "town", "field", "island", "hill_sunrise"]
WHO = ["youth", "philosopher", "father", "grey"]
MOODS = ["happy", "calm", "worried", "sad", "angry", "tired", "smirk", "plain"]
ACTIONS = ["idle", "walk", "trudge", "slump", "stop", "point", "point_viewer", "look_around",
           "give", "reach", "paint", "arms_crossed", "whisper", "arms_up", "nod"]
PROPS = ["desk", "paper_tower", "falling_paper", "lamp", "floating_head", "bookshelf", "fireplace",
         "door", "path", "cube", "easel", "briefcase", "big_backpack", "tree", "house", "cloud",
         "sun", "hill", "island", "bed", "window", "rug", "chair"]
CAMERA_MOVES = ["static", "push_in", "pull_back", "orbit", "rise", "track"]
HEADS = ["mom", "boss", "stranger"]

DEFAULT = {
    "set": "field",
    "actors": [{"who": "youth", "pos": [-0.7, 0], "action": "idle"},
               {"who": "philosopher", "pos": [0.7, 0], "action": "nod"}],
    "camera": {"move": "push_in", "target": [0, 0, 0.8], "dist": 4.4, "height": 1.3},
}

GUIDE = """Every scene has a "stage": a small 3D scene built from a fixed kit.
Units are metres. x: left (-) to right (+). y: depth, 0 is the front, bigger is
further from the camera. z: height. The youth is 1.6 tall, the philosopher 1.2.
Keep main actors within x -1.5..1.5 and y 0..1.5.

{"set": SET, "props": [PROP...], "actors": [ACTOR...], "camera": CAMERA}

SET, one of:
- "bedroom_night": dark bedroom with window and bed
- "study": the philosopher's warm study with bookshelves (add a fireplace prop at pos [0.1, 4.15])
- "workshop": bright room with windows
- "town": square with houses and trees, checkered pavement
- "field": green checkered meadow with hills and trees
- "island": floating grass island in the sky, centre [0, 2.5], radius 4.6
- "hill_sunrise": hilltop at sunrise; actors here need a height: pos [x, 1.2, 0.97]

ACTOR: {"who": "youth"|"philosopher"|"father"|"grey", "pos": [x, y], "face": degrees,
"action": ACTION, "mood": "happy"|"calm"|"worried"|"sad"|"angry"|"tired"|"plain"}
- "face": 0 looks at the camera, 90 looks right, -90 looks left, 180 looks away.
- "grey" is a faceless-looking grey person for crowds and "other people".
- optional "to": [x, y] (target for walk/trudge), "carry": "big_backpack",
  "offset": seconds (so a crowd does not move in sync).
ACTION, one of: "idle", "walk", "trudge" (bent under a load), "slump" (collapses
forward), "stop" (raises a hand), "point" (optional "sweep": degrees), "point_viewer",
"look_around", "give" ("side": 0 left arm, 1 right arm), "reach" (both arms forward),
"paint", "arms_crossed" (shakes head, taps foot), "whisper" ("lean": 1 or -1),
"arms_up" (relief, joy), "nod".

PROP: {"type": TYPE, "pos": [x, y] or [x, y, z], ...}. TYPE, one of:
- "desk"; "lamp" (on a desk: same pos); "bed"; "chair"; "rug"; "window" (pos [x, y, z] on the back wall y 4.38)
- "paper_tower" ("height": number of sheets 3..16, "z": 0.66 when it stands on a desk, "seed": any number)
- "falling_paper" ("top": height they fall from)
- "floating_head" ("who": "mom"|"boss"|"stranger", pos [x, y, z] with z about 3, "follow": metres per second to the right)
- "bookshelf", "fireplace" (against the back wall, y about 4.15)
- "door" ("color": "#rrggbb", glows), "path" ("from": [x, y], "to": [x, y]: a road on the ground)
- "cube" (glowing, "color", pos [x, y, z], optional "to": [x, y, z] to fly there, "start", "span" seconds)
- "easel" (a painting appears on it), "briefcase", "big_backpack" (lying on the ground, "size")
- "tree", "house" ("color", "roof"), "cloud" (pos [x, y, z] far away, e.g. [-5, 22, 7]), "sun", "hill"

CAMERA: {"move": "static"|"push_in"|"pull_back"|"orbit"|"rise"|"track",
"target": [x, y, z], "dist": metres, "height": camera height, "angle": degrees around the target}
- One actor full body: dist 3.4, target z 0.7. Two actors: dist 4.4, target z 0.9.
  Wide shot: dist 6, target z 1.2. Close-up of a face: dist 2.6.
- A lower target z moves the subject up in the frame; captions cover the lower third.
- "track" also needs "track": [dx, dy, dz], how far the target moves during the scene.

Example: {"set": "town", "props": [{"type": "floating_head", "who": "boss", "pos": [-1, 0.2, 3.3],
"follow": 0.42}], "actors": [{"who": "youth", "pos": [-1.1, 0], "to": [1.0, 0], "face": 90,
"action": "trudge", "carry": "big_backpack"}], "camera": {"move": "track", "target": [-1, 0, 1.6],
"track": [2.1, 0, 0], "dist": 6.2, "height": 1.7}}

Make every scene look different from the one before (other set, framing or action) and show
the idea as a visual metaphor, not just two people talking."""


def _vec(value: Any, sizes: tuple[int, ...], what: str) -> None:
    ok = isinstance(value, (list, tuple)) and len(value) in sizes and all(
        isinstance(v, (int, float)) and not isinstance(v, bool) for v in value)
    if not ok:
        raise ValueError(f"{what} must be a list of {' or '.join(map(str, sizes))} numbers")


def validate(stage: Any) -> dict[str, Any]:
    """Raise ValueError with a clear message when a stage uses unknown parts."""
    if not isinstance(stage, dict):
        raise ValueError("stage must be an object")
    if stage.get("set") not in SETS:
        raise ValueError(f"unknown set '{stage.get('set')}', choose from {SETS}")
    for prop in stage.setdefault("props", []):
        if prop.get("type") not in PROPS:
            raise ValueError(f"unknown prop type '{prop.get('type')}', choose from {PROPS}")
        if prop["type"] == "path":
            _vec(prop.get("from"), (2,), "path.from")
            _vec(prop.get("to"), (2,), "path.to")
        elif "pos" in prop:
            _vec(prop["pos"], (2, 3), f"{prop['type']}.pos")
        if prop["type"] == "floating_head" and prop.get("who", "mom") not in HEADS:
            raise ValueError(f"floating_head.who must be one of {HEADS}")
        if prop["type"] in ("floating_head", "cube", "cloud", "sun", "window") and "pos" in prop:
            _vec(prop["pos"], (3,), f"{prop['type']}.pos")
        if "to" in prop and prop["type"] == "cube":
            _vec(prop["to"], (3,), "cube.to")
    actors = stage.setdefault("actors", [])
    if len(actors) > 8:
        raise ValueError("at most 8 actors per scene")
    for actor in actors:
        if actor.get("who") not in WHO:
            raise ValueError(f"unknown actor '{actor.get('who')}', choose from {WHO}")
        if actor.setdefault("action", "idle") not in ACTIONS:
            raise ValueError(f"unknown action '{actor['action']}', choose from {ACTIONS}")
        if actor.get("mood") is not None and actor["mood"] not in MOODS:
            raise ValueError(f"unknown mood '{actor['mood']}', choose from {MOODS}")
        _vec(actor.setdefault("pos", [0, 0]), (2, 3), "actor.pos")
        if "to" in actor:
            _vec(actor["to"], (2, 3), "actor.to")
        if actor.get("carry") not in (None, "big_backpack"):
            raise ValueError("actor.carry can only be 'big_backpack'")
    camera = stage.setdefault("camera", {})
    if camera.setdefault("move", "push_in") not in CAMERA_MOVES:
        raise ValueError(f"unknown camera move '{camera['move']}', choose from {CAMERA_MOVES}")
    for key, sizes in (("target", (3,)), ("track", (3,))):
        if key in camera:
            _vec(camera[key], sizes, f"camera.{key}")
    for key in ("dist", "height", "angle", "amount"):
        if key in camera and not isinstance(camera[key], (int, float)):
            raise ValueError(f"camera.{key} must be a number")
    if not 1.5 <= camera.get("dist", 6.0) <= 14:
        raise ValueError("camera.dist must be between 1.5 and 14")
    return stage
