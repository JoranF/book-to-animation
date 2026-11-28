"""Step 1: write the script. Own words, original examples, no book quotes."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from . import config, llm, music, plan as plan_mod, stage as stage_mod
from .voice import strip_tags

# The script is written in three steps (see write_script):
# 1. WRITER_SYSTEM on SCRIPT_MODEL: what is said, by whom, and what we see.
# 2. CHECK_SYSTEM on CHECK_MODEL: a first-time viewer says if they got it;
#    unclear lines go back to the writer once.
# 3. STAGE_SYSTEM on STAGE_MODEL: the 3D stage of every scene (long JSON).
# Splitting keeps the expensive model on the creative part only.

WRITER_SYSTEM = """You write scripts for a YouTube Shorts channel that explains ideas \
from philosophy and psychology books as short animated stories.

Hard rules:
- Explain the IDEA in your own words. Never quote or closely paraphrase the \
book. No sentences from the book, no chapter structure, no character lines \
from the book. Do not mention the book title or authors in the narration.
- This Short covers ONE narrow idea (the episode below). Do not summarise the \
book or touch its other ideas. A viewer who has seen ten other Shorts from \
this series must still find this one new.
- 80 to 105 words of narration in total (about 35 to 45 seconds).
- 8 to 12 scenes. Each scene is ONE line: 1 or 2 short sentences.
- The first sentence is the hook: under 14 words, creates tension or \
curiosity, no greeting, no "did you know".
- End with one question or one line that makes people comment or rewatch.

Clarity comes first: a viewer scrolling past hears every line ONCE, with no \
context and no rewatch. If they do not get it, they swipe.
- Before writing, decide the idea in one plain sentence a 12-year-old would \
understand ("idea" in the JSON). Every line must serve that sentence.
- Build the whole Short on ONE concrete everyday situation the viewer has \
lived (a group chat left on read, a job interview, a family dinner, a gym \
mirror, a missed bus...). Follow that one situation from start to end. No \
second example, no switching to an abstract case.
- Plain spoken English: short common words, short sentences, "you". No \
jargon or theory words (no "teleology", "aetiology", "inferiority complex", \
"ego"...); say what it means instead. No metaphor on top of a metaphor.
- Shape: hook (tension) -> the situation -> the youth says what most people \
believe -> the philosopher turns it around with a question or a twist -> the \
PAYOFF: one line that says the idea plainly, near the end -> what it means \
for the viewer, or the closing question.
- The payoff is said straight, not as a riddle or a clever pun. Someone who \
only heard the payoff line must still get the idea.
- Every "it", "that" and "this" points at something said in the line before. \
No inside jokes, no references to other episodes, no names the viewer has \
not heard.

Engagement:
- The Short is a CONVERSATION, not a lecture: at least half of the scenes \
are the youth and the philosopher talking to each other, and each line \
reacts to the line before it. The youth is impatient and a bit sarcastic: he \
objects, cuts in, jokes, gets it wrong (the way the viewer would). The \
philosopher stays calm and answers short, with a twist or a question back. \
A character line is at most 12 words. No speeches, no "As I said". The \
narrator only does quick set-ups and bridges (the hook may be said by a \
character instead).
- Tension in the first two seconds, a new beat every 3 to 4 seconds, one \
moment of friction or humour between the two, and the answer to the hook \
only near the end.

Characters (they appear on screen in a late-90s low-poly 3D game world):
{characters}
Each scene needs:
- "speaker": "narrator", "philosopher" or "youth", each with their own voice.
- "narration": the line, acted by a voice model that follows delivery tags \
in square brackets. Start a line with one tag for the emotion when it helps \
([sighs], [laughs], [whispers], [shouts], [curious], [mischievously], \
[annoyed], [deadpan]) and put [pause] or [long pause] exactly where a beat of \
silence makes the line land: before a punchline, after a hard question, \
before the last line. Use "..." for a trailing-off thought and a dash for a \
cut-off. At most 2 tags per line, none on most narrator lines. Tags are not \
shown in the captions and do not count as words.
- "image": one sentence saying what we see, so a 3D artist can build it \
from this kit: {kit}. Whoever speaks must be in the picture (the narrator \
speaks over any picture). Show the everyday situation and make the idea \
visible as a simple picture (a weight, a door, a path, a tower of papers...). \
Change the place at least twice.

Return ONLY JSON:
{{"idea": "the idea in one plain sentence", \
"title": "YouTube title under 60 chars", "hook": "the first sentence", \
"hook_type": "question|bold_claim|contradiction|story|you_statement", \
"description": "2 sentence YouTube description, may name the book", \
"hashtags": ["#shorts", "..."], \
"music_mood": "one of {moods}", \
"scenes": [{{"speaker": "youth", "narration": "...", "image": "..."}}]}}"""

CHECK_SYSTEM = """You test scripts of animated YouTube Shorts on viewers who \
have never heard of the idea. Read the lines as a tired 16-year-old scrolling \
at night who hears each line once. Be strict: if you have to think twice, it \
is not clear.

Answer in JSON only:
{"understood": "the idea in your own words, one sentence, as the viewer \
would say it to a friend",
"score": 1-10 (10 = every viewer gets the idea and the example at first \
listen; 7 = clear with one weak spot; 4 or less = most would be lost),
"problems": ["line N: what is confusing and why", "..."] (empty when clear; \
look for jargon, abstract words, a missing step between two lines, an \
unclear "it"/"that", a second example, a payoff that is a riddle, a joke \
that needs context)}"""

STAGE_SYSTEM = """You are the 3D layout artist of an animated YouTube Shorts \
channel in a late-90s low-poly game style. The script is finished: you \
build the stage of every scene from a fixed kit. Never change a line.

The characters:
{characters}

{guide}

To keep it short: when a scene uses the same set and the same props as the \
scene before, write "props": "same" instead of repeating them.
Use the "image" of each scene as the brief. The speaker of a scene must be \
an actor in it, unless the speaker is the narrator. Roughly 2.5 spoken words \
per second, so "at" times fit the line.

Return ONLY JSON: {{"stages": [STAGE for scene 1, STAGE for scene 2, ...]}} \
with exactly one stage per scene, in order."""

KIT_SUMMARY = (
    "places: " + ", ".join(stage_mod.SETS) + "; people: the youth, the philosopher, a father, "
    "faceless grey people; things: " + ", ".join(stage_mod.PROPS) + "; the people can " +
    ", ".join(a.replace("_", " ") for a in stage_mod.ACTIONS)
)


def _extract_json(text: str) -> dict[str, Any]:
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise ValueError("The model did not return JSON")
    return json.loads(match.group(0))


def validate(script: dict[str, Any], book: dict[str, Any]) -> dict[str, Any]:
    scenes = script.get("scenes") or []
    if not 5 <= len(scenes) <= 16:
        raise ValueError(f"Expected 5-16 scenes, got {len(scenes)}")
    for number, scene in enumerate(scenes, 1):
        spoken = str(scene.get("voice_text") or scene.get("narration") or "").strip()
        if not strip_tags(spoken):
            raise ValueError(f"Scene {number} is missing 'narration'")
        scene["voice_text"] = spoken                 # with [tags], for the voice
        scene["narration"] = strip_tags(spoken)      # clean, for captions and timing
        if scene.get("speaker") not in config.SPEAKERS:
            scene["speaker"] = "narrator"
        try:
            scene["stage"] = stage_mod.validate(scene.get("stage") or dict(stage_mod.DEFAULT))
        except ValueError as exc:
            raise ValueError(f"Scene {number} stage: {exc}") from exc
        for actor in scene["stage"]["actors"]:      # the speaker's mouth moves
            if actor["who"] == scene["speaker"]:
                actor["talking"] = True
    words = sum(len(s["narration"].split()) for s in scenes)
    if not 60 <= words <= 160:
        raise ValueError(f"Narration has {words} words, expected 60-160")
    script.setdefault("hook", scenes[0]["narration"])
    script.setdefault("title", script["hook"][:60])
    script.setdefault("hook_type", "unknown")
    script.setdefault("description", "")
    script.setdefault("hashtags", ["#shorts"])
    if script.get("music_mood") not in music.MOODS:
        script.pop("music_mood", None)            # the editor picks one
    return script


def validate_dialogue(script: dict[str, Any]) -> dict[str, Any]:
    """Check the writer's part (lines, speakers) before anything is staged."""
    scenes = script.get("scenes") or []
    if not 5 <= len(scenes) <= 16:
        raise ValueError(f"Expected 8-12 scenes, got {len(scenes)}")
    for number, scene in enumerate(scenes, 1):
        if not strip_tags(str(scene.get("voice_text") or scene.get("narration") or "")):
            raise ValueError(f"Scene {number} is missing 'narration'")
        if scene.get("speaker") not in config.SPEAKERS:
            scene["speaker"] = "narrator"
    words = sum(len(strip_tags(str(s.get("voice_text") or s.get("narration"))).split()) for s in scenes)
    if not 60 <= words <= 135:
        raise ValueError(f"Narration has {words} words, expected 80-105")
    return script


def _ask_json(system: str, messages: list[dict[str, Any]], check, *, model: str, effort: str,
              step: str, max_tokens: int = 16000, tries: int = 3) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Ask until the answer parses and passes `check`. Returns the result and the conversation."""
    error: Exception | None = None
    for _ in range(tries):
        text = llm.ask(system, messages, max_tokens, model=model, effort=effort, step=step)
        try:
            result = check(_extract_json(text))
            return result, messages + [{"role": "assistant", "content": text}]
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            error = exc
            messages = messages + [{"role": "assistant", "content": text or "(empty)"},
                                   {"role": "user", "content": f"Invalid: {exc}. Return the corrected JSON only."}]
    raise RuntimeError(f"Could not get a valid {step}: {error}")


def _lines(script: dict[str, Any]) -> str:
    return "\n".join(f"{i}. {s.get('speaker')}: {strip_tags(str(s.get('voice_text') or s.get('narration')))}"
                     for i, s in enumerate(script["scenes"], 1))


def check_clarity(script: dict[str, Any]) -> dict[str, Any]:
    """A first-time viewer rates how clear the lines are (score 1-10, problems per line)."""
    def check(data: dict[str, Any]) -> dict[str, Any]:
        score = data.get("score")
        if not isinstance(score, (int, float)) or isinstance(score, bool):
            raise ValueError("'score' must be a number from 1 to 10")
        problems = data.get("problems") or []
        if not isinstance(problems, list):
            raise ValueError("'problems' must be a list")
        return {"score": max(1, min(int(round(score)), 10)), "understood": str(data.get("understood") or ""),
                "problems": [str(p) for p in problems][:8]}

    user = f"The lines of the Short, in order:\n{_lines(script)}"
    result, _ = _ask_json(CHECK_SYSTEM, [{"role": "user", "content": user}], check,
                          model=config.CHECK_MODEL, effort=config.CHECK_EFFORT, step="clarity",
                          max_tokens=4000, tries=2)
    return result


def stage_scenes(script: dict[str, Any], book: dict[str, Any]) -> dict[str, Any]:
    """Build the 3D stage of every scene that has none yet (on STAGE_MODEL)."""
    scenes = script["scenes"]
    if all(isinstance(s.get("stage"), dict) for s in scenes):
        return script                                # hand-made, or already staged
    characters = "\n".join(f'- "{key}": {c["prompt"]}' for key, c in book["characters"].items())
    brief = [{"scene": i, "speaker": s["speaker"], "line": strip_tags(str(s.get("voice_text") or s["narration"])),
              "words": len(strip_tags(str(s.get("voice_text") or s["narration"])).split()), "image": s.get("image", "")}
             for i, s in enumerate(scenes, 1)]

    def check(data: dict[str, Any]) -> list[dict[str, Any]]:
        stages = data.get("stages")
        if not isinstance(stages, list) or len(stages) != len(scenes):
            raise ValueError(f"'stages' must be a list of exactly {len(scenes)} stages")
        out: list[dict[str, Any]] = []
        for number, (stage, scene) in enumerate(zip(stages, scenes), 1):
            if isinstance(stage, dict) and stage.get("props") == "same":
                if not out or out[-1]["set"] != stage.get("set"):
                    raise ValueError(f"Scene {number}: \"props\": \"same\" needs the same set as the scene before")
                stage["props"] = json.loads(json.dumps(out[-1]["props"]))
            try:
                stage = stage_mod.validate(stage)
            except ValueError as exc:
                raise ValueError(f"Scene {number} stage: {exc}") from exc
            if scene["speaker"] != "narrator" and scene["speaker"] not in {a["who"] for a in stage["actors"]}:
                raise ValueError(f"Scene {number}: the speaker '{scene['speaker']}' must be an actor in the stage")
            out.append(stage)
        return out

    system = STAGE_SYSTEM.format(characters=characters, guide=stage_mod.GUIDE)
    user = f"The scenes (JSON):\n{json.dumps(brief, ensure_ascii=False)}"
    stages, _ = _ask_json(system, [{"role": "user", "content": user}], check,
                          model=config.STAGE_MODEL, effort=config.STAGE_EFFORT, step="staging", max_tokens=32000)
    for scene, stage in zip(scenes, stages):
        scene["stage"] = stage
    return script


def write_script(book: dict[str, Any], episode: dict[str, Any], learnings: str = "",
                 avoid: list[str] | None = None, trends_brief: str = "",
                 previous: dict[str, Any] | None = None, feedback: str = "") -> dict[str, Any]:
    """Write the script for one episode (see plan.py for what an episode is):
    the dialogue, a clarity check (one fix round when unclear), then the staging."""
    characters = "\n".join(
        f'- "{key}": {c["prompt"]}' for key, c in book["characters"].items()
    )
    fmt = episode.get("format") if episode.get("format") in plan_mod.FORMATS else "reframe"
    user = (
        f"Book: {book['title']} ({book.get('school', '')}).\n"
        f"What the book is about (background only): {book['summary']}\n\n"
        f"Episode: {episode['title']}\n"
    )
    if episode.get("chapter"):
        user += f"Part of the book: {episode['chapter']}\n"
    if episode.get("angle"):
        user += f"The one idea and angle: {episode['angle']}\n"
    if episode.get("hook"):
        user += f"Planned hook (keep it or make it sharper): {episode['hook']}\n"
    user += f"Format \"{fmt}\": {plan_mod.FORMATS[fmt]}\n"
    if avoid:
        user += ("\nHooks of Shorts we already made. Yours must sound and be built "
                 "differently, with a different example and opening scene:\n"
                 + "\n".join(f"- {h}" for h in avoid) + "\n")
    if learnings:
        user += (
            "\nWhat worked and did not work on this channel so far "
            f"(use it):\n{learnings}\n"
        )
    if trends_brief:
        user += (
            "\nWhat is working in this niche on Shorts and TikTok right now (research "
            "from the last weeks). Use what fits this one idea; never copy a hook or "
            f"a title:\n{trends_brief}\n"
        )
    if previous and feedback:
        old = {k: previous.get(k) for k in ("title", "hook", "hook_type", "description", "hashtags", "music_mood")}
        old["scenes"] = [{"speaker": sc.get("speaker"), "narration": sc.get("voice_text") or sc.get("narration"),
                          "image": sc.get("image")} for sc in previous.get("scenes") or []]
        user += (
            "\nThis is a REDO. The earlier version of this Short (JSON):\n"
            f"{json.dumps(old, ensure_ascii=False)}\n\n"
            f"The channel owner watched it and wants this changed:\n{feedback.strip()}\n"
            "Write a new version that does what the feedback asks. Keep what the feedback does "
            "not mention when it worked; every hard rule above still applies.\n"
        )
    system = WRITER_SYSTEM.format(characters=characters, kit=KIT_SUMMARY, moods="|".join(music.MOODS))
    script, convo = _ask_json(system, [{"role": "user", "content": user}], validate_dialogue,
                              model=config.SCRIPT_MODEL, effort=config.SCRIPT_EFFORT, step="script")

    if config.CLARITY_MIN > 0:
        try:
            clarity = check_clarity(script)
            if clarity["score"] < config.CLARITY_MIN:
                fix = ("A test viewer heard these lines once and understood: "
                       f"\"{clarity['understood']}\" (clarity {clarity['score']}/10).\n"
                       "What confused them:\n" + "\n".join(f"- {p}" for p in clarity["problems"]) +
                       "\nRewrite the lines so this viewer gets the idea at first listen. Keep the hook, "
                       "the characters and every rule. Return the full JSON only.")
                script, _ = _ask_json(system, convo + [{"role": "user", "content": fix}], validate_dialogue,
                                      model=config.SCRIPT_MODEL, effort="medium", step="script_fix")
                clarity = {**check_clarity(script), "before": clarity["score"]}
            script["clarity"] = clarity
        except RuntimeError as exc:      # the check is a safety net, never a reason to stop
            print(f"[script] clarity check skipped: {exc}")
    return validate(stage_scenes(script, book), book)


def load_book(slug: str) -> dict[str, Any]:
    path = config.BOOKS_DIR / slug / "book.json"
    if not path.exists():
        raise FileNotFoundError(f"Unknown book '{slug}' (no {path})")
    return json.loads(path.read_text())


def load_learnings() -> str:
    """The owner's notes, the numbers of posted Shorts and Claude's playbook (see learn.py)."""
    from . import learn, pipeline
    return learn.text(pipeline.list_shorts())
