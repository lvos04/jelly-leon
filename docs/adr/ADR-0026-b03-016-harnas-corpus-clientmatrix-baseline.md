# ADR-0026 — B03-016: één harnasraamwerk voor corpusgenerator, clientmatrix en baselines van stock Jellyfin

- **Status:** Aanvaard (2026-11-09) — bouwerbesluit binnen B03-016 (golf 0); geen gebruikersbesluit nodig (de genomen
  besluiten BG-37 en BG-38 zijn gevolgd).
- **Werkpakket / testen:** B03-016 (golf 0 nu als voormeting tegen stock 12.4; definitief in P4-0 op de 12.x-digest van de
  forkbasis). Bouwt mee aan JLT-63 (rooktest stock-clients), JLT-65 (differentiële controle-run) en de eerste rij van elke
  functie (B03-020, -030, -040, -052/054, -060, -070), die hun metingen in dit raamwerk leveren.
- **Uitvoering:** `tools/b03-harnas/` (Python 3.12, alleen standaardbibliotheek; Node 22 + Playwright 1.63.0 voor de
  browsers), bewijs in `docs/platform-v2/test-evidence/b03-016-*`.

## Context

Het bouwplan (B03 2.0 §10.13–§10.15 en de rij B03-016) vraagt één corpusgenerator met grondwaarheid en seed voor alle
recepten van F1–F6, testsets die vóór het afstemmen bevroren worden met een sha256-manifest, een CI-guard tegen beperkt
gelicentieerde testdata, een clientmatrix (Chromium/Firefox/WebKit, Android-telefoon/-tablet/-tv in een KVM-container,
webOS/Tizen via UA-simulatie, stock-web via `--webdir`, één derden-client met legacy-headers, desktop alleen na een spike)
en één harnasraamwerk met meetprotocol: exclusief meetslot onder `stack.lock`, geen docker-build of Gradle tegelijk,
loadavg in het bewijs, ≥ 3 runs, A/B afwisselend, een run boven de lastgrens is ongeldig, n en Wilson-intervallen, het
label smoke-gate bij te kleine n, en een differentiële controle-run.

De ontwikkelmachine is gedeeld (22 CPU's, 14,5 GiB RAM, schijf ~90 % vol) en heeft een Meteor Lake-iGPU; de NAS-GPU's
(A310, UHD 770) zijn hier niet beschikbaar.

## Besluit

1. **Eén Python-pakket `b03h`** (stdlib) met vaste onderdelen: `statistiek` (Wilson, t-interval, bootstrap, gate-label),
   `meetslot` (sloten, last, A/B-volgorde), `bewijs` (verplichte velden per metriek; validatie volgens contract §11),
   `corpus` (generator, recepten, manifest, download), `guard` (CI-guard), `stock` (wegwerp-stockserver), `baseline`,
   `clientmatrix`, `android`, `diffrun`, `legacy`. Geen numpy/scipy: dezelfde getallen in CI en lokaal.
2. **Recepten draaien met de jellyfin-ffmpeg uit de vastgezette stock-image** (`--ffmpeg docker`, zonder netwerk, als de
   eigen gebruiker, bron alleen-lezen). Uitvoer **bit-exact**: `-fflags/-flags +bitexact`, geen metadata, exacte lengtes via
   `trim`/`atrim`, vaste seeds (ook voor het `noise`-filter) en **één encoderthread** — gemeten: libx264 met meerdere
   threads gaf per run een andere uitvoer. Een set wordt in `.bouw-…` gemaakt en pas na het manifest atomair hernoemd.
3. **Bevriezen** = het manifest (alleen paden, groottes, sha256, recept, seed, parameters, ffmpeg-versie, licenties) komt in
   `docs/platform-v2/test-evidence/b03-016-corpus/`. Een tweede generatie met dezelfde seed moet exact gelijk zijn, anders
   weigert de generator (nieuwe versie nodig). De media zelf blijven buiten de repo en worden na gebruik opgeruimd (BG-38).
4. **Beperkte licenties (BG-37):** sets met Pioneer One of fanondertitels krijgen in elke JSON een markering en een
   `LICENTIE-BEPERKT.txt`. De CI-guard weigert in commits (hele boom én elk commitbereik, ook als een latere commit het
   bestand weer weghaalt) en in images: namen (Pioneer One, MovieLens, Addic7ed, het corpuspad), sha256 van de beperkte
   bronbestanden (hernoemd telt ook), MovieLens-CSV-koppen, de markering, en in de repo elk media-/ondertitelbestand
   buiten de kleine upstream-testbestanden.
5. **Twee baselines op één wegwerpserver:** stock-standaard en stock-best wisselen per run het encodingprofiel
   (`profielen/stock-*.json`); de profielen staan in de repo en de config-sha256 per systeem in het bewijs. Bibliotheken
   zonder online metadata (geen internetverkeer vanuit de meetserver, gelijke metadata voor alle systemen) — dit is de
   enige afwijking van "puur standaard" en staat in het profiel.
6. **"Buiten de eigen processen"** wordt gemeten, niet geschat: CPU van de hele machine (`/proc/stat`) min de CPU van het
   harnas en zijn nakomelingen (browsers) min de cgroup-CPU van de eigen testcontainers. Een tijdgevoelige run wordt
   begrensd herhaald tot hij geldig is; ongeldige pogingen blijven in het bewijs.
7. **Emulators** alleen in een container met `--device /dev/kvm` (gid via `--group-add`), 4 GiB geheugen = swaplimiet,
   `--network host` (de app bereikt de server via 10.0.2.2), onder `gradle.lock` binnen `stack.lock`; AVD's buiten de repo;
   officiële APK's via de downloader met de sha256 uit de GitHub-release. Afspelen wordt gestart via de officiële
   afstandsbedieningsroute en aan de serverkant gecontroleerd (PositionTicks ≥ 2 s).
8. **Desktop:** alleen een tijdgebonden spike; zonder geslaagde spike staat de desktop op **Geblokkeerd** met reden
   (acceptatie B03-016), nooit "half geslaagd".

## Gevolgen

- Elke functierij (B03-020 … B03-070) gebruikt dezelfde statistiek, hetzelfde slot en hetzelfde bewijsformaat; een
  winstclaim zonder baseline of op een niet-bevroren set is onmogelijk zonder het raamwerk te omzeilen.
- Metingen hangen af van de last van andere agents op de gedeelde machine: ongeldige runs kosten tijd, maar maken geen
  resultaat mooier dan het is.
- De Meteor Lake-iGPU geldt als functioneel bewijs en bovengrens ("Intel-iGPU-getest (ontwikkelmachine)"); A310/UHD 770
  blijven NIET GEVALIDEERD (hardware). Tot contract 1.2 stond die waarde in de opmerking (niet in §11); sinds contract 1.3
  is het een vaste validatiewaarde en staat hij in `validatie` (C1.3-JL-02, bewaakt door
  `tools/jelly-leon/tests/test_evidence_contract.py`).
- De metingen hier zijn **voormetingen op 12.4**; in P4-0 worden ze herhaald op exact de 12.x-tag en -digest van de
  forkbasis (label `definitief-forkbasis`).
