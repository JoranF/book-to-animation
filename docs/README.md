# Documentatie: book-to-animation

Dit is de levende documentatie van het project. Hier staat wat er gebouwd is,
hoe het werkt, hoe je het op de server zet en hoe je het aan iemand anders
overdraagt. Houd het bij: elke keer dat er iets verandert aan de setup, pas je
het bijbehorende bestand aan en zet je een regel in het [logboek](logboek.md).

> Geheimen (API-keys, wachtwoorden) staan **nooit** in deze docs, in de repo of
> in een chat. Ze staan alleen in het Environment-tabblad van Dokploy. In deze
> docs staan alleen de **namen** van de variabelen.

## Waar begin je?

| Je wilt... | Lees |
| --- | --- |
| In 5 minuten snappen wat dit is | [Overzicht](#in-het-kort) hieronder |
| Iemand inwerken of het project overdragen | [overdracht.md](overdracht.md) |
| Weten welke apps er op de server draaien en hoe ze samenhangen | [architectuur.md](architectuur.md) |
| De apps (opnieuw) opzetten op Dokploy | [dokploy-setup.md](dokploy-setup.md) |
| Begrijpen hoe een Short gemaakt wordt | [pipeline.md](pipeline.md) |
| De GPU en ACE-Step-muziek aan de praat krijgen | [gpu-acestep.md](gpu-acestep.md) |
| Postiz, YouTube en TikTok koppelen | [postiz-en-publiceren.md](postiz-en-publiceren.md) |
| Weten welke personages, props en achtergronden er zijn, en ze laten (her)maken | [asset-library.md](asset-library.md) |
| Feedback geven op Shorts, leren van analytics, automatisch posten per account | [feedback-loop-en-autopost.md](feedback-loop-en-autopost.md) |
| Iets is stuk (521, 502, lege tab, build faalt) | [problemen-oplossen.md](problemen-oplossen.md) |
| Zien wat er wanneer gedaan is | [logboek.md](logboek.md) |
| Weten wat er nog open staat | [status-en-open-punten.md](status-en-open-punten.md) |

Het zusterproject **stream-clipper** (Twitch-clips, en tegenwoordig ook hét
dashboard voor alles) heeft zijn eigen docs:
https://github.com/JoranF/stream-clipper/tree/main/docs

## In het kort

- **Doel:** filosofieboeken (eerst *The Courage to Be Disliked*) omzetten in
  geanimeerde YouTube Shorts / TikToks, later ook long form, zo veel mogelijk
  automatisch, om met YouTube geld te verdienen.
- **Stijl:** late-jaren-90 low-poly 3D, zoals vroege 3D-platformgames, met een
  CRT-filter. Eigen personages: de Filosoof en de Jongeman. Geen bestaande
  game-IP.
- **Taal van de video's:** Engels.
- **Eén Short = één smal idee** uit één hoofdstuk (episodeplan van 45 afleveringen).
- **Hoe:** Claude schrijft het script, ElevenLabs spreekt de stemmen in,
  headless Blender rendert de 3D-beelden, FFmpeg monteert alles met captions,
  geluidseffecten en muziek. Postiz plaatst op YouTube en TikTok.
- **Waar:** alles draait op de eigen Dokploy-server (`*.joranit.com`, via Cloudflare).
- **Niet gebruiken:** Higgsfield en fal (bewust geschrapt).
