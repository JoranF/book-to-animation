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
| 2. Voice | Fixed voices with word timings for captions. A scene can be spoken by the narrator, the philosopher or the youth (`"speaker"`) | ElevenLabs Eleven v4 with `ELEVENLABS_API_KEY` (follows delivery tags like `[sighs]` and `[pause]` that the script writer puts in each line; falls back to Multilingual v2 if v4 is refused), else the free built-in Piper voice |
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

### Books

Nine books have a plan: *The Courage to Be Disliked* (45 episodes) and eight
public-domain classics, about 15 episodes each: *Meditations* (Marcus
Aurelius), *On the Shortness of Life* (Seneca), *The Enchiridion*
(Epictetus), *The Prince* (Machiavelli), *The Art of War* (Sun Tzu), *Beyond
Good and Evil* (Nietzsche), *The Wisdom of Life* (Schopenhauer) and *Habit*
(William James). Public-domain books carry no takedown risk, modern ones do.
`GET /api/books` lists them with how many episodes are made. `POST
/api/shorts` with `"book": "auto"` picks the book with the fewest Shorts that
still has episodes left, so an autopilot takes turns between books.

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
gets. `b2a/world.py` holds the shapes. New sets, props or movements are
added in `stage.py` and in `world.py` (sets, props) or `motion.py` (movements).

### How the characters move (pose to pose)

`b2a/motion.py` animates like a key-pose animator instead of looping sine
waves. Every action is a short sequence of strong key poses from a library of
about 40 (hand on chest, palms up, finger raised, hands on hips, arms crossed,
hand to chin...). The inbetweens use easing that fits the move: slow in and
out, a snap with a small overshoot for a gesture stroke, a heavy drop for a
slump. Big moves get anticipation (a dip before a jump, the arm pulled back
before a point), the head and forearms drag a few frames behind the body
(overlap and follow-through), and held poses keep breathing and drifting
(moving holds). Arms, weight shifts and glances run on separate layers.

Which poses, in what order and on which hand is a seeded choice per shot, so
a `talk` in the close-up and in the two-shot never look the same. The
speaker's gesture strokes and head nods land on stressed words, taken from the
voice's word timings. The mood sets the energy: angry is fast and big, sad is
slow and small with the head down. The philosopher keeps his cane hand low and
gestures with the other one, except when he points with the cane. An actor
can also play several actions in one shot: `"actions": ["talk", "shrug"]`.

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
`PATCH /api/shorts/{id}/feedback`, and the Studio contract below.

## Sound effects

`b2a/sfx.py` makes retro 8-bit sound effects in code with a Python port of
the sfxr synth from [jsfxr](https://github.com/chr15m/jsfxr) (public
domain). Nine kinds (sting, whoosh, blip, jump, thud, laugh, no, down, chime),
three seeded variants each, cached in `DATA_DIR/sfx/`. The editor places them
from the script: a sting on the hook, a soft whoosh on every cut, a sound for
the listener's reaction (startle = jump, facepalm = thud, laugh, shake head,
slump or shrug) and a chime on the last line, at most two per scene.
`meta.json` lists which kinds a Short used, so the analytics can compare.
`SFX_VOLUME` (default 0.25, 0 = off), `SFX_VARY=0` keeps one variant per kind.
`python -m b2a.cli sfx` makes the whole library to listen to.

## Music (ACE-Step on the GPU)

The script writer picks a `music_mood` (curious, tense, warm, playful,
melancholy, triumphant). With `ACESTEP_URL` set, the music comes from
[ACE-Step 1.5](https://github.com/ace-step/ACE-Step-1.5) (open model, MIT),
running as its own Dokploy Compose app on the GPU: `musicgen/docker-compose.yml` with its own `musicgen/Dockerfile` (swaps in the CUDA 12.6 build of PyTorch, because the 12.8 build has no kernels for our Pascal GTX 1050 Ti).
Every mood gets a prompt in the late-90s console style, instrumental, with a
fixed tempo and key. Tracks are kept in `DATA_DIR/music/<mood>/` and reused
once a mood has `MUSIC_PER_MOOD` tracks (default 4), so the GPU only works
while the library fills. `python -m b2a.cli music` fills it in one go.
If ACE-Step is missing or fails, the chiptune made in code is used, so music
never stops a Short. Tracks in `assets/music/` still win over both.

| Variable | What |
| --- | --- |
| `ACESTEP_URL` | `http://b2a-acestep:8001` (the compose app, over dokploy-network) |
| `ACESTEP_API_KEY` | Same random string as in the compose app |
| `MUSIC_BACKEND` | `auto` (default) or `chiptune` to switch ACE-Step off |
| `MUSIC_PER_MOOD`, `ACESTEP_TIMEOUT` | Library size per mood (4), seconds per track (900) |

The server needs the NVIDIA driver and the NVIDIA Container Toolkit
(`nvidia-smi` and `docker run --rm --gpus all ubuntu nvidia-smi` must work).

## Trend research

`b2a/trends.py` follows the workflow of the ScrapeCreators "trend-discovery"
and "outlier-post-finder" skills: search a few niche queries (`trends` in
`book.json`), keep the numbers, score every post by its lift over the median
of the same search, and let Claude write a brief: topics, hook patterns,
formats, viewer problems, what to avoid, and a 0-10 trend fit for every
planned episode. Sources: YouTube via yt-dlp and Reddit top of the week (free),
plus TikTok and YouTube search through ScrapeCreators when
`SCRAPECREATORS_API_KEY` is set (about 1 credit per search). A source that
fails is skipped and noted.

The brief (kept 14 days, `TRENDS_MAX_AGE_DAYS`) goes into the script prompt
("use what fits, never copy a hook"), and "next episode" picks the
best-fitting episode inside the chapter whose turn it is. `meta.json` records
which brief a Short was written with. Run it weekly:
`python -m b2a.cli trends`, or `POST /api/trends` (then `GET /api/trends`).

## Studio: one dashboard for every pipeline

`studio/` is a second, small app (its own Docker image, `studio/Dockerfile`,
no Blender inside). It is the one place to log in, review the videos of every
pipeline and send them to Postiz. The pipelines stay separate apps and know
nothing about Postiz.

Each pipeline is a tab. A pipeline plugs in by offering a tiny contract
(described in `studio/sources.py`) behind HTTP basic auth with its own
password: `GET /api/items?status=`, the video file, and optionally
`POST /api/items/{id}/status` and `POST /api/items/{id}/sent`. This app
offers it for its Shorts; the stream clipper offers the same.

In Studio: Approve or Reject a pending video, then "Post with Postiz" on an
approved one: tick the channels (YouTube, TikTok, Instagram, ...), leave the
time empty to post now or pick a time to schedule. Studio downloads the video
from the pipeline, uploads it to Postiz with fitting settings per platform
(`studio/postiz.py`) and tells the pipeline what was sent (kept in `meta.json`
under `posts`). Nothing is posted automatically.

Settings of the Studio app:

| Variable | What |
| --- | --- |
| `STUDIO_PASSWORD` | Login password of the dashboard (any username) |
| `POSTIZ_URL`, `POSTIZ_API_KEY` | Your Postiz server and its API key |
| `SOURCE_SHORTS_URL`, `SOURCE_SHORTS_PASSWORD` | This app's address and its `APP_PASSWORD` |
| `SOURCE_CLIPS_URL`, `SOURCE_CLIPS_PASSWORD` | The stream clipper's address and its `REVIEW_PASSWORD` |

Any other pipeline: `SOURCE_<NAME>_URL` and `SOURCE_<NAME>_PASSWORD` give a
tab called Name. Set `STUDIO_URL` on this app to show a link to Studio.

Run it locally: `uvicorn studio.app:app --port 8001`.

## Feedback loop

`meta.json` stores what we want to learn from per video: episode, chapter,
format, topic, hook, hook
type, length, word count, scene count, sets used, voice, music mood and
source, sound effects, trend brief and cost, plus empty
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
