"""The script is written in steps on different models: dialogue, clarity check, staging."""
import json

import pytest

from b2a import config, llm, pipeline, plan, script as script_mod

BOOK = script_mod.load_book("courage-to-be-disliked")
EXAMPLE = json.loads((config.BOOKS_DIR / "courage-to-be-disliked" / "examples" / "n3-03.json").read_text())
EPISODE = plan.find_episode("courage-to-be-disliked", "n3-03")


def dialogue():
    d = json.loads(json.dumps(EXAMPLE))
    for scene in d["scenes"]:
        scene.pop("stage", None)
    return {**d, "idea": "Other people's opinion of you is their job, not yours."}


def stages(same_props_on_second=False):
    out = [json.loads(json.dumps(s["stage"])) for s in EXAMPLE["scenes"]]
    if same_props_on_second:
        out[1] = {**out[1], "set": out[0]["set"], "props": "same"}
    return {"stages": out}


class FakeClaude:
    def __init__(self, scores=(8,), stage_answers=None):
        self.calls, self.scores, self.stage_answers = [], list(scores), list(stage_answers or [stages()])

    def __call__(self, system, messages, max_tokens=16000, model=None, effort=None, step="script"):
        self.calls.append({"step": step, "model": model, "effort": effort, "messages": messages, "system": system})
        llm.record(step, model, 1000, 2000)
        if step in ("script", "script_fix"):
            return json.dumps(dialogue())
        if step == "clarity":
            score = self.scores.pop(0) if self.scores else 8
            return json.dumps({"understood": "you cannot control what others think",
                               "score": score, "problems": [] if score >= 7 else ["line 3: 'it' is unclear"]})
        if step == "staging":
            answer = self.stage_answers.pop(0) if len(self.stage_answers) > 1 else self.stage_answers[0]
            return json.dumps(answer)
        raise AssertionError(step)


@pytest.fixture
def clarity_on(monkeypatch):
    monkeypatch.setattr(config, "CLARITY_MIN", 7)


def test_steps_run_on_their_own_models(monkeypatch, clarity_on):
    fake = FakeClaude(scores=[8])
    monkeypatch.setattr(llm, "ask", fake)
    script = script_mod.write_script(BOOK, EPISODE)
    assert [c["step"] for c in fake.calls] == ["script", "clarity", "staging"]
    models = {c["step"]: c["model"] for c in fake.calls}
    assert models == {"script": config.SCRIPT_MODEL, "clarity": config.CHECK_MODEL, "staging": config.STAGE_MODEL}
    assert all(s["stage"]["set"] for s in script["scenes"]) and script["clarity"]["score"] == 8
    # the writer gets the clarity rules but not the long 3D manual; the stager gets the manual
    writer, stager = fake.calls[0]["system"], fake.calls[2]["system"]
    assert "ONE concrete everyday situation" in writer and "CAMERA:" not in writer
    assert "CAMERA:" in stager and "Never change a line" in stager


def test_unclear_script_gets_one_fix_round(monkeypatch, clarity_on):
    fake = FakeClaude(scores=[4, 8])
    monkeypatch.setattr(llm, "ask", fake)
    script = script_mod.write_script(BOOK, EPISODE)
    steps = [c["step"] for c in fake.calls]
    assert steps == ["script", "clarity", "script_fix", "clarity", "staging"]
    fix = next(c for c in fake.calls if c["step"] == "script_fix")
    assert "'it' is unclear" in fix["messages"][-1]["content"] and fix["model"] == config.SCRIPT_MODEL
    assert script["clarity"] == {"score": 8, "understood": "you cannot control what others think",
                                 "problems": [], "before": 4}


def test_a_failing_clarity_check_does_not_stop_the_short(monkeypatch, clarity_on):
    fake = FakeClaude()

    def broken(system, messages, max_tokens=16000, model=None, effort=None, step="script"):
        if step == "clarity":
            return "no json here"
        return fake(system, messages, max_tokens, model, effort, step)

    monkeypatch.setattr(llm, "ask", broken)
    script = script_mod.write_script(BOOK, EPISODE)
    assert "clarity" not in script and len(script["scenes"]) == len(EXAMPLE["scenes"])


def test_staging_reuses_props_and_retries_bad_stages(monkeypatch):
    bad = stages()
    bad["stages"][0] = {**bad["stages"][0], "set": "moon"}
    fake = FakeClaude(stage_answers=[bad, stages(same_props_on_second=True)])
    monkeypatch.setattr(llm, "ask", fake)
    script = script_mod.write_script(BOOK, EPISODE)
    staging = [c for c in fake.calls if c["step"] == "staging"]
    assert len(staging) == 2 and "unknown set 'moon'" in staging[1]["messages"][-1]["content"]
    assert script["scenes"][1]["stage"]["props"] == script["scenes"][0]["stage"]["props"]


def test_cost_is_split_per_step_with_each_models_price():
    used = {"script": {"claude-opus-5-5": {"input_tokens": 3000, "output_tokens": 6000}},
            "staging": {"claude-sonnet-5-5": {"input_tokens": 5000, "output_tokens": 6000}},
            "clarity": {"claude-sonnet-5-5": {"input_tokens": 800, "output_tokens": 600}}}
    parts = pipeline.cost_breakdown(EXAMPLE, used, "elevenlabs")
    assert parts["script"] == pytest.approx((3000 * 4 + 6000 * 20) / 1e6, abs=1e-4)
    assert parts["staging"] == pytest.approx((5000 * 2 + 6000 * 10) / 1e6, abs=1e-4)
    assert 0.05 < parts["voice"] < 0.2
    assert pipeline.estimate_cost(EXAMPLE, None, "elevenlabs", used) == pytest.approx(sum(parts.values()), abs=0.01)
    # a Short from before the split still gets a price from its token totals
    old = pipeline.cost_breakdown(EXAMPLE, None, "piper", {"input_tokens": 4000, "output_tokens": 10000})
    assert old["script"] == pytest.approx(0.216, abs=1e-3) and "voice" not in old


def test_haiku_is_called_without_the_fallback_beta(monkeypatch):
    sent = {}

    class Reply:
        usage = type("U", (), {"input_tokens": 1, "output_tokens": 1})()
        stop_reason = "end_turn"
        content = [type("B", (), {"type": "text", "text": "ok"})()]

    class Client:
        def __init__(self):
            self.beta = type("Beta", (), {"messages": type("M", (), {"create": staticmethod(
                lambda **kw: sent.setdefault(kw["model"], kw) and Reply())})()})()

    monkeypatch.setattr(llm.anthropic, "Anthropic", Client)
    llm.ask("s", [{"role": "user", "content": "x"}], model="claude-haiku-5-5", effort="low", step="t")
    llm.ask("s", [{"role": "user", "content": "x"}], model="claude-sonnet-5-5", effort="low", step="t")
    assert "fallbacks" not in sent["claude-haiku-5-5"] and sent["claude-sonnet-5-5"]["fallbacks"] == "default"
