# Status en open punten

Stand: 27-11-2026. Werk dit bij als iets klaar is of erbij komt.

## Werkt

- book-to-animation draait op https://book.joranit.com (status done).
- Shorts maken via de tab Book Shorts in het dashboard (clipper.joranit.com).
- Postiz draait, account bestaat.
- GPU zichtbaar voor Docker met `--gpus all` (driver 580 + toolkit).

## Nog niet getest tegen de echte diensten

- De Claude-scriptaanroep met het stage-formaat en de ElevenLabs v4-aanroep
  (alleen met mocks getest). Kijk mee bij de eerste echte run.
- Posten via Postiz naar YouTube/TikTok.
- `SFX_VOLUME` 0.25 is een gok; nog niet beluisterd in een echte Short.
- Kostprijzen in `meta.json` zijn aannames.

## Open

| Punt | Wie | Notitie |
| --- | --- | --- |
| PR #2 (ACE-Step build-fix) mergen, acestep-app terug naar `claude/project-thread-es72oc` | Joran / Claude | |
| acestep: eerste start bekijken (GPU, model laden), bibliotheek vullen, daarna stoppen | Claude | laatste status in Dokploy: error |
| PR #3 (CRT zonder bolling) reviewen en mergen | Joran | |
| YouTube API-audit en TikTok app review | Joran | zie [postiz-en-publiceren.md](postiz-en-publiceren.md); tot die tijd YouTube privé, TikTok via inbox |
| `DISABLE_REGISTRATION=true` in Postiz controleren | Joran | standaard staat hij open |
| Wekelijkse trend research inplannen (Dokploy schedule) | Claude | `python -m b2a.cli trends` |
| Analytics-loop afmaken: stats op dag 2 en 7 → playbook voor de scripts | later | pas defaults aanpassen bij ≥10 clips per variant |
| Long form bouwen | later | plan bestaat, niets gebouwd; wie keurt script en ruwe montage goed? |
| Oude studio-app uitzetten of verwijderen | Joran | niet meer nodig |
