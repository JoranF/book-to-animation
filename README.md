# book-to-animation

Turns an idea from a philosophy book into a finished vertical YouTube Short
(9:16, 30 to 60 seconds, English) that looks like a late-90s low-poly 3D
console game on an old TV. First book: *The Courage to Be Disliked*, with the
Philosopher and the Youth as recurring characters.

## How it works

`book + topic (+ idea)` goes in, `short.mp4` comes out.

| Step | What | How |
| --- | --- | --- |
| 1. Script | Hook, explanation in our own words, original examples, no book quotes. Also describes every scene as a 3D "stage". | Claude through fal's OpenRouter endpoint |
| 2. Voice | Fixed voices with word timings for captions. A scene can be spoken by the narrator, the philosopher or the youth (`"speaker"`) | ElevenLabs with `ELEVENLABS_API_KEY`, else ElevenLabs through fal, else the free built-in Piper voice |
| 3. Visuals | Real low-poly 3D: characters, sets, props and movements are built in code and rendered by headless Blender | `b2a/world.py` |
| 4. Edit | Cuts on the voice, CRT look, word-by-word captions, chiptune music composed in code, loudness | FFmpeg |

Because the pictures and the music are made on our own server, a Short costs
about $0.10 (script and premium voice) or nothing at all with the free voice
and a ready-made script. Rendering takes roughly 6 to 10 minutes on 4 CPU
cores, no GPU needed.

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
15 movements, 23 props, 6 camera moves) and is the manual the script writer
gets. `b2a/world.py` holds the shapes and movements. New sets, props or
movements are added in both files.

## Run it

```bash
pip install -r requirements.txt        # also needs ffmpeg
# free voice (once):
mkdir -p voices && curl -L https://github.com/rhasspy/piper/releases/download/v0.0.2/voice-en-us-libritts-high.tar.gz | tar xz -C voices

# from a ready-made script, no key needed:
python -m b2a.cli make --topic "Separation of tasks" \
  --script books/courage-to-be-disliked/examples/separation-of-tasks.json

# let Claude write the script (needs FAL_KEY with credits):
export FAL_KEY=...
python -m b2a.cli make --topic "Life is not a competition"
```

Output lands in `data/shorts/<id>/`: `short.mp4`, `thumb.jpg`, `script.json`,
`meta.json`. Every step is cached there, so a failed run can be continued with
`--id <id>`.

## Web app (Dokploy)

The Docker image starts a small web app on port 8000: a form to start a Short,
progress, and a gallery to watch and download results. Set `APP_PASSWORD` (the
login password, any username), `ELEVENLABS_API_KEY` (voices) and `FAL_KEY`
(script writing) in the Environment tab, and mount a volume at `/data`.

API: `POST /api/shorts {"book","topic","idea"}`, `GET /api/shorts`,
`GET /api/shorts/{id}`, `GET /files/{id}/short.mp4`,
`PATCH /api/shorts/{id}/feedback`.

## Feedback loop

`meta.json` stores what we want to learn from per video: topic, hook, hook
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
