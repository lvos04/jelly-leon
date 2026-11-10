# Bouwverificatie B03-015 deel A — overname van de kijkgeschiedenis uit Emby (golf 0, 2026-11-09)

Omgeving: Ubuntu-ontwikkelmachine (22 CPU's, 14,5 GiB RAM, Docker Engine), Python 3.12 (venv `tools/jelly-leon/.venv`,
niet gecommit) en GitHub Actions (`ubuntu-24.04`). Containers: **echte** `emby/embyserver:4.10.2.0@sha256:7082c63b…65cc1`
(digest op 2026-11-09 gecontroleerd met `docker buildx imagetools inspect`) en stock
`jellyfin/jellyfin:12.4@sha256:fea863d0…1771`. Stacks lokaal alleen onder `flock …/.lokaal/stack.lock`; containers, volumes
en de testset zijn na elke run opgeruimd (BG-38: alleen het recept in `testbibliotheek.py` en het manifest in het bewijs
blijven).

**Niets hiervan is op de echte NAS, met de echte Emby van de gebruiker of op echte apparaten uitgevoerd.** D07 (versie,
gebruikers, bibliotheken en mountpaden van de echte Emby) is niet gemeten. Validatie: *Sim* (echte containers op de
ontwikkelmachine en in CI); JLT-74 blijft **Geblokkeerd — NIET GEVALIDEERD (echte NAS)**.

## 1. Wat is gebouwd

| Onderdeel | Pad | Commit(s) |
|---|---|---|
| Beoordeling JellyPlex-Watched v9.0.0 → eigen tool | `docs/adr/ADR-0025-…` | `4da5292f5` |
| Overnametool (alleen standaardbibliotheek) + unit- en simulatortests | `tools/emby-overname/` | `3461a04ba`, `650bd9765`, `746b1def9` |
| JSON Schemas (export, plan, rapport, akkoord) | `tools/emby-overname/schemas/` | `f069c761a` |
| E2E-harnas, loggende proxy, MediaGuard-simulator, testbibliotheek | `tools/emby-overname/e2e/` | `a169b278d` … `63718a92d` |
| CI-job *emby-overname* | `.github/workflows/jelly-leon-ci.yml` | `a169b278d` |
| Procedure en controlelijst voor de gebruiker | `docs/platform-v2/OVERNAME_EMBY.md` | (deze ronde) |

## 2. Tests — exacte commando's en uitkomsten

| Commando | Uitkomst |
|---|---|
| `tools/jelly-leon/.venv/bin/python -m pytest -q tools/emby-overname/tests` | **70 geslaagd** (unit, Emby-/Jellyfin-simulators, schema's) |
| `tools/jelly-leon/.venv/bin/ruff check --config tools/emby-overname/ruff.toml tools/emby-overname` | geen meldingen |
| `tools/jelly-leon/.venv/bin/python -m pytest -q tools/jelly-leon/tests` | **166 geslaagd** (incl. EVIDENCE-§11-test met JLT-rijen) |
| `actionlint .github/workflows/jelly-leon-ci.yml` | geen meldingen |
| `flock /home/transcode/truenas-v2/.lokaal/stack.lock nice -n 10 tools/jelly-leon/.venv/bin/python tools/emby-overname/e2e/proefrun.py --modus corpus --uitvoer …/corpus-3` | **57/57 geslaagd** (§3; echt mediacorpus, harde links, sha256 gecontroleerd) |
| GitHub Actions *Jelly Leon CI*, job *emby-overname* (`--modus synthetisch --ffmpeg docker`) | **56/56 geslaagd**, run 42695702468 volledig groen (§4) |

## 3. Proefrun met het echte mediacorpus (lokaal)

Bewijs: `test-evidence/b03-015-proefrun-corpus.json` (alle controles met detail) en een voorbeeld van het rapport in
`test-evidence/b03-015-voorbeeldrapport/` (`rapport.md`, `rapport.html`, `rapport.json` + `.sha256`).

Opzet: 24 corpusbestanden (sha256 tegen `SHA256SUMS.bron.txt`/`SHA256SUMS.afgeleid.txt` gecontroleerd) als twee bomen:
Emby onder `/mnt/emby/media`, Jellyfin onder `/data/media` (padvertaling). Opzettelijke gaten (JLT-72): zonder ID's maar
gelijk pad (`pad`), zonder ID's en ander pad (`geen_id`), ontbreekt in Jellyfin (`ontbreekt`), dezelfde IMDb-ID op twee
Jellyfin-items (`dubbel`), twee versies met dezelfde IMDb-ID (Emby bundelt die tot één item → `dubbel`), absolute
anime-nummering in Emby tegenover seizoenen in Jellyfin, en een gewijzigd bestand (zelfde pad, andere grootte) met een
onthouden spoorkeuze (`ander_bestand`). Vijf Emby-gebruikers: beheerder (gekoppeld aan de bestaande Jellyfin-beheerder),
Anna en Bram (volwassenen), Kim (kind: leeftijdsgrens PG, tag Horror geblokkeerd, geen toegang buitenshuis, geen downloads)
en Gast (alleen Films).

Uitkomst (run `corpus-3`, 2026-11-09 20:48–21:05 UTC, loadavg 3,1 → 4,5): **57 van 57 controles geslaagd** —
B03-016-corpuscontrole 1/1, JLT-70 21/21, JLT-71 11/11, JLT-72 7/7, JLT-73 17/17 (per test: *Sim-geslaagd*).

| Test | Kern van het bewijs (gemeten) |
|---|---|
| JLT-70 | Emby bevatte 23 items gezien (met datum en aantal), 7 hervatpunten, 6 favorieten, 0 beoordelingen. Eerste overzetting: 43 schrijfacties, allemaal via `POST /Users/New`, `/Users/{id}/Policy`, `/Users/Configuration` en `/UserItems/{id}/UserData`. Onafhankelijke grondwaarheid (per pad, niet via de tool): **31 van 31 koppelbare items exact** (gezien, aantal, datum, hervatpunt op de tick, favoriet), 5 op de afhandellijst, 36 = 36. Kind: Films+Series expliciet, leeftijdsgrens via de classificatienaam (PG → 10), tag Horror geblokkeerd, geen toegang buitenshuis, geen downloads; gast alleen Films; voorkeuren (o.a. ondertitels altijd, Nederlands) overgezet; **geen enkele gebruiker ziet in Jellyfin iets wat hij in Emby niet mocht zien**. Emby-wachtwoord en leeg wachtwoord → 401. Na een nieuw wachtwoord: inloggen en "Verder kijken" op de exacte tick (protocolsimulator; 3 hervatpunten). Herimport uit het archief op een lege Jellyfin met Emby gestopt: 35 exact + 5 afhandellijst = 40. |
| JLT-71 | Tweede run: 0 schrijfacties (proxy) en dezelfde inhoud-sha256 (`71569c07…`). Delta: precies 3 schrijfacties (nieuw gezien, hervatpunt verder, favoriet erbij); nieuwere Jellyfin-waarde niet overschreven; in Emby verwijderde favoriet ter beslissing op de afhandellijst. Kill na 2 schrijfacties (exit 137, ná het verzoek en vóór "klaar"): hervatten schreef elke actie precies één keer (5 = 5 gepland), herstel herkende 1 al uitgevoerde schrijfactie; aantallen niet dubbel opgeteld. |
| JLT-72 | Afhandellijst: `geen_id` 2, `dubbel` 1 (dezelfde IMDb-ID op twee Jellyfin-items), `ontbreekt` 2 (o.a. absolute anime-aflevering 3: nooit gegokt), `ander_bestand` 1 (spoorkeuze op het gewijzigde bestand niet overgenomen, wel gemeld); 0 stil weggelaten. |
| JLT-73 | Loggende proxy: **826 verzoeken naar Emby, allemaal GET**, alle routes op de witte lijst, geen sleutel in een URL. Testhaak: POST en DELETE vóór het netwerk geweigerd (0 netwerkverzoeken). Emby-kijkgegevens per gebruiker identiek vóór en na **elke** toolrun; exportarchief vóór/na identiek. Geen API-sleutel in logs, rapporten, exports of proxylogs. MediaGuard-**simulator** (Emby `X-Emby-Token`, Jellyfin `Authorization: MediaBrowser Token=…`): kijkpauze op Emby na 0,1 s en op Jellyfin na 0,8 s; 0 mislukte polls. |

## 4. GitHub Actions

*Jelly Leon CI* run **42695702468** (commit `63718a92d`): **alle 7 jobs groen** — manifest, forkregels, upstream-solution
(build + tests), plugins, image + levenscyclus, stock-client-smoketest en **emby-overname** (ruff, 70 tool-tests en de
proefrun met zelfgemaakte clips: **56 van 56 controles**, JLT-70 21/21, JLT-71 11/11, JLT-72 7/7, JLT-73 17/17). Eerdere
run 42692598131 (commit `64d12ab17`) ook volledig groen (56/56). Bewijs: `test-evidence/b03-015-proefrun-ci-synthetisch.json`.
De mislukte CI-runs daarvoor zijn de iteraties uit §5 (harnas en één echte toolbevinding: door Emby gebundelde versies).

## 5. Bevindingen uit de echte containers (gemeten, niet aangenomen)

1. **Emby geeft `PlayCount` en `LastPlayedDate` in lijsten alleen met `Fields=UserDataPlayCount,UserDataLastPlayedDate`**
   (zonder: `PlayCount: 0`, geen datum). De tool vraagt beide; JellyPlex-Watched vraagt alleen de datum (ADR-0025).
2. **Emby 4.10.2.0 bundelt films met dezelfde IMDb-ID in verschillende mappen tot één item met twee versies** (niet in elke
   run even snel; in CI eerst niet, later wel). Jellyfin 12.4 houdt twee items. De tool meldt dit als `dubbel` en kiest nooit
   één versie.
3. **Emby zet bij `POST /Users/{id}/Items/{id}/UserData` ontbrekende velden terug** (`Played` werd weer `false`); van
   belang voor testopzet, niet voor de tool (die schrijft nooit in Emby).
4. **Beoordelingen:** na `POST /Users/{id}/Items/{id}/Rating?Likes=true` (HTTP 200) gaf Emby in de UserData geen `Rating`
   of `Likes` terug, niet in de lijst en niet in het itemdetail (`beoordeling_diagnose` in het bewijs); het rapport toont
   dan 0 beoordelingen in Emby (capability_unavailable aan de bron).
5. **Onthouden spoorkeuzes** zijn alleen zichtbaar via `GET /Items/{id}/PlaybackInfo?UserId=…`; Jellyfin 12.4 heeft geen
   officiële route om ze te zetten. Waar Emby en Jelly Leon verschillend kiezen, staat het op de afhandellijst.
6. **Jellyfin 12.4** geeft tijdens het opstarten een HTML-pagina/HTTP 503; een lege Jellyfin startte in CI de
   bibliotheekscan niet altijd vanzelf (`POST /Library/Refresh` lost het op). Beide alleen relevant voor de testopzet.

## 6. Wat niet is gedaan (eerlijk)

- Geen echte NAS, geen echte Emby van de gebruiker (D07 niet gemeten): JLT-74 **Geblokkeerd — NIET GEVALIDEERD (echte NAS)**.
- Geen Android-emulator en geen stock-web-UI: inloggen en hervatten alleen op protocolniveau gesimuleerd.
- De MediaGuard-delen zijn een simulator; Δ-MG-DUAL/Δ-MG-AUTH zijn werk van media-guard-ultimate.
- Spoorkeuzes kunnen via de officiële Jellyfin 12.4-API niet worden gezet (`capability_unavailable`, afhandellijst).
- De overname-assistent (UI, zodat de gebruiker geen terminal nodig heeft) bestaat nog niet (P4-0).
- Herhaling tegen `jelly-leon:12.x` (gate P4-0) en deel B (overname van een Jellyfin-installatie) nog niet.

## P4-0-herhaling tegen jelly-leon:12.x (2026-11-10)

De gate P4-0 vraagt JLT-70…73 ook tegen de jelly-leon-image (bouwplan §8.3, FASERING golf 0 → P4-0). `proefrun.py` kreeg
daarvoor `--jellyfin-image` (standaard blijft stock 12.4; het bewijs noemt de gebruikte image).

| Commando | Uitkomst |
|---|---|
| `flock …/stack.lock nice -n 10 tools/jelly-leon/.venv/bin/python tools/emby-overname/e2e/proefrun.py --modus corpus --jellyfin-image jelly-leon:p40 --uitvoer …/emby-p40` | **57/57 geslaagd** (corpus 1/1, JLT-70 21/21, JLT-71 11/11, JLT-72 7/7, JLT-73 17/17) in 16 min 19 s; echte `emby/embyserver:4.10.2.0@sha256:7082c63b…65cc1` en de lokaal gebouwde jelly-leon-image 12.4.0-jl.0 (image-ID `sha256:53a03a44…50ed`, gebouwd op commit `7dc66d364`, echte jelly-leon-web-build `5ced8a246`); bewijs `test-evidence/p40/b03-015-proefrun-corpus-jelly-leon-12.4.json` |

Gemeten: dezelfde uitkomst als tegen stock 12.4 (31/31 koppelbare items exact gelijk, 0 stil weggelaten: 37/37
verantwoord, tweede run 0 schrijfacties met identieke inhoud-sha256, alleen GET naar Emby, Emby-kijkgegevens per
gebruiker vóór en na identiek, herimport uit het archief exact). Containers, testset en werkmappen zijn daarna
opgeruimd (BG-38). Nog steeds alleen Sim: de echte Emby op de NAS (D07, JLT-74) is niet gebruikt.

## QA-review golf 0 + P4-0 (2026-11-10)

Onafhankelijke herhaling door de QA-reviewer, met een eigen build van de jelly-leon-image (`jelly-leon:qa`, commit
`5206ab4bf`, echte web-build `5ced8a246`) en de echte `emby/embyserver:4.10.2.0@sha256:7082c63b…65cc1`. Alles Sim; de echte
Emby op de NAS (D07, JLT-74) is niet gebruikt.

**Gevonden en gerepareerd**

1. **Doelcontrole ontbrak (HARDE EIS: nooit schrijven in Emby).** Gemeten met een wegwerp-Emby 4.10.2.0: Emby accepteert
   óók de Jellyfin-header `Authorization: MediaBrowser … Token="<Emby-sleutel>"` (`GET /Users` → 200). Wees het adres van
   Jelly Leon per vergissing naar Emby (verkeerde keuze in de latere overname-assistent), dan hield niets in de tool
   schrijfacties (`POST /Users/New`, `/Users/{id}/Policy`, …) naar Emby tegen behalve toevallige API-verschillen. Nu:
   eerst zónder sleutel `GET /System/Info/Public` en alleen door bij `ProductName` "Jellyfin Server" (Emby meldt geen
   ProductName — gemeten); zelfde adres of zelfde server-ID als de bron → exit 9; zonder bevestigd doel weigert de client
   elk verzoek vóór het netwerk (commit `5206ab4bf`). Unit- en integratietests; bewezen dat ze zonder de controle falen.
   In de E2E-proefrun (JLT-73) nu ook tegen de echte Emby: Jelly Leon-adres → Emby, met de Emby-sleutel: proefrun en
   overzetten exit 9, van de doelkant alleen 2× `GET /System/Info/Public`, Emby-kijkgegevens vóór/na identiek.
2. **Een GET liet Emby schrijven.** In de eerste QA-proefrun faalde de controle "exportarchief vóór en na identiek":
   bij de beheerder verschilde de spoorkeuze van *Spring (2019).mkv* (vóór: grootte 0, geen audio; na: 81 782 463 bytes,
   opus/eng). Nagemeten met een wegwerp-Emby: Emby had dat VP9/Opus-bestand na de scan niet geanalyseerd (grootte 0,
   0 streams); de eerste `GET /Items/{id}/PlaybackInfo` gaf leeg terug en liet Emby het bestand op de achtergrond alsnog
   analyseren en opslaan (de tweede gaf wel grootte en streams). Geen kijkgegevens, maar wel een door de tool veroorzaakte
   schrijfactie in Emby. Nu vraagt de tool voor een bestand met grootte 0 geen PlaybackInfo (zo'n bestand is nooit
   afgespeeld en heeft dus geen onthouden spoorkeuze) en noemt het item in de export onder `spoorkeuzes_niet_gelezen`.
3. **Overclaim in EVIDENCE.json.** JLT-60, JLT-63, JLT-70 en JLT-73 stonden op `Sim-geslaagd` terwijl een deel van de
   acceptatie niet is uitgevoerd (Android-emulator/stock-web na de upgrade; Android-emulators, SyncPlay, skipknoppen en
   downloaden; het MediaGuard-deel alleen met een eigen simulator omdat Δ-MG-DUAL/Δ-MG-AUTH ontbreken). Teruggezet naar
   `Sim-getest` met uitleg in `opmerking`.
4. **Clientdeel JLT-70 deels ingevuld:** `proefrun.py --browser chromium` laat een overgezette gebruiker in een echte
   Chromium (Playwright-harnas van B03-016) inloggen met het nieuwe wachtwoord en op de detailpagina hervatten; gemeten aan
   de serversessie (eerste `PositionTicks` binnen 3 s van het overgezette hervatpunt) en aan het beeld. Ook in CI. De
   Android-emulator blijft open.
5. **Harnas:** de wachtlus op de bibliotheekscan wachtte altijd de volle 15 minuten, omdat door Emby gebundelde versies
   alleen in de itemdetails staan; die worden nu meegenomen zodra Jellyfin klaar is.

**Herhaalde metingen (lokaal, onder `stack.lock`)**

| Commando | Uitkomst |
|---|---|
| `flock …/stack.lock nice -n 10 …/proefrun.py --modus corpus --jellyfin-image jelly-leon:qa --browser chromium --uitvoer …/proefrun-corpus` (vóór reparatie 2) | 61/62: alles geslaagd behalve "exportarchief vóór en na identiek" (bevinding 2); verkeerd-doel-controle en browser-hervatten geslaagd (Kim, eerste PositionTicks 1 172 121 350 tegen 1 170 126 007 verwacht) |
| Eigen analyse van `proxy-emby.jsonl` van die run | 905 verzoeken naar Emby, **alle GET**, alle HTTP 200, 0 met een sleutel in de URL, alleen routes van de witte lijst (`/Items/{id}/PlaybackInfo` 414×, `/Users/{id}/Items` 120×, …); naar Jelly Leon alleen de toegestane POST-routes (UserData 39, Users/New 4, Policy 4, Configuration 4) |
| Idem na reparatie 2 en de scanlus | **62/62 geslaagd** in 2 min 7 s (corpus 1/1, JLT-70 24/24, JLT-71 11/11, JLT-72 7/7, JLT-73 19/19); exportarchief vóór/na identiek; *Spring* staat bij de beheerder onder `spoorkeuzes_niet_gelezen`; browser: Kim hervat *B03 Testserie S01E02* via Direct Play, eerste PositionTicks 1 170 126 000 tegen 1 170 126 007 verwacht; bewijs `test-evidence/p40-qa/b03-015-proefrun-corpus-jelly-leon-qa.json` (de mislukte eerste run: `…-voor-reparatie.json`) |
| Eigen analyse van `proxy-emby.jsonl` (run na reparatie) | 893 verzoeken naar Emby, **alle GET**, alle HTTP 200, 0 sleutels in een URL, alleen routes van de witte lijst; `test-evidence/p40-qa/verkeersmeting-eigen-telling.json` |
| Image-E2E zoals CI-job *image*, `jelly-leon:qa`, onder `stack.lock` | levenscyclus 31/31 (lege `/config`, healthy, herstart en nieuwe container zonder dataverlies, downgradeweigering met `/config` byte-gelijk), CI-guard testdatalicenties op de image in orde, terugzetproef 10/10, upgradeproef 10.11.11 → 12.4 18/18 (JLT-61 b opnieuw gemeten: stock 10.11.11 gezond, aanmelden HTTP 500, geen stille schade → blijft Sim-mislukt), compat-API 5/5, UG-runtime 6/6; `test-evidence/p40-qa/` |

GitHub Actions *Jelly Leon CI* run **42762467348** (commit `17165e8ec`): **8/8 jobs groen**; de job emby-overname draaide de
proefrun synthetisch met `--browser chromium`: **61/61**, waaronder het verkeerde doel (exit 9, alleen 2× `GET /System/Info/Public`)
en hervatten in Chromium (eerste PositionTicks 224 008 750 tegen 222 276 007 overgezet); bewijs
`test-evidence/p40-qa/ci-42762467348-b03-015-proefrun-synthetisch.json`.

Na afloop opgeruimd: containers, werkmappen en testsets (BG-38); de Emby-image en `jelly-leon:qa` zijn lokaal verwijderd
(opnieuw op te halen/bouwen op digest en commit).
