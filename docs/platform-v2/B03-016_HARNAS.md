# B03-016 — echt mediacorpus, clientmatrix-testomgeving en baselinemeting standaard Jellyfin

Werkpakket B03-016 (F0 - Inventaris & onderzoek · Testen · P0), golf 0: **voormeting tegen stock
`jellyfin/jellyfin:12.4@sha256:fea863d0…1771`**; in P4-0 opnieuw op exact de 12.x-tag en -digest van de forkbasis.
Bindend: bouwplan B03 2.0 §10.13–§10.15 en de rij B03-016; besluiten BG-37 (testdata met beperkende licentie alleen
lokaal) en BG-38 (testsets on demand maken en weggooien; alleen recept en manifest blijven). Ontwerpkeuzes: ADR-0026.
Gemeten uitkomsten: `BOUWVERIFICATIE_B03-016.md`. Code: `tools/b03-harnas/`.

Dit is gereedschap voor de ontwikkelmachine en CI. Het draait nooit op de NAS en komt nooit in de Jelly Leon-image (de
image-guard in CI controleert dat). Er is dus geen Custom App-formulier voor; de installatie van Jelly Leon zelf staat in
`deploy/truenas/CUSTOM_APP.md`.

## 1. Corpus en corpusgenerator (deel a)

- **Bestaand corpus** (`<WERKMAP>/.lokaal/media-corpus`, CORPUS.md): 34 bronbestanden, 75 ondertitels,
  31 afgeleide gevallen, sha256 per bestand en licentie per bron. Controle: `python -m b03h corpus bron-controle`
  (= `sha256sum -c` op `SHA256SUMS.bron.txt`, `SHA256SUMS.ondertitels.txt` en `SHA256SUMS.afgeleid.txt`).
- **Eén generator, acht recepten** (`python -m b03h corpus lijst`):

| Recept | Functie | Wat (grondwaarheid in de set) | Streef-n bij `--schaal vol` |
|---|---|---|---|
| `f1-framecode` | F1 | hero.mp4 met 16 binaire blokken per frame + tijdcode; decodeerregel en geometrie | 1 video (236 s) |
| `f2-dsyn` | F2 | 300 stub-items met NFO (genres, tags, personen, type, keur), 3 huishoudens met verborgen voorkeur, training/test | 300 items, 6 gebruikers |
| `f3-ondertitels` | F3 | per fouttype (verkeerde taal, onvertaald, geschud, afgekapt, gehallucineerd, verschoven, inhoudelijk verkeerd) varianten in vensters van 25 cues; kalibratiesplit ToS + Sintel, testsplit Pioneer One (beperkt) | ≥ 20 per type per split |
| `f4-tqc` | F4 | T-QC: decode_error per codecklasse (H.264, HEVC8/10, AV1, MPEG-2, VP9, MPEG-4) met framemd5-grondwaarheid, audio-decode_error per codec, truncated/container_error, stilte/kanaal/korter, dropout/clipping, ondertitel offset/drift/andere versie/taal; N-QC-rommelig | 30 / 20 / 32 / 20 per klasse; rommelig 5 per soort |
| `f5-fouten` | F5 | gecontroleerde fouten: liegende `canPlayType`/`isTypeSupported` (init-scripts), geforceerd Android-profiel (AC3/E-AC3/DTS), WebKit + Sintel; devset 3, testset 6 × 3 clients; + ASS | 3 + 18 combinaties |
| `f6-segmenten` | F6 | 6 series × 10 afleveringen met intro, aftiteling, recap, preview, post-/mid-credit, intro buiten het IS-venster, nieuwe OP in seizoen 2, augmentatie per aflevering | intro/outro 60, recap ≥ 40, preview ≥ 30, beschermd ≥ 30, buiten venster ≥ 20, nieuwe OP ≥ 20 |
| `ass` | F5 | Sintel 120–180 s met het NL-spoor als ASS | 1 |
| `groot-bestand` | F4/F5 | Sintel herhaald via stream-copy tot de doelgrootte (≤ 20 GB, met vrije-ruimtecontrole) | standaard 4 GB (`--param doel_bytes=…`) |

- **Reproduceerbaar:** de recepten gebruiken de jellyfin-ffmpeg uit de vastgezette stock-image (`--ffmpeg docker`), vaste
  seeds, bitexact-vlaggen, exacte lengtes via `trim`/`atrim` en één encoderthread. Zelfde seed + parameters = zelfde
  `set_sha256`. Dat wordt getest (CI: alle recepten twee keer op een synthetisch mini-corpus) en lokaal op het echte corpus.
- **Schrijven:** een set wordt in `.bouw-…` gemaakt en pas na het manifest atomair hernoemd; downloads gaan altijd via een
  tijdelijk bestand + sha256 + `os.replace` met een exclusief slot per doel (analyse 5 §5.2: twee schrijvers maakten eerder
  een clip corrupt).
- **Bevriezen vóór het afstemmen:** `python -m b03h corpus maak <recept> --schaal vol --bevries` legt het manifest vast in
  `test-evidence/b03-016-corpus/<recept>.v<versie>.<schaal>.manifest.json` (alleen paden, groottes, sha256, seed,
  parameters, ffmpeg-versie, bronnen met sha256 en licenties). Bestaat dat al, dan moet de nieuwe set exact gelijk zijn;
  anders weigert de generator ("niet reproduceerbaar" of "nieuwe versie nodig").
- **Opruimen (BG-38):** `python -m b03h corpus opruimen <set>` of `--alles` (alleen onder de uitvoermap).
- **CI-guard testdatalicenties:** `python -m b03h guard --git .` (hele boom), `--bereik . A..B` (elke gepushte commit, ook
  als een latere commit het bestand weer weghaalt) en `--image REF`. Weigert namen (Pioneer One, MovieLens, Addic7ed,
  corpuspad), de sha256 van de beperkte bronbestanden (`b03h/beperkt_sha256.txt`; hernoemen helpt niet), MovieLens-CSV-koppen,
  de markering die de generator in elke beperkte set zet, en in de repo elk media- of ondertitelbestand buiten de kleine
  upstream-testbestanden. Negatieve tests in `tools/b03-harnas/tests/test_guard.py`.

## 2. Clientmatrix (deel b)

`python -m b03h clientmatrix` start een wegwerp-stockserver (127.0.0.1, media alleen-lezen) en doet per client een rooktest
met `hero.mp4` (orakel: binnen 15 s currentTime ≥ 2 s, beeld, geen fout en geen stilte bij een item met audio).

| Client / omgeving | Rol | Hoe | Label |
|---|---|---|---|
| Chromium, Firefox, WebKit (Playwright 1.63.0, headless) | stock-web | inloggen en afspelen via de UI | Sim-getest; WebKit op Linux is geen Safari |
| webOS en Tizen | Jelly Leon-webclient (profielcode) | Chromium met de UA van de tv; DeviceProfile wordt gevangen | Sim-getest (UA-simulatie, geen echte decoder); echte tv NIET GEVALIDEERD (hardware) |
| stock-web via `--webdir` | stock-web | jellyfin-web uit de stock-image, geserveerd met `--webdir` door een andere server | Sim-getest (mechanisme voor stock-web tegen Jelly Leon) |
| derden-client met legacy-headers | stock-native (derden) | X-Emby-Token, X-MediaBrowser-Token, X-Emby-Authorization, `api_key`, `ApiKey` | Sim-getest (gemeten status per vorm; besluit BG-01) |
| Android-telefoon (API 35, pixel_6), tablet (API 35, pixel_tablet) | officiële jellyfin-android 2.7.3 = Jelly Leon-webclient (webweergave) | emulator in een container met `--device /dev/kvm`, 4 GiB, onder `gradle.lock` in `stack.lock`; afspelen via `POST /Sessions/{id}/Playing`, gecontroleerd aan de serverkant | Sim-getest of Sim-mislukt met reden |
| Android TV (API 34 x86, tv_1080p) | officiële jellyfin-androidtv 0.19.10 (native) | idem | idem |
| Desktop 2.0.0 onder Xvfb | Jelly Leon-webclient | alleen na de gezamenlijke spike (`desktop/`) | Geblokkeerd zonder geslaagde spike |
| Swiftfin, Safari, Apple TV | stock-native | — | NIET GEVALIDEERD (Mac/Xcode) |
| Echte tv's, telefoons, receivers, Chromecast, DLNA | alle | — | NIET GEVALIDEERD (hardware), JLT-69 (D15) |

De emulator mist AC3/E-AC3/DTS/TrueHD- en Dolby Vision-decoders (analyse 5 §2.2); passthrough- en HDR-beslissingen van
echte tv's zijn hier dus niet te toetsen.

## 3. Harnas, meetprotocol en baselines (deel c)

- **Eén harnasraamwerk** (`b03h.statistiek`, `b03h.meetslot`, `b03h.bewijs`): exclusief meetslot onder `stack.lock`;
  `gradle.lock` en `docker-build.lock` worden per run gecontroleerd; loadavg vóór en na en de CPU van de machine, van het
  harnas (incl. browsers) en van de eigen testcontainers per run in het bewijs; **een run is ongeldig** (niet mislukt) bij
  loadavg(1 min) > 4 vóór de run, andere processen > 4 kernen tijdens de run of een actief zwaar slot. Tijdgevoelige runs
  worden begrensd herhaald; ongeldige pogingen blijven zichtbaar.
- **≥ 3 runs, A/B gebalanceerd afwisselend** (a,b | b,a | a,b). Proporties: n, k en het Wilson-95 %-interval; de gate
  gebruikt de ondergrens, bij te kleine n heet het **smoke-gate (n = …)**. Continue waarden: t-interval over de geldige
  runs. Elke metriek krijgt een herhaling die binnen het interval van de eerste meting moet vallen.
- **Twee baselines** op dezelfde server en datamap: **stock-standaard** (`profielen/stock-standaard.json`) en **stock-best**
  (`profielen/stock-best.json`: handmatige QSV op `/dev/dri/renderD128` met tonemapping en low-power, de
  client-instellingen per functie). De config-sha256 per systeem staat in het bewijs. "Aantoonbaar beter" alleen tegen
  stock-best; alleen tegen stock-standaard heet het "beter dan de standaardinstelling".
- **Voormeting en definitief apart gelabeld:** `--label voormeting-12.4` (nu) of `definitief-forkbasis` (P4-0, met
  `--image` op de 12.x-digest van de forkbasis).
- **Differentiële controle-run** (`python -m b03h diffrun`): twee systemen, hetzelfde scenario (gezien met vaste datum,
  favoriet, vind-ik-leuk, hervatpunt met spoorkeuze) op kopieën van dezelfde datamap; vergelijking van de echte
  12.x-tabellen met vaste uitzonderingen (`Users.LastActivityDate`/`LastLoginDate`, `BaseItems.DateLastSaved`,
  `UserData.LastPlayedDate`, `Devices`-tokens en -tijden, `ActivityLogs`-tijden) en een toegestane wijzigingslijst per module
  (`--toegestaan`). `--negatieve-proef` bewijst dat een echte wijziging gevonden wordt. Geheime kolommen worden nooit getoond.
- De eerste rij van elke functie (B03-020, -030, -040, -052/054-voorbereiding, -060, -070) levert haar eigen metingen in dit
  raamwerk; hier staan de gemeenschappelijke voormetingen (Direct Play, transcode op de iGPU, functie-API's).

## 4. Wat hier NIET gevalideerd kan worden

- A310 en UHD 770 (de Meteor Lake-iGPU is functioneel bewijs en bovengrens: **Intel-iGPU-getest (ontwikkelmachine)**, in de
  opmerking): **NIET GEVALIDEERD (hardware)**; render-node en render-gid op de NAS komen uit D08.
- Echte tv's, telefoons, receivers (D15): **NIET GEVALIDEERD (hardware)**; Swiftfin/Safari: **NIET GEVALIDEERD (Mac/Xcode)**.
- De NAS, zijn HDD-pool en de echte bibliotheek: **NIET GEVALIDEERD (echte NAS)**.
