"""Thin wrapper around fal. Reads FAL_KEY from the environment."""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import requests


def _require_key() -> str:
    key = os.environ.get("FAL_KEY")
    if not key:
        raise RuntimeError("FAL_KEY is not set. Add it as an environment variable.")
    return key


def run(endpoint: str, arguments: dict[str, Any], retries: int = 2) -> dict[str, Any]:
    """Submit a job to fal's queue and wait for the result."""
    _require_key()
    import fal_client  # imported lazily so rendering works without the package

    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return fal_client.subscribe(endpoint, arguments=arguments)
        except Exception as exc:  # noqa: BLE001 - fal raises several types
            last = exc
            text = str(exc).lower()
            # Billing and validation problems will not fix themselves.
            if any(s in text for s in ("balance", "credits", "403", "422", "401")):
                break
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"fal call to {endpoint} failed: {last}") from last


def upload(path: Path) -> str:
    _require_key()
    import fal_client

    return fal_client.upload_file(str(path))


def chat(model: str, messages: list[dict[str, str]], max_tokens: int = 4000) -> str:
    """Call an LLM through fal's OpenAI-compatible OpenRouter endpoint."""
    from . import config

    resp = requests.post(
        config.LLM_URL,
        headers={"Authorization": f"Key {_require_key()}"},
        json={"model": model, "messages": messages, "max_tokens": max_tokens},
        timeout=180,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"LLM call failed ({resp.status_code}): {resp.text[:500]}")
    return resp.json()["choices"][0]["message"]["content"]


def download(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with requests.get(url, stream=True, timeout=300) as resp:
        resp.raise_for_status()
        with open(tmp, "wb") as fh:
            for chunk in resp.iter_content(1 << 16):
                fh.write(chunk)
    tmp.replace(dest)
    return dest
