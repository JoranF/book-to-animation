# Postiz en publiceren op YouTube en TikTok

**Postiz** (open source, zelf gehost op https://postiz.joranit.com) beheert
alle social accounts en plant posts in. Onze apps praten met de Postiz Public
API; Postiz praat met YouTube en TikTok.

## Hoe een video online komt

1. Een Short of clip wordt goedgekeurd in het dashboard (clipper.joranit.com),
   door jou of door de automatische review.
2. Je klikt **Send** (of de autopost-schakelaar doet het): kanalen aanvinken,
   tijd leeg = nu, of een tijd kiezen = inplannen. Het dashboard uploadt de
   video naar Postiz en maakt de post.
3. Postiz plaatst op het platform. Elk uur haalt het dashboard de status, de
   link en views/likes/comments/shares op.

Afspraken:
- Book Shorts gaan alleen naar de kanalen onder de Postiz-"customer"
  **Book to Animation**. Stream-clips gaan naar **NL Clips** of **US Clips**.
- TikTok-posts van Shorts krijgen het AI-label.
- Laat nooit twee apps dezelfde video posten (bijv. autopost in stream-clipper
  én handmatig via de oude Studio).
- Postiz staat ~30 API-calls per uur toe voor alles samen
  (`POSTIZ_CALLS_PER_HOUR`, standaard 28; 8 blijven over voor posten).

## Instellingen (namen)

- In **Postiz** zelf: `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`,
  `TIKTOK_CLIENT_ID`, `TIKTOK_CLIENT_SECRET` (plus de basis uit
  [dokploy-setup.md](dokploy-setup.md#1-postiz)).
- In **stream-clipper**: `POSTIZ_URL=https://postiz.joranit.com` en
  `POSTIZ_API_KEY` (Postiz → Settings → Public API). De code plakt
  `/api/public/v1` er zelf achter.

## Redirect-URL's voor de developer-apps

| Platform | Redirect URI |
| --- | --- |
| YouTube (Google Cloud OAuth client) | `https://postiz.joranit.com/integrations/social/youtube` |
| TikTok (TikTok for Developers) | `https://postiz.joranit.com/integrations/social/tiktok` |

## YouTube koppelen

1. Google Cloud Console → nieuw project → **YouTube Data API v3** aanzetten.
2. *OAuth consent screen*: type External, app-naam, support-mail, scopes die Postiz vraagt (upload + readonly).
3. *Credentials → OAuth client ID* → Web application, redirect URI zoals hierboven.
4. Client ID en secret in de Environment van Postiz, redeploy.
5. In Postiz: *Add channel → YouTube*, inloggen met het kanaal.

**Beperking zolang de app niet geaudit is:** uploads via een niet-geverifieerd
API-project worden door YouTube **altijd privé** gezet. Voor publiek posten
moet het Google-project door de **YouTube API Services audit** (compliance
check) en de OAuth-app geverifieerd zijn.

## TikTok koppelen

1. developers.tiktok.com → app aanmaken → producten **Login Kit** en **Content Posting API**.
2. Redirect URI zoals hierboven, scopes voor video upload/publish.
3. Client key en secret als `TIKTOK_CLIENT_ID` / `TIKTOK_CLIENT_SECRET` in Postiz, redeploy.
4. In Postiz: *Add channel → TikTok*.

**Beperking zolang de app niet goedgekeurd is:** een niet-geaudite app mag
alleen posten als **SELF_ONLY** (alleen jij ziet het). Daarom staat de
standaard op `UPLOAD`: de video komt in de inbox van de TikTok-app en jij tikt
daar zelf op Post. `DIRECT_POST` werkt pas na TikTok's app review.

## Stand van de app reviews

*Nog aan te vullen uit het Claude-in-Chrome-logboek van de aanvraag voor de
YouTube-audit en TikTok-review (wat is ingediend, wanneer, welke
schermafbeeldingen/video's, wat het antwoord was).*
