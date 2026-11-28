# Opzetten op Dokploy (stap voor stap)

Zo zet je alles vanaf nul op, of controleer je of het nog klopt. Volgorde:
Postiz → book-to-animation → stream-clipper (dashboard) → acestep (optioneel).

## Gouden regels

1. **Geheimen alleen in Dokploy.** Elke app heeft een tabblad *Environment*.
   Daar komen de keys en wachtwoorden. Nooit in git, nooit in een chat (ook niet
   met Claude).
2. **Environment opslaan vervangt alles.** Dokploy (en de Claude-connector)
   slaat het Environment-veld in één keer op. Wie via de API één regel wil
   toevoegen zonder de rest te kennen, wist de bestaande geheimen. Voeg regels
   dus zelf toe in de browser en laat de rest staan. Claude kan de waarden niet
   zien (ze komen terug als `[REDACTED]`), en geeft daarom regels om te plakken.
3. **Domeinpoort = de poort van de app**, niet de standaard 3000. Al onze
   eigen apps luisteren op **8000**, Postiz op **5000**.
4. **Deploy na elke env-wijziging** (knop *Deploy* of *Redeploy*), anders ziet
   de container de nieuwe waarde niet.
5. Na een push naar de ingestelde branch bouwt Dokploy zelf opnieuw
   (auto-deploy). book-to-animation bouwt ~15 minuten, stream-clipper ~1-2
   minuten, acestep ~45 minuten.

## Voorbereiding

- Een server met Dokploy (en daarmee Docker en Traefik).
- In Dokploy: *Settings → Git* de **Dokploy GitHub App** geïnstalleerd op
  `JoranF/book-to-animation` en `JoranF/stream-clipper`.
- In Cloudflare een A-record per subdomein (`book`, `clipper`, `postiz`,
  eventueel `studio`) naar het IP van de server. Proxy (oranje wolk) mag aan;
  zet SSL/TLS dan op **Full** zodat Cloudflare HTTPS naar Traefik praat.

## 1. Postiz

1. Nieuw project `postiz` → *Create Service → Template* → **Postiz**.
2. Domein: `postiz.joranit.com`, service `postiz-app`, poort **5000**, HTTPS met Let's Encrypt.
3. Environment (namen; waarden zelf kiezen of uit de developer-portals):
   - `POSTIZ_HOST`, `JWT_SECRET`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`, `TEMPORAL_USER`, `TEMPORAL_PASSWORD`
   - `DISABLE_REGISTRATION` — **zet op `true` zodra je eigen account bestaat**, anders kan iedereen zich registreren (standaard `false`!)
   - Per platform dat je wilt koppelen: `YOUTUBE_CLIENT_ID`/`YOUTUBE_CLIENT_SECRET`, `TIKTOK_CLIENT_ID`/`TIKTOK_CLIENT_SECRET` (ook beschikbaar: Facebook, Instagram, LinkedIn, X)
   - Optioneel `OPENAI_API_KEY` (alleen voor de AI-chat in Postiz; zonder deze key loopt die vast, de rest werkt)
4. Deploy. Er draaien 6 containers. In de logs van de backend hoort
   "Configuration check completed without any issues" te staan.
5. Log in, maak je account, zet daarna `DISABLE_REGISTRATION=true` en redeploy.
6. *Settings → Public API*: maak de API-key. Die gaat als `POSTIZ_API_KEY` naar stream-clipper.

YouTube en TikTok koppelen: zie [postiz-en-publiceren.md](postiz-en-publiceren.md).

## 2. book-to-animation (Shorts maken)

1. Project `book-to-animation` → *Create Service → Application*.
2. Provider GitHub, repo `JoranF/book-to-animation`, branch
   `claude/project-thread-es72oc` (dit is de deploy-branch; de repo heeft geen
   `main`). Build type **Dockerfile**, pad `Dockerfile`.
3. *Advanced → Volumes*: volume `book-to-animation-data` op **`/data`**
   (alle Shorts, muziekbibliotheek, SFX, trends staan hier).
4. Domein `book.joranit.com`, poort **8000**, HTTPS.
5. Environment:

   | Naam | Verplicht | Wat |
   | --- | --- | --- |
   | `APP_PASSWORD` | ja | Login van de webapp (willekeurige gebruikersnaam) en de API. stream-clipper gebruikt hem ook |
   | `ANTHROPIC_API_KEY` | ja | Claude schrijft de scripts |
   | `ELEVENLABS_API_KEY` | ja voor goede stemmen | Zonder: gratis Piper-stem |
   | `ACESTEP_URL` | nee | `http://b2a-acestep:8001` als ACE-Step draait |
   | `ACESTEP_API_KEY` | nee | Zelfde waarde als in de acestep-app |
   | `SCRAPECREATORS_API_KEY` | nee | TikTok in de trend research |
   | `STUDIO_URL` | nee | Link naar het dashboard in de webapp |
   | (modellen per stap) | nee | De vijf regels hieronder zijn alleen de standaard: in het dashboard (Book Shorts → "Claude models per step", of book.joranit.com) kies je per stap model en effort; dat wordt bewaard in `DATA_DIR/model_settings.json` en wint van de env |
   | `SCRIPT_MODEL` / `SCRIPT_EFFORT` | nee | Schrijft de dialoog. Standaard `claude-opus-5-5`, `high` |
   | `STAGE_MODEL` / `STAGE_EFFORT` | nee | Maakt de 3D-regie per scène. Standaard `claude-sonnet-5-5`, `medium` (goedkoopst: `claude-haiku-5-5`) |
   | `CHECK_MODEL` / `CHECK_EFFORT` | nee | Duidelijkheidscheck. Standaard `claude-sonnet-5-5`, `low` |
   | `CLARITY_MIN` | nee | Score (1-10) waaronder de schrijver één herkansing krijgt. Standaard 7, `0` = check uit |
   | `ANALYSIS_MODEL` / `ANALYSIS_EFFORT` | nee | Trend-brief en playbook. Standaard `claude-sonnet-5-5`, `medium` |
   | `ELEVENLABS_VOICE_NARRATOR` / `_PHILOSOPHER` / `_YOUTH` | nee | Voice-id's per personage |
   | `ELEVENLABS_MODEL`, `ELEVENLABS_FALLBACK_MODEL`, `ELEVENLABS_STABILITY` | nee | Standaard `eleven_v4`, `eleven_multilingual_v2`, 0.4 |
   | `TTS_BACKEND` | nee | `auto`, `elevenlabs` of `piper` |
   | `SFX_VOLUME`, `SFX_VARY`, `MUSIC_VOLUME` | nee | Mixniveaus (0.25 / 1 / 0.16) |
   | `MUSIC_BACKEND`, `MUSIC_PER_MOOD`, `ACESTEP_TIMEOUT` | nee | `auto`, 4, 900 |
   | `TRENDS_MAX_AGE_DAYS` | nee | 14 |
   | `RENDER_WORKERS` | nee | Scènes tegelijk renderen (2) |
   | `PRICE_*` | nee | Alleen voor de kostenschatting in `meta.json`. Claude-prijzen staan per model in `config.MODEL_PRICES`; zet `PRICE_TTS_PER_1K_CHARS` op wat je ElevenLabs-abonnement echt kost |

6. Deploy (~15 min). Check https://book.joranit.com: inlogscherm met basic auth.

## 3. stream-clipper (het dashboard)

Zie de docs van stream-clipper voor alle variabelen:
https://github.com/JoranF/stream-clipper/blob/main/docs/dokploy-setup.md.
Kort: Compose-service uit `JoranF/stream-clipper` @ `main`, domein
`clipper.joranit.com` → service `clipper`, poort 8000, HTTPS (Twitch-embeds
werken alleen op HTTPS). Koppel daarna in *Settings → Book to Animation* het
adres `https://book.joranit.com` met het `APP_PASSWORD` van stap 2.

## 4. acestep (muziek op de GPU, optioneel)

Alleen als de GPU werkt. Volledige uitleg: [gpu-acestep.md](gpu-acestep.md).

1. Project `book-to-animation` → *Create Service → Compose*, naam `acestep`.
2. GitHub, repo `JoranF/book-to-animation`, branch `claude/project-thread-es72oc`
   (zodra PR #2 gemerged is), compose path `musicgen/docker-compose.yml`,
   watch path `musicgen/**`. **Auto-deploy uit**: elke build duurt ~45 min.
3. Environment: `ACESTEP_API_KEY=` (lange willekeurige string). Zelfde waarde
   plus `ACESTEP_URL=http://b2a-acestep:8001` in book-to-animation.
4. Geen domein: alleen book-to-animation praat ermee, over `dokploy-network`.
5. Deploy. De eerste start downloadt ~10 GB modellen.
6. Muziekbibliotheek vullen (`python -m b2a.cli music` in de book-to-animation-
   container, of gewoon Shorts maken), daarna **acestep stoppen** om RAM vrij
   te maken. De nummers blijven in `/data/music/<mood>/`.

## 5. (Oud) studio

Niet meer nodig sinds het dashboard in stream-clipper zit. Wil je hem toch:
Application uit deze repo, Dockerfile `studio/Dockerfile`, watch path
`studio/**`, poort 8000. Env: `STUDIO_PASSWORD`, `POSTIZ_URL`,
`POSTIZ_API_KEY`, `SOURCE_SHORTS_URL` + `SOURCE_SHORTS_PASSWORD`
(= `APP_PASSWORD`), `SOURCE_CLIPS_URL` + `SOURCE_CLIPS_PASSWORD`
(= `REVIEW_PASSWORD` van stream-clipper).

## Controlelijst na het opzetten

- [ ] https://postiz.joranit.com laadt, registratie staat dicht
- [ ] https://book.joranit.com vraagt om een wachtwoord en toont de episodes
- [ ] https://clipper.joranit.com laadt, de tab Book Shorts toont episodes (koppeling werkt)
- [ ] In het dashboard zie je de Postiz-kanalen bij "Send"
- [ ] (GPU) `docker run --rm --gpus all ubuntu nvidia-smi` op de server toont de 1050 Ti
