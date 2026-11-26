"""The one place that talks to Claude (script writing and episode plans)."""
from __future__ import annotations

from typing import Any

import anthropic

from . import config

usage: dict[str, int] = {"input_tokens": 0, "output_tokens": 0}


def ask(system: str, messages: list[dict[str, Any]], max_tokens: int = 16000) -> str:
    """Send a conversation, get the text of the answer. Reads ANTHROPIC_API_KEY."""
    try:
        reply = anthropic.Anthropic().beta.messages.create(
            model=config.SCRIPT_MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
            thinking={"type": "adaptive"},
            output_config={"effort": config.SCRIPT_EFFORT},
            # If the model declines, the API retries on its recommended fallback.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
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
    usage["input_tokens"] += reply.usage.input_tokens
    usage["output_tokens"] += reply.usage.output_tokens
    if reply.stop_reason == "refusal":
        raise RuntimeError("Claude declined to write this")
    text = "".join(block.text for block in reply.content if block.type == "text")
    if reply.stop_reason == "max_tokens":
        raise RuntimeError("Claude's answer was cut off (max_tokens)")
    return text
