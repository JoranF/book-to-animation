# Logboek

Wat er wanneer gedaan is, nieuwste onderaan per dag. Voeg bij elke
verandering een regel toe (datum, wat, waarom, link naar PR/commit).

## 26-11-2026: start en eerste pipeline

- Idee: filosofieboeken → geanimeerde Shorts, eerst *The Courage to Be Disliked*.
  Advies vooraf: semi-automatisch starten, eigen invalshoek (YouTube-regels
  voor AI-content), ~10 Shorts testen voor verder automatiseren.
- Keuzes van Joran: **geen Higgsfield**; stijl late-90s low-poly 3D met CRT;
  taal Engels; draaien op eigen Dokploy-server.
- Eerste versie met fal voor beelden en scripts (commit `20ee8b2`), maar fal-
  tegoed op en wens voor meer controle → overgestapt op **headless Blender**
  voor echte low-poly 3D en **ElevenLabs** voor stemmen (`94f058d`).
- Joran: "per hoofdstuk één idee, anders lijkt alles op elkaar" → **episodeplan**
  van 45 afleveringen; scripts via **Claude API** in plaats van fal; fal
  helemaal verwijderd; personages die echt met elkaar praten (`7fdaf4a`).
- Stemmen naar **Eleven v4** met regie-tags en pauzes (`45cac18`).
- Postiz gekozen als tool voor meerdere accounts/platforms en zelf gehost op
  Dokploy (postiz.joranit.com).
- Posten via Postiz vanuit de webapp (`73690f6`), daarna één dashboard voor
  alle pipelines (`105a02f`), en die als losse **Studio**-app (`e94fc59`,
  studio.joranit.com).
- Onderzoek engagement + analytics-loop: playbook met creatieve standaarden
  (hook op 0 s, 20-40 s, elke 1,5-3 s een nieuw beeld, captions woord voor
  woord, loop-einde). Gratis analytics via YouTube Analytics API / Postiz.
- Plan voor long form gemaakt (12-16 min, niets gebouwd).
- Domeinen van sslip.io naar `*.joranit.com` via Cloudflare. book.joranit.com
  gaf geen site: domeinpoort stond op 3000 → **8000** gezet.
- Env-variabelen: Claude kan ze niet veilig via de connector zetten (alles
  wordt vervangen) → Joran plakt zelf.

## 27-11-2026: geluid, muziek, GPU, één dashboard

- Uit de resourcelijst van Nick Saraev gekozen: **jsfxr** (retro SFX),
  **ACE-Step 1.5** (muziek op eigen GPU), **trend research**
  (ScrapeCreators-skills). Blender MCP en mocap bewust nog niet.
- [PR #1](https://github.com/JoranF/book-to-animation/pull/1) gemerged: SFX,
  ACE-Step-koppeling, trends.
- GPU-traject:
  - Dokploy zag geen GPU. `lspci`: **GTX 1050 Ti** (Pascal).
  - Driver **580** + NVIDIA Container Toolkit geïnstalleerd door Joran.
  - nvidia als standaard Docker-runtime gezet → **Dokploy plat** (Traefik
    Exited, 521/502). Teruggezet; GPU wordt nu per compose aangevraagd.
  - torch cu128 heeft geen sm_61 → eigen `musicgen/Dockerfile` met **cu126**.
  - Eerste build faalde op de eigen GPU-check (geen GPU tijdens build) →
    [PR #2](https://github.com/JoranF/book-to-animation/pull/2): check op
    ingebakken lijst, Python via uv. Pascal-check geslaagd.
  - acestep-app in Dokploy aangemaakt (auto-deploy uit), staat tijdelijk op
    de branch van PR #2. Laatste deploy: status **error/onbekend**, eerste
    start nog niet gezien.
- Postiz nagelopen: 6 containers op, configuratie zonder fouten, account
  bestaat. Uitgezocht wat nodig is voor YouTube- en TikTok-koppeling en audits.
- stream-clipper werd het **ene dashboard** voor clips én Book Shorts
  (stream-clipper PR #3). De Studio-app hier is daardoor niet meer nodig.
- [PR #3](https://github.com/JoranF/book-to-animation/pull/3) (open): de
  bolling (barrel warp) uit het CRT-effect gehaald.
- Documentatie (deze map) gestart.

## 28-11-2026: feedback-loop en automatisch posten

- Joran: "de feedback-functie ook voor de boekvideo's, en het moet zichzelf verbeteren
  op analytics en mijn feedback". Redo met feedback, vaste notities, cijfers uit Postiz
  in de script-prompt en een Claude-playbook vanaf 8 geposte Shorts (`b2a/learn.py`,
  [PR #7](https://github.com/JoranF/book-to-animation/pull/7)). Zie
  [feedback-loop-en-autopost.md](feedback-loop-en-autopost.md).
- In het clipper-dashboard: automatisch posten per account aan/uit en clips van één
  upload spreiden over dagen ([stream-clipper PR #9](https://github.com/JoranF/stream-clipper/pull/9)).

## 28-11-2026: kosten per Short omlaag en duidelijkere scripts

- Joran: "videos kosten nu 40 cent in plaats van 10, wat is er veranderd?" en "de
  verhalen zijn soms moeilijk te begrijpen". Gemeten in de `meta.json`'s op de server:
  niets was duurder geworden. De Short van 11 cent (n1-02 *Anger is a tool*) had een
  handgeschreven voorbeeldscript, dus geen Claude-aanroep. Alle Shorts met een
  Claude-script kostten $0,35-0,48: Claude ~$0,21-0,35 (Opus 5.5 op effort high,
  7.700-12.700 output-tokens, vooral denkwerk en de lange 3D-regie-JSON) en de stem
  ~$0,11-0,14. De schatting rekende bovendien met $5/$25 in plaats van de echte
  Opus 5.5-prijs $4/$20.
- Script nu in stappen op het model dat erbij past: Opus schrijft alleen de dialoog,
  Sonnet 5.5 doet een duidelijkheidscheck (score 1-10, één herkansing onder de 7) en
  de 3D-regie (`"props": "same"` scheelt herhaling). Trend-brief en playbook ook op
  Sonnet. Shorts korter: 80-105 woorden, 8-12 scènes (35-45 s). Schrijfregels voor
  duidelijkheid: één idee in één zin, één alledaagse situatie van begin tot eind,
  geen jargon, payoff recht uitgesproken. `meta.json` krijgt kosten per stap,
  tokens per model en de duidelijkheidsscore; het dashboard toont ze.
  Nieuwe env-namen: `STAGE_MODEL`, `STAGE_EFFORT`, `CHECK_MODEL`, `CHECK_EFFORT`,
  `CLARITY_MIN`, `ANALYSIS_MODEL`, `ANALYSIS_EFFORT`.
- Joran: "geef in de webfront de opties welk model voor wat". Per stap (dialoog,
  3D-regie, duidelijkheidscheck, trends/playbook) model en effort kiezen, plus de
  duidelijkheidsdrempel, in het dashboard en op book.joranit.com. Opgeslagen in
  `DATA_DIR/model_settings.json` (`b2a/settings.py`), API `GET/PUT /api/settings/models`;
  de env-variabelen blijven de standaard. Geldt vanaf de volgende Short.

## 28-11-2026: asset library voor personages, props en achtergronden

- Joran: "worden personages, items en achtergronden opgeslagen zodat we ze kunnen
  hergebruiken, en als er iets nieuws nodig is of iets opnieuw moet, automatisch
  toevoegen of opnieuw maken?" Antwoord: de vaste kit (cast, 7 sets, 23 props) stond
  al in code en zag er dus altijd hetzelfde uit, maar iets nieuws kon niet: de regie
  moest zich behelpen met de kit.
- Nieuw: **asset library** (`b2a/assets.py`, zie [asset-library.md](asset-library.md)).
  De 3D-regie mag nieuwe props, sets en (zwijgende) personages aanvragen; eerst wordt
  op naam, alias en tags hergebruikt, anders ontwerpt `ASSET_MODEL` (Sonnet 5.5) een
  low-poly recept dat in `/data/assets` wordt bewaard, met preview-PNG. Assets kun je
  markeren voor rebuild (met notitie), ook ingebouwde props en sets; de Jongeman en de
  Filosoof zitten op slot. Beheer via book.joranit.com (*Asset library*), de API
  `/api/assets` en `python -m b2a.cli assets`. Nieuwe env-namen: `ASSET_MODEL`,
  `ASSET_EFFORT`, `ASSET_MAX_NEW`, `ASSET_PREVIEWS`. `meta.json` krijgt
  `assets_made` en `assets_used`.
