# Architectuur: wat draait waar

Alles draait op één eigen server met **Dokploy** (een zelf-gehost
"Heroku": bouwt Docker-images uit GitHub en zet ze achter **Traefik**, de
reverse proxy met Let's Encrypt-certificaten). De domeinen staan bij
**Cloudflare** en wijzen naar die server.

## De server

| Wat | Waarde (stand 27-11-2026) |
| --- | --- |
| CPU / RAM | 4 cores, 16 GB RAM (waarvan ~11 GB in gebruik door alle apps samen) |
| Schijf | ~400 GB vrij, maar traag bij het wegschrijven van grote images |
| GPU | NVIDIA GTX 1050 Ti (Pascal, sm_61, 4 GB VRAM), driver 580 + NVIDIA Container Toolkit |
| Let op | `nvidia` is **niet** de standaard Docker-runtime (dat legde Dokploy plat, zie [problemen-oplossen.md](problemen-oplossen.md#gpu-als-standaard-runtime-legt-dokploy-plat)) |

Op dezelfde server draaien ook andere projecten van Joran (webshops,
websites, schoolprojecten). Wees dus voorzichtig met acties die de hele server
raken: Docker herstarten, de standaard-runtime wijzigen, `docker system prune`.

## De apps voor dit project

```
                 Cloudflare DNS (*.joranit.com)
                              │
                         Traefik (Dokploy)
      ┌───────────────┬───────┴────────┬──────────────────┐
      ▼               ▼                ▼                  ▼
 book.joranit.com  clipper.joranit.com  postiz.joranit.com  studio.joranit.com
 book-to-animation stream-clipper       Postiz             (oude Studio-app,
 (Shorts maken)    = het dashboard      (plaatst posts)     niet meer nodig)
      │   ▲           │      │                ▲
      │   └── API ────┘      └── API (posten, stats) ──┘
      │
      └── intern via dokploy-network ──► b2a-acestep:8001 (ACE-Step, GPU, geen domein)
```

| App | Dokploy-project | Type | Repo / branch | Domein → poort |
| --- | --- | --- | --- | --- |
| **book-to-animation** | book-to-animation | Application (Dockerfile) | `JoranF/book-to-animation` @ `claude/project-thread-es72oc`, auto-deploy aan | https://book.joranit.com → **8000** |
| **acestep** | book-to-animation | Compose (`musicgen/docker-compose.yml`) | zelfde repo, tijdelijk @ `claude/project-thread-etvkfd` (PR #2), auto-deploy uit | geen domein, intern `http://b2a-acestep:8001` |
| **studio** (oud) | book-to-animation | Application (`studio/Dockerfile`) | zelfde repo @ `claude/project-thread-es72oc`, watch path `studio/**` | https://studio.joranit.com → 8000 |
| **stream-clipper** | stream-clipper | Compose (`docker-compose.yml`) | `JoranF/stream-clipper` @ `main`, auto-deploy aan | https://clipper.joranit.com → 8000 (service `clipper`) |
| **postiz** | postiz | Compose (Dokploy-template) | image `ghcr.io/gitroomhq/postiz-app:latest` + postgres 17, redis, temporal, elasticsearch | https://postiz.joranit.com → 5000 (service `postiz-app`) |

Dokploy-id's (handig voor wie met de Dokploy API of de Claude-connector werkt):

| App | Id |
| --- | --- |
| book-to-animation (application) | `rDMry6V0lE6dFiIxPzjFa`, appName `book-to-animation-xroolo`, volume `book-to-animation-data` op `/data` |
| studio (application) | `zcW-fgX3IRm5cGQLy-LTC` |
| acestep (compose) | `CqoDROEhCMEa7r8ERua05` |
| stream-clipper (compose) | `u3SSdDfzlQnGrCfzMnEvQ`, volume `clipper-data` op `/data` |
| postiz (compose) | `p_B14fO0AipnqG-wvtKT4`, appName `postiz-postiz-ahlwne` |

## Wie praat met wie

1. **Het dashboard is stream-clipper** (clipper.joranit.com, header "Studio").
   Daar staat een tab **Book Shorts**: je kiest een boek en episode, drukt op
   *Make Short*, en het dashboard roept de API van book-to-animation aan.
2. **book-to-animation** maakt de Short (script, stem, Blender, montage) en
   bewaart hem in `/data/shorts/<id>/`. Het weet niets van Postiz.
3. Voor muziek vraagt book-to-animation, als `ACESTEP_URL` gezet is, een
   nummer aan **ACE-Step** over het interne Docker-netwerk. Faalt dat, dan
   gebruikt hij chiptune die in code gemaakt wordt.
4. Na goedkeuring stuurt **het dashboard** de video naar **Postiz** (concept of
   ingepland), en Postiz plaatst op YouTube / TikTok. Elk uur haalt het
   dashboard statistieken op uit Postiz.

### Waarom er een "oude Studio" is

Op 26-11 is eerst een losse Studio-app gebouwd (`studio/` in deze repo) die
video's van alle pipelines via een klein contract (`GET /api/items`,
`POST /api/items/{id}/status`, `POST /api/items/{id}/sent`) ophaalt en naar
Postiz stuurt. Op 27-11 is het dashboard van stream-clipper uitgebreid tot
hét dashboard voor alles (stream-clipper PR #3). De Studio-app staat sindsdien
op "idle" en is niet meer nodig. Het contract bestaat nog wel in
book-to-animation en stream-clipper; een nieuwe generator kan er zo op
aansluiten.

## Externe diensten

| Dienst | Waarvoor | Env-variabele (naam) | Kosten |
| --- | --- | --- | --- |
| Anthropic (Claude API) | Scripts, trend-briefs, clips kiezen en reviewen | `ANTHROPIC_API_KEY` | per gebruik, centen per Short |
| ElevenLabs | Stemmen (model Eleven v4) | `ELEVENLABS_API_KEY` | abonnement (Starter ±$5/mnd ≈ 50 Shorts) |
| Twitch | Streams en VOD's voor stream-clipper | `TWITCH_CLIENT_ID`, `TWITCH_CLIENT_SECRET` | gratis |
| ScrapeCreators (optioneel) | TikTok-trends | `SCRAPECREATORS_API_KEY` | ±1 credit per zoekopdracht |
| Whop (optioneel) | Betaalde clipping-campagnes | `WHOP_CLIENT_ID`, `WHOP_CLIENT_SECRET` | - |
| Google Cloud (YouTube Data API) | Postiz → YouTube | in Postiz: `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET` | gratis, audit nodig voor publiek posten |
| TikTok for Developers | Postiz → TikTok | in Postiz: `TIKTOK_CLIENT_ID`, `TIKTOK_CLIENT_SECRET` | gratis, app review nodig voor publiek posten |
| GitHub | Code, Dokploy bouwt uit GitHub via de Dokploy GitHub App | - | gratis |
| Cloudflare | DNS voor joranit.com | - | gratis |
