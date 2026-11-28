"""The one place that talks to Claude (script writing, checks, briefs, plans)."""
from __future__ import annotations

from typing import Any

import anthropic

from . import config

# Running totals since the process started. `usage` is the sum over every
# model; `steps` splits it per step and model, so a Short can show what each
# step cost (see pipeline.estimate_cost).
usage: dict[str, int] = {"input_tokens": 0, "output_tokens": 0}
steps: dict[str, dict[str, dict[str, int]]] = {}


def _has_fallbacks(model: str) -> bool:
    """Server-side refusal fallbacks exist for these models, not for Haiku."""
    return model.startswith(("claude-opus-5", "claude-sonnet-5-5", "claude-fable-5"))


def ask(system: str, messages: list[dict[str, Any]], max_tokens: int = 16000,
        model: str | None = None, effort: str | None = None, step: str = "script") -> str:
    """Send a conversation, get the text of the answer. Reads ANTHROPIC_API_KEY."""
    model = model or config.SCRIPT_MODEL
    kwargs: dict[str, Any] = dict(
        model=model, max_tokens=max_tokens, system=system, messages=messages,
        thinking={"type": "adaptive"},
        output_config={"effort": effort or config.SCRIPT_EFFORT},
    )
    if _has_fallbacks(model):
        # If the model declines, the API retries on its recommended fallback.
        kwargs.update(betas=["server-side-fallback-2026-07-01"], fallbacks="default")
    try:
        reply = anthropic.Anthropic().beta.messages.create(**kwargs)
    except anthropic.AuthenticationError as exc:
        raise RuntimeError("ANTHROPIC_API_KEY is missing or not valid") from exc
    except anthropic.RateLimitError as exc:
        raise RuntimeError("Claude API rate limit reached, try again in a minute") from exc
    except anthropic.APIStatusError as exc:
        raise RuntimeError(f"Claude API error {exc.status_code}: {exc.message}") from exc
    except anthropic.APIConnectionError as exc:
        raise RuntimeError("Could not reach the Claude API") from exc
    except anthropic.AnthropicError as exc:   # e.g. no key configured at all
        raise RuntimeError(f"Claude API is not set up: {exc}") from exc
    record(step, model, reply.usage.input_tokens, reply.usage.output_tokens)
    if reply.stop_reason == "refusal":
        raise RuntimeError("Claude declined to write this")
    text = "".join(block.text for block in reply.content if block.type == "text")
    if reply.stop_reason == "max_tokens":
        raise RuntimeError("Claude's answer was cut off (max_tokens)")
    return text


def record(step: str, model: str, input_tokens: int, output_tokens: int) -> None:
    usage["input_tokens"] += input_tokens
    usage["output_tokens"] += output_tokens
    per = steps.setdefault(step, {}).setdefault(model, {"input_tokens": 0, "output_tokens": 0})
    per["input_tokens"] += input_tokens
    per["output_tokens"] += output_tokens


def snapshot() -> dict[str, dict[str, dict[str, int]]]:
    return {s: {m: dict(t) for m, t in per.items()} for s, per in steps.items()}


def since(before: dict[str, dict[str, dict[str, int]]]) -> dict[str, dict[str, dict[str, int]]]:
    """What was used per step and model after `before` (a snapshot())."""
    out: dict[str, dict[str, dict[str, int]]] = {}
    for step, per in steps.items():
        for model, tok in per.items():
            old = before.get(step, {}).get(model, {})
            diff = {k: tok[k] - old.get(k, 0) for k in tok}
            if any(diff.values()):
                out.setdefault(step, {})[model] = diff
    return out


def cost(used: dict[str, dict[str, dict[str, int]]]) -> dict[str, float]:
    """USD per step for a since() result."""
    out: dict[str, float] = {}
    for step, per in used.items():
        total = 0.0
        for model, tok in per.items():
            p_in, p_out = config.model_price(model)
            total += (tok.get("input_tokens", 0) * p_in + tok.get("output_tokens", 0) * p_out) / 1e6
        out[step] = total
    return out
