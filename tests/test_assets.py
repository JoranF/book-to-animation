"""The asset library: reuse by name and tags, make what is missing, rebuild on request."""
import json

import pytest
from fastapi.testclient import TestClient

from b2a import assets, config, llm, script as script_mod, stage as stage_mod

PHONE = {"description": "a black smartphone with a glowing blue screen", "tags": ["phone", "mobile", "screen"],
         "recipe": {"parts": [
             {"shape": "box", "color": "#222222", "size": [0.4, 0.06, 0.8], "at": [0, 0, 0.4]},
             {"shape": "box", "color": "#3fa9ff", "size": [0.34, 0.02, 0.66], "at": [0, -0.04, 0.42], "glow": 1.5,
              "moves": True}], "motion": {"type": "pulse", "speed": 2, "amount": 0.05}}}
CLASSROOM = {"description": "a classroom with a green board", "tags": ["school", "class", "room"],
             "recipe": {"sky": "#bfe6ff", "room": {"floor": "#c7b48c", "floor2": "#b8a57c", "wall": "#e9edc9"},
                        "parts": [{"shape": "box", "color": "#2f6f4f", "size": [3, 0.1, 1.4], "at": [0, 4.35, 1.8]}],
                        "props": [{"type": "desk", "pos": [2.4, 3.4]}]}}
TEACHER = {"description": "a teacher in a purple cardigan", "tags": ["teacher", "school"],
           "recipe": {"scale": 1.0, "skin": "#e0ac85", "top": "#7b2cbf", "legs": "#3f444d", "shorts": "#3f444d",
                      "shoes": "#222222", "hair_style": "bun", "hair": "#4a4038", "glasses": True, "mood": "calm"}}


class FakeDesigner:
    def __init__(self, answers):
        self.answers, self.calls = answers, []

    def __call__(self, system, messages, max_tokens=16000, model=None, effort=None, step="script"):
        self.calls.append({"step": step, "model": model, "text": messages[-1]["content"]})
        llm.record(step, model, 500, 800)
        return json.dumps(self.answers.pop(0))


@pytest.fixture(autouse=True)
def _library(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setenv("ASSET_PREVIEWS", "0")


def test_builtin_kit_is_in_the_catalog_and_the_recurring_characters_are_locked():
    names = {(a["kind"], a["name"]) for a in assets.catalog()}
    assert ("character", "philosopher") in names and ("set", "study") in names and ("prop", "desk") in names
    assert assets.get("character", "youth")["locked"]
    with pytest.raises(ValueError):
        assets.mark_rebuild("character", "philosopher")
    with pytest.raises(ValueError):
        assets.create("character", "youth", "another youth")


def test_a_missing_prop_is_made_once_and_then_reused_by_name_alias_and_tags(monkeypatch):
    fake = FakeDesigner([PHONE])
    monkeypatch.setattr(llm, "ask", fake)
    asset, made = assets.ensure("prop", "smartphone", "a phone", ["phone"])
    assert made and asset["source"] == "generated" and asset["version"] == 1
    assert fake.calls[0]["step"] == "assets" and fake.calls[0]["model"] == config.ASSET_MODEL
    # found again without a new Claude call: same name, other spelling, or a name from its tags
    for name in ("smartphone", "Smart-Phone ", "phone"):
        again, made = assets.ensure("prop", name, "")
        assert not made and again["name"] == "smartphone"
    assert len(fake.calls) == 1
    assert "phone" in assets.load("prop", "smartphone")["aliases"]
    # but something that only shares a word is not the same thing
    assert assets.find("prop", "phone_booth", "a red phone booth on the street") is None
    assert "smartphone" in assets.known()["prop"]


def test_recipes_are_checked():
    with pytest.raises(ValueError, match="shape"):
        assets.check_recipe("prop", {"parts": [{"shape": "teapot", "color": "#ffffff", "size": [1, 1, 1]}]})
    with pytest.raises(ValueError, match="colour"):
        assets.check_recipe("prop", {"parts": [{"shape": "box", "color": "red", "size": [1, 1, 1]}]})
    with pytest.raises(ValueError, match="built-in props"):
        assets.check_recipe("set", {**CLASSROOM["recipe"], "props": [{"type": "smartphone"}]})
    look = assets.check_recipe("character", TEACHER["recipe"])
    assert look["shoe_tip"] == "#222222" and look["glasses"]


def test_marked_assets_are_rebuilt_the_next_time_a_short_uses_them(monkeypatch):
    fake = FakeDesigner([PHONE, {**PHONE, "description": "a bigger phone"}])
    monkeypatch.setattr(llm, "ask", fake)
    assets.ensure("prop", "smartphone", "a phone")
    assets.mark_rebuild("prop", "smartphone", "make it bigger")
    assert assets.get("prop", "smartphone")["rebuild"]
    stages = [{"set": "study", "props": [{"type": "smartphone", "pos": [0, 0]}], "actors": []}]
    recipes = assets.prepare(stages, "short-1")
    phone = assets.load("prop", "smartphone")
    assert phone["version"] == 2 and not phone["rebuild"] and phone["description"] == "a bigger phone"
    assert "make it bigger" in fake.calls[1]["text"] and len(phone["history"]) == 1
    assert recipes["smartphone"]["version"] == 2 and phone["used"] == 1 and phone["used_in"] == ["short-1"]
    assert assets.for_stage(stages[0], recipes) == {"smartphone": recipes["smartphone"]}
    # built-in assets need no recipe: Blender builds them from code
    assert "study" not in recipes


def test_a_builtin_prop_can_be_rebuilt_and_reset(monkeypatch):
    monkeypatch.setattr(llm, "ask", FakeDesigner([PHONE]))
    assets.mark_rebuild("prop", "chair", "an old wooden chair")
    assert assets.get("prop", "chair")["source"] == "builtin_pending"
    assets.prepare([{"set": "study", "props": [{"type": "chair"}], "actors": []}])
    assert assets.get("prop", "chair")["source"] == "generated"
    assets.reset("prop", "chair")
    assert assets.get("prop", "chair")["source"] == "builtin"


def test_the_stager_can_ask_for_new_assets_and_they_are_kept(monkeypatch):
    example = json.loads((config.BOOKS_DIR / "courage-to-be-disliked" / "examples" / "n3-03.json").read_text())
    script = {**example, "scenes": [{"speaker": "narrator", **{k: v for k, v in s.items() if k != "stage"}}
                                    for s in example["scenes"]]}
    stages = [json.loads(json.dumps(s["stage"])) for s in example["scenes"]]
    stages[0]["set"] = "classroom"
    stages[0]["props"] = [{"type": "Smart Phone", "pos": [0.4, 0.2], "z": 0.66}]
    stages[0]["actors"].append({"who": "teacher", "pos": [1.2, 0.8], "action": "talk"})
    new = [{"kind": "prop", "name": "Smart Phone", "description": "a phone"},
           {"kind": "set", "name": "classroom", "description": "a classroom"},
           {"kind": "character", "name": "teacher", "description": "a teacher"}]
    answers = [{"stages": stages, "new_assets": new}, PHONE, CLASSROOM, TEACHER]

    def fake(system, messages, max_tokens=16000, model=None, effort=None, step="script"):
        if step == "staging":
            assert "NEW ASSETS" in system and "LIBRARY" in system
        return json.dumps(answers.pop(0))
    monkeypatch.setattr(llm, "ask", fake)
    book = script_mod.load_book("courage-to-be-disliked")
    staged = script_mod.validate(script_mod.stage_scenes(script, book), book)
    first = staged["scenes"][0]["stage"]
    assert first["set"] == "classroom" and first["props"][0]["type"] == "smart_phone"
    assert {m["name"] for m in staged["assets_made"]} == {"smart_phone", "classroom", "teacher"}
    assert assets.known()["heights"]["teacher"] == 1.6
    # the next Short gets them in its library list and does not make them again
    assert '"smart_phone"' in assets.library_guide()
    assert script_mod.ensure_assets([{"kind": "prop", "name": "smart_phone"}], []) == {}


def test_new_assets_per_short_are_limited(monkeypatch):
    monkeypatch.setattr(config, "ASSET_MAX_NEW", 1)
    monkeypatch.setattr(llm, "ask", FakeDesigner([PHONE]))
    with pytest.raises(ValueError, match="at most 1"):
        script_mod.ensure_assets([{"kind": "prop", "name": "smartphone"}, {"kind": "prop", "name": "laptop"}], [])


def test_stage_validation_knows_the_library(monkeypatch):
    stage = {"set": "classroom", "props": [], "actors": [{"who": "youth", "pos": [0, 0]}]}
    with pytest.raises(ValueError, match="new_assets"):
        stage_mod.validate(json.loads(json.dumps(stage)))
    monkeypatch.setattr(llm, "ask", FakeDesigner([CLASSROOM]))
    assets.ensure("set", "classroom", "a classroom")
    assert stage_mod.validate(stage)["set"] == "classroom"


def test_asset_api(monkeypatch):
    from b2a import server
    monkeypatch.setenv("APP_PASSWORD", "pw")
    monkeypatch.setattr(llm, "ask", FakeDesigner([PHONE]))
    assets.ensure("prop", "smartphone", "a phone")
    client = TestClient(server.app)
    client.auth = ("u", "pw")
    listed = client.get("/api/assets").json()["assets"]
    assert any(a["name"] == "smartphone" and a["source"] == "generated" for a in listed)
    assert "recipe" not in listed[0]
    assert client.get("/api/assets/prop/smartphone").json()["recipe"]["parts"]
    r = client.post("/api/assets/prop/smartphone/rebuild", json={"note": "rounder"})
    assert r.json()["status"] == "marked" and assets.get("prop", "smartphone")["rebuild_note"] == "rounder"
    assert client.delete("/api/assets/prop/smartphone/rebuild").json()["asset"]["rebuild"] is False
    assert client.post("/api/assets/character/youth/rebuild", json={}).status_code == 409
    assert client.get("/api/assets/prop/..%2Fsecret").status_code == 404
    assert client.patch("/api/assets/prop/smartphone", json={"aliases": ["mobile phone"]}).json()["aliases"] == ["mobile_phone"]
    assert client.delete("/api/assets/prop/smartphone").json()["asset"] is None
    assert client.delete("/api/assets/prop/desk").status_code == 404
