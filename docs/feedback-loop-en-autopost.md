# Feedback-loop en volledig automatisch posten (Book Shorts)

Toegevoegd op 28-11-2026. Werkt samen met het dashboard in stream-clipper (https://clipper.joranit.com),
dat sinds PR #3/#6 daar de Book Shorts maakt, keurt en post. De losse Studio-app staat stil (idle).

## Hoe de lus loopt

1. Het dashboard (autopilot, Instellingen > Book to Animation) start een nieuwe aflevering, keurt hem
   goed als hij de checks haalt en plant hem in Postiz op de kanalen onder de klant "Book to Animation".
2. Elk uur haalt het dashboard views, likes, comments en shares uit Postiz en stuurt die per Short naar
   deze app (`PATCH /api/shorts/{id}/feedback`). Ze komen in `meta.json` > `analytics`.
3. `b2a/learn.py` vergelijkt de Shorts per keuze: format, hook-type, lengte, dialoog of verteller,
   muziekstemming, boek. Vanaf 5 Shorts met cijfers gaat dat overzicht mee in elke nieuwe script-prompt.
   Vanaf 8 schrijft Claude er maximaal 8 regels "playbook" van (`DATA_DIR/playbook.json`), hooguit 1x per dag.
4. Jouw eigen feedback weegt altijd zwaarder dan de cijfers:
   - **Redo met feedback** op een Short-kaart: Claude herschrijft het script met jouw opmerking en er komt
     een nieuwe versie onder "To review". De oude gaat naar Rejected (een al geposte blijft onder Sent).
     Vinkje "Ook gebruiken voor toekomstige Shorts" (standaard aan) maakt er een vaste notitie van.
   - **Notities** in het blok "Feedback loop" op de Book Shorts-pagina gelden voor alle volgende Shorts.
     Opgeslagen in `DATA_DIR/notes.json`.
   - Onder "What the script writer is told now" zie je precies wat het script-model meekrijgt.

## API (deze app)

| Endpoint | Wat |
| --- | --- |
| `POST /api/shorts/{id}/redo` `{feedback, remember}` | nieuwe versie in de wachtrij (1 tegelijk per Short) |
| `GET/POST /api/notes`, `DELETE /api/notes/{id}` | vaste notities |
| `GET /api/learnings` | tekst voor de prompt + cijfers + playbook |
| `PATCH /api/shorts/{id}/feedback` `{analytics}` | cijfers van het dashboard |

## Automatisch posten per account (dashboard)

- Instellingen > Automatic posting > **Accounts**: per Postiz-account een schakelaar. Uit = automatisch
  posten (clips en Book Shorts) slaat dat account over; met de hand versturen kan nog wel.
- **Spreiden**: maximaal N clips van dezelfde video/upload per dag per publiek (standaard 2). Een podcast
  van 20 clips voor een Whop-campagne gaat dus over meerdere dagen. Clips van een upload blijven 30 dagen in
  de wachtrij (`AUTOPOST_UPLOAD_MAX_AGE_DAYS`), stream-clips 5 dagen (`AUTOPOST_MAX_AGE_DAYS`).
- Dubbel posten: alleen het dashboard post automatisch. Een Short die verstuurd is staat in deze app op
  `posted` en het dashboard onthoudt de Postiz-ids, dus hij gaat niet twee keer.

## Beperkingen die blijven

- YouTube: zolang het Google API-project niet geaudit is, worden uploads via de API privé gezet.
- TikTok: zonder goedgekeurde app alleen naar de inbox / SELF_ONLY; kies "inbox" in de instellingen tot de
  review rond is.
- Instagram: alleen een Business- of Creator-account kan via Postiz posten.
- Cijfers komen alleen binnen zolang Postiz ze voor dat platform teruggeeft.
