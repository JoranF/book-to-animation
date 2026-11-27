# GPU en ACE-Step (muziek)

ACE-Step 1.5 is een open muziekmodel (MIT-licentie) dat de achtergrondmuziek
maakt op de eigen GPU, dus zonder copyrightclaims en zonder kosten per
nummer. Het draait als losse Compose-app `acestep` (container `b2a-acestep`).

## De kaart: GTX 1050 Ti

| | |
| --- | --- |
| Chip | GP107, generatie **Pascal**, compute capability **sm_61** |
| VRAM | 4 GB |
| Gevolg | ACE-Step kiest zelf de laagste stand: alleen het muziekmodel (DiT), INT8, deels in het gewone RAM. Traag, maar we maken maar 24 nummers (4 per stemming) en hergebruiken die |
| Geen bf16 | De kaart kan geen bf16; nog niet bewezen dat alles op INT8 werkt. De eerste echte start is de test |

## Wat er op de server moet staan

Eenmalig, via SSH:

```bash
# 1. Driver: neem de 580-reeks. Dat is de laatste die Pascal ondersteunt; nieuwere niet.
sudo apt install nvidia-driver-580
sudo reboot
nvidia-smi                     # moet de 1050 Ti tonen

# 2. NVIDIA Container Toolkit (volg de officiële installatie van NVIDIA voor je distro), dan:
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker

# 3. Test of Docker de GPU ziet:
docker run --rm --gpus all ubuntu nvidia-smi
```

### ⚠️ Zet nvidia NIET als standaard-runtime

Dokploy heeft een knop **"Enable GPU"** / *Setup GPU*, en er zijn handleidingen
die `"default-runtime": "nvidia"` in `/etc/docker/daemon.json` zetten. **Doe
dat niet op deze server.** Op 27-11-2026 legde dat Dokploy plat: na de
herstart van Docker kwam `dokploy-traefik` niet terug (Exited), alle sites
gaven Cloudflare-fout **521** en het Dokploy-panel 502. Het is teruggezet naar
niet-standaard.

Daarom vraagt `musicgen/docker-compose.yml` de GPU **expliciet** aan:

```yaml
deploy:
  resources:
    reservations:
      devices:
        - driver: nvidia
          count: 1
          capabilities: [gpu]
```

Ging het toch mis? Zie [problemen-oplossen.md](problemen-oplossen.md#gpu-als-standaard-runtime-legt-dokploy-plat).

> Dokploy's eigen GPU-check (*Settings → GPU*) zei op 27-11 nog steeds "geen
> driver, 0 GPU's", terwijl `--gpus all` en de torch-test wél werkten. Vertrouw
> op de commando's hierboven, niet op die check.

## Waarom een eigen Dockerfile (cu126)

De standaard-PyTorch van ACE-Step (torch 2.10 + **CUDA 12.8**) heeft **geen
kernels voor Pascal**. Op de server gaf dat `no kernel image is available`.
De **CUDA 12.6**-build van dezelfde torch-versie heeft die wel (de lijst bevat
`sm_60`, en sm_60-kernels draaien op een sm_61-kaart).

`musicgen/Dockerfile` doet daarom:
1. Basisimage CUDA 12.6, Python via `uv` (niet via apt/deadsnakes: dat kostte 25 min en 300 pakketten).
2. ACE-Step vastgezet op v0.1.8, geïnstalleerd uit zijn lockfile.
3. torch vervangen door de cu126-build.
4. **Controle tijdens de build** op de ingebakken architectuurlijst van torch
   (`torch.cuda.get_arch_list()` werkt tijdens een build niet, want er hangt
   dan geen GPU aan; dat was de eerste mislukte build, opgelost in PR #2).
5. De API starten zonder dat `uv` torch weer terugzet.

Zelf testen of een torch-versie je kaart ondersteunt:

```bash
docker run --rm --gpus all python:3.11-slim sh -c "pip install -q torch==2.10.0 --index-url https://download.pytorch.org/whl/cu126 && python -c 'import torch; print(torch.cuda.get_device_name(0), torch.cuda.get_arch_list()); print((torch.ones(2, device=\"cuda\")*2).sum())'"
```

Goed als je `tensor(4., device='cuda:0')` ziet.

## Draaien en weer uitzetten

- Build duurt ~45 min; het wegschrijven van de grote image is traag op deze
  schijf (op 27-11 >50 min bezig zonder fouten).
- Eerste start downloadt ~10 GB modellen naar het volume `acestep-checkpoints`.
- RAM is krap (~11 van 16 GB al in gebruik). Laat acestep alleen draaien om de
  bibliotheek te vullen (bijvoorbeeld 's nachts) en **stop hem daarna** in Dokploy.
- book-to-animation praat ermee via `ACESTEP_URL=http://b2a-acestep:8001` en
  `ACESTEP_API_KEY` (in beide apps dezelfde waarde). Faalt ACE-Step, dan valt
  hij terug op chiptune; een Short faalt dus nooit door de muziek.
