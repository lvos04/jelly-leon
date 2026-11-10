# Bouwverificatie B03-016 — corpus, clientmatrix en baselinemeting standaard Jellyfin (golf 0, voormeting 12.4)

Datum: 2026-11-09/10 (ontwikkelmachine van de gebruiker: Intel Core Ultra 9 185H, 22 CPU's, 14,5 GiB RAM, Meteor
Lake-iGPU op `/dev/dri/renderD128`; gedeeld met andere agents). Alles hier is **Sim-getest** op de ontwikkelmachine of in
CI. De transcodes van stock-best zijn **Intel-iGPU-getest (ontwikkelmachine)**; dat is functioneel bewijs en een
bovengrens, géén capaciteit van de A310 of UHD 770 (**NIET GEVALIDEERD (hardware)**). Echte tv's en telefoons: **NIET
GEVALIDEERD (hardware)**; Swiftfin/Safari: **NIET GEVALIDEERD (Mac/Xcode)**; de NAS: **NIET GEVALIDEERD (echte NAS)**.
Procedure: `B03-016_HARNAS.md`; besluit: ADR-0026; code: `tools/b03-harnas/`.

Stock-image in alle metingen: `docker.io/jellyfin/jellyfin:12.4@sha256:fea863d0cd9ec445985d9c75fc6ed64e38a1d2766cf0c250a33d553f4fc1b771`
(server meldt 12.4.0). Alle metingen zijn **voormetingen** (label `voormeting-12.4`); in P4-0 worden ze herhaald op de
12.x-digest van de forkbasis (label `definitief-forkbasis`).

## 1. Corpus en corpusgenerator (deel a)

| Controle | Commando | Uitkomst |
|---|---|---|
| `sha256sum -c` bron, ondertitels, afgeleid | `python -m b03h corpus bron-controle` | **groen**: 34 + 75 + 31 bestanden (2026-11-10T00:05Z) |
| Elk recept reproduceerbaar (zelfde seed → zelfde `set_sha256`) op het echte corpus, jellyfin-ffmpeg 8.1.3 uit de stock-image | `python -m b03h corpus maak <recept> --schaal vol --ffmpeg docker --bevries` (twee keer) | f1, f2, f3, f4, f5, ass: vol twee keer gelijk ("gelijk aan bevroren manifest"; f4 vol ≈ 8–15 min per run); f6: vol één keer (≈ 12 min) en klein twee keer gelijk; groot-bestand (4 GB) vol één keer |
| Reproduceerbaar in CI (synthetisch mini-corpus, host-ffmpeg) | `pytest tools/b03-harnas/tests/test_corpus.py` | 8/8 recepten twee keer bit-gelijk; andere seed → andere set |
| Grondwaarheid en licentie per set | manifest + `grondwaarheid.json` per set | in elk manifest; beperkte sets gemarkeerd |
| Sets opgeruimd na gebruik (BG-38) | `python -m b03h corpus opruimen` | alle sets weg; alleen de bevroren manifesten staan in `test-evidence/b03-016-corpus/` |

Bevroren manifesten (alleen paden, groottes, sha256, recept, seed, parameters, ffmpeg-versie, bronnen met sha256 en licenties):

| Recept | Bestanden | Grootte | Licentie | Aantallen (streef-n van het plan) |
|---|---|---|---|---|
| f1-framecode (vol) | 2 | 55,8 MB | vrij | 1 video van 236 s; decodeerregel getest: 96/96 frames juist gelezen (klein) |
| f2-dsyn (vol) | 621 | 10,1 MB | vrij | 240 films + 20 series × 3 afleveringen = 300 stub-items; 6 gebruikers in 3 huishoudens |
| f3-ondertitels (vol) | 288 | 0,5 MB | **beperkt** (Pioneer One, fanondertitels) | per fouttype 20 per split (kalibratie en test); testsplit: 22 goede vensters (menselijke referentie); "verkeerde taal" alleen in de kalibratiesplit (geen andere talen voor Pioneer One) |
| f4-tqc (vol) | 684 | 0,8 GB | **beperkt** (Pioneer One-fragmenten) | decode_error 210 (30 per codecklasse, alle 210 effectief beschadigd volgens framemd5), audio 120 (20 per codec, 120 effectief), truncated 24 + container_error 8, audio- en ondertitelklassen 20 elk, N-QC-rommelig 8 × 5 |
| f5-fouten (vol) | 18 | 69,6 MB | vrij | devset 3, testset 6 × 3 clients = 18, ASS-bestand |
| f6-segmenten (vol) | 61 | 0,39 GB | vrij | intro 60, outro 60, recap 48 (≥ 40), preview 30 (≥ 30), beschermd 60 (≥ 30; post-credit 15, mid-credit 15, preview na ED 30), intro buiten het IS-venster 29 (≥ 20), nieuwe OP 24 (≥ 20) |
| ass (vol) | 2 | 69,6 MB | vrij | Sintel 120–180 s met NL als ASS |
| groot-bestand (vol) | 2 | 4,69 GB | vrij | Sintel 4× via stream-copy (doel 4 GB; ≤ 20 GB; vrije-ruimtecontrole) |

Gemeten tijdens het bouwen (en opgelost): libx264 met meerdere threads gaf per run een andere uitvoer; het
`noise`-filter kiest standaard een willekeurige seed; en de muxer verweefde audio die > 10 s voorliep per run anders.
De recepten gebruiken daarom één encoderthread, een vaste ruis-seed, `-max_interleave_delta 0` en exacte lengtes via
`trim`/`atrim` (ADR-0026).

**CI-guard testdatalicenties:** `python -m b03h guard --git .` → "in orde" op deze repo; de negatieve tests
(`tests/test_guard.py`) bewijzen dat een commit met een MovieLens-CSV, een Pioneer One-bestand, een fanondertitel, een
gemarkeerde grondwaarheid, een mkv of een MPEG-TS geweigerd wordt, ook als een latere commit het bestand weer weghaalt
(`--bereik`) en ook hernoemd (sha256). In CI draait de guard op de hele boom, op de gepushte commits en op de gebouwde
Jelly Leon-image (`--image jelly-leon:ci`).

## 2. Clientmatrix (deel b)

Bewijs: `test-evidence/b03-016-clientmatrix-rooktest.json` (+ schermafdrukken in de gelijknamige map). Rooktest: elke
client start en speelt `hero.mp4` (CC BY 4.0) af tegen de wegwerp-stockserver 12.4 op 127.0.0.1. Orakel voor de browsers:
binnen 15 s currentTime ≥ 2 s, beeld, geen fout en geen stilte bij een item met audio. Voor de apps: afspelen gestart via
de officiële afstandsbedieningsroute `POST /Sessions/{id}/Playing` en aan de serverkant gecontroleerd (PositionTicks loopt
na het commando ≥ 2 s op).

| Client | Rol | Uitkomst | Toelichting (gemeten) |
|---|---|---|---|
| Chromium 153 (Playwright 1.63, headless) | stock-web | **Sim-getest** (geslaagd) | Direct Play, eerste frame 615 ms, audio gedecodeerd |
| Firefox 155 | stock-web | **Sim-getest** (geslaagd) | Direct Play, eerste frame 487 ms |
| WebKit 26.6 (Linux; géén Safari) | stock-web | **Sim-getest** (geslaagd) | Direct Play, eerste frame 886 ms |
| webOS via UA-simulatie (Chromium-engine) | Jelly Leon-webclient (profielcode) | **Sim-getest** (UA-simulatie, geen echte decoder) | tv-layout; DeviceProfile met AC3/E-AC3/HEVC in mkv/mp4/ts; echte tv NIET GEVALIDEERD (hardware) |
| Tizen via UA-simulatie (Chromium-engine) | idem | **Sim-getest** (UA-simulatie) | idem (plus msmpeg4v2, aac_latm) |
| stock-web via `--webdir` (jellyfin-web uit de stock-image) | stock-web | **Sim-getest** (geslaagd) | mechanisme voor stock-web tegen de Jelly Leon-server |
| derden-client met legacy-headers (gesimuleerd) | stock-native (derden) | **Sim-getest** (gemeten) | 12.4 (`EnableLegacyAuthorization` = false): `X-Emby-Token`, `X-MediaBrowser-Token`, `X-Emby-Authorization` en `?api_key=` → **401** op `/System/Info` en `/Users/{id}/Items`; `Authorization: MediaBrowser Token=…` en `?ApiKey=` → 200; `/Videos/{id}/stream?static=true` → **206 ook zonder token** (ADR-0009). Besluit derden-clients: BG-01 |
| jellyfin-android 2.7.3 (officiële release-APK, sha256 f9f4b3ab…), telefoon-AVD API 35 x86_64 (pixel_6, scherm 720x1600) | Jelly Leon-webclient (webweergave) | **Sim-getest** (binnen 4 GiB) | inloggen in de webweergave; native speler (Direct Play); boot 21 s |
| idem, tablet-AVD API 35 (pixel_tablet, 1280x800, ≥ 600 dp) | idem | **Sim-getest** (binnen 4 GiB) | idem |
| jellyfin-androidtv 0.19.10 (officiële release-APK, sha256 8510a517…), Android TV API 34 x86 (tv_720p) | stock-native | **Sim-getest** (binnen 4 GiB) | inloggen via Quick Connect (`POST /QuickConnect/Authorize` door de testgebruiker); Direct Play |
| idem, Android TV API 36 x86_64 (image met sdkmanager geïnstalleerd) | stock-native | **Sim-getest** (binnen 4 GiB) | idem |
| desktop 2.0.0 onder Xvfb (eigen build uit jelly-leon-clients) | Jelly Leon-webclient | **Geblokkeerd** (spike niet geslaagd) | zie §2.3 |
| Swiftfin, Safari, Apple TV | stock-native | **NIET GEVALIDEERD (Mac/Xcode)** | geen Mac/Xcode |
| Echte tv's, telefoons, receivers, Chromecast, DLNA | alle | **NIET GEVALIDEERD (hardware)** | D15 onbekend; JLT-69 |

### 2.1 Emulators: geheugen en locks

Alle emulatorruns in een container met `--device /dev/kvm` (gid via `--group-add`), `--memory 4g --memory-swap 4g`,
onder `gradle.lock` binnen `stack.lock`, één tegelijk. Geen OOM-kill in de geslaagde runs (`memory.events: oom_kill 0`);
`memory.peak` ligt op de limiet omdat de paginacache van de systeemimages meetelt. Gemeten en opgelost: met het standaard
pixel_6-scherm (1080x2400) en Vulkan werd de telefoonemulator binnen 4 GiB door de OOM-killer gestopt zodra de app
afspeelde (`oom_kill 1`, `memory.peak 4097 MiB`); met een kleiner scherm en `-feature -Vulkan` niet meer. Het Android
TV-image weigerde adb ("unauthorized") tot de adb-server vóór de emulator start (sleutel in het image).

### 2.2 In CI

De CI-job draait dezelfde rooktest tegen stock 12.4 met een synthetisch mini-corpus. Een GitHub-runner heeft geen
audiohardware: gemeten in runs 42725506092 en 42726891316 decodeert Chromium met een desktop-UA daar geen audio (beeld
speelt wel; met webOS/Tizen-UA wel audio) en blijft WebKit/GStreamer na ~0,2 s hangen, ook met een PulseAudio-null-sink.
In CI telt daarom het beeld voor die twee (waarschuwing in de log); het audio-orakel en WebKit zijn lokaal getoetst (tabel
hierboven). CI-run 42728331528 (commit bd5488d2b): alle 8 jobs groen.

### 2.3 Desktop-spike — **Geblokkeerd** (spike niet geslaagd)

`python -m b03h desktop` (bewijs `test-evidence/b03-016-desktop-spike.json`). jellyfin-desktop 2.0.0 is gebouwd uit de
forkbron in `jelly-leon-clients/desktop` (commit f11bf13, alleen gelezen) met de bouwomgeving van die repo onder
`docker-build.lock` (62/62 stappen) en draait onder Xvfb in een container met libmpv en de Intel-VA-API-driver. Gemeten:
de app start (na het toevoegen van de QML-runtimemodules uit `desktop/debian/control`), en **ruwe CDP via de Node
22-WebSocket werkt** (`/json/version`: `jellyfin-desktop/2.0.0`; de servers-pagina is bestuurbaar) — Playwright
`connectOverCDP` is daarvoor niet nodig. **Niet gelukt:** na het versturen van het serveradres laadt de app de
jellyfin-web van de server niet binnen 60 s (blijft op `find-webclient.html`; oorzaak in `jmpCheckServerConnectivity` niet
vastgesteld). Inloggen en afspelen van `hero.mp4` en de ChunkLoadError-vraag uit analyse 5 §4 zijn daardoor niet beproefd.
Volgens de acceptatie staat de desktop daarom op **Geblokkeerd**; vervolg is de gezamenlijke spike met
`jelly-leon-clients` (consolelog van de app uitlezen via CDP `Runtime.consoleAPICalled`, of de servers-check overslaan met
een vooraf ingevuld profiel).

## 3. Baselines (deel c)

Bewijs: `test-evidence/b03-016-baseline-voormeting-12.4.json` (+ ruwe gegevens per run in de gelijknamige map:
gevangen DeviceProfiles, beslissingsmatrix, orakelresultaten per item, transcoderuns met ffmpeg-log-gegevens). Twee
systemen op één wegwerpserver: **stock-standaard** (config-sha256 `a1c12f6c…`) en **stock-best** (`1df13ed9…`: handmatige
QSV op `/dev/dri/renderD128` met tonemapping en low-power, `profielen/stock-best.json`). Meetslot `stack.lock`; per run
loadavg, CPU van machine/harnas/containers en zware sloten; A/B gebalanceerd afwisselend; ≥ 3 runs; tijdgevoelige runs
begrensd herhaald tot ze geldig zijn. Alle runs in het bewijs zijn geldig. Een tweede, volledig nieuwe meetsessie (nieuwe
server, 2026-11-10T01:59Z) is de herhaling ("sessie 2").

### 3.1 Overzicht (uit `python -m b03h rapport`)

| Metriek | Systeem | Waarde (eerste meting) | 95 %-interval | Gate | Geldige runs | Herhaling(en) | Herhaling binnen interval |
|---|---|---|---|---|---|---|---|
| F6-a-mediasegments | stock-standaard | 0/14 | [0; 0,215] | smoke-gate (n = 14) | 3/3 | [0, 0, 'sessie 2: 0'] | ja |
| F3-a-ondertitels-nld-zoeken | stock-standaard | 0/4 | [0; 0,49] | smoke-gate (n = 4) | 3/3 | [0, 0, 'sessie 2: 0'] | ja |
| F4-a-kwaliteitsmeldingen | stock-standaard | 0/8 | [0; 0,324] | smoke-gate (n = 8) | 3/3 | [0, 0, 'sessie 2: 0'] | ja |
| F2-a-koude-start | stock-standaard | categorieen=0, suggesties=12, similar_serie_pioneer=2, similar_sintel=[] | — | — | 3/3 | runs + sessie 2 | ja |
| F6-a-mediasegments | stock-best | 0/14 | [0; 0,215] | smoke-gate (n = 14) | 3/3 | [0, 0, 'sessie 2: 0'] | ja |
| F3-a-ondertitels-nld-zoeken | stock-best | 0/4 | [0; 0,49] | smoke-gate (n = 4) | 3/3 | [0, 0, 'sessie 2: 0'] | ja |
| F4-a-kwaliteitsmeldingen | stock-best | 0/8 | [0; 0,324] | smoke-gate (n = 8) | 3/3 | [0, 0, 'sessie 2: 0'] | ja |
| F2-a-koude-start | stock-best | categorieen=0, suggesties=12, similar_serie_pioneer=2, similar_sintel=[] | — | — | 3/3 | runs + sessie 2 | ja |
| F5-K6-transcode-dv-p8.1-1080p-snelheid | stock-best | 6,533 × realtime | [6,505; 6,562] | gate | 3/3 | ['6,45', '5,98', '5,66'] | **nee** |
| F5-K6-transcode-dv-p8.1-1080p-cpu | stock-best | 0,155 CPU-s per media-s | [0,122; 0,187] | gate | 3/3 | ['0,157', '0,157', '0,152'] | ja |
| F5-K6-transcode-dv-p8.1-1080p-eerste-frame | stock-best | 1743 ms | [1701,21; 1784,79] | gate | 3/3 | ['1868', '1857', '1947'] | **nee** |
| F5-K6-transcode-hevc10-hdr10-1080p-snelheid | stock-best | 6,647 × realtime | [6,481; 6,812] | gate | 3/3 | ['6,38', '5,75', '5,75'] | **nee** |
| F5-K6-transcode-hevc10-hdr10-1080p-cpu | stock-best | 0,144 CPU-s per media-s | [0,135; 0,153] | gate | 3/3 | ['0,157', '0,151', '0,143'] | ja |
| F5-K6-transcode-hevc10-hdr10-1080p-eerste-frame | stock-best | 1679 ms | [1559,58; 1798,42] | gate | 3/3 | ['1753', '1711', '1857'] | ja |
| F5-K6-transcode-dv-p8.1-1080p-snelheid | stock-standaard | 3,937 × realtime | [3,861; 4,013] | gate | 3/3 | ['3,5', '3,7'] | **nee** |
| F5-K6-transcode-dv-p8.1-1080p-cpu | stock-standaard | 3,686 CPU-s per media-s | [3,646; 3,727] | gate | 3/3 | ['3,847', '3,794'] | **nee** |
| F5-K6-transcode-dv-p8.1-1080p-eerste-frame | stock-standaard | 2455 ms | [2066,989; 2843,011] | gate | 3/3 | ['2915', '2645'] | ja |
| F5-K6-transcode-hevc10-hdr10-1080p-snelheid | stock-standaard | 4,067 × realtime | [4,052; 4,081] | gate | 3/3 | ['4', '3,88', '3,64'] | **nee** |
| F5-K6-transcode-hevc10-hdr10-1080p-cpu | stock-standaard | 3,472 CPU-s per media-s | [3,447; 3,497] | gate | 3/3 | ['3,535', '3,502', '3,562'] | **nee** |
| F5-K6-transcode-hevc10-hdr10-1080p-eerste-frame | stock-standaard | 2429,333 ms | [2370,478; 2488,189] | gate | 3/3 | ['2447', '2607', '2923'] | **nee** |
| F5-B1-dp-beslissing-chromium | stock-best | 16/25 | [0,445; 0,798] | gate | 3/3 | [16, 16, 'sessie 2: 16'] | ja |
| F5-B1-dp-beslissing-firefox | stock-best | 17/25 | [0,484; 0,828] | gate | 3/3 | [17, 17, 'sessie 2: 17'] | ja |
| F5-B1-dp-beslissing-webkit | stock-best | 21/25 | [0,653; 0,936] | gate | 3/3 | [21, 21, 'sessie 2: 21'] | ja |
| F5-B1-dp-beslissing-chromium | stock-standaard | 16/25 | [0,445; 0,798] | gate | 3/3 | [16, 16, 'sessie 2: 16'] | ja |
| F5-B1-dp-beslissing-firefox | stock-standaard | 17/25 | [0,484; 0,828] | gate | 3/3 | [17, 17, 'sessie 2: 17'] | ja |
| F5-B1-dp-beslissing-webkit | stock-standaard | 21/25 | [0,653; 0,936] | gate | 3/3 | [21, 21, 'sessie 2: 21'] | ja |
| F5-K3-dp-effectief-chromium | stock-best | 16/25 | [0,445; 0,798] | gate | 1/1 | [] | — |
| F5-K3-dp-effectief-firefox | stock-best | 17/25 | [0,484; 0,828] | gate | 1/1 | [] | — |
| F5-K3-dp-effectief-webkit | stock-best | 20/25 | [0,609; 0,911] | gate | 1/1 | [] | — |
| F5-K3-dp-effectief-chromium | stock-standaard | 16/25 | [0,445; 0,798] | gate | 2/2 | [16] | ja |
| F5-K3-dp-effectief-firefox | stock-standaard | 17/25 | [0,484; 0,828] | gate | 2/2 | [17] | ja |
| F5-K3-dp-effectief-webkit | stock-standaard | 20/25 | [0,609; 0,911] | gate | 2/2 | [20] | ja |


Lezen: proporties = k/n met Wilson-95 %-interval (gate = ondergrens; bij n < streef-n "smoke-gate"); continue waarden =
gemiddelde over de geldige runs met t-interval; "herhaling binnen interval" = de runs van sessie 2 vallen binnen het
95 %-voorspellingsinterval van sessie 1 (continu) of binnen het Wilson-interval (proporties).

### 3.2 Wat de metingen zeggen (voormeting, stock 12.4)

- **Direct Play-beslissingen (F5 B1)** met de echte jellyfin-web-profielen: Chromium 16/25, Firefox 17/25, WebKit 21/25 —
  exact gelijk aan analyse 5 §6.2, in beide systemen, in alle runs en in sessie 2. **Effectief** (orakel, F5 K3):
  Chromium 16/25, Firefox 17/25, WebKit 20/25 (Sintel mkv + AC3: Direct Play gekozen, speelt niet = 1 onterechte DP), in
  beide systemen. Verschil a/b zit in wat er überhaupt speelt: stock-standaard 23/25 in Chromium en Firefox (de 4K-DV- en
  4K-HDR10-transcode in software haalt binnen 10 s geen 2 s afspeeltijd), stock-best 25/25.
- **Upstream-gedrag (gemeten):** een "kale" `PlaybackInfo`-aanvraag zonder `MediaSourceId` + `AudioStreamIndex` toetst in
  12.4 de audiocodec niet: Sintel (mkv + AC3) krijgt dan Direct Play in Chromium terwijl het profiel geen AC3 kent; met de
  velden die de webclient meestuurt: Transcode (AudioCodecNotSupported). Het harnas vraagt daarom zoals de webclient;
  kandidaat voor `UPSTREAM_GEDRAG.md` (B03-019).
- **Transcode op de iGPU (F5 B5/B5b/K6):** DV P8.1 1080p → H.264 SDR in een echte Chromium-sessie: stock-standaard
  (libx264 + tonemapx) 3,94× realtime bij 3,69 CPU-seconden per mediaseconde (≈ 14 kernen tijdens de transcode), eerste
  frame 2,5 s; stock-best (h264_qsv + tonemap_vaapi) 6,53× bij 0,155 CPU-s per media-s (≈ 1 kern), eerste frame 1,7 s.
  HEVC10-HDR10 vergelijkbaar (4,07× / 3,47 tegen 6,65× / 0,144). Stock-best gebruikt dus ≈ 24× minder CPU per
  mediaseconde. **Intel-iGPU-getest (ontwikkelmachine)**; geen capaciteit van A310/UHD 770.
- **Herhaalbaarheid:** alle beslissings- en functiemetingen en het CPU-gebruik van stock-best vallen in sessie 2 binnen
  het interval. De **snelheid** (× realtime) en deels het eerste frame niet: in sessie 2 lag de snelheid 3–14 % lager
  (stock-best DV 6,45/5,98/5,66 tegen 6,53 in sessie 1; stock-standaard DV 3,5/3,7 tegen 3,94), terwijl alle runs geldig
  waren (loadavg < 4, andere processen < 1 kern). Vermoedelijke oorzaak (niet bewezen): thermische terugschakeling van de
  laptop-CPU/-iGPU na urenlange belasting. Gevolg voor het protocol: absolute snelheden zijn tussen sessies niet stabiel
  genoeg; een functie-gate vergelijkt daarom alleen **afwisselend binnen één sessie** (zoals het plan voorschrijft) en
  rapporteert de spreiding tussen sessies. Dit is als bevinding opgenomen, niet weggepoetst.
- **Functies zonder Jelly Leon (F2/F3/F4/F6):** MediaSegments 0/14 afleveringen (Wilson-bovengrens 0,215; smoke-gate n = 14),
  NL-ondertitels zoeken 0/4 (geen provider), kwaliteitsmeldingen 0/8 (stock meldt beschadiging, afkapping, stilte,
  clipping, ontbrekende audio, verkeerde taaltags, M&E-hoofdspoor en een foutieve HLG-tag nergens; de afgekapte clip houdt
  zijn volledige duur van 62,08 s en de HLG-getagde HDR10-clip heet `HDR10`), aanbevelingen bij een koude start: 0
  categorieën, 12 willekeurige suggesties, 2 "vergelijkbare" items voor Pioneer One en geen voor Sintel (online metadata
  uit). Identiek in alle runs en in sessie 2.
- De eerste rij van elke functie (B03-020, -030, -040, -052/054, -060, -070) levert haar eigen metrieken in dit raamwerk (met
  de bevroren testsets uit §1); de definitieve meting volgt in P4-0 op de forkbasis-digest.

## 4. Differentiële controle-run

`python -m b03h diffrun` (bewijs `test-evidence/b03-016-diffrun-stock-stock.json`): twee stock-containers op kopieën van
dezelfde datamap (17 items), hetzelfde scenario (14 handelingen: gezien met vaste datum, favoriet, vind-ik-leuk,
hervatpunt 12,345 s met spoorkeuze). Vergelijking van alle 33 tabellen van de 12.x-database (`jellyfin.db`: o.a.
`BaseItems`, `UserData`, `Users`, `Devices`, `ActivityLogs`): **0 verschillen buiten de vaste uitzonderingen**. Geraakte
uitzonderingen: `Users.LastActivityDate/LastLoginDate`, `UserData.LastPlayedDate` (tijdstip van afspelen),
`Devices.AccessToken/DateCreated/DateModified/DateLastActivity`, `ActivityLogs.DateCreated`. **Negatieve proef**
(`--negatieve-proef`, één extra favoriet op systeem b): 2 verschillen in `UserData` gevonden
(`test-evidence/b03-016-diffrun-negatieve-proef.json`). Tokens en wachtwoorden komen nooit in het rapport. In CI draait
dezelfde controle-run met negatieve proef (run 42728331528: groen).

## 5. Wat NIET gevalideerd is en wat ontbreekt

| Onderdeel | Status | Reden |
|---|---|---|
| A310 en UHD 770 (capaciteit, LP-modus, AV1-encode) | NIET GEVALIDEERD (hardware) | alleen de Meteor Lake-iGPU van de ontwikkelmachine; D08 onbekend |
| Echte tv's, telefoons, tablets, receivers (D15) | NIET GEVALIDEERD (hardware) | emulators en UA-simulatie hebben geen AC3/DTS/DV-decoders; JLT-69 |
| Swiftfin, Safari, Apple TV | NIET GEVALIDEERD (Mac/Xcode) | geen Mac |
| NAS, HDD-pool, echte bibliotheek | NIET GEVALIDEERD (echte NAS) | — |
| Definitieve baselines op de forkbasis-digest | open (P4-0) | de fork draait nog op 10.11.11 (B03-014) |
| F3-testsplit: "verkeerde taal" en OPUS-MT-uitvoer als goed document | ontbreekt | geen andere talen voor Pioneer One; OPUS-MT is P5 (optionele app) |
| PGS/VobSub, TrueHD/DTS/Atmos, DV-profiel 7, echte anime | ontbreekt in het corpus | CORPUS.md §4; JLT-47 deels Geblokkeerd |
| WebKit en het audio-orakel in CI | alleen lokaal getoetst | runner zonder audiohardware (§2.2) |
