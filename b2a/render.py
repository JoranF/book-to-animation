"""Step 4: edit everything into one vertical video with FFmpeg.

Scenes are cut on the voice, get a CRT look, burned-in captions and music.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from . import config

W, H, FPS = config.WIDTH, config.HEIGHT, config.FPS
X264 = ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS)]


def ffmpeg(*args: str) -> None:
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {proc.stderr[-1500:]}")


def duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout
    return float(json.loads(out)["format"]["duration"])


# --- scenes ----------------------------------------------------------------

FILL = f"scale={W}:{H}:force_original_aspect_ratio=increase:flags=neighbor,crop={W}:{H}"


def scene_from_clip(clip: Path, seconds: float, dest: Path) -> None:
    """Fit a generated clip to the scene length: slow down a little, then hold."""
    stretch = min(max(seconds / max(duration(clip), 0.1), 1.0), 1.3)
    vf = f"setpts={stretch:.4f}*PTS,{FILL},fps={FPS},tpad=stop_mode=clone:stop_duration=20"
    ffmpeg("-i", str(clip), "-vf", vf, "-t", f"{seconds:.3f}", "-an",
           *X264, "-crf", "14", "-preset", "veryfast", str(dest))


def scene_from_image(image: Path, seconds: float, dest: Path, index: int) -> None:
    """Slow camera move over a still image (alternating push in / pull out)."""
    frames = max(int(round(seconds * FPS)), 1)
    zoom = f"1+0.12*on/{frames}" if index % 2 == 0 else f"1.12-0.12*on/{frames}"
    vf = (
        f"scale={W * 2}:{H * 2}:force_original_aspect_ratio=increase,crop={W * 2}:{H * 2},"
        f"zoompan=z='{zoom}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps={FPS}"
    )
    ffmpeg("-i", str(image), "-vf", vf, "-frames:v", str(frames),
           *X264, "-crf", "14", "-preset", "veryfast", str(dest))


# --- captions --------------------------------------------------------------

def _ts(seconds: float) -> str:
    cs = max(int(round(seconds * 100)), 0)
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def caption_chunks(words: list[dict[str, Any]], max_words: int = 3, max_chars: int = 13) -> list[list[dict[str, Any]]]:
    """Small groups of words, never running across the end of a sentence."""
    chunks: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for word in words:
        length = sum(len(w["text"]) + 1 for w in current) + len(word["text"])
        if current and (len(current) >= max_words or length > max_chars):
            chunks.append(current)
            current = []
        current.append(word)
        if word["text"].rstrip('"\')').endswith((".", "?", "!", ":")):
            chunks.append(current)
            current = []
    if current:
        chunks.append(current)
    return chunks


def write_captions(words: list[dict[str, Any]], dest: Path) -> Path:
    """Word-by-word captions: the spoken word lights up yellow."""
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{config.FONT_NAME},64,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,7,4,2,40,40,560,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    for chunk in caption_chunks(words):
        chars = sum(len(w["text"]) for w in chunk) + len(chunk) - 1
        size = "" if chars <= 14 else f"\\fs{max(int(64 * 14 / chars), 34)}"
        for i, word in enumerate(chunk):
            end = chunk[i + 1]["start"] if i + 1 < len(chunk) else max(word["end"], word["start"] + 0.12)
            parts = []
            for j, other in enumerate(chunk):
                text = other["text"].upper().replace("{", "(").replace("}", ")")
                parts.append(f"{{\\c&H00E5FF&}}{text}{{\\c&HFFFFFF&}}" if j == i else text)
            pop = "{\\fscx108\\fscy108\\t(0,90,\\fscx100\\fscy100)" + size + "}" if i == 0 else ("{" + size + "}" if size else "")
            lines.append(f"Dialogue: 0,{_ts(word['start'])},{_ts(end)},Cap,,0,0,0,,{pop}{' '.join(parts)}")
    dest.write_text(header + "\n".join(lines) + "\n", encoding="utf-8")
    return dest


# --- final edit ------------------------------------------------------------

def scanlines(dest: Path) -> Path:
    """Transparent PNG with dark horizontal lines, laid over the picture."""
    if not dest.exists():
        ffmpeg("-f", "lavfi", "-i", f"color=black:s={W}x{H},format=rgba,"
               "geq=r=0:g=0:b=0:a='if(lt(mod(Y,6),2),95,if(lt(mod(Y,6),3),40,0))'",
               "-frames:v", "1", str(dest))
    return dest


def crt_filter() -> str:
    """Old game on an old TV: chunky pixels, colour bleed, scanlines, glow."""
    return (
        f"[0:v]scale={W // 3}:{H // 3}:flags=bicubic,scale={W}:{H}:flags=neighbor,"
        "eq=saturation=1.2:contrast=1.06:brightness=0.02,"
        "rgbashift=rh=-3:bh=3,gblur=sigma=0.8[px];"
        "[px][1:v]overlay=0:0,noise=alls=7:allf=t,"
        "vignette=angle=PI/5,"
        "lenscorrection=k1=0.045:k2=0.02:i=bilinear[crt]"
    )


def _esc(path: Path) -> str:
    return str(path).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def render(scenes: list[dict[str, Path | None]], times: list[tuple[float, float]],
           voice: Path, words: list[dict[str, Any]], music: Path | None,
           work: Path, dest: Path, crt: bool = True, sfx: Path | None = None) -> Path:
    work.mkdir(parents=True, exist_ok=True)
    total = times[-1][1]

    parts = []
    for i, (scene, (start, end)) in enumerate(zip(scenes, times)):
        part = work / f"part_{i:02d}.mp4"
        if scene.get("clip"):
            scene_from_clip(scene["clip"], end - start, part)
        else:
            scene_from_image(scene["image"], end - start, part, i)
        parts.append(part)
    concat = work / "concat.txt"
    concat.write_text("".join(f"file '{p.resolve()}'\n" for p in parts))
    silent = work / "silent.mp4"
    ffmpeg("-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", str(silent))

    captions = write_captions(words, work / "captions.ass")
    subs = f"ass='{_esc(captions)}':fontsdir='{_esc(config.FONT_FILE.parent)}'"
    video = (crt_filter() + f";[crt]{subs}[v]") if crt else f"[0:v]{subs}[v]"

    inputs = ["-i", str(silent), "-loop", "1", "-i", str(scanlines(work / "scanlines.png")),
              "-i", str(voice)]
    fade = f"afade=t=out:st={max(total - 1.2, 0):.2f}:d=1.2"
    # voice (input 2), then optional music and sound effects, mixed under the voice
    beds, labels = [], []
    if music:
        inputs += ["-stream_loop", "-1", "-i", str(music)]
        beds.append(f"[{2 + len(beds) + 1}:a]aresample=48000,volume={config.MUSIC_VOLUME},afade=t=in:d=0.4[mu]")
        labels.append("[mu]")
    if sfx:
        inputs += ["-i", str(sfx)]
        beds.append(f"[{2 + len(beds) + 1}:a]aresample=48000,apad[fx]")
        labels.append("[fx]")
    if beds:
        audio = (
            "[2:a]aresample=48000,apad[vo];" + ";".join(beds) + ";"
            f"[vo]{''.join(labels)}amix=inputs={1 + len(labels)}:duration=first:normalize=0,{fade},"
            "loudnorm=I=-14:TP=-1.5:LRA=11[a]"
        )
    else:
        audio = f"[2:a]aresample=48000,apad,{fade},loudnorm=I=-14:TP=-1.5:LRA=11[a]"

    dest.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg(*inputs, "-filter_complex", f"{video};{audio}", "-map", "[v]", "-map", "[a]",
           "-t", f"{total:.3f}", *X264, "-crf", "18", "-preset", "medium",
           "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", str(dest))
    return dest


def thumbnail(video: Path, dest: Path, at: float = 0.6) -> Path:
    ffmpeg("-ss", f"{at:.2f}", "-i", str(video), "-frames:v", "1", "-q:v", "3", str(dest))
    return dest
