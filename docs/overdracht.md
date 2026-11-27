# Overdracht: zo leer je dit aan iemand anders

Dit is een leerpad voor iemand die het project overneemt of meehelpt. Reken
op een middag voor dag 1 en een paar sessies om het echt zelf te kunnen.

## Wat de nieuwe persoon nodig heeft

- **GitHub**: toegang tot `JoranF/book-to-animation` en `JoranF/stream-clipper`.
- **Dokploy**: een eigen gebruiker (Dokploy → *Settings → Users → Invite*),
  bij voorkeur alleen met rechten op de projecten book-to-animation,
  stream-clipper en postiz (er draaien ook andere projecten op de server).
- **Postiz**: een eigen login of een gedeeld team in Postiz.
- **SSH** naar de server: alleen als hij/zij ook de GPU of Traefik moet
  repareren. Dat is serverbreed; geef dit bewust.
- Keys deel je **niet** via chat of mail. Ze staan in Dokploy; wie Dokploy-
  toegang heeft, ziet ze daar. Moet iemand een eigen key (eigen Anthropic- of
  ElevenLabs-account), dan zet die persoon hem zelf in Dokploy.

## Dag 1: begrijpen

1. Lees [README.md](README.md) en [architectuur.md](architectuur.md). Teken
   het plaatje zelf na: welke app praat met welke.
2. Bekijk de voorbeeld-Shorts (projectbestanden: `shorts/*.mp4`) en de
   SFX-sampler. Zo weet je hoe het eruit hoort te zien en klinken.
3. Open https://clipper.joranit.com, tab **Book Shorts**: kijk naar het
   episodeplan, maak één Short met *Make Short* en volg de voortgang.
4. Lees [pipeline.md](pipeline.md) terwijl de Short rendert, en open daarna
   `script.json` en `meta.json` van die Short (in de webapp op
   book.joranit.com of in het volume).
5. Keur hem goed of af en stuur hem als **concept** (draft) naar Postiz. Kijk
   in Postiz hoe hij daar binnenkomt.

## Dag 2: zelf beheren

1. Loop [dokploy-setup.md](dokploy-setup.md) door in het echte Dokploy-panel:
   vind elke app, het domein, de poort, het Environment-tabblad (namen, niet
   de waarden), de deploylogs.
2. Doe een kleine wijziging in de code (bijv. een tekst), push naar een
   branch, open een PR, merge, en zie Dokploy zelf opnieuw bouwen.
3. Lees [problemen-oplossen.md](problemen-oplossen.md). Oefen "wat doe je bij
   een 521" droog: welk commando, op welke machine.
4. Lees [postiz-en-publiceren.md](postiz-en-publiceren.md) en
   [gpu-acestep.md](gpu-acestep.md): de twee lastigste stukken infrastructuur.

## Dag 3: inhoud en groei

1. Lees de episodes van één hoofdstuk in `books/the-courage-to-be-disliked/episodes.json`.
   Begrijp waarom elke Short maar één idee heeft.
2. Lees de stream-clipper-docs (campagnes, autopost, analytics).
3. Bekijk de analytics in het dashboard. Wat werkt? Zet een les in
   `data/learnings.md`; die gaat mee in elke nieuwe scriptprompt.

## Afspraken die je moet weten

- Geen Higgsfield, geen fal. Beelden: Blender. Scripts: Claude. Stemmen: ElevenLabs.
- Video's in het Engels; stijl late-90s low-poly met CRT; alleen eigen personages.
- Eén smal idee per Short; engagement (hook, tempo) gaat voor.
- Niets gaat live zonder dat een mens het gezien heeft, tenzij de
  autopilot-schakelaars bewust aan staan.
- Geheimen alleen in Dokploy.
- Nooit views kopen of botten.
- Werken met Claude: geef Claude de taak in het project, Claude werkt op een
  eigen `claude/...`-branch en opent een PR. Jij merget.

## Checklist: kan de nieuwe persoon het?

- [ ] Kan uitleggen wat elke app doet en welke poort/domein hij heeft
- [ ] Heeft zelf een Short gemaakt, gereviewd en als concept naar Postiz gestuurd
- [ ] Weet waar de deploylogs staan en hoe je een app opnieuw deployt
- [ ] Weet waarom je env-variabelen in de browser toevoegt en daarna deployt
- [ ] Weet wat te doen bij een 521 en waarom nvidia geen standaard-runtime mag zijn
- [ ] Weet waarom YouTube-uploads privé zijn en TikTok via de inbox gaat
- [ ] Weet waar het logboek staat en zet er zelf een regel in
