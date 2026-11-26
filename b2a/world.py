"""The channel's low-poly 3D world, built in code and drawn by headless Blender.

Everything here is original and made from simple shapes: two recurring
characters, a few sets, props and a small library of movements. A scene is
described as data (see STAGE.md) and rendered frame by frame.

Axes: X is right, Y is away from the camera, Z is up. Characters face the
camera (towards -Y) when their "face" angle is 0.
"""
from __future__ import annotations

import math
from typing import Any, Callable

import bpy
from mathutils import Vector

FPS = 15                # low frame rate on purpose, like an old console
RES = (360, 640)        # rendered small, scaled up with hard pixels later
AMBIENT = 0.42          # flat fill light baked into every material

sin, cos, pi = math.sin, math.cos, math.pi
Updater = Callable[[float, float], None]   # (seconds, scene length)


# --- basics ---------------------------------------------------------------

def rgb(hex_color: str) -> tuple[float, float, float]:
    """#rrggbb to linear colour."""
    h = hex_color.lstrip("#")
    vals = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in vals)


_materials: dict[tuple, Any] = {}


def material(color: str, glow: float = 0.0, checker: str | None = None, tiles: float = 1.0):
    key = (color, glow, checker, tiles)
    if key in _materials:
        return _materials[key]
    mat = bpy.data.materials.new(f"m_{color}_{glow}_{checker}")
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    diffuse = nodes.new("ShaderNodeBsdfDiffuse")
    emission = nodes.new("ShaderNodeEmission")
    add = nodes.new("ShaderNodeAddShader")
    emission.inputs["Strength"].default_value = glow or AMBIENT
    if checker:
        tex = nodes.new("ShaderNodeTexChecker")
        coord = nodes.new("ShaderNodeNewGeometry")   # world position: squares of 1/tiles metres
        tex.inputs["Color1"].default_value = (*rgb(color), 1)
        tex.inputs["Color2"].default_value = (*rgb(checker), 1)
        tex.inputs["Scale"].default_value = tiles
        links.new(coord.outputs["Position"], tex.inputs["Vector"])
        links.new(tex.outputs["Color"], diffuse.inputs["Color"])
        links.new(tex.outputs["Color"], emission.inputs["Color"])
    else:
        diffuse.inputs["Color"].default_value = (*rgb(color), 1)
        emission.inputs["Color"].default_value = (*rgb(color), 1)
    links.new(diffuse.outputs["BSDF"], add.inputs[0])
    links.new(emission.outputs["Emission"], add.inputs[1])
    links.new(add.outputs["Shader"], out.inputs["Surface"])
    _materials[key] = mat
    return mat


def joint(name: str, loc=(0, 0, 0), parent=None):
    obj = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = loc
    obj.parent = parent
    return obj


def shape(kind: str, color: str, size=(1, 1, 1), loc=(0, 0, 0), rot=(0, 0, 0), parent=None,
          glow: float = 0.0, sides: int = 6, top: float = 1.0, checker: str | None = None,
          tiles: float = 1.0):
    """One low-poly part. Sizes are full width, depth and height."""
    if kind == "box":
        bpy.ops.mesh.primitive_cube_add(size=1)
    elif kind == "tube":      # cylinder or cone, `top` is the top radius ratio
        bpy.ops.mesh.primitive_cone_add(vertices=sides, radius1=0.5, radius2=0.5 * top, depth=1)
    elif kind == "ball":
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=0.5)
    elif kind == "head":
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=0.5)
    elif kind == "ring":
        bpy.ops.mesh.primitive_torus_add(major_segments=8, minor_segments=3,
                                         major_radius=0.5, minor_radius=0.09)
    elif kind == "plane":
        bpy.ops.mesh.primitive_plane_add(size=1)
    else:
        raise ValueError(kind)
    obj = bpy.context.active_object
    obj.scale = size
    obj.location = loc
    obj.rotation_euler = [math.radians(a) for a in rot]
    obj.data.materials.append(material(color, glow, checker, tiles))
    obj.parent = parent
    return obj


def deg(obj, x=0.0, y=0.0, z=0.0) -> None:
    obj.rotation_euler = (math.radians(x), math.radians(y), math.radians(z))


def ease(x: float) -> float:
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


# --- characters -----------------------------------------------------------

LOOKS: dict[str, dict[str, Any]] = {
    "youth": dict(scale=1.0, skin="#f2c39a", top="#d62828", legs="#f2c39a", shorts="#7a7f8a",
                  shoes="#f4f4f4", shoe_tip="#f08a24", hair="#1d2a6b", hair_style="spikes",
                  stripe="#ffffff", pack="#2f9e44", wide=1.0, mood="worried"),
    "philosopher": dict(scale=0.76, skin="#eab892", top="#d9a521", legs="#6b4a2f", shorts="#6b4a2f",
                        shoes="#3d2b1f", shoe_tip="#3d2b1f", hair=None, hair_style="bald",
                        beard="#f5f5f5", glasses=True, shirt="#1f9aa0", coat=True, cane=True,
                        wide=1.25, head=1.18, mood="calm"),
    "father": dict(scale=1.05, skin="#e0ac85", top="#5c6370", legs="#3f444d", shorts="#3f444d",
                   shoes="#222222", shoe_tip="#222222", hair="#4a4038", hair_style="flat",
                   tie="#b02a37", wide=1.2, mood="angry"),
    "grey": dict(scale=0.98, skin="#a9adb5", top="#8a8f98", legs="#70757d", shorts="#70757d",
                 shoes="#5a5e65", shoe_tip="#5a5e65", hair=None, hair_style="bald", wide=1.05,
                 mood="plain"),
}

HEADS: dict[str, dict[str, Any]] = {
    "mom": dict(skin="#f0c2a2", hair="#7a3b1d", hair_style="bun", mood="sad"),
    "boss": dict(skin="#e3a987", hair="#2b2b2b", hair_style="flat", mood="angry", tie="#b02a37"),
    "stranger": dict(skin="#d9b08c", hair="#e0b83a", hair_style="spikes", mood="smirk"),
}


def build_face(head, look: dict[str, Any], r: float, mood: str) -> dict[str, Any]:
    """Eyes, brows and mouth as tiny blocks stuck on the front of the head."""
    front = -r * 0.92
    parts: dict[str, Any] = {"brows": [], "eyes": []}
    for side in (-1, 1):
        eye = shape("box", "#ffffff", (r * 0.42, r * 0.1, r * 0.46), (side * r * 0.36, front, r * 0.12), parent=head)
        shape("box", "#16161d", (r * 0.2, r * 0.1, r * 0.26), (side * r * 0.33, front - r * 0.04, r * 0.08), parent=head)
        tilt = {"worried": 18, "sad": 22, "angry": -24, "smirk": -8, "tired": 10}.get(mood, 0) * side
        brow_color = look.get("beard") or look.get("hair") or "#3a2d25"
        brow = shape("box", brow_color, (r * 0.5, r * 0.1, r * 0.11),
                     (side * r * 0.36, front - r * 0.02, r * 0.46), rot=(0, tilt, 0), parent=head)
        parts["eyes"].append(eye)
        parts["brows"].append(brow)
    happy = mood in ("happy", "calm", "smirk")
    mouth_w = r * (0.5 if happy else 0.3)
    parts["mouth"] = shape("box", "#5a1f1f", (mouth_w, r * 0.1, r * 0.1), (0, front, -r * 0.42), parent=head)
    if happy:
        for side in (-1, 1):
            shape("box", "#5a1f1f", (r * 0.1, r * 0.1, r * 0.1), (side * mouth_w * 0.6, front, -r * 0.34), parent=head)
    if mood in ("sad", "worried", "angry"):
        for side in (-1, 1):
            shape("box", "#5a1f1f", (r * 0.1, r * 0.1, r * 0.1), (side * mouth_w * 0.6, front, -r * 0.5), parent=head)
    return parts


def build_head(parent, look: dict[str, Any], r: float, mood: str, z: float = 0.0):
    neck = joint("neck", (0, 0, z), parent)
    head = shape("head", look["skin"], (r * 2, r * 2, r * 2.05), (0, 0, r * 0.9), parent=neck)
    # children of `head` live in its scaled space, so use unit sizes
    unit = 0.5
    style = look.get("hair_style")
    if style == "spikes":
        for x, y, tilt in ((-0.28, 0.0, 28), (0.0, -0.12, -6), (0.28, 0.0, -28), (-0.12, 0.25, 12), (0.14, 0.22, -14)):
            shape("tube", look["hair"], (0.42, 0.42, 0.6), (x, y, unit * 0.95), rot=(-18, tilt, 0),
                  parent=head, sides=4, top=0.0)
    elif style == "flat":
        shape("box", look["hair"], (0.92, 0.9, 0.3), (0, 0.06, unit * 0.82), parent=head)
    elif style == "bun":
        shape("box", look["hair"], (0.96, 0.9, 0.34), (0, 0.08, unit * 0.8), parent=head)
        shape("ball", look["hair"], (0.45, 0.45, 0.45), (0, 0.2, unit * 1.35), parent=head)
    face = build_face(head, look, unit, mood)
    if look.get("beard"):
        shape("tube", look["beard"], (0.8, 0.5, 0.7), (0, -0.3, -unit * 0.95), rot=(180, 0, 0),
              parent=head, sides=5, top=0.0)
    if look.get("glasses"):
        for side in (-1, 1):
            shape("ring", "#2b2b33", (0.4, 0.4, 0.4), (side * 0.18, -unit * 0.99, 0.06), rot=(90, 0, 0), parent=head)
    return neck, head, face


class Character:
    """A segmented low-poly figure: body parts hang from joints we can turn."""

    def __init__(self, kind: str, pos=(0.0, 0.0), face: float = 0.0, mood: str | None = None,
                 carry: str | None = None):
        look = LOOKS[kind]
        self.kind, self.look = kind, look
        s = look["scale"]
        self.s = s
        w = look["wide"]
        leg, torso_h, arm = 0.6 * s, 0.52 * s, 0.5 * s
        r_head = 0.25 * s * look.get("head", 1.0) * (1.0 if kind != "youth" else 1.05)
        self.leg = leg
        self.pos = Vector((pos[0], pos[1], pos[2] if len(pos) > 2 else 0.0))
        self.face_angle = face
        self.root = joint(f"{kind}_root", self.pos)
        self.body = joint("body", (0, 0, leg), self.root)

        if look.get("coat"):   # long cardigan that widens downwards
            shape("tube", look["top"], (0.52 * s * w, 0.42 * s * w, torso_h + 0.3 * s), (0, 0, torso_h / 2 - 0.15 * s),
                  parent=self.body, sides=7, top=0.62)
            shape("box", look["shirt"], (0.14 * s, 0.05, torso_h * 0.8), (0, -0.17 * s * w, torso_h * 0.5), parent=self.body)
        else:
            shape("tube", look["top"], (0.4 * s * w, 0.3 * s * w, torso_h), (0, 0, torso_h / 2),
                  parent=self.body, sides=6, top=1.2)
        if look.get("tie"):
            shape("box", look["tie"], (0.07 * s, 0.04, torso_h * 0.6), (0, -0.17 * s * w, torso_h * 0.6), parent=self.body)
        if look.get("pack") and carry != "big_backpack":
            shape("box", look["pack"], (0.3 * s, 0.16 * s, 0.34 * s), (0, 0.2 * s, torso_h * 0.6), parent=self.body)
        if carry == "big_backpack":
            big_backpack(self.body, (0, 0.42 * s, torso_h * 0.75), 1.0 * s)

        self.neck, self.head, self.face = build_head(self.body, look, r_head, mood or look["mood"], torso_h)

        self.arms, self.hands = [], []
        for side in (-1, 1):
            shoulder = joint("shoulder", (side * (0.24 * s * w + 0.03), 0, torso_h * 0.92), self.body)
            shape("tube", look["top"], (0.15 * s, 0.15 * s, arm), (0, 0, -arm / 2), parent=shoulder, sides=5, top=1.15)
            if look.get("stripe"):
                shape("tube", look["stripe"], (0.165 * s, 0.165 * s, 0.05 * s), (0, 0, -arm * 0.3), parent=shoulder, sides=5)
            hand = shape("ball", look["skin"], (0.16 * s, 0.16 * s, 0.16 * s), (0, 0, -arm - 0.03 * s), parent=shoulder)
            self.arms.append(shoulder)
            self.hands.append(hand)
        self.arm_l, self.arm_r = self.arms       # screen left, screen right when facing us
        self.arm_len = arm

        self.legs = []
        for side in (-1, 1):
            hip = joint("hip", (side * 0.11 * s * w, 0, leg), self.root)
            shape("tube", look["shorts"], (0.17 * s, 0.17 * s, leg * 0.5), (0, 0, -leg * 0.25), parent=hip, sides=5)
            shape("tube", look["legs"], (0.13 * s, 0.13 * s, leg * 0.5), (0, 0, -leg * 0.72), parent=hip, sides=5)
            shape("box", look["shoes"], (0.2 * s, 0.34 * s, 0.14 * s), (0, -0.07 * s, -leg + 0.07 * s), parent=hip)
            shape("box", look["shoe_tip"], (0.2 * s, 0.1 * s, 0.1 * s), (0, -0.25 * s, -leg + 0.05 * s), parent=hip)
            self.legs.append(hip)

        if look.get("cane"):
            shape("tube", "#7a4a21", (0.04, 0.04, leg + torso_h * 0.75), (0.02, -0.04, -arm - 0.02 + (leg + torso_h * 0.75) / 2 - (leg + torso_h * 0.75) + 0.12),
                  parent=self.arm_r, sides=5)
        self.rest()

    # pose helpers -----------------------------------------------------------
    def rest(self) -> None:
        self.root.location = self.pos
        deg(self.root, z=self.face_angle)
        self.body.location = (0, 0, self.leg)
        for part in (self.body, self.neck, *self.arms, *self.legs):
            deg(part)
        deg(self.arm_l, y=7)
        deg(self.arm_r, y=-7)

    def breathe(self, t: float, amount: float = 1.0) -> None:
        self.body.location.z = self.leg + 0.012 * self.s * amount * sin(t * 2.6)

    def arm(self, side: int, forward: float = 0.0, out: float = 7.0) -> None:
        """Lift an arm: `forward` degrees to the front, `out` degrees sideways."""
        sign = 1 if side == 0 else -1
        deg(self.arms[side], x=-forward, y=sign * out)


def big_backpack(parent, loc, size: float):
    pack = joint("big_backpack", loc, parent)
    shape("box", "#2f9e44", (0.8 * size, 0.6 * size, 1.0 * size), (0, 0, 0), parent=pack)
    shape("box", "#237a34", (0.6 * size, 0.2 * size, 0.4 * size), (0, 0.36 * size, -0.15 * size), parent=pack)
    shape("box", "#8a5a2b", (0.9 * size, 0.5 * size, 0.28 * size), (0, 0, 0.62 * size), rot=(0, 6, 0), parent=pack)
    shape("ball", "#c9483b", (0.4 * size, 0.4 * size, 0.4 * size), (-0.2 * size, 0.05, 0.9 * size), parent=pack)
    shape("box", "#3b6fc9", (0.3 * size, 0.3 * size, 0.3 * size), (0.22 * size, 0, 0.9 * size), rot=(0, 20, 30), parent=pack)
    return pack


# --- movements ------------------------------------------------------------
# Each movement poses a character for time t (seconds) of a scene T seconds long.

def act_idle(c: Character, t, T, p):
    c.breathe(t)
    deg(c.neck, z=6 * sin(t * 0.9), x=2 * sin(t * 1.3))
    c.arm(0, 3 * sin(t * 1.4)); c.arm(1, -3 * sin(t * 1.4))


def _walk_pose(c: Character, t, speed=1.0, swing=32.0, lean=0.0):
    phase = t * 6.0 * speed
    deg(c.legs[0], x=swing * sin(phase)); deg(c.legs[1], x=-swing * sin(phase))
    c.arm(0, swing * 0.8 * sin(phase)); c.arm(1, -swing * 0.8 * sin(phase))
    c.body.location.z = c.leg + 0.03 * c.s * abs(sin(phase))
    deg(c.body, x=-lean)


def _move(c: Character, t, T, p):
    to = p.get("to")
    if not to:
        return
    k = t / max(T, 0.01)
    c.root.location = c.pos.lerp(Vector((to[0], to[1], c.pos.z)), k)


def act_walk(c, t, T, p):
    _walk_pose(c, t, p.get("speed", 1.0))
    _move(c, t, T, p)
    deg(c.neck, x=-4)


def act_trudge(c, t, T, p):     # walking bent under a heavy load
    _walk_pose(c, t, 0.55, swing=20, lean=28)
    _move(c, t, T, p)
    deg(c.neck, x=14)


def act_slump(c, t, T, p):      # sitting/standing collapse, head sinking
    k = ease(t / max(T * 0.8, 0.1))
    deg(c.body, x=-(12 + 26 * k))
    deg(c.neck, x=-(10 + 30 * k), z=4 * sin(t * 1.1))
    c.arm(0, 35 + 10 * k, 18); c.arm(1, 35 + 10 * k, 18)
    c.body.location.z = c.leg - 0.02 * k


def act_stop(c, t, T, p):       # raise an open hand: stop
    k = ease(t / 0.8)
    c.breathe(t)
    c.arm(0, 35 * k, 7 + (118 + 4 * sin(t * 3)) * k)
    c.arm(1, 4, 7)
    deg(c.neck, x=-8 * ease((t - 1.6) / 0.4) * (1 - ease((t - 2.2) / 0.4)))


def act_point(c, t, T, p):      # point with the right arm (cane hand for the philosopher)
    k = ease(t / 0.7)
    sweep = p.get("sweep", 0.0) * sin(t * 1.5)
    c.breathe(t)
    c.arm(1, p.get("lift", 80) * k, 8 + sweep)
    c.arm(0, 3 * sin(t * 1.4))
    deg(c.neck, z=sweep * 0.6)


def act_point_viewer(c, t, T, p):
    k = ease(t / 0.9)
    c.breathe(t)
    deg(c.body, x=-10 * k)
    c.arm(0, 78 * k + 2 * sin(t * 4), 7 + 14 * k)
    deg(c.neck, x=4 * k, z=5 * sin(t * 1.2))
    for side, brow in zip((-1, 1), c.face["brows"]):
        brow.location.z = 0.23 + (0.06 * ease((t - 1.0) / 0.4) if side == 1 else 0)


def act_look_around(c, t, T, p):
    c.breathe(t)
    deg(c.neck, z=38 * sin(t * 1.6))
    c.arm(0, 3 * sin(t)); c.arm(1, -3 * sin(t))


def act_give(c, t, T, p):       # hand something over with one arm, hug with the other
    k = ease((t - 0.3) / 1.0)
    c.breathe(t)
    c.arm(p.get("side", 1), 70 * k, 20 * k)
    c.arm(1 - p.get("side", 1), 55, -18)
    deg(c.neck, z=(12 if p.get("side", 1) else -12) * k)


def act_reach(c, t, T, p):
    k = ease((t - 0.2) / 1.0)
    c.breathe(t)
    c.arm(0, 70 * k, 10); c.arm(1, 70 * k, 10)


def act_paint(c, t, T, p):
    c.breathe(t, 2)
    c.arm(1, 78 + 22 * sin(t * 4.2), 6 + 14 * sin(t * 2.1))
    c.arm(0, 10, 12)
    deg(c.neck, z=8 * sin(t * 2.1), x=-4)
    deg(c.body, z=5 * sin(t * 2.1))


def act_arms_crossed(c, t, T, p):
    c.breathe(t)
    c.arm(0, 62, -42); c.arm(1, 62, -42)
    deg(c.neck, z=16 * sin(t * 3.2) * ease((t - 1.0) / 0.5))
    deg(c.legs[1], x=10 * max(sin(t * 7), 0))


def act_whisper(c, t, T, p):    # lean to a neighbour and point at someone
    c.breathe(t)
    lean = p.get("lean", 1)
    deg(c.body, y=8 * lean + 3 * sin(t * 2 + lean))
    deg(c.neck, z=20 * lean + 8 * sin(t * 3 + lean))
    c.arm(1 if lean > 0 else 0, 70 + 6 * sin(t * 5 + lean), 10)


def act_arms_up(c, t, T, p):    # relief: arms wide open to the sky
    k = ease((t - 0.2) / 1.2)
    c.arm(0, 20 * k, 7 + 128 * k); c.arm(1, 20 * k, 7 + 128 * k)
    deg(c.neck, x=14 * k)
    deg(c.body, x=6 * k)
    c.body.location.z = c.leg + 0.02 * c.s * sin(t * 2.2) * k


def act_nod(c, t, T, p):
    c.breathe(t)
    deg(c.neck, x=-12 * max(sin(t * 3.0), 0))
    c.arm(0, 3 * sin(t)); c.arm(1, 4)


def act_talk(c, t, T, p):       # explaining with both hands
    c.breathe(t)
    c.arm(0, 38 + 16 * sin(t * 4.1), 16 + 8 * sin(t * 2.3))
    c.arm(1, 34 + 16 * sin(t * 4.1 + 2.0), 16 + 8 * sin(t * 2.9))
    deg(c.body, z=4 * sin(t * 1.7), x=3)


def act_shrug(c, t, T, p):      # "how should I know": shoulders and palms up, twice
    c.breathe(t)
    k = max(sin(t * 3.0), 0) ** 0.5
    c.arm(0, 30 * k, 7 + 40 * k); c.arm(1, 30 * k, 7 + 40 * k)
    c.body.location.z = c.leg + 0.035 * c.s * k
    deg(c.neck, y=10 * k)


def act_shake_head(c, t, T, p):
    c.breathe(t)
    deg(c.neck, z=24 * sin(t * 6.0) * (1 - 0.5 * ease(t / max(T, 0.1))))
    c.arm(0, 4); c.arm(1, 4)


def act_facepalm(c, t, T, p):   # hand to the forehead, head sinks
    k = ease((t - 0.15) / 0.45)
    c.breathe(t, 1 - k * 0.5)
    c.arm(1, 150 * k, -24 * k)
    deg(c.neck, x=-16 * k, z=5 * sin(t * 2.5) * k)
    deg(c.body, x=-5 * k)


def act_startle(c, t, T, p):    # jumps back in surprise, then stares
    k = ease(t / 0.18) - ease((t - 0.25) / 0.35)
    c.body.location.z = c.leg + 0.16 * c.s * k
    hold = ease(t / 0.2)
    c.arm(0, 25 * hold, 7 + 55 * hold); c.arm(1, 25 * hold, 7 + 55 * hold)
    deg(c.body, x=9 * hold)
    deg(c.neck, x=6 * hold)


def act_laugh(c, t, T, p):
    bounce = abs(sin(t * 9.0))
    c.body.location.z = c.leg + 0.03 * c.s * bounce
    deg(c.body, x=7 + 3 * bounce)
    deg(c.neck, x=12 + 6 * bounce)
    c.arm(0, 50, -30); c.arm(1, 50, -30)


def speak(c: Character, t: float) -> None:
    """Layer on top of any action: flapping mouth and a lively head."""
    mouth = c.face["mouth"]
    base = c.__dict__.setdefault("mouth_base", tuple(mouth.scale))
    syllable = abs(sin(t * 10.5)) * (0.55 + 0.45 * abs(sin(t * 2.7)))
    mouth.scale = (base[0] * (1 - 0.25 * syllable), base[1], base[2] * (1 + 3.2 * syllable))
    c.neck.rotation_euler.x += math.radians(3.5 * sin(t * 5.2))
    c.neck.rotation_euler.y += math.radians(2.5 * sin(t * 3.1))


ACTIONS: dict[str, Callable] = {
    "talk": act_talk, "shrug": act_shrug, "shake_head": act_shake_head,
    "facepalm": act_facepalm, "startle": act_startle, "laugh": act_laugh,
    "idle": act_idle, "walk": act_walk, "trudge": act_trudge, "slump": act_slump,
    "stop": act_stop, "point": act_point, "point_viewer": act_point_viewer,
    "look_around": act_look_around, "give": act_give, "reach": act_reach, "paint": act_paint,
    "arms_crossed": act_arms_crossed, "whisper": act_whisper, "arms_up": act_arms_up, "nod": act_nod,
}


# --- props ----------------------------------------------------------------
# A prop builder returns an optional updater that animates it.

def prop_desk(p) -> Updater | None:
    x, y = p.get("pos", (0, 0))
    shape("box", "#9a6a3a", (1.3, 0.6, 0.07), (x, y, 0.62))
    for dx in (-0.58, 0.58):
        for dy in (-0.24, 0.24):
            shape("box", "#7a4f26", (0.07, 0.07, 0.6), (x + dx, y + dy, 0.3))
    return None


def prop_paper_tower(p) -> Updater:
    x, y = p.get("pos", (0, 0))
    base = p.get("z", 0.0)
    n = p.get("height", 9)
    seed = p.get("seed", 0)
    sheets = []
    for i in range(n):
        color = ("#f4f1e8", "#e6e0cf", "#c94f4f", "#f4f1e8", "#4f79c9", "#ead9a0")[(i + seed) % 6]
        thick = 0.11 if i % 3 else 0.16
        sheet = shape("box", color, (0.42, 0.32, thick), (x, y, base + 0.07 + i * 0.125), rot=(0, 0, (i * 37 + seed * 20) % 30 - 15))
        sheets.append(sheet)

    def update(t, T):
        for i, sheet in enumerate(sheets):
            sway = 0.012 * i * sin(t * 2.2 + seed) * (1 + 0.3 * sin(t * 5.1 + i))
            sheet.location.x = x + sway
            sheet.rotation_euler.y = math.radians(1.2 * i * sin(t * 2.2 + seed))
    return update


def prop_falling_paper(p) -> Updater:
    x, y = p.get("pos", (0, 0))
    sheets = [shape("box", "#f4f1e8", (0.3, 0.22, 0.012), (x, y, 2)) for _ in range(p.get("count", 4))]

    def update(t, T):
        for i, sheet in enumerate(sheets):
            cycle = ((t * 0.5 + i * 0.27) % 1.0)
            sheet.location = (x + 0.5 * sin(i * 2.4) + 0.2 * sin(t * 3 + i), y - 0.2 * i, p.get("top", 2.3) * (1 - cycle))
            sheet.rotation_euler = (t * 2 + i, 0.6 * sin(t * 3 + i), t + i)
    return update


def prop_lamp(p) -> Updater | None:
    x, y = p.get("pos", (0, 0))
    z = p.get("z", 0.66)
    shape("tube", "#3b3f4a", (0.16, 0.16, 0.04), (x, y, z + 0.02), sides=6)
    shape("tube", "#3b3f4a", (0.03, 0.03, 0.4), (x, y, z + 0.22), sides=4)
    shape("tube", "#ffd866", (0.3, 0.3, 0.2), (x, y, z + 0.48), sides=6, top=0.45, glow=2.2)
    light = bpy.data.objects.new("lamp", bpy.data.lights.new("lamp", "POINT"))
    bpy.context.scene.collection.objects.link(light)
    light.location = (x, y - 0.2, z + 0.5)
    light.data.energy = 90
    light.data.color = rgb("#ffcf70")
    light.data.shadow_soft_size = 0
    return None


def prop_floating_head(p) -> Updater:
    look = HEADS[p.get("who", "mom")]
    x, y, z = p.get("pos", (0, 0, 2.4))
    size = p.get("size", 0.42)
    anchor = joint("float", (x, y, z))
    neck, head, face = build_head(anchor, look, size, look["mood"])
    if look.get("tie"):
        shape("box", look["tie"], (size * 0.3, size * 0.15, size * 0.7), (0, -size * 0.2, -size * 0.55), parent=anchor)
    phase = p.get("phase", x * 2.0)

    def update(t, T):
        anchor.location = (x + (p.get("follow", 0.0) * t), y, z + 0.09 * sin(t * 2.4 + phase))
        deg(neck, x=14, z=14 * sin(t * 3.4 + phase))
    return update


def prop_bookshelf(p) -> Updater | None:
    x, y = p.get("pos", (0, 0))
    w, h = p.get("w", 1.5), p.get("h", 2.6)
    shape("box", "#5a3a1f", (w, 0.35, h), (x, y, h / 2))
    colors = ("#b23a48", "#2a6f97", "#e9c46a", "#588157", "#7b2cbf", "#e76f51", "#f1faee")
    rows = int(h / 0.52)
    for row in range(rows):
        cols = int(w / 0.14) - 1
        for col in range(cols):
            tall = 0.3 + 0.1 * ((row * 5 + col * 3) % 3)
            shape("box", colors[(row * 3 + col * 2 + col // 3) % len(colors)], (0.1, 0.2, tall),
                  (x - w / 2 + 0.14 + col * 0.14, y - 0.12, 0.14 + row * 0.52 + tall / 2))
    return None


def prop_fireplace(p) -> Updater:
    x, y = p.get("pos", (0, 0))
    shape("box", "#8d5b4c", (1.5, 0.4, 1.3), (x, y, 0.65))
    shape("box", "#1c1410", (0.9, 0.1, 0.75), (x, y - 0.2, 0.42))
    shape("box", "#6e463a", (1.7, 0.5, 0.1), (x, y, 1.35))
    flames = [shape("tube", color, (0.24, 0.12, 0.5), (x + dx, y - 0.24, 0.3), sides=4, top=0.0, glow=3.0)
              for dx, color in ((-0.22, "#ff7b1c"), (0.0, "#ffd23f"), (0.22, "#ff7b1c"))]
    light = bpy.data.objects.new("fire", bpy.data.lights.new("fire", "POINT"))
    bpy.context.scene.collection.objects.link(light)
    light.location = (x, y - 0.9, 0.6)
    light.data.color = rgb("#ff9a3c")
    light.data.shadow_soft_size = 0

    def update(t, T):
        for i, flame in enumerate(flames):
            flame.scale.z = 0.42 + 0.16 * sin(t * 9 + i * 2.1) + 0.06 * sin(t * 23 + i)
            flame.location.z = 0.1 + flame.scale.z / 2
        light.data.energy = 130 + 40 * sin(t * 9)
    return update


def prop_door(p) -> Updater:
    x, y = p.get("pos", (0, 0))
    color = p.get("color", "#59c3ff")
    shape("box", "#6b4a2f", (0.95, 0.14, 1.9), (x, y, 0.95))
    panel = shape("box", color, (0.75, 0.06, 1.65), (x, y - 0.08, 0.9), glow=1.5)
    shape("ball", "#ffd23f", (0.09, 0.09, 0.09), (x + 0.27, y - 0.14, 0.9), glow=2)
    emission = panel.data.materials[0].node_tree.nodes["Emission"]
    panel.data.materials[0] = panel.data.materials[0].copy()
    emission = panel.data.materials[0].node_tree.nodes["Emission"]
    phase = p.get("phase", 0.0)

    def update(t, T):
        emission.inputs["Strength"].default_value = 1.4 + 0.9 * sin(t * 3 + phase)
    return update


def prop_path(p) -> Updater | None:
    """Flat strip on the ground between two points."""
    (x0, y0), (x1, y1) = p["from"], p["to"]
    length = math.hypot(x1 - x0, y1 - y0)
    angle = math.degrees(math.atan2(y1 - y0, x1 - x0))
    shape("box", p.get("color", "#e8d8a8"), (length, p.get("w", 0.8), 0.04), ((x0 + x1) / 2, (y0 + y1) / 2, 0.02),
          rot=(0, 0, angle), checker=p.get("checker", "#d1bd84"), tiles=p.get("tiles", 1.25))
    return None


def prop_cube(p) -> Updater:
    x, y, z = p.get("pos", (0, 0, 1))
    size = p.get("size", 0.28)
    cube = shape("box", p.get("color", "#3fa9ff"), (size, size, size), (x, y, z), glow=1.6)
    to = p.get("to")
    start, span = p.get("start", 0.4), p.get("span", 1.2)

    def update(t, T):
        k = ease((t - start) / span) if to else 0
        here = Vector((x, y, z)).lerp(Vector(to), k) if to else Vector((x, y, z))
        cube.location = here + Vector((0, 0, 0.03 * sin(t * 3 + x)))
        cube.rotation_euler = (0.3, 0.2, t * 1.6 + x)
    return update


def prop_easel(p) -> Updater:
    x, y = p.get("pos", (0, 0))
    for dx in (-0.3, 0.3):
        shape("box", "#7a4f26", (0.06, 0.06, 1.7), (x + dx, y, 0.85), rot=(0, -dx * 20, 0))
    shape("box", "#f4f1e8", (0.95, 0.06, 1.1), (x, y - 0.06, 1.2))
    dabs = []
    spots = (("#e63946", -0.25, 1.5), ("#ffd23f", 0.1, 1.35), ("#2a9d8f", 0.25, 1.0), ("#457b9d", -0.15, 0.95),
             ("#f4a261", 0.0, 1.15), ("#9b5de5", -0.3, 1.2), ("#e63946", 0.28, 1.5))
    for color, dx, z in spots:
        dabs.append(shape("box", color, (0.24, 0.02, 0.22), (x + dx, y - 0.1, z)))

    def update(t, T):
        for i, dab in enumerate(dabs):   # the painting fills in while he paints
            show = ease((t - i * T / (len(dabs) + 2)) / 0.3)
            dab.scale = (0.24 * show, 0.02, 0.22 * show)
    return update


def prop_briefcase(p) -> Updater | None:
    x, y = p.get("pos", (0, 0))
    shape("box", "#4a3426", (0.5, 0.16, 0.36), (x, y, 0.18))
    shape("box", "#2c1f17", (0.2, 0.05, 0.06), (x, y, 0.4))
    return None


def prop_big_backpack(p) -> Updater | None:
    x, y, *rest = p.get("pos", (0, 0))
    pack = big_backpack(None, (x, y, (rest[0] if rest else 0.0) + 0.5 * p.get("size", 1.0)), p.get("size", 1.0))
    deg(pack, y=p.get("tilt", 8), z=p.get("turn", 20))
    return None


def prop_tree(p) -> Updater | None:
    x, y = p.get("pos", (0, 0))
    s = p.get("size", 1.0)
    shape("tube", "#7a4f26", (0.25 * s, 0.25 * s, 0.9 * s), (x, y, 0.45 * s), sides=5)
    shape("tube", "#2f9e44", (1.3 * s, 1.3 * s, 1.3 * s), (x, y, 1.4 * s), sides=6, top=0.0)
    shape("tube", "#37b24d", (1.0 * s, 1.0 * s, 1.1 * s), (x, y, 2.1 * s), sides=6, top=0.0)
    return None


def prop_house(p) -> Updater | None:
    x, y = p.get("pos", (0, 0))
    color = p.get("color", "#f2e3c6")
    w, h = p.get("w", 2.4), p.get("h", 2.6)
    shape("box", color, (w, 2.0, h), (x, y, h / 2))
    shape("tube", p.get("roof", "#c1440e"), (w * 1.5, 2.9, 1.2), (x, y, h + 0.6), rot=(0, 0, 45), sides=4, top=0.0)
    shape("box", "#6b4a2f", (0.6, 0.06, 1.2), (x - w * 0.2, y - 1.01, 0.6))
    shape("box", "#8ecae6", (0.6, 0.06, 0.6), (x + w * 0.22, y - 1.01, h * 0.62), glow=0.8)
    return None


def prop_cloud(p) -> Updater:
    x, y, z = p.get("pos", (0, 12, 6))
    s = p.get("size", 1.0)
    color = p.get("color", "#ffffff")
    anchor = joint("cloud", (x, y, z))
    for dx, dz, k in ((0, 0, 1.0), (-0.9, -0.1, 0.7), (0.9, -0.12, 0.75), (0.35, 0.3, 0.6)):
        shape("ball", color, (1.6 * s * k, 0.8 * s * k, 0.9 * s * k), (dx * s, 0, dz * s), parent=anchor, glow=0.95)

    def update(t, T):
        anchor.location.x = x + p.get("drift", 0.12) * t
    return update


def prop_sun(p) -> Updater | None:
    x, y, z = p.get("pos", (0, 30, 3))
    shape("head", p.get("color", "#ffe08a"), (p.get("size", 5),) * 3, (x, y, z), glow=1.25)
    return None


def prop_hill(p) -> Updater | None:
    x, y = p.get("pos", (0, 0))
    w, h = p.get("w", 9.0), p.get("h", 1.6)
    hill = shape("ball", p.get("color", "#52b043"), (w, w, h * 2), (x, y, 0), checker=p.get("checker"), tiles=p.get("tiles", 3))
    del hill
    return None


def prop_island(p) -> Updater | None:
    """Floating island: checkered top, rocky cone underneath."""
    x, y = p.get("pos", (0, 0))
    r = p.get("r", 4.0)
    shape("tube", "#52b043", (r * 2, r * 2, 0.3), (x, y, -0.15), sides=10, checker="#3f9a35", tiles=0.5)
    shape("tube", "#8a6a48", (r * 2, r * 2, r * 1.3), (x, y, -0.3 - r * 0.65), rot=(180, 0, 0), sides=10, top=0.12)
    return None


def prop_bed(p) -> Updater | None:
    x, y = p.get("pos", (0, 0))
    shape("box", "#6b4a2f", (1.1, 2.0, 0.3), (x, y, 0.2))
    shape("box", "#3a6ea5", (1.05, 1.5, 0.16), (x, y - 0.2, 0.42))
    shape("box", "#f4f1e8", (0.8, 0.4, 0.14), (x, y + 0.72, 0.44))
    return None


def prop_window(p) -> Updater | None:
    x, y, z = p.get("pos", (0, 0, 1.8))
    shape("box", "#6b4a2f", (1.1, 0.08, 1.1), (x, y, z))
    shape("box", p.get("color", "#1b2a55"), (0.95, 0.1, 0.95), (x, y - 0.02, z), glow=0.7)
    shape("ball", "#fff7c2", (0.28, 0.05, 0.28), (x + 0.2, y - 0.08, z + 0.2), glow=3)
    shape("box", "#6b4a2f", (0.05, 0.12, 0.95), (x, y - 0.03, z))
    shape("box", "#6b4a2f", (0.95, 0.12, 0.05), (x, y - 0.03, z))
    return None


def prop_rug(p) -> Updater | None:
    x, y = p.get("pos", (0, 0))
    shape("tube", p.get("color", "#b23a48"), (p.get("w", 2.6), p.get("d", 1.8), 0.03), (x, y, 0.015), sides=8)
    return None


def prop_chair(p) -> Updater | None:
    x, y = p.get("pos", (0, 0))
    color = p.get("color", "#2f6f4f")
    shape("box", color, (0.9, 0.8, 0.45), (x, y, 0.3))
    shape("box", color, (0.9, 0.2, 1.1), (x, y + 0.35, 0.75))
    for dx in (-0.45, 0.45):
        shape("box", color, (0.16, 0.8, 0.7), (x + dx, y, 0.4))
    return None


PROPS: dict[str, Callable] = {
    "desk": prop_desk, "paper_tower": prop_paper_tower, "falling_paper": prop_falling_paper,
    "lamp": prop_lamp, "floating_head": prop_floating_head, "bookshelf": prop_bookshelf,
    "fireplace": prop_fireplace, "door": prop_door, "path": prop_path, "cube": prop_cube,
    "easel": prop_easel, "briefcase": prop_briefcase, "big_backpack": prop_big_backpack,
    "tree": prop_tree, "house": prop_house, "cloud": prop_cloud, "sun": prop_sun, "hill": prop_hill,
    "island": prop_island, "bed": prop_bed, "window": prop_window, "rug": prop_rug, "chair": prop_chair,
}


# --- sets -----------------------------------------------------------------

def sky(top: str, sun_angle=(50, 0, 30), sun_color="#ffffff", sun_power=2.6) -> None:
    world = bpy.data.worlds.new("world")
    bpy.context.scene.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (*rgb(top), 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 1.0
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    bpy.context.scene.collection.objects.link(sun)
    deg(sun, *sun_angle)
    sun.data.energy = sun_power
    sun.data.color = rgb(sun_color)
    sun.data.angle = 0


def ground(color: str, checker: str | None = None, tiles: float = 0.5, size: float = 80) -> None:
    shape("plane", color, (size, size, 1), (0, 0, 0), checker=checker, tiles=tiles)


def room(floor: str, floor2: str, wall: str, width=7.0, depth=4.5, height=7.0) -> None:
    shape("plane", floor, (width, depth + 6, 1), (0, depth / 2 - 3, 0), checker=floor2, tiles=1.0)
    shape("box", wall, (width, 0.2, height), (0, depth, height / 2))
    for side in (-1, 1):
        shape("box", wall, (0.2, depth + 6, height), (side * width / 2, depth / 2 - 3, height / 2))
    shape("box", "#4a3426", (width, 0.26, 0.18), (0, depth - 0.02, 0.09))


def set_bedroom_night(p):
    sky("#0b1026", (55, 0, 20), "#8fa8ff", 0.5)
    room("#7a5a3a", "#6b4e31", "#3d4a7a")
    PROPS["window"]({"pos": (-1.6, 4.38, 2.1)})
    PROPS["bed"]({"pos": (2.4, 3.2)})


def set_study(p):
    sky("#1a1210", (60, 0, -25), "#ffd9a0", 1.3)
    room("#8a5a35", "#74492a", "#7b3f2e")
    PROPS["bookshelf"]({"pos": (-2.3, 4.2), "w": 1.9, "h": 3.0})
    PROPS["bookshelf"]({"pos": (2.5, 4.2), "w": 1.5, "h": 3.0})
    PROPS["rug"]({"pos": (0, 1.2)})


def set_workshop(p):
    sky("#bfe6ff", (55, 0, 25), "#fff4d6", 2.2)
    room("#d8c7a3", "#c7b48c", "#f3e9d2")
    PROPS["window"]({"pos": (-2.0, 4.38, 2.2), "color": "#8fd3ff"})
    PROPS["window"]({"pos": (2.0, 4.38, 2.2), "color": "#8fd3ff"})


def set_town(p):
    sky("#6ec6ff", (52, 0, 35), "#fff6dd", 2.6)
    ground("#d9d2c0", "#c2b9a3")
    for x, color, roof in ((-4.2, "#f2e3c6", "#c1440e"), (-0.6, "#f7c8a0", "#3a6ea5"), (3.4, "#e9edc9", "#c1440e"),
                           (7.4, "#f2e3c6", "#7b2cbf"), (-8.0, "#f7c8a0", "#3a6ea5")):
        PROPS["house"]({"pos": (x, 7.5), "color": color, "roof": roof})
    PROPS["tree"]({"pos": (-2.4, 5.6)}); PROPS["tree"]({"pos": (5.4, 5.8), "size": 0.9})


def set_field(p):
    sky("#6ec6ff", (50, 0, 30), "#fff6dd", 2.6)
    ground("#58b947", "#4aa63b")
    PROPS["hill"]({"pos": (-7, 16), "w": 16, "h": 2.6, "color": "#4aa63b"})
    PROPS["hill"]({"pos": (8, 20), "w": 20, "h": 3.4, "color": "#3f9a35"})
    PROPS["tree"]({"pos": (-3.6, 6.5), "size": 1.2}); PROPS["tree"]({"pos": (3.9, 8.0)})


def set_island(p):
    sky("#4fb4ff", (48, 0, 30), "#fff6dd", 2.7)
    PROPS["island"]({"pos": (0, 2.5), "r": 4.6})
    PROPS["island"]({"pos": (-9, 16), "r": 2.2}); PROPS["island"]({"pos": (8, 20), "r": 2.8})


def set_hill_sunrise(p):
    sky("#ff9e6d", (78, 0, 180), "#ffb36b", 2.4)
    ground("#3f8f4f", None)
    PROPS["hill"]({"pos": (0, 1.2), "w": 11, "h": 1.0, "color": "#5cb85c", "checker": "#4fa851", "tiles": 0.5})
    PROPS["sun"]({"pos": (0, 60, 5.5), "size": 16})
    PROPS["hill"]({"pos": (-14, 30), "w": 26, "h": 3.5, "color": "#2f6f4f"})
    PROPS["hill"]({"pos": (16, 34), "w": 30, "h": 4.2, "color": "#2a6247"})


SETS: dict[str, Callable] = {
    "bedroom_night": set_bedroom_night, "study": set_study, "workshop": set_workshop,
    "town": set_town, "field": set_field, "island": set_island, "hill_sunrise": set_hill_sunrise,
}


# --- camera ---------------------------------------------------------------

def make_camera(spec: dict[str, Any]) -> Updater:
    cam = bpy.data.objects.new("camera", bpy.data.cameras.new("camera"))
    bpy.context.scene.collection.objects.link(cam)
    bpy.context.scene.camera = cam
    cam.data.lens = spec.get("lens", 30)
    cam.data.sensor_fit = "VERTICAL"
    cam.data.sensor_height = 36
    target = Vector(spec.get("target", (0, 0, 1.0)))
    dist, height, angle = spec.get("dist", 6.0), spec.get("height", 1.5), spec.get("angle", 0.0)
    move = spec.get("move", "push_in")
    amount = spec.get("amount", 1.0)

    def update(t, T):
        k = t / max(T, 0.01)
        d, h, a, look = dist, height, angle, target.copy()
        if move == "push_in":
            d = dist * (1 - 0.16 * amount * k)
        elif move == "pull_back":
            d = dist * (0.8 + 0.3 * amount * k)
            h = height + 0.5 * amount * k
        elif move == "orbit":
            a = angle + 22 * amount * (k - 0.5)
        elif move == "rise":
            h = height + 1.3 * amount * k
        elif move == "track":
            shift = Vector(spec.get("track", (0, 0, 0))) * k
            look = target + shift
        rad = math.radians(a)
        cam.location = look + Vector((d * sin(rad), -d * cos(rad), h - look.z))
        if move == "track":
            cam.location = Vector((look.x + d * sin(rad), look.y - d * cos(rad), h))
        direction = look - cam.location
        cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    return update


# --- scene ----------------------------------------------------------------

def build_scene(stage: dict[str, Any]) -> list[Updater]:
    """Build one scene from its description and return its animation steps."""
    _materials.clear()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    updaters: list[Updater] = []

    SETS[stage.get("set", "field")](stage)
    for spec in stage.get("props", []):
        updater = PROPS[spec["type"]](spec)
        if updater:
            updaters.append(updater)
    for spec in stage.get("actors", []):
        char = Character(spec["who"], spec.get("pos", (0, 0)), spec.get("face", 0.0),
                         spec.get("mood"), spec.get("carry"))
        action = ACTIONS[spec.get("action", "idle")]

        def animate(t, T, char=char, action=action, spec=spec):
            char.rest()
            action(char, t + spec.get("offset", 0.0), T, spec)
            if spec.get("talking"):
                speak(char, t)
        updaters.append(animate)
    updaters.append(make_camera(stage.get("camera", {})))
    return updaters


def setup_render(width: int = RES[0], height: int = RES[1]) -> None:
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 12
    scene.cycles.use_adaptive_sampling = False
    scene.cycles.use_denoising = False
    scene.cycles.max_bounces = 0
    scene.cycles.pixel_filter_type = "BOX"
    scene.cycles.filter_width = 0.01     # no anti-aliasing: hard jagged edges
    scene.cycles.use_light_tree = False
    scene.render.resolution_x, scene.render.resolution_y = width, height
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.use_persistent_data = True
    scene.view_settings.view_transform = "Standard"
    scene.render.threads_mode = "AUTO"


def render_scene(stage: dict[str, Any], seconds: float, out_dir: str, fps: int = FPS,
                 only_frame: int | None = None) -> int:
    """Render a scene as numbered PNG frames. Returns the number of frames."""
    updaters = build_scene(stage)
    setup_render()
    frames = max(int(round(seconds * fps)), 1)
    todo = [only_frame] if only_frame is not None else range(frames)
    for frame in todo:
        t = frame / fps
        for update in updaters:
            update(t, seconds)
        bpy.context.scene.render.filepath = f"{out_dir}/f_{frame:04d}.png"
        bpy.ops.render.render(write_still=True)
    return frames
