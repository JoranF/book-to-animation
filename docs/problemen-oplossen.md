# Problemen oplossen

Eerst altijd: in Dokploy de app openen → *Deployments* (buildlog) en *Logs*
(runtime). Claude kan dat ook via de Dokploy-connector, maar niet je domeinen
zelf openen.

## Cloudflare 521 op alle sites (of Dokploy-panel 502)

**Betekenis:** Cloudflare bereikt de server, maar daar antwoordt niemand op
poort 443/80. Bijna altijd staat **Traefik** uit.

**Herstel (SSH op de server):**

```bash
sudo docker ps -a | grep -i traefik       # staat dokploy-traefik op Exited?
sudo docker start dokploy-traefik
sudo docker logs --tail 50 dokploy-traefik
```

Daarna laden de sites binnen een paar seconden weer. Komt hij niet op, kijk in
de logs naar poort-conflicten of een kapotte config in
`/etc/dokploy/traefik/`. Draait Dokploy zelf ook niet:
`sudo docker service ls` en `sudo docker service ps dokploy`.

**Oorzaak op 27-11-2026:** het instellen van nvidia als standaard Docker-
runtime en de herstart van Docker daarna (zie volgende kopje).

## GPU als standaard-runtime legt Dokploy plat

Symptoom: na "Enable GPU" in Dokploy of `"default-runtime": "nvidia"` in
`/etc/docker/daemon.json` + `systemctl restart docker` komen Traefik en
andere containers niet terug → 521 / 502, Postiz op "error".

Herstel:
1. Haal `"default-runtime": "nvidia"` uit `/etc/docker/daemon.json`
   (laat de `runtimes`-sectie met nvidia staan, die is nodig voor `--gpus`).
2. `sudo systemctl restart docker`
3. `sudo docker start dokploy-traefik` (zie hierboven) en controleer dat
   Postiz en de apps weer "done" zijn; anders per app *Redeploy*.
4. Vraag de GPU per app aan in de compose (`deploy.resources.reservations.devices`),
   zoals `musicgen/docker-compose.yml` doet.

## Site geeft 404 / "Bad Gateway" maar de container is gezond

Het domein in Dokploy wijst naar de **verkeerde poort**. Dokploy zet standaard
**3000**; onze apps luisteren op **8000** (Postiz: 5000). Zo is book.joranit.com
op 26-11 gerepareerd: poort 3000 → 8000, geen redeploy nodig.

## Certificaatfout direct na een nieuw domein

Let's Encrypt heeft een paar minuten nodig. Staat Cloudflare-proxy aan, zet
SSL/TLS op *Full*. Blijft het, controleer of het A-record naar het goede IP wijst.

## Tab in het dashboard is leeg

- Book Shorts: klopt het adres (`https://book.joranit.com`, niet het oude
  `sslip.io`-adres) en het wachtwoord (= `APP_PASSWORD`) onder
  *Settings → Book to Animation*?
- Kanalen ontbreken bij Send: `POSTIZ_URL` / `POSTIZ_API_KEY` in stream-clipper
  gezet en geredeployed? Staan de kanalen onder de juiste customer in Postiz?

## Env-variabele toegevoegd maar app ziet hem niet

Na opslaan moet je **deployen**. En: Claude kan via de connector niet één
regel toevoegen zonder alle andere te wissen, dus doe het zelf in de browser.

## acestep-build faalt of duurt eindeloos

- "no kernel image is available": verkeerde torch-build (cu128). Gebruik de
  cu126-Dockerfile ([gpu-acestep.md](gpu-acestep.md)).
- Lege architectuurlijst tijdens build: bekend, opgelost in PR #2 (check op de
  ingebakken lijst, niet op de GPU).
- `ln: failed to create symbolic link '/etc/resolv.conf'` is een onschuldige
  waarschuwing van systemd in Docker.
- Image wegschrijven duurt >45 min: normaal op deze schijf, zolang er geen
  fout staat.

## Dokploy-connector van Claude reageert niet

Opent het panel in de browser wel? Dan de connector opnieuw verbinden in de
claude.ai-instellingen. Opent het panel ook niet: zie 521 hierboven.
