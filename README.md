# book-to-animation

Turns an idea from a philosophy book into a finished vertical YouTube Short
(9:16, 30 to 60 seconds, English) in a late-90s low-poly 3D game style with a
CRT filter. First book: *The Courage to Be Disliked*, with the Philosopher and
the Youth as recurring characters.

## How it works

`book + topic (+ idea)` goes in, `short.mp4` comes out. Four steps, all through
[fal](https://fal.ai) with one key:

| Step | What | Model (default) |
| --- | --- | --- |
| 1. Script | Hook, explanation in our own words, original examples, no book quotes | Claude via fal's OpenRouter endpoint |
| 2. Voice | One fixed voice, with word timings for captions | ElevenLabs v4 (`Brian`) |
| 3. Visuals | Character reference per book (made once), one image per scene, short animation per scene | Nano Banana 2, H3 Max Turbo |
| 4. Edit | Cuts on the voice, CRT look, word-by-word captions, music, loudness | FFmpeg |

Estimated cost per Short: about $1.50 to $2 (9 scenes, all animated). Set
`ANIMATE=3` to animate only the first three scenes (the rest gets a camera
move) for roughly $1, or `ANIMATE=none` for about $0.90.

The look lives in `b2a/style.py`. Books live in `books/<slug>/book.json`.
Models, voice and prices live in `b2a/config.py` and can be overridden with
environment variables.

## Run it

```bash
pip install -r requirements.txt        # also needs ffmpeg
export FAL_KEY=...                      # never commit this
python -m b2a.cli make --topic "Separation of tasks"
# or reuse a hand-checked script:
python -m b2a.cli make --topic "Separation of tasks" \
  --script books/courage-to-be-disliked/examples/separation-of-tasks.json
```

Output lands in `data/shorts/<id>/`: `short.mp4`, `thumb.jpg`, `script.json`,
`meta.json`. Every step is cached there, so a failed run can be continued with
`--id <id>` without paying twice.

## Web app (Dokploy)

The Docker image starts a small web app on port 8000: a form to start a Short,
progress, and a gallery to watch and download results.

1. In Dokploy create an Application from this repo (build type: Dockerfile).
2. Environment: `FAL_KEY` and `APP_PASSWORD` (the login password, any username).
3. Add a volume mounted at `/data` so videos survive a redeploy.
4. Add a domain pointing to port 8000.

API: `POST /api/shorts {"book","topic","idea"}`, `GET /api/shorts`,
`GET /api/shorts/{id}`, `GET /files/{id}/short.mp4`,
`PATCH /api/shorts/{id}/feedback`.

## Feedback loop

`meta.json` stores what we want to learn from per video: topic, hook, hook
type, length, word count, scene count, voice, models and cost, plus empty
`youtube` and `analytics` blocks. The upload and analytics steps (later) fill
those through `PATCH /api/shorts/{id}/feedback`. Whatever is written to
`data/learnings.md` is given to the script writer on every new Short.

## Tests

```bash
pip install pytest httpx && python -m pytest
```

The tests run offline: fal is replaced by placeholder media and the full edit
is rendered with FFmpeg.

## Notes

- Captions use Press Start 2P (SIL Open Font License, see `assets/fonts`).
- Drop `.mp3` files in `assets/music/` to use your own music instead of
  generating a track per Short.
- Scripts explain ideas in original words and never quote the book.
