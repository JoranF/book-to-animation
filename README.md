# book-to-animation

Turns an idea from a philosophy book into a finished vertical YouTube Short
(9:16, 30 to 60 seconds, English) that looks like a late-90s low-poly 3D
console game on an old TV. First book: *The Courage to Be Disliked*, with the
Philosopher and the Youth as recurring characters.

## How it works

`book + episode` goes in, `short.mp4` comes out.

| Step | What | How |
| --- | --- | --- |
| 0. Episode plan | Every book is split into chapters with a list of episodes. One episode is one narrow idea with its own hook, angle and format, so the Shorts do not all look alike | `books/<book>/episodes.json`, `b2a/plan.py` |
| 1. Script | Hook, a fast conversation between the youth and the philosopher in our own words, original examples, no book quotes. Also describes every scene as a 3D "stage". | Claude API (`ANTHROPIC_API_KEY`), `b2a/llm.py` |
| 2. Voice | Fixed voices with word timings for captions. A scene can be spoken by the narrator, the philosopher or the youth (`"speaker"`) | ElevenLabs with `ELEVENLABS_API_KEY`, else the free built-in Piper voice |
| 3. Visuals | Real low-poly 3D: characters, sets, props and movements are built in code and rendered by headless Blender | `b2a/world.py` |
| 4. Edit | Cuts on the voice, CRT look, word-by-word captions, chiptune music composed in code, loudness | FFmpeg |

Because the pictures and the music are made on our own server, a Short only
costs the script (Claude) and the voice (ElevenLabs): roughly $0.10 to $0.40,
or nothing with the free voice and a ready-made script. `meta.json` stores an
estimate per Short (the prices behind it are assumptions, see `.env.example`).
Rendering takes roughly 6 to 10 minutes on 4 CPU cores, no GPU needed.

### Episodes

*The Courage to Be Disliked* has 45 planned episodes over the five nights of
the book. Each has an id (`n2-06`), a hook, an angle with an example of our
own, and one of six formats (myth_buster, mini_story, one_question, dialogue,
challenge, reframe). "Next" takes the first episode without a Short and lets
the chapters take turns. The script writer also gets the hooks of the last 15
Shorts and is told to build this one differently. A free topic still works.

For a new book: add `books/<slug>/book.json`, run
`python -m b2a.cli plan --book <slug>`, read the plan through and commit it.

### Characters that talk to each other

Every scene is one line with a `"speaker"`: narrator, philosopher or youth,
each with their own voice. Scripts are written as a quick back-and-forth (the
youth objects and jokes, the philosopher answers short), with the narrator
only for bridges. In the 3D scene the speaker's mouth moves automatically,
`"look_at"` turns actors toward each other, the listener gets a reaction
(`startle`, `facepalm`, `shake_head`, `laugh`, `shrug`) and the camera cuts
between a two-shot and close-ups with `"focus"`.

### The 3D kit

The characters are always exactly the same because they are models, not
generated images. A scene is plain data:

```json
{"set": "study",
 "props": [{"type": "fireplace", "pos": [0.1, 4.15]}],
 "actors": [{"who": "philosopher", "pos": [0, 0.6], "action": "stop"}],
 "camera": {"move": "push_in", "target": [0, 0.6, 0.7], "dist": 3.5, "height": 1.15}}
```

`b2a/stage.py` lists everything a scene may use (7 sets, 4 kinds of people,
21 movements, 23 props, 6 camera moves) and is the manual the script writer
gets. `b2a/world.py` holds the shapes and movements. New sets, props or
movements are added in both files.

## Run it

```bash
pip install -r requirements.txt        # also needs ffmpeg
# free voice (once):
mkdir -p voices && curl -L https://github.com/rhasspy/piper/releases/download/v0.0.2/voice-en-us-libritts-high.tar.gz | tar xz -C voices

# show the plan (x = already made):
python -m b2a.cli episodes

# an episode with a ready-made script, no key needed:
python -m b2a.cli make --episode n2-06

# let Claude write the next episode:
export ANTHROPIC_API_KEY=...
python -m b2a.cli make --episode next

# or a free topic:
python -m b2a.cli make --topic "Why you check your phone" --idea "..."
```

Output lands in `data/shorts/<id>/`: `short.mp4`, `thumb.jpg`, `script.json`,
`meta.json`. Every step is cached there, so a failed run can be continued with
`--id <id>`.

## Web app (Dokploy)

The Docker image starts a small web app on port 8000: pick an episode (or the
next one), follow the progress, and watch and download results in a gallery.
Set `APP_PASSWORD` (the login password, any username), `ANTHROPIC_API_KEY`
(script writing) and `ELEVENLABS_API_KEY` (voices) in the Environment tab, and
mount a volume at `/data`.

API: `GET /api/episodes?book=`, `POST /api/shorts {"book","episode"}` (an id
or `"next"`; or `"topic"` and `"idea"` for a free topic), `GET /api/shorts`,
`GET /api/shorts/{id}`, `GET /files/{id}/short.mp4`,
`PATCH /api/shorts/{id}/feedback`.

## Feedback loop

`meta.json` stores what we want to learn from per video: episode, chapter,
format, topic, hook, hook
type, length, word count, scene count, sets used, voice and cost, plus empty
`youtube` and `analytics` blocks. The upload and analytics steps (later) fill
those through `PATCH /api/shorts/{id}/feedback`. Whatever is written to
`data/learnings.md` is given to the script writer on every new Short.

## Tests

```bash
pip install pytest httpx && python -m pytest
```

Runs offline. It draws one frame of every example scene with Blender and
renders a full edit with placeholder media.

## Notes

- Captions use Press Start 2P (SIL Open Font License, see `assets/fonts`).
- The free voice is the Piper LibriTTS model (CC BY 4.0: credit "LibriTTS" in
  the video description when you use it).
- Drop `.mp3` or `.wav` files in `assets/music/` to use your own music.
- Scripts explain ideas in original words and never quote the book.
- All characters and worlds are original designs made from simple shapes.
