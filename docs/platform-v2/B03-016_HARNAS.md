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
  Op 27 november 2026 kwamen alle 140 bestanden overeen met hun manifest. [Corpuscontrole voor S-P40-50](test-evidence/b03-016-corpuscontrole-2026-11-27.json)
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
met `hero.mp4` (orakel: binnen 15 s currentTime ≥ 2 s, beeld, geen fout en controle op audiodecodering waar beschikbaar).

| Client / omgeving | Rol | Hoe | Label |
|---|---|---|---|
| Chromium, Firefox, WebKit (Playwright 1.63.0, headless) | stock-web | inloggen en afspelen via de UI | Sim-getest; WebKit op Linux is geen Safari |
| webOS en Tizen | Jelly Leon-webclient (profielcode) | Chromium met de UA van de tv; DeviceProfile wordt gevangen | Sim-getest (UA-simulatie, geen echte decoder); echte tv NIET GEVALIDEERD (hardware) |
| stock-web via `--webdir` | stock-web | jellyfin-web uit de stock-image, geserveerd met `--webdir` door een andere server | Sim-getest (mechanisme voor stock-web tegen Jelly Leon) |
| derden-client met legacy-headers | stock-native (derden) | X-Emby-Token, X-MediaBrowser-Token, X-Emby-Authorization, `api_key`, `ApiKey` | Sim-getest (gemeten status per vorm; besluit BG-01) |
| Android-telefoon (API 35, pixel_6), tablet (API 35, pixel_tablet) | officiële jellyfin-android 2.7.3 = Jelly Leon-webclient (webweergave) | emulator in een container met `--device /dev/kvm`, 4 GiB, onder `gradle.lock` in `stack.lock`; afspelen via `POST /Sessions/{id}/Playing`, gecontroleerd aan de serverkant | Sim-getest of Sim-mislukt met reden |
| Android TV (API 34 x86, tv_1080p) | officiële jellyfin-androidtv 0.19.10 (native) | idem | idem |
| Desktop 2.0.0 onder Xvfb | Jelly Leon-webclient | bestaande desktopbuild van de clientrepo, echte afspeel- en hervatknop, posities uit de desktopsessie | [Sim-getest op de lokale fork](test-evidence/b03-016-desktop-spike.json) |
| Swiftfin, Safari, Apple TV | stock-native | — | NIET GEVALIDEERD (Mac/Xcode) |
| Echte tv's, telefoons, receivers, Chromecast, DLNA | alle | — | NIET GEVALIDEERD (hardware), JLT-69 (D15) |

De emulator mist AC3/E-AC3/DTS/TrueHD- en Dolby Vision-decoders (analyse 5 §2.2); passthrough- en HDR-beslissingen van
echte tv's zijn hier dus niet te toetsen.

### Desktoprooktest met hero.mp4

```sh
python -m b03h desktop --stap alles --build <clientbouwmap> --image <lokale-serverimage> --uit <bewijs.json>
```

In een ketenkloon wijst `B03_LOCK_DIR` naar de gedeelde map met `stack.lock`, `B03_CORPUS` naar het testcorpus en
`B03_WERK` naar een eigen tijdelijke werkmap. De bouwmap van `make desktop-bouw` bevat `build/src/jellyfin-desktop`.
Het harnas legt de SHA-256 van het uitvoerbare bestand vast. Voor Xvfb gebruikt het de testimage uit de clientrepo
(`--desktop-image`) met 1 GiB gedeeld geheugen. De desktop en de CDP-besturing bereiken de wegwerptestserver via een eigen intern netwerk.

Een nieuwe testkijker opent `hero.mp4`, speelt, stopt en drukt op **Hervatten**. Omdat dit corpusbestand korter
duurt dan vijf minuten staat `MinResumeDurationSeconds` op deze testserver op nul. Het bewijs bevat het opgeslagen
hervatpunt, de eerste positie na de klik en het opnieuw opgeslagen punt na stoppen. Elke meetreeks bevat paren
`[seconden sinds de klik, afspeelpositie in seconden]`. Een nulmelding bij hervatten, een ontbrekende webclient,
een ChunkLoadError of minder dan twee seconden gemeten voortgang geeft `Sim-mislukt` en exitcode 1.

Het CDP-consolelog groepeert herkenbare meldingen per fase, bron en niveau. Vrije consoleargumenten kunnen
aanmeldgegevens bevatten en worden als aantallen bewaard. Bij een afgebroken meting betekent `chunkloaderror: null`
dat de vraag openstaat.

Op 27 november 2026 laadde Desktop 2.0.0 de webclient van de lokale Jelly Leon-image van bronrevisie `48293b48a`.
De container had 1 GiB gedeeld geheugen. Een nieuwe testkijker meldde zich aan en speelde `hero.mp4` via Direct Play.
Bij de eerste stop bewaarde de testserver 17,934 s. Na **Hervatten** gaven de eerste sessiemeting en de
voortgangsmelding beide 17,934 s. Alle drie de gemeten sessieposities waren positief. Na de volgende stop was
20,645 s bewaard. CDP registreerde bij de start één `net::ERR_NAME_NOT_RESOLVED` en tijdens de hele proef geen
`ChunkLoadError`. [Meetreeksen en consolelog](test-evidence/b03-016-desktop-spike.json)

Voor deze run nam een externe `flock` zonder tijdlimiet het gedeelde `stack.lock` voor de duur van de containerproef.
De wachttijd van 6.653,773 s staat in `gedeeld_stackslot.wachttijd_s`. Het harnas kreeg binnen die vergrendeling
een eigen `B03_LOCK_DIR`. Het veld `stackslot_wacht_s` meet de wachttijd op dat binnenslot.

## 3. Harnas, meetprotocol en baselines (deel c)

- **Eén harnasraamwerk** (`b03h.statistiek`, `b03h.meetslot`, `b03h.bewijs`): exclusief meetslot onder `stack.lock`;
  `gradle.lock` en `docker-build.lock` worden per run gecontroleerd; loadavg vóór en na en de CPU van de machine, van het
  harnas (incl. browsers) en van de eigen testcontainers per run in het bewijs; **een run is ongeldig** (niet mislukt) bij
  loadavg(1 min) > 4 vóór de run, andere processen > 4 kernen tijdens de run of een actief zwaar slot. Tijdgevoelige runs
  worden begrensd herhaald; ongeldige pogingen blijven zichtbaar.
- Na drie ongeldige pogingen stopt `baseline` met exitcode 1. Het bestand `ongeldige-pogingen.json` in de map naast
  het gevraagde JSON-bestand bewaart de fase, de reden en de belasting van elke poging. Het afspeelorakel meet elk
  stockprofiel drie keer bij `--runs 3`. Voor de definitieve afspeel- en transcodemeting vraagt de testserver de
  rendernode aan bij Docker. Het transcodebewijs voor stock-best vereist een gemeten H.264-QSV-encode.
- **≥ 3 runs, A/B gebalanceerd afwisselend** (a,b | b,a | a,b). Proporties: n, k en het Wilson-95 %-interval; de gate
  gebruikt de ondergrens, bij te kleine n heet het **smoke-gate (n = …)**. Continue waarden: t-interval over de geldige
  runs. Elke metriek krijgt een herhaling die binnen het interval van de eerste meting moet vallen.
- **Twee baselines** op dezelfde server en datamap: **stock-standaard** (`profielen/stock-standaard.json`) en **stock-best**
  (`profielen/stock-best.json`: handmatige QSV op `/dev/dri/renderD128` met tonemapping en low-power, de
  client-instellingen per functie). De config-sha256 per systeem staat in het bewijs. "Aantoonbaar beter" alleen tegen
  stock-best; alleen tegen stock-standaard heet het "beter dan de standaardinstelling".
- De historische sessies van 10 november 2026 hebben het label `voormeting-12.4`. S-P40-50 meet opnieuw op dezelfde
  vastgezette 12.4-digest. Nieuwe geldige metingen krijgen `definitief-forkbasis`.
- `python -m b03h rapport <baseline.json>` toont per metriek de steekproefgrootte, het interval, de image, de seed en
  de éénminuutslast vóór elke run van beide sessies. Bij een telling vergelijkt het rapport de afzonderlijke herhalingen.
  Het JSON-bewijs bevat ook de meetmethode en de belasting na afloop.
- **Differentiële controle-run** (`python -m b03h diffrun`): twee systemen, hetzelfde scenario (gezien met vaste datum,
  favoriet, vind-ik-leuk, hervatpunt met spoorkeuze) op kopieën van dezelfde datamap; vergelijking van de echte
  12.x-tabellen met vaste uitzonderingen (`Users.LastActivityDate`/`LastLoginDate`, `BaseItems.DateLastSaved`,
  `UserData.LastPlayedDate`, `Devices`-tokens en -tijden, `ActivityLogs`-tijden) en een toegestane wijzigingslijst per module
  (`--toegestaan`). `--negatieve-proef` bewijst dat een echte wijziging gevonden wordt. Geheime kolommen worden nooit getoond.
  De vergelijking opent databasekopieën alleen-lezen en weigert ontbrekende bestanden, databases zonder tabellen en
  scenario's zonder bibliotheekitems. Na het weglaten van de uitzonderingskolommen telt elk exemplaar van een rij mee.
- De eerste rij van elke functie (B03-020, -030, -040, -052/054-voorbereiding, -060, -070) levert haar eigen metingen in dit
  raamwerk; hier staan de gemeenschappelijke voormetingen (Direct Play, transcode op de iGPU, functie-API's).

### Meetpoging op de forkbasis van 27 november 2026 (B03-016)

De lokale stockserver meldde versie 12.4.0 en gebruikte de vastgezette image
`docker.io/jellyfin/jellyfin:12.4@sha256:fea863d0cd9ec445985d9c75fc6ed64e38a1d2766cf0c250a33d553f4fc1b771`.
De eerste run van het profiel `stock-standaard` in de fase `functies` leverde drie ongeldige pogingen op.

| Poging | Aanvang (UTC) | Loadavg vóór de run (1 min) | CPU van andere processen (kernen) |
|---:|---|---:|---:|
| 1 | 21:09:41 | 6,54 | 5,345 |
| 2 | 21:11:42 | 6,33 | 2,072 |
| 3 | 21:13:42 | 5,60 | 3,452 |

Alle drie overschreden de lastgrens van 4,0. Het harnas stopte met exitcode 1. Met nul geldige runs is er geen interval
voor deze sessie. De definitieve meting van beide profielen, de herhaalsessie en de vergelijking van stock met de fork
staan open. [Lastgegevens van alle drie de pogingen](test-evidence/b03-016-afgewezen-functies-2026-11-27.json)

### Bibliotheekscan van de lokale testserver (I06-06-05)

Op 27 november 2026 indexeerde stock 12.4 op de forkbasis-digest 40 films en 14 afleveringen. Elke film en elke
aflevering had een eigen pad. Alle afleveringen hadden een afleveringsnummer en verwezen naar een van de drie series.
De database koppelde 16 ondertitelsporen aan 6 items. De SQL-controle las de database van de wegwerpserver na de scan.
Absolute anime-nummering, muziek en live-tv zijn in deze proef niet gecontroleerd. [SQL-query's en meetwaarden](test-evidence/b03-016-bibliotheek-2026-11-27.json)

## 4. Wat hier NIET gevalideerd kan worden

- A310 en UHD 770 (de Meteor Lake-iGPU is functioneel bewijs en bovengrens: **Intel-iGPU-getest (ontwikkelmachine)**, in de
  opmerking): **NIET GEVALIDEERD (hardware)**; render-node en render-gid op de NAS komen uit D08.
- Echte tv's, telefoons, receivers (D15): **NIET GEVALIDEERD (hardware)**; Swiftfin/Safari: **NIET GEVALIDEERD (Mac/Xcode)**.
- De NAS, zijn HDD-pool en de echte bibliotheek: **NIET GEVALIDEERD (echte NAS)**.

## B03-060 — apparaten en afspeelfouten

De ingang `b03h apparaten` gebruikt de stockserver, de afspeelactie van `dp` en `orakel`, de profielwissel en het
meetslot van B03-016. Daarom staat het harnas in `tools/b03-harnas`. Het werkpakket noemt het oudere pad
`tools/jelly-leon/e2e/`. De tweede start gebruikt dezelfde browsersessie als de eerste. De statische proef gebruikt
een apart video-element en vraagt de oorspronkelijke bron op. Voor de ASS- en tekst-SRT-proef kiest de lokale
testgebruiker Nederlandse ondertitels. De ondertitelinstelling wordt na de meting hersteld.
[Meetcommando en uitvoer](../../tools/b03-harnas/README.md#jlt-40--meetcommando-winstmeting-apparaatprofielen)

| Metriek | Waarneming |
|---|---|
| K1 | Een door PlaybackInfo gekozen Direct Play is onterecht bij een mediafout, terugval of onvoldoende voortgang. Binnen tien seconden na de afspeelklik moet `currentTime ≥ 2` zijn met een positieve videobreedte. De proef blijft het hele startvenster op fouten letten, ook bij vervanging van de speler. |
| K2 | Na een mislukte Direct Play blijft dezelfde klik maximaal 60 seconden onder observatie. Een voortschrijdende beeldklok levert de hersteltijd in milliseconden. Zonder herstel staat er `> 60 s (geen automatisch herstel)`. |
| K3 | Direct Plays die het beeldorakel halen, gedeeld door alle starts. De noemer en het Wilson-95%-interval staan bij elke set en elk startnummer. |
| K4 en K5 | K4 vergelijkt effectieve Direct Plays met het bevestigde potentieel van de geforceerde statische proef. HDR zonder bevestigde scherm- of tonemapcapaciteit krijgt een aparte telling. K5 telt transcodes waarbij de geforceerde proef wel speelt. |
| K6 | De actieve sessie levert het soort video-encode, de hardwaremethode en de beeldsnelheid. CPU-kernen zijn het verschil in cgroup-CPU-seconden van de eigen server, gedeeld door de verstreken tijd tijdens de encode. Een ontbrekende sessiemeting of CPU-waarde blijft zichtbaar. |
| K7 | Gevraagde HLS-streams met ondertitelmethode Encode tellen als inbranding. Het gekozen spoor en het oorspronkelijke externe ondertitelprofiel bepalen of de inbranding onnodig was. |
| K8 en K9 | De vergelijking met gelijke `encoding.xml` hoort bij JLT-46. Routering en uitval vereisen de opstelling van JLT-44/45. |

Het geluidsoordeel **audio niet stil** blijft **niet gemeten** tot S-G2-35. Aantallen gedecodeerde bytes en de
aanwezigheid van een audiospoor zeggen niets over de amplitude. Per run staan de éénminuutslast, CPU-gegevens en
eventuele afgewezen pogingen in het JSON-rapport. De herhaalcontrole vergelijkt de beslissing en de tijden van
hetzelfde item en startnummer met de eerste geldige run. De tijdmarge is ±10%. De eerste stock-standaardrun vergelijkt
alle 25 individuele A5-beslissingen met analyse 5, ook als twee verschillen elkaar in het totaal opheffen.

De volledige recepten `f5-fouten` en `ass` leverden met ffmpeg 8.1.3 en de bibliotheken uit de vastgezette
stockimage de bevroren bytes op. De SHA-256-controle herkende een afwijkend ASS-bestand bij systeem-ffmpeg 8.0.1.
Het meetrapport vermeldt nul geldige stockruns bij een éénminuutslast van 7,20 en een ontbrekende definitieve baseline.
[Corpuscontrole](test-evidence/b03-060-corpuscontrole.json) · [Meetpoging](test-evidence/b03-060-voormeting.md)

De historische A5-matrix koos Direct Play voor 16/25 items in Chromium, 17/25 in Firefox en 21/25 in WebKit.
Bij WebKit speelde één gekozen item, Sintel, niet af. Dit zijn de referentiecijfers van de historische sessie.
[Bronmatrix van 10 november](test-evidence/b03-016-baseline-voormeting-12.4/dp-matrix.json)

De rooktest speelde `hero.mp4` op de telefoon-, tablet- en tv-emulators. Het clientharnas rapporteerde voor de
tablet daarnaast drie OOM-kills bij 4 GiB en één van drie succesvolle herhalingen bij 5 GiB. De hervatproef van
de tv-app leverde vijf van vijf per server op. S-P40-70 kon de tabletproef niet herhalen vanwege ontbrekende
KVM-toegang. S-P40-90 liet de desktop op de lokale fork afspelen en hervatten. Deze uitkomsten zijn overgenomen.
[Clientmatrix](test-evidence/b03-016-clientmatrix-rooktest.json) · [Desktopproef](test-evidence/b03-016-desktop-spike.json)
