# Bouwverificatie P4-0 — jelly-leon naar Jellyfin 12.4 (B03-014, B03-019; herhaling B03-015/016)

Datum: 2026-11-10. Omgeving: Ubuntu-ontwikkelmachine (22 CPU's, 14,5 GiB RAM + 4 GiB swap, gedeeld), Docker Engine 29.1.3
(buildx 0.30.1), Python 3.12 (venv `tools/jelly-leon/.venv`, niet gecommit) en GitHub Actions (`ubuntu-24.04`). Zware
stappen onder `flock …/.lokaal/docker-build.lock` (image en .NET) en de stacks onder `flock …/.lokaal/stack.lock`, met
`nice -n 10`; .NET met `-m:4`.

**Niets hiervan is op de echte NAS, met de echte kijkgeschiedenis van de gebruiker of op echte apparaten uitgevoerd.**
Validatie overal *Sim* (echte containers op de ontwikkelmachine en in CI); echte NAS, tv's, telefoons en Swiftfin/Safari:
**NIET GEVALIDEERD**. Nergens staat Gereed of Geslaagd.

## 1. Versiekeuze en herbasis

| Stap | Commando | Uitkomst |
|---|---|---|
| Nieuwste stabiele tag | `tools/jelly-leon/.venv/bin/python tools/jelly-leon/upstream_sync.py kies --spoor nieuwste --spoor patch` | `nieuwste` = **v12.4** (nieuwer dan de basis: v12.0…v12.4; alleen rc-tags daarnaast); `patch`: geen kandidaat. `git ls-remote --tags`: v12.4 = `83d0d0e7f76e` |
| Herbasis zonder hulp (EX48) | `upstream_sync.py merge --tag v12.4 --methode herbasis --maak-lokale-tag` | exit 2 `INCOMPATIBEL (herbasis)`: 1 conflict in `.github/workflows/commands.yml`; alles teruggedraaid (gedrag ongewijzigd) |
| Herbasis met handmatig oplossen (nieuw, commit `102738f17`) | `… --handmatig-oplossen` → guard op de nieuwe upstream-regel → `git add` → `upstream_sync.py voltooi` | per patch: JL-0001 `conflict` in `commands.yml` (overige 3 bestanden schoon) → `conflict_handmatig_opgelost`; herbasis-commit `7c4b54a56` (ouders `102738f17` en `83d0d0e7f`), baseline-commit `457333040` (forkversie **12.4.0-jl.0**, `dotnet_sdk_major` 10.0, plugin `net10.0`/12.4.0) |
| Nieuwe upstream-workflows | `grep -c 'secrets\.' .github/workflows/*` | `openapi-workflow-run.yml` (12.4) gebruikt `JF_BOT_TOKEN` na een workflow_run → guard in JL-0001; `openapi-merge.yml` is upstream al begrensd; ADR-0007 bijgewerkt |
| Forkregels | `check_fork_consistency.py`; `patch_register_check.py` | in orde: basis v12.4 (`83d0d0e7f76e`), 283 afwijkende paden waarvan 5 in JL-0001, geen ongeregistreerde core-patch |

## 2. Handwerk (ADR-0011, B03-014)

| Onderdeel | Waarde (gemeten met `docker buildx imagetools inspect`) |
|---|---|
| `SDK_IMAGE` | `mcr.microsoft.com/dotnet/sdk:10.0.403@sha256:212fe4cb74627d5adf9817a4088906ae3edff1bd853bb27565d4b46731efe61e` (= tag `10.0`; hoogste 10.0.x in de MCR-taglijst) |
| `RUNTIME_IMAGE`, `JL_RUNTIME_IMAGE` (CI én upstream-sync) | `docker.io/jellyfin/jellyfin:12.4@sha256:fea863d0cd9ec445985d9c75fc6ed64e38a1d2766cf0c250a33d553f4fc1b771` |
| `NODE_IMAGE` | `docker.io/library/node:24.22.2-bookworm-slim@sha256:01d566e8d94d8c619591d78652babfccd3c6992a3dffa9ed5ab39e11cf6c70e9` (= jelly-leon-web `toolchain.node_image`) |
| Web-bron | `web_upstream_tag` v12.4 (`0a580ce8df89`), `web_fork_commit` `5ced8a246` (P4-0 van jelly-leon-web, na de review) |
| Manifest | versie en tag `12.4.0-jl.0`; resources ongewijzigd 4 CPU's / 4096 MiB (voorlopig, BG-07) |
| Plugin | `net10.0`, Jellyfin.Controller/Model 12.4.0, testpakketten als upstream (xunit.v3); geen `IMediaSegmentProvider`, dus `CleanupExtractedData` n.v.t. |

## 3. Build en volledige upstream-testsuite

Commando (lokaal; `$SDK` = de SDK-image hierboven):
`flock …/docker-build.lock nice -n 10 docker run --rm --user $(id -u):$(id -g) --memory 7g --cpus 6 … $SDK sh -c
'dotnet restore Jellyfin.sln; dotnet build Jellyfin.sln -c Release --no-restore -m:4; dotnet test Jellyfin.sln -c Release
--no-build -m:4 --logger trx …'`.

- Build: **0 waarschuwingen, 0 fouten**.
- Run 1: 4206 tests, 4059 geslaagd, **131 mislukt — allemaal** `libfontconfig.so.1` ontbreekt in de SDK-image (SkiaSharp;
  124 integratie- en 7 Skia-tests). Omgevingsafwijking, gedocumenteerd (ADR-0027 §8).
- Run 2 (zelfde build; `libfontconfig1` in de wegwerpcontainer, `dotnet test` als eigen gebruiker): **4206 tests, 4190
  geslaagd, 0 mislukt, 16 overgeslagen** (upstream-skips). Per assembly: `test-evidence/p40/upstream-testsuite.txt`.
- Plugins in dezelfde container: build 0/0, **16/16** tests.
- GitHub Actions job *Upstream-solution bouwen en testen* (SDK-kanaal 10.0.x uit global.json): groen (zie §9).

## 4. OpenAPI (alleen upstream-wijzigingen)

- `docs/openapi/jelly-leon.openapi.json` = export van de 12.4-fork. Vergeleken met de door upstream gepubliceerde
  `jellyfin-openapi-12.4.json` (repo.jellyfin.org): `openapi_drift.py` → **structureel gelijk**, alleen 9
  description-teksten verschillen (bekende XML-docvolgorde, ADR-0010). De fork voegt dus niets toe aan de upstream-API.
- Upgraderapport 10.11.11 → 12.4 (`tools/jelly-leon/openapi_upgraderapport.py`, `test-evidence/p40/openapi-10.11.11-naar-12.4.json`):
  388 → 364 operaties; 25 uit de spec, waarvan **22 nog in de broncode** (alleen verborgen met `IgnoreApi`: o.a. alle
  HLS-playlists `master.m3u8`/`main.m3u8`, `PlayingItems`, `MusicGenres`) en **3 echt verwijderd**
  (`GET /Environment/NetworkShares`, `GET /Items/{itemId}/CriticReviews`, `GET /LiveTv/Recordings/Groups/{groupId}`);
  1 nieuw (`GET /Items/{itemId}/Collections`); 12 operaties met een verwijderde of strengere parameter
  (`breakOnNonKeyFrames`, `disableFirstEpisode` weg; `DELETE /Devices` `id` nu een lijst); 20 schema's met strengere
  `required`/verwijderde velden (o.a. `SessionInfoDto.NowPlayingQueueFullItems`, `StartupRemoteAccessDto.EnableAutomaticPortMapping`).
- **Beoordeling clientimpact.** Verborgen HLS-routes antwoorden nog (UG-GEM-3, runtime-test: 401 zonder token, niet
  404). Onbekende queryparameters negeert ASP.NET; strengere `required` raakt alleen gegenereerde clients met strikte
  validatie. Wat wél breekt is de **oude aanmelding** (UG-GEM-1): MediaGuard (`X-Emby-Token`) → Δ-MG-AUTH (BG-01); de
  eigen tools (overnametool, harnas, smoketest, Hub-adapter v1) gebruiken `Authorization: MediaBrowser …` en werken
  (gemeten, §6–§8). `StartupRemoteAccessDto.EnableAutomaticPortMapping` sturen onze tools nog mee: 12.4 negeert het
  veld (wizard gemeten). Waarneming: 12.4 zet het sessietoken als `ApiKey=` in `TranscodingUrl` (upstream-gedrag; de
  compat-rapporten maskeren het).

## 5. Image (echte jelly-leon-web 12.4-build)

De lokale image (`jelly-leon:p40`, image-ID `sha256:53a03a44…50ed`) is gebouwd op commit `7dc66d364`; latere commits raken
de inhoud van de image niet (alleen tools, documentatie en CI). De CI-job *image* bouwt hem op elke commit opnieuw.

`flock …/docker-build.lock nice -n 10 docker buildx build --builder jl-begrensd (docker-container, 8 GiB, CPU 0-7)
-f deploy/allinone/Dockerfile --build-context jelly-leon-web=<git archive 5ced8a246> --build-arg FORK_VERSION=12.4.0-jl.0
--build-arg BUILD_JOBS=4 --build-arg WEB_BUILD_JOBS=4 --load -t jelly-leon:p40 .` → geslaagd in 2 min 30 s, 2,85 GB.

| Test | Commando | Uitkomst |
|---|---|---|
| Levenscyclus | `image_lifecycle.py --image jelly-leon:p40 --expected-version 12.4.0 --verwacht-web-ref 5ced8a246…` | **31/31** (`test-evidence/p40/image-lifecycle.json`): smoketest nieuw 25/25 en herstart 27/27 (legacy-headers geweigerd), elk proces 568 zonder capabilities, healthcheck zonder root, `<title>Jelly Leon</title>` en 32/32 bundels, herkomst web 5ced8a246, datamap-versie vastgelegd, **downgradeweigering** (datamap-versie 99.0.0-jl.0 → exit 1, /config byte-gelijk, 27 bestanden), 6 fail-closed-weigeringen |
| Terugzetproef stock 12.4 → Jelly Leon → stock | `rollback_sim.py --upstream-image jellyfin/jellyfin:12.4@sha256:fea863d0… --image jelly-leon:p40` | **10/10** (`test-evidence/p40/rollback-sim-stock-12.4.json`) |

## 6. Upgradeproef 10.11.11 → Jelly Leon 12.4 (JLT-60, JLT-61 a/b)

`flock …/stack.lock nice -n 10 tools/jelly-leon/.venv/bin/python tools/jelly-leon/e2e/upgrade_proef.py --image jelly-leon:p40
--expected-version 12.4.0` → **18/18 stappen** (`test-evidence/p40/upgrade-proef-10.11.11-naar-12.4.json`):

- Gevulde 10.11.11-datamap (stock op digest): 5 gebruikers (beheerder, ouder, tiener met grens 13 en tag `horror`, gast
  met alleen *Films*, kind zonder bibliotheken); gezien met datum en aantal (2× en 5×), hervatpunten, favorieten,
  beoordeling 8, vind-ik-leuk, voorkeuren nld, **onthouden spoorkeuze** van de gast (eng/eng tegen voorkeur nld, via
  afspeelmeldingen), 5 apparaten, metadata-override met `LockData` en een afspeellijst.
- Jelly Leon 12.4 op dezelfde datamap: migraties zonder handwerk; **VÓÓR = NA: 0 verschillen** per gebruiker
  (gezien, aantal, datum, hervatpunt, favoriet, beoordeling, spoorkeuze, voorkeuren, rechten, zichtbaarheid,
  apparaten, override, afspeellijst; sha256 in het rapport). Daarom is geen akkoord op verschillen nodig; een verschil
  zou de proef laten falen (niets wordt stil geaccepteerd).
- Hervatten: de gast krijgt 15 000 000 ticks (1,5 s), staat in *Verder kijken*, sporen 2/4, stream 206.
- Legacy-auth na de migratie uit (`EnableLegacyAuthorization=False`; X-Emby-Token 401, api_key 401, moderne header 200).
- Plugin `GET /media/v1/version` = `compatibel` op de gemigreerde datamap.
- **Differentiële controle-run** (b03h.diffrun): stock 12.4 en Jelly Leon 12.4 elk op een eigen kopie van dezelfde
  10.11.11-datamap → jellyfin.db **0 verschillen** over 33 tabellen; stock 12.4 op een kopie geeft hetzelfde NA-rapport.
- **JLT-61 a:** kopie van vóór + oude image → jellyfin.db **byte-gelijk** (sha256), kijkgegevens = VÓÓR, stream 206.
- **JLT-61 b (gemeten):** alleen de oude stock-image 10.11.11 op de gemigreerde datamap → start "gezond", aanmelden
  **HTTP 500** — **geen zichtbare weigering** (zie §10); daarna dezelfde map weer met Jelly Leon = NA (**geen stille
  schade**). De eigen downgradeweigering van de jelly-leon-image is in §5 bewezen.
- Mediabestanden: sha256 vóór = na.

Niet in deze proef: inloggen en hervatten in stock-web en de Android-emulator na de upgrade (webdeel: jelly-leon-web
`upgrade_proef.py`, 50/50 in Modern en Legacy op stock 12.4 + fork-dist; emulator: niet herhaald).

## 7. B03-019: register van upstream-gedrag, compat-rooktest en sync-proef

| Onderdeel | Commando | Uitkomst |
|---|---|---|
| Register `UPSTREAM_GEDRAG.md` (UG-GEM-1…12) | `tools/jelly-leon/.venv/bin/python tools/jelly-leon/upstream_gedrag_check.py --overzicht` | 12 ankers gevonden, 6 runtime-tests gekoppeld, geen onbekende UG-verwijzing |
| Tegenproef op de 10.11.11-boom | idem met `--repo <git archive 1fbd87392>` + register | exit 1: **4 van 12** ankers falen (UG-GEM-1, -3, -5, -11) — de controle blokkeert echt |
| Runtime-tests op stock 12.4 | `e2e/upstream_gedrag_runtime.py --image jellyfin/jellyfin:12.4@sha256:fea863d0…` | **6/6** (`test-evidence/p40/upstream-gedrag-runtime-stock-12.4.json`) |
| Runtime-tests op Jelly Leon 12.4 | `e2e/upstream_gedrag_runtime.py --image jelly-leon:p40` | **6/6** (`…-jelly-leon.json`) |
| API-regressie (JLT-64 met de bestaande plugin; PlaybackInfo-deel JLT-63) | `e2e/compat_api.py --image jelly-leon:p40` | **5/5** (`test-evidence/p40/compat-api.json`): 18 Jellyfin-antwoorden (incl. PlaybackInfo met 3 profielen, mét MediaSourceId/AudioStreamIndex) **0 verschillen** met stock; Direct Play én transcode gedekt; OpenAPI alleen `+/media/v1/version` (+ schema `ForkVersionInfo`) |
| Unittests forktools | `tools/jelly-leon/.venv/bin/python -m pytest -q tools/jelly-leon/tests` | **199 geslaagd** (ook `tools/emby-overname/tests` 70, `tools/b03-harnas/tests` 52) |
| Clientmatrix-rooktest tegen de jelly-leon-image (JLT-63 rooktestdeel) | `PYTHONPATH=tools/b03-harnas python -m b03h clientmatrix --onderdelen web,ua,legacy,webdir --image jelly-leon:p40 --uit test-evidence/p40/clientmatrix-rooktest-jelly-leon-12.4.json` | **7/7 clients** Sim-getest: Jelly Leon-webclient in Chromium/Firefox/WebKit, webOS/Tizen-UA, stock-web over de ingebouwde web heen, legacy-headers geweigerd (statische stream speelt); details in `CLIENT_COMPAT_MATRIX.md` §4 |
| JLT-67 (sync 12.x → 12.y) | — | **Niet uitgevoerd:** v12.4 is op 2026-11-10 de nieuwste stabiele tag (`release-12.z` heeft nog geen nieuwe tag). Het mechanisme staat klaar: herbasisresultaat per core-patch, ankercontrole en runtime-tests op de runtime van de nieuwe tag in `upstream-sync.yml` |

## 8. Overname uit Emby herhaald tegen jelly-leon:12.4 (JLT-70…73)

`flock …/stack.lock nice -n 10 tools/jelly-leon/.venv/bin/python tools/emby-overname/e2e/proefrun.py --modus corpus
--jellyfin-image jelly-leon:p40 --uitvoer …` (nieuwe optie, commit `0899e546c`) → **57/57** in 16 min 19 s (corpus 1/1,
JLT-70 21/21, JLT-71 11/11, JLT-72 7/7, JLT-73 17/17) met de echte `emby/embyserver:4.10.2.0@sha256:7082c63b…65cc1`;
31/31 koppelbare items exact, 37/37 Emby-items met kijkgegevens verantwoord, tweede run 0 schrijfacties, alleen GET naar
Emby, Emby-kijkgegevens vóór en na identiek, herimport exact. Bewijs:
`test-evidence/p40/b03-015-proefrun-corpus-jelly-leon-12.4.json`; testset en containers daarna opgeruimd (BG-38).

## 9. GitHub Actions

Run **42753563000** (*Jelly Leon CI*, commit `d6a064278` — alle code van deze ronde; daarna alleen documentatie, bewijs,
tests zonder Docker en een padcorrectie in de clientmatrix): **8/8 jobs groen**.

| Job | Uitkomst |
|---|---|
| Forkregels (patchregister, versies, contractkopie, tool-tests, ruff, shellcheck, actionlint, **register upstream-gedrag**) | geslaagd |
| Manifest §9 (validator appstore-en-fork) | geslaagd |
| Upstream-solution bouwen en testen (.NET 10.0.x uit global.json; volledige upstream-testsuite; OpenAPI-drift tegen de 12.4-export) | geslaagd (4 min) |
| Plugins bouwen en testen (net10.0) | geslaagd |
| Stock-client-smoketest (fork-build op `JL_RUNTIME_IMAGE` 12.4) + **UG-runtimetests op `JL_RUNTIME_IMAGE`** | geslaagd: smoketest 25/25, UG 6/6 |
| Image (echte jelly-leon-web-build) | geslaagd: levenscyclus 31/31, CI-guard testdata, terugzetproef 10/10, **upgradeproef 18/18**, **compat-API 5/5**, **UG op de image 6/6** |
| B03-016-harnas (corpus, guard, clientmatrix tegen stock 12.4, controle-run) | geslaagd |
| Overname uit Emby (synthetisch, echte Emby + stock 12.4) | geslaagd |

CI-rapporten van deze run (artefacten, zonder geheimen): `test-evidence/p40/ci-42753563000/` (levenscyclus, terugzetproef,
upgradeproef met het oordeel `jlt_61_b`, compat-API, UG-runtimetests op stock en op de image, stock-client-smoketest).

Eerdere runs van deze ronde (42751020743, 42752381982) zijn door de concurrency-regel afgebroken of faalden op de nog
niet aangepaste smoketest (oude aanmeldheaders in 12.x, gerepareerd in `49481a226`).

## 10. Wat niet gehaald of niet gevalideerd is

- **JLT-61 (b) voor de overgang 10.11.11 → 12.4: Sim-mislukt.** Stock 10.11.11 (en de nooit uitgebrachte
  10.11.11-jl.0) kennen geen downgradeweigering; gemeten: gezond, aanmelden HTTP 500, geen blijvende schade. Vanaf
  12.4.0-jl.0 weigert de jelly-leon-image een nieuwere datamap zichtbaar (§5, Sim-geslaagd met een gesimuleerd nieuwere
  datamap-versie; een echte 12.y-image bestaat nog niet).
- **JLT-62** (overname van een bestaande Jellyfin-installatie: schrijfopties, mountcontrole, bestaande plugins): niet
  gebouwd in deze ronde. B03-015 deel B geldt alleen als D07 een Jellyfin-installatie meet; de gebruiker gebruikt Emby.
- **JLT-67:** geen 12.y-tag (zie §7).
- **Δ-MG-AUTH en Δ-MG-DUAL** (media-guard-ultimate): niet geleverd; zonder die levering geen B03-batch op de NAS en
  `mediaguard: onbekend` (gate P4-0).
- Baselines B03-016 op de 12.x-digest van de forkbasis: de forkbasis is dezelfde 12.4-digest als de voormeting; een
  nieuwe definitieve meetsessie onder het meetslot is in deze ronde niet gedraaid.
- Echte NAS, echte Emby (D07), echte apparaten (D15), Swiftfin/Safari: NIET GEVALIDEERD.

## 11. QA-review (2026-11-10)

Onafhankelijke herhaling met een eigen build (`jelly-leon:qa`): levenscyclus 31/31, terugzetproef 10/10, upgradeproef
18/18 (JLT-61 b blijft Sim-mislukt), compat-API 5/5, UG-runtime 6/6, overname uit Emby 62/62 na twee reparaties in de
overnametool (doelcontrole en geen door een GET uitgelokte analyse in Emby). JLT-60 en JLT-63 staan sindsdien op
`Sim-getest` (de Android-emulator en de overige clientscenario's zijn niet uitgevoerd). Details en commando's:
`BOUWVERIFICATIE_B03-015.md` §QA-review; bewijs in `test-evidence/p40-qa/`; CI-run 42762467348 groen (8/8).
