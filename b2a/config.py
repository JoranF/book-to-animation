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

# --- fal endpoints -------------------------------------------------------
LLM_URL = "https://fal.run/openrouter/router/openai/v1/chat/completions"
SCRIPT_MODEL = os.environ.get("SCRIPT_MODEL", "anthropic/claude-sonnet-4.5")
TTS_MODEL = os.environ.get("TTS_MODEL", "elevenlabs/tts/eleven-v4")
TTS_VOICE = os.environ.get("TTS_VOICE", "Brian")
STT_MODEL = os.environ.get("STT_MODEL", "fal-ai/elevenlabs/speech-to-text")

# --- voice ---------------------------------------------------------------
# auto: ElevenLabs through fal when FAL_KEY is set, else the free local voice.
# auto: ElevenLabs when ELEVENLABS_API_KEY is set, else ElevenLabs through fal
# when FAL_KEY is set, else the free local voice.
TTS_BACKEND = os.environ.get("TTS_BACKEND", "auto")  # auto | elevenlabs | fal | piper
SPEAKERS = ["narrator", "philosopher", "youth"]
# ElevenLabs voice ids per speaker (defaults: Brian, George, Liam).
ELEVENLABS_VOICES = {
    "narrator": os.environ.get("ELEVENLABS_VOICE_NARRATOR", "nPczCjzI2devNBz1zQrb"),
    "philosopher": os.environ.get("ELEVENLABS_VOICE_PHILOSOPHER", "JBFqnCBsd6RMkjVDRZzb"),
    "youth": os.environ.get("ELEVENLABS_VOICE_YOUTH", "TX3LPaxmHKxFdv7VOQHJ"),
}
ELEVENLABS_MODEL = os.environ.get("ELEVENLABS_MODEL", "eleven_multilingual_v2")
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

# USD list prices used for the cost estimate stored with every Short.
PRICES = {"tts_per_1k_chars": 0.08, "llm_script": 0.03}
