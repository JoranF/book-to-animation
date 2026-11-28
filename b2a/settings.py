"""Which Claude model (and effort) does which step, changeable from the dashboard.

The environment variables in config.py are the defaults. Choices made in the
web front are saved in DATA_DIR/model_settings.json and win over them; apply()
puts them into config before every job.
"""
from __future__ import annotations

import json
from typing import Any

from . import config

# step key -> (label, model attribute, effort attribute, what it does)
STEPS = {
    "script": ("Dialogue", "SCRIPT_MODEL", "SCRIPT_EFFORT",
               "Writes what is said. The creative part: hook, jokes, the idea."),
    "staging": ("3D staging", "STAGE_MODEL", "STAGE_EFFORT",
                "Builds every scene from the 3D kit: set, props, poses, camera. Long JSON, most tokens."),
    "clarity": ("Clarity check", "CHECK_MODEL", "CHECK_EFFORT",
                "A first-time viewer scores the lines 1-10; below the minimum the dialogue is fixed once."),
    "analysis": ("Trends and playbook", "ANALYSIS_MODEL", "ANALYSIS_EFFORT",
                 "Weekly trend brief and the rules learned from the channel's numbers."),
}
MODELS = {
    "claude-opus-5-5": "Opus 5.5",
    "claude-sonnet-5-5": "Sonnet 5.5",
    "claude-haiku-5-5": "Haiku 5.5",
    "claude-fable-5-2": "Fable 5.2",
}
EFFORTS = ["low", "medium", "high", "xhigh", "max"]

# The values from the environment, before anything from the dashboard.
DEFAULTS: dict[str, Any] = {attr: getattr(config, attr) for _, m, e, _ in STEPS.values() for attr in (m, e)}
DEFAULTS["CLARITY_MIN"] = config.CLARITY_MIN


def _path():
    return config.DATA_DIR / "model_settings.json"


def saved() -> dict[str, Any]:
    try:
        data = json.loads(_path().read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def apply() -> None:
    """Put the dashboard's choices (or the env defaults) into config."""
    data = saved()
    for key, (_, model_attr, effort_attr, _) in STEPS.items():
        step = data.get(key) or {}
        model = step.get("model")
        effort = step.get("effort")
        setattr(config, model_attr, model if model in MODELS else DEFAULTS[model_attr])
        setattr(config, effort_attr, effort if effort in EFFORTS else DEFAULTS[effort_attr])
    minimum = data.get("clarity_min")
    config.CLARITY_MIN = minimum if isinstance(minimum, int) and 0 <= minimum <= 10 else DEFAULTS["CLARITY_MIN"]


def view() -> dict[str, Any]:
    """What the dashboard shows: every step with its current and default choice."""
    apply()
    steps = []
    for key, (label, model_attr, effort_attr, help_text) in STEPS.items():
        steps.append({"key": key, "label": label, "help": help_text,
                      "model": getattr(config, model_attr), "effort": getattr(config, effort_attr),
                      "default_model": DEFAULTS[model_attr], "default_effort": DEFAULTS[effort_attr]})
    models = [{"id": m, "name": name, "price_in": config.model_price(m)[0], "price_out": config.model_price(m)[1]}
              for m, name in MODELS.items()]
    return {"steps": steps, "models": models, "efforts": EFFORTS,
            "clarity_min": config.CLARITY_MIN, "default_clarity_min": DEFAULTS["CLARITY_MIN"]}


def save(body: dict[str, Any]) -> dict[str, Any]:
    """Store new choices. Unknown models or efforts raise ValueError; a step left out keeps its value;
    {"reset": true} goes back to the env defaults."""
    if body.get("reset"):
        _path().unlink(missing_ok=True)
        return view()
    data = saved()
    for key in STEPS:
        step = body.get(key)
        if step is None:
            continue
        if not isinstance(step, dict):
            raise ValueError(f"{key} must be an object with model and effort")
        model, effort = step.get("model"), step.get("effort")
        if model is not None and model not in MODELS:
            raise ValueError(f"{key}: unknown model '{model}', choose from {list(MODELS)}")
        if effort is not None and effort not in EFFORTS:
            raise ValueError(f"{key}: unknown effort '{effort}', choose from {EFFORTS}")
        data[key] = {**(data.get(key) or {}), **{k: v for k, v in (("model", model), ("effort", effort)) if v}}
    if "clarity_min" in body:
        try:
            minimum = int(body["clarity_min"])
        except (TypeError, ValueError):
            raise ValueError("clarity_min must be a whole number from 0 to 10") from None
        if not 0 <= minimum <= 10:
            raise ValueError("clarity_min must be from 0 to 10 (0 turns the check off)")
        data["clarity_min"] = minimum
    _path().parent.mkdir(parents=True, exist_ok=True)
    _path().write_text(json.dumps(data, indent=2))
    return view()
