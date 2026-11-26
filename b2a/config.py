"""Central settings. Everything can be overridden with environment variables."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("DATA_DIR", ROOT / "data"))
BOOKS_DIR = ROOT / "books"
ASSETS_DIR = ROOT / "assets"
FONT_FILE = ASSETS_DIR / "fonts" / "PressStart2P-Regular.ttf"
FONT_NAME = "Press Start 2P"

# --- script writing (Claude API, key in ANTHROPIC_API_KEY) ---------------
SCRIPT_MODEL = os.environ.get("SCRIPT_MODEL", "claude-opus-5-5")
SCRIPT_EFFORT = os.environ.get("SCRIPT_EFFORT", "high")  # low | medium | high

# --- voice ---------------------------------------------------------------
# auto: ElevenLabs when ELEVENLABS_API_KEY is set, else the free local voice.
TTS_BACKEND = os.environ.get("TTS_BACKEND", "auto")  # auto | elevenlabs | piper
SPEAKERS = ["narrator", "philosopher", "youth"]
# ElevenLabs voice ids per speaker (defaults: Brian, George, Liam).
ELEVENLABS_VOICES = {
    "narrator": os.environ.get("ELEVENLABS_VOICE_NARRATOR", "nPczCjzI2devNBz1zQrb"),
    "philosopher": os.environ.get("ELEVENLABS_VOICE_PHILOSOPHER", "JBFqnCBsd6RMkjVDRZzb"),
    "youth": os.environ.get("ELEVENLABS_VOICE_YOUTH", "TX3LPaxmHKxFdv7VOQHJ"),
}
# Eleven v4 acts out delivery tags like [sighs] and [pause]. If the account or
# the endpoint refuses it, the fallback model reads the plain line instead.
ELEVENLABS_MODEL = os.environ.get("ELEVENLABS_MODEL", "eleven_v4")
ELEVENLABS_FALLBACK_MODEL = os.environ.get("ELEVENLABS_FALLBACK_MODEL", "eleven_multilingual_v2")
ELEVENLABS_STABILITY = float(os.environ.get("ELEVENLABS_STABILITY", "0.4"))  # lower = more acting
# Speakers of the free voice model for the same three roles.
PIPER_SPEAKERS = {"narrator": None, "philosopher": 5, "youth": 19}
PIPER_MODEL = os.environ.get("PIPER_MODEL", str(ROOT / "voices" / "en-us-libritts-high.onnx"))
_speaker = os.environ.get("PIPER_SPEAKER", "8")
PIPER_SPEAKER = int(_speaker) if _speaker else None
PIPER_LENGTH_SCALE = float(os.environ.get("PIPER_LENGTH_SCALE", "1.18"))

# --- output --------------------------------------------------------------
WIDTH, HEIGHT, FPS = 1080, 1920, 30
MUSIC_VOLUME = float(os.environ.get("MUSIC_VOLUME", "0.16"))
TAIL_SECONDS = 0.5  # silence after the last word

# Rough USD prices for the cost estimate stored with every Short. They are
# assumptions: set them to what your own plans really charge.
PRICES = {
    "tts_per_1k_chars": float(os.environ.get("PRICE_TTS_PER_1K_CHARS", "0.20")),
    "llm_in_per_mtok": float(os.environ.get("PRICE_LLM_IN_PER_MTOK", "5")),
    "llm_out_per_mtok": float(os.environ.get("PRICE_LLM_OUT_PER_MTOK", "25")),
}
