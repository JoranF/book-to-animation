# Hoe een Short gemaakt wordt

De technische details staan in de [README](../README.md) van de repo (Engels).
Dit is de uitleg in gewone taal, voor wie het moet leren.

## Van boek tot video in 5 stappen

`boek + episode` gaat erin, `short.mp4` komt eruit (9:16, 30-60 s, Engels).

| # | Stap | Wat gebeurt er | Code |
| --- | --- | --- | --- |
| 0 | **Episodeplan** | Het boek is opgeknipt in hoofdstukken ("nachten") met per hoofdstuk afleveringen. Elke aflevering is één smal idee met een eigen hook, invalshoek en format (myth_buster, mini_story, one_question, dialogue, challenge, reframe). *The Courage to Be Disliked* heeft er 45 (`n1-01` t/m `n5-10`). "Next" pakt de eerste die nog niet gemaakt is, en de hoofdstukken wisselen elkaar af | `books/<boek>/episodes.json`, `b2a/plan.py` |
| 1 | **Script** | Claude schrijft een snel gesprek tussen de Jongeman en de Filosoof (verteller alleen voor overgangen), in eigen woorden, geen citaten uit het boek. Elke zin krijgt regie voor de stem (`[sighs]`, `[pause]`) en een 3D-"stage": welke set, props, wie staat waar, welke beweging, welke camera. Ook kiest Claude een muziekstemming | `b2a/llm.py`, `b2a/script.py`, `b2a/stage.py` |
| 2 | **Stem** | ElevenLabs Eleven v4 spreekt elke zin in met de stem van dat personage, met tijdstempels per woord voor de captions. Weigert v4, dan Multilingual v2; zonder key de gratis Piper-stem | `b2a/voice.py` |
| 3 | **Beeld** | Headless Blender bouwt de low-poly personages en sets in code en rendert elke scène (360x640, 15 fps, CPU). Mond beweegt bij praten, luisteraar reageert (schrikken, facepalm, lachen), camera wisselt tussen two-shot en close-ups | `b2a/world.py`, `b2a/blender_render.py`, `b2a/visuals.py` |
| 4 | **Montage** | FFmpeg knipt op de stem, legt het CRT-filter erover, brandt captions woord voor woord in (font Press Start 2P), mixt retro-geluidseffecten en muziek, en normaliseert het volume | `b2a/render.py`, `b2a/sfx.py`, `b2a/music.py` |

Een Short rendert in ~6-10 minuten op 4 cores. Kosten: alleen Claude en
ElevenLabs, ruwweg $0,10-0,40 per Short (de prijzen in `meta.json` zijn een
schatting).

## Wat er per Short wordt opgeslagen

In `/data/shorts/<id>/` (op de server in het volume `book-to-animation-data`):

- `short.mp4`, `thumb.jpg`
- `script.json`: het complete script met scènes
- `meta.json`: alles om van te leren: episode, hoofdstuk, format, hook en
  hooktype, lengte, aantal woorden en scènes, sets, stem, muziek, SFX,
  trend-brief, kosten, review-status (`pending` / `approved` / ...) en wat er
  gepost is

Elke stap wordt gecachet. Een mislukte run kun je afmaken met `--id <id>`.

## Extra's

- **Geluidseffecten**: 9 soorten 8-bit geluiden (sting op de hook, whoosh bij
  een cut, geluid bij een reactie, chime aan het eind), in code gemaakt met
  een Python-versie van jsfxr. Sampler: `sfx/retro-sfx-sampler.mp3` in de projectbestanden.
- **Muziek**: per stemming (curious, tense, warm, playful, melancholy,
  triumphant) 4 nummers van ACE-Step, daarna hergebruikt. Zonder ACE-Step:
  chiptune uit code. Eigen `.mp3` in `assets/music/` wint altijd.
- **Trend research**: wekelijks zoeken op YouTube (yt-dlp) en Reddit (gratis),
  plus TikTok via ScrapeCreators. Claude maakt er een brief van (onderwerpen,
  hookpatronen, wat te vermijden, en per episode een score 0-10). Die brief
  gaat 14 dagen mee in de scriptprompt en bepaalt welke episode "next" wordt.
  Draaien: `python -m b2a.cli trends` of `POST /api/trends`. *Er is nog geen
  wekelijkse planning voor ingesteld.*
- **Leren van resultaten**: alles wat in `data/learnings.md` staat, krijgt de
  scriptschrijver bij elke nieuwe Short mee. Het dashboard (stream-clipper)
  haalt views/likes per post uit Postiz.

## Commando's (in de container of lokaal)

```bash
python -m b2a.cli episodes                    # plan bekijken (x = al gemaakt)
python -m b2a.cli make --episode n2-06        # één episode
python -m b2a.cli make --episode next         # volgende uit het plan
python -m b2a.cli make --topic "..." --idea "..."   # vrij onderwerp
python -m b2a.cli trends                      # trend research
python -m b2a.cli sfx                         # hele SFX-bibliotheek maken
python -m b2a.cli music                       # muziekbibliotheek vullen (ACE-Step)
python -m b2a.cli plan --book <slug>          # episodeplan voor een nieuw boek
```

In Dokploy open je een shell in de container via de app → *Docker Terminal*.

## Een nieuw boek toevoegen

1. Maak `books/<slug>/book.json` (titel, auteur, hoofdstukken, personages, trend-zoekwoorden).
2. `python -m b2a.cli plan --book <slug>` laat Claude een episodeplan maken.
3. **Lees het plan zelf door**, pas aan wat niet klopt, en commit het.
4. Nieuwe sets, props of bewegingen nodig? Voeg ze toe in zowel
   `b2a/world.py` (de vormen) als `b2a/stage.py` (de catalogus die Claude krijgt).

## Regels voor de inhoud

- Eigen woorden en eigen voorbeelden, nooit lange stukken uit het boek.
- Alle personages en werelden zijn eigen ontwerpen uit simpele vormen.
- Gratis Piper-stem gebruikt? Zet "LibriTTS" (CC BY 4.0) in de beschrijving.
- YouTube demonetiseert "inauthentic content" (sjabloonvideo's met weinig
  variatie). Varieer daarom sets, problemen en eindes, kijk elke video na voor
  hij live gaat, en vink de AI-melding aan.
