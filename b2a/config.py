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
# The script is written in steps, each on the model that fits it:
# - the dialogue (the creative part that decides engagement): SCRIPT_MODEL
# - the 3D staging of every scene (long, mechanical JSON): STAGE_MODEL
# - the clarity check by a "first-time viewer": CHECK_MODEL
# - trend briefs and the playbook from the numbers: ANALYSIS_MODEL
SCRIPT_MODEL = os.environ.get("SCRIPT_MODEL", "claude-opus-5-5")
SCRIPT_EFFORT = os.environ.get("SCRIPT_EFFORT", "high")  # low | medium | high | xhigh | max
STAGE_MODEL = os.environ.get("STAGE_MODEL", "claude-sonnet-5-5")
STAGE_EFFORT = os.environ.get("STAGE_EFFORT", "medium")
CHECK_MODEL = os.environ.get("CHECK_MODEL", "claude-sonnet-5-5")
CHECK_EFFORT = os.environ.get("CHECK_EFFORT", "low")
ANALYSIS_MODEL = os.environ.get("ANALYSIS_MODEL", "claude-sonnet-5-5")
ANALYSIS_EFFORT = os.environ.get("ANALYSIS_EFFORT", "medium")
# Clarity check: a score from 1 to 10; below CLARITY_MIN the writer gets one
# chance to fix the lines the checker did not understand. 0 turns it off.
CLARITY_MIN = int(os.environ.get("CLARITY_MIN", "7"))

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
# Retro sound effects (b2a/sfx.py). 0 turns them off.
SFX_VOLUME = float(os.environ.get("SFX_VOLUME", "0.25"))
SFX_VARY = os.environ.get("SFX_VARY", "1") != "0"   # 0 = always the same variant of each sound

# --- music ---------------------------------------------------------------
# auto: ACE-Step when ACESTEP_URL is set (own GPU service, see musicgen/), else
# the chiptune composed in code. Generated tracks are kept in a library per
# mood and reused, so the GPU only works until the library is full.
MUSIC_BACKEND = os.environ.get("MUSIC_BACKEND", "auto")  # auto | acestep | chiptune
ACESTEP_URL = os.environ.get("ACESTEP_URL", "").rstrip("/")
ACESTEP_API_KEY = os.environ.get("ACESTEP_API_KEY", "")
ACESTEP_TIMEOUT = float(os.environ.get("ACESTEP_TIMEOUT", "900"))   # seconds per track
MUSIC_PER_MOOD = int(os.environ.get("MUSIC_PER_MOOD", "4"))          # library size per mood

# --- trend research (b2a/trends.py) ---------------------------------------
# YouTube (yt-dlp) and Reddit are free. With SCRAPECREATORS_API_KEY TikTok and
# YouTube search are added (about 1 credit per search).
TRENDS_MAX_AGE_DAYS = int(os.environ.get("TRENDS_MAX_AGE_DAYS", "14"))
TAIL_SECONDS = 0.5  # silence after the last word

# USD prices for the cost estimate stored with every Short. Claude list prices
# per million tokens (input, output); a model not in this list uses the
# PRICE_LLM_* fallback. The voice price is an assumption: set it to what your
# ElevenLabs plan really charges per 1,000 characters.
MODEL_PRICES = {
    "claude-opus-5-5": (4.0, 20.0),
    "claude-opus-5": (5.0, 25.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-fable-5-2": (8.0, 40.0),
}
PRICES = {
    "tts_per_1k_chars": float(os.environ.get("PRICE_TTS_PER_1K_CHARS", "0.20")),
    "llm_in_per_mtok": float(os.environ.get("PRICE_LLM_IN_PER_MTOK", "5")),
    "llm_out_per_mtok": float(os.environ.get("PRICE_LLM_OUT_PER_MTOK", "25")),
}


def model_price(model: str) -> tuple[float, float]:
    """(input, output) USD per million tokens."""
    return MODEL_PRICES.get(model, (PRICES["llm_in_per_mtok"], PRICES["llm_out_per_mtok"]))
