# Asset library: personages, props en achtergronden

Sinds 28-11-2026. Code: `b2a/assets.py` (bibliotheek), `b2a/world.py` (bouwt de
recepten in Blender), `b2a/script.py` (`ensure_assets`, de 3D-regie vraagt nieuwe
assets aan).

## Twee soorten assets

| Soort | Wat | Waar |
| --- | --- | --- |
| **Ingebouwd** | De vaste kit in code: de Jongeman, de Filosoof, de vader, grijze mensen, 7 sets, 23 props | `b2a/world.py` + `b2a/stage.py` |
| **Gegenereerd** | Door Claude gemaakt toen een script iets nodig had dat er nog niet was (een telefoon, een klaslokaal, een leraar) | `/data/assets/<prop\|set\|character>/<naam>.json` op het volume |

Een gegenereerd asset is een klein JSON-"recept" van low-poly vormen (box, tube,
ball, ...) met kleuren, plus optioneel een beweging (bob, spin, sway, pulse). Een
personage is een "look" (huid, kleren, haar, bril, ...) op hetzelfde lichaam als de
vaste cast, dus het beweegt net zo. Bij het maken rendert Blender er een preview van:
`/data/assets/previews/<soort>-<naam>.png`.

## Hoe het werkt bij een nieuwe Short

1. De 3D-regie (Sonnet 5.5) krijgt de kit **en de bibliotheek** ("LIBRARY") mee en
   gebruikt bestaande assets gewoon op naam.
2. Heeft een scène iets nodig dat er niet is, dan zet de regie het in `new_assets`
   met naam, soort, omschrijving en tags.
3. Eerst **hergebruik**: dezelfde naam, een alias, dezelfde naam anders geschreven
   (`smart_phone` = `smartphone`), of een naam die in de tags staat ("phone" vindt de
   smartphone). Iets dat alleen een woord deelt ("phone booth") telt niet. Nieuwe
   personages worden nooit omgewisseld voor de vaste cast.
4. Niets gevonden: `ASSET_MODEL` (standaard Sonnet 5.5) ontwerpt het, de vorm wordt
   gecontroleerd (max. 48 onderdelen, geldige kleuren en maten) en het wordt
   opgeslagen. Elke volgende Short hergebruikt het.
5. Maximaal `ASSET_MAX_NEW` (standaard 3) nieuwe assets per Short. `0` = alleen kit
   en bibliotheek.
6. Bij het renderen gaan de recepten mee in de scène naar Blender. `meta.json` krijgt
   `assets_made` (wat nieuw was) en `assets_used` (naam → versie).

Nieuwe personages spreken niet: de stemmen zijn er alleen voor verteller, Filosoof en
Jongeman.

## Opnieuw maken (rebuild)

- **Rebuild next time**: het asset wordt opnieuw gemaakt zodra een Short het weer
  gebruikt. Met een notitie ("maak hem groter", "rode kleur") die het model meekrijgt.
- **Rebuild now**: meteen opnieuw maken (los van een Short).
- De vorige 5 versies blijven bewaard in `history` van het JSON-bestand; het
  versienummer gaat omhoog.
- Een **ingebouwde** prop of set kun je ook laten herbouwen: dan komt er een
  gegenereerde versie die het origineel vervangt. "Back to built-in" zet het origineel
  terug.
- **De Jongeman en de Filosoof zijn op slot.** Die veranderen nooit, zodat elke
  aflevering dezelfde show is.

## Waar bedien je het

- **book.joranit.com** → uitklapblok *Asset library*: alles met preview, versie,
  hoe vaak gebruikt, knoppen voor rebuild en verwijderen.
- **API** (basic auth, zelfde wachtwoord als de app):
  - `GET /api/assets`: alles (ingebouwd + gegenereerd), zonder recepten
  - `GET /api/assets/{soort}/{naam}`: één asset met recept
  - `GET /api/assets/{soort}/{naam}/preview`: de PNG
  - `POST /api/assets`: `{kind, name, description, tags}` zelf iets laten maken
  - `POST /api/assets/{soort}/{naam}/rebuild`: `{note, now}`
  - `DELETE /api/assets/{soort}/{naam}/rebuild`: rebuild-markering weghalen
  - `PATCH /api/assets/{soort}/{naam}`: tags, aliassen of omschrijving aanpassen
  - `DELETE /api/assets/{soort}/{naam}`: gegenereerd asset weg (ingebouwd komt terug)
- **CLI** in de container:

```bash
python -m b2a.cli assets list
python -m b2a.cli assets new smartphone --kind prop --note "a black phone with a blue screen"
python -m b2a.cli assets rebuild smartphone --kind prop --note "bigger screen"         # volgende keer
python -m b2a.cli assets rebuild smartphone --kind prop --note "bigger screen" --now   # nu
python -m b2a.cli assets reset chair --kind prop      # terug naar het ingebouwde origineel
python -m b2a.cli assets preview classroom --kind set
```

## Instellingen (env, namen)

`ASSET_MODEL`, `ASSET_EFFORT`, `ASSET_MAX_NEW`, `ASSET_PREVIEWS` (`0` = geen
preview-render). Model en effort zijn ook te kiezen in het dashboard bij
"Claude models per step" (stap *New assets*).

## Kosten

Een nieuw asset is één Sonnet-aanroep (geschat een paar cent) en ~2 s Blender voor de
preview. Hergebruik kost niets. De tokens staan in `meta.json` onder stap `assets`.
