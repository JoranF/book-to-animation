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
IMAGE_MODEL = os.environ.get("IMAGE_MODEL", "fal-ai/nano-banana-2")
IMAGE_EDIT_MODEL = os.environ.get("IMAGE_EDIT_MODEL", "fal-ai/nano-banana-2/edit")
VIDEO_MODEL = os.environ.get("VIDEO_MODEL", "minimax/h3-max-turbo/image-to-video")
VIDEO_RESOLUTION = os.environ.get("VIDEO_RESOLUTION", "768P")
MUSIC_MODEL = os.environ.get("MUSIC_MODEL", "google/lyria-3.5")

# "all" animates every scene, "none" uses a camera move on stills only,
# a number animates that many scenes (the hook first) to save money.
ANIMATE = os.environ.get("ANIMATE", "all")

# --- output --------------------------------------------------------------
WIDTH, HEIGHT, FPS = 1080, 1920, 30
MUSIC_VOLUME = float(os.environ.get("MUSIC_VOLUME", "0.14"))
TAIL_SECONDS = 0.5  # silence after the last word

# USD list prices used for the cost estimate stored with every Short.
PRICES = {
    "tts_per_1k_chars": 0.08,
    "stt_per_minute": 0.03,
    "image": 0.08,
    "video_per_second": 0.01875,
    "music": 0.10,
    "llm_script": 0.03,
}
