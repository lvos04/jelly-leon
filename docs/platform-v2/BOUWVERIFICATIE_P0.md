# Bouwverificatie P0 (B03-001 / B03-013) — gemeten op 2026-11-09

Omgeving: gedeelde bouwcontainer (4 CPU, 15 GB), Docker. Alle .NET-stappen in
`mcr.microsoft.com/dotnet/sdk:9.0.320@sha256:07ed28d9e7279248fcea27334880f6c415b42c631c39b8bc5b3caf13ec6fdaa2`
met `--network host`, `HTTPS_PROXY` en de proxy-CA alleen als runtime-mount (nooit in repo of Dockerfile),
`--cpus 2`, NuGet-cache als Docker-volume. Ruwe uitvoer (ingekort): `test-evidence/p0-dotnet-build-test.txt`.

**Niets hiervan is op de echte NAS, met echte GPU's of op echte clients uitgevoerd.**

> **Bijgewerkt in de P0-afronding (§11, Ubuntu-machine):** de 4 omgevingsfouten uit §3 slagen daar en op GitHub; de
> volledige image mét echte web-build (§8: hier geblokkeerd) is gebouwd en getest; GitHub-CI is groen (§9). De
> §§1–10 hieronder zijn de oorspronkelijke sandboxmetingen en blijven ongewijzigd staan.
>
> **Contract 1.2-ronde (§13):** contractkopie + drifttest, manifest §9 (GPU-parameter), Custom App-instructie, rooktest
> op elk proces, *Custom User* met `no_new_privs`, en de CI-job *image* bouwt nu de echte `jelly-leon-web`-build.

## 1. Restore en build

| Commando | Resultaat | Duur |
|---|---|---|
| `dotnet restore Jellyfin.sln` (NuGet via proxy) | geslaagd | 2 min 03 s |
| `dotnet build Jellyfin.sln -c Release -m:2 --no-restore` | **geslaagd, 0 waarschuwingen, 0 fouten** | 3 min 48 s |
| `dotnet publish Jellyfin.Server -c Release --runtime linux-x64 --self-contained` | geslaagd (170 MB) | 1 min 57 s |

NuGet was **niet** geblokkeerd. Bekende blokkade in de bouwomgeving: `repo.jellyfin.org` (pluginrepository) en
GitHub-archiefdownloads (`github.com/.../archive/...`) geven HTTP 403 via de proxy.

## 2. Tests upstream-solution

`dotnet test Jellyfin.sln -c Release --no-build -m:2` (1 min 42 s): **2 555 tests — 2 544 geslaagd, 7 overgeslagen
(upstream `Skip`), 4 mislukt.**

| Project | Geslaagd | Overgeslagen | Mislukt |
|---|---:|---:|---:|
| Jellyfin.Api.Tests | 79 | 0 | 0 |
| Jellyfin.Common.Tests | 30 | 0 | 0 |
| Jellyfin.Controller.Tests | 28 | 0 | 0 |
| Jellyfin.Extensions.Tests | 141 | 0 | 0 |
| Jellyfin.LiveTv.Tests | 48 | 0 | 0 |
| Jellyfin.MediaEncoding.Tests | 47 | 0 | 0 |
| Jellyfin.MediaEncoding.Hls.Tests | 17 | 0 | 0 |
| Jellyfin.MediaEncoding.Keyframes.Tests | 2 | 0 | 0 |
| Jellyfin.Model.Tests | 627 | 0 | 0 |
| Jellyfin.Naming.Tests | 614 | 0 | 0 |
| Jellyfin.Networking.Tests | 117 | 0 | **2** |
| Jellyfin.Providers.Tests | 235 | 0 | 0 |
| Jellyfin.Server.Implementations.Tests | 420 | 4 | 0 |
| Jellyfin.Server.Integration.Tests | 100 | 3 | 0 |
| Jellyfin.Server.Tests | 5 | 0 | **2** |
| Jellyfin.XbmcMetadata.Tests | 34 | 0 | 0 |

### 3. Analyse van de 4 mislukte tests (omgeving, geen forkwijziging)

De servercode is identiek aan upstream v10.11.11; de oorzaak ligt in de bouwomgeving:

1. `NetworkParseTests.TestBindInterfaceOverrides` (2×) lost `jellyfin.org` op via DNS; de bouwcontainer heeft geen
   externe DNS. **Bewijs:** herhaald met `--add-host jellyfin.org:203.0.113.10` → `Jellyfin.Networking.Tests` 119/119.
2. `ParseNetworkTests.TestNetworks` (2×, `ip6: True`) verwacht dat `localhost` ook `::1` oplevert; de kernel van de
   bouwomgeving heeft geen IPv6 (`/proc/sys/net/ipv6` ontbreekt, ook `--sysctl` kan het niet aanzetten). Niet lokaal
   te herstellen; op GitHub-runners (met IPv6-loopback) horen ze te slagen — **NIET GEVALIDEERD** tot de eerste CI-run.

### 4. OpenAPI

`OpenApiSpecTests` (onderdeel van de run) schrijft `openapi.json`; die is **byte-gelijk** aan
`docs/openapi/jelly-leon.openapi.json` (sha256 `f0580e74a4e4…`, 315 paden, `info.version` 10.11.11). De CI vergelijkt
dit bij elke run (drift = falen).

## 5. Plugins

`dotnet restore/build/test plugins/JellyLeon.Plugins.sln -c Release -m:2` tegen NuGet `Jellyfin.Controller` /
`Jellyfin.Model` **10.11.11**: build 0 waarschuwingen/0 fouten, **13/13 tests geslaagd**.

## 6. Forktools (Python 3.12, alleen standaardbibliotheek)

`tools/jelly-leon/.venv/bin/pytest -q tools/jelly-leon/tests` → **28 geslaagd** (patchregister, consistentie,
upstream-sync incl. EX48-simulatie met een nep-upstream: compatibele tag gemerged; conflicterende tag → exit 2, branch
opgeruimd, werkboom schoon; rc/downgrade/vuile boom geweigerd; uiteenlopende releasereeksen: gewone merge faalt op een
nooit gewijzigd bestand, herbasis slaagt met upstream-inhoud + fork-paden + opnieuw toegepaste patch en twee ouders;
patch die niet meer past → exit 2; plugin-`TargetFramework` volgt de upstream-ABI).
`actionlint 1.7.12` op `jelly-leon-ci.yml`, `upstream-sync.yml` en de vier met JL-0001 gewijzigde upstream-workflows:
geen meldingen (de enige melding in de map betreft het ongewijzigde upstream-bestand `project-automation.yml`).

### 6a. Echte syncproef naar upstream v12.4 (lokaal, tijdelijke kloon, niets gepusht)

| Stap | Resultaat |
|---|---|
| `upstream_sync.py kies` (echte `git ls-remote` op github.com/jellyfin/jellyfin) | `patch`: geen nieuwere 10.11.x; `nieuwste`: **v12.4** (v12.0…v12.4) |
| `upstream_sync.py merge --tag v12.4 --methode merge` | exit 2, **79 conflicten** (4 in fork-patches, 75 door upstream-backports op de 10.11-releasebranch) |
| `upstream_sync.py merge --tag v12.4` (auto → herbasis) | exit 2, **1 conflict**: `.github/workflows/commands.yml` (JL-0001) — terecht falen, EX48 |
| Kenmerken v12.4 | `global.json` SDK 10.0.0, `TargetFramework` net10.0, `AssemblyVersion` 12.4.0 |

Bouwen/testen van v12.4: niet uitgevoerd (eerst conflict oplossen; .NET 10-SDK) — NIET GEVALIDEERD.

## 7. Stock-client-smoketest (Sim-getest)

`tools/jelly-leon/e2e/stock_client_smoke.py` tegen een lege server (zelfgemaakte WAV, geen auteursrechtelijk materiaal):

| Opzet | Resultaat |
|---|---|
| Fork-build (self-contained) op `jellyfin/jellyfin:10.11.11@sha256:aefb67e6…`, `--user 568:568 --cap-drop ALL --security-opt no-new-privileges`, plugin geïnstalleerd | **17/17** |
| Stock image `jellyfin/jellyfin:10.11.11` (upstream-binary) + Jelly Leon-plugin — referentie | **17/17** (plugin werkt ook op stock) |
| Fork-build uit de Docker-server-stage via `deploy/allinone/entrypoint.sh` als root → 568 | **17/17**; `/proc/1/status`: Uid/Gid 568, `CapEff=0`, `CapBnd=0`, `NoNewPrivs=1` |

Waarneming (geen slaagcriterium): streamen zonder token geeft HTTP 200 (upstream-gedrag, ADR-0009).

Entrypoint extra (Sim-getest): herstart zonder chown; gesimuleerde `/dev/dri/renderD128` met gid 107 → groep
toegevoegd, `card0` met gid 0 → geweigerd met waarschuwing; start als 568 → niets aangepast; ontbrekende mount →
NL-foutmelding en exitcode 1.

## 8. Alles-in-één image (schets)

| Stap | Resultaat |
|---|---|
| `docker buildx build -f deploy/allinone/Dockerfile --target server` (BuildKit, optioneel CA-geheim) | geslaagd (publish + plugin in 110 s) |
| Volledige image (`--build-context jelly-leon-web=…`) | **Geblokkeerd in deze bouwomgeving**: `npm ci` van de web-client haalt `classList.js` als GitHub-archief op → HTTP 403 van de proxy. Niet omzeild. In GitHub Actions naar verwachting geen probleem — NIET GEVALIDEERD. |
| Volledige image met de stage `web` vervangen door de upstream-web-dist (review, §10) | gebouwd; levenscyclustest **16/16** (`test-evidence/p0-image-lifecycle.json`) |

## 9. Niet uitgevoerd (eerlijk)

- Geen run op GitHub Actions (workflows nog niet op de standaardbranch en niet uitgevoerd).
- Geen echte NAS, geen TrueNAS-formulier, geen A310/UHD 770, geen echte clients/tv's, geen voltooide upstream-sync naar
  v12.4 (de syncproef faalde terecht op een conflict; bouwen/testen van 12.4 niet uitgevoerd).

## 10. Onafhankelijke review P0 (2026-11-09)

Alles opnieuw gedraaid op een `git archive`-export (geen lokale bouwresten), .NET-stappen in dezelfde SDK-container
(`--cpus 2`, `-m:2`, `nice -n 10`); ruwe uitvoer: `test-evidence/p0-review-dotnet-build-test.txt`.

| Controle | Resultaat |
|---|---|
| `dotnet build Jellyfin.sln -c Release -m:2` | 0 waarschuwingen, 0 fouten (bevestigd) |
| `dotnet test Jellyfin.sln -c Release --no-build -m:2` | 2 555 tests: 2 544 geslaagd, 7 overgeslagen, dezelfde 4 omgevingsfouten (geen DNS voor `jellyfin.org`, `/proc/sys/net/ipv6` ontbreekt — beide hier nagemeten) |
| OpenAPI-drift upstream | `openapi.json` byte-gelijk aan `docs/openapi/jelly-leon.openapi.json` (sha256 `f0580e74a4e4…`) |
| Plugins (incl. nieuwe `OpenApiContractTests`) | 0 waarschuwingen/0 fouten, **16/16**; mutatieproef (veld/enumwaarde weg uit de OpenAPI) → 2 tests falen |
| Forktools: `pytest`, `ruff`, `shellcheck`, `actionlint` (mét shellcheck) | **39** geslaagd; lint schoon |
| Technische identiteit | `git diff upstream-v10.11.11 HEAD` buiten fork-eigen paden: alleen de 4 workflowbestanden van JL-0001; `SharedVersion.cs`, `LICENSE`, `CONTRIBUTORS.md` ongewijzigd; server meldt `Jellyfin Server` 10.11.11 |
| Digests | `jellyfin/jellyfin:10.11.11`, `node:22.23.4-bookworm-slim`, `dotnet/sdk:9.0.320` en de gepinde GitHub-actions-SHA's opnieuw nagekeken: kloppen |
| Manifest | validator van appstore-en-fork (alleen lezen): geldig, 1 waarschuwing (digest volgt bij release) |
| Volledige image (productie-Dockerfile, stage `web` = upstream-web-dist 10.11.11; de broncode van `jelly-leon-web` is gelijk aan upstream) | gebouwd; proxy-CA niet in de image; `tools/jelly-leon/e2e/image_lifecycle.py` **16/16**: lege opslag → *healthy* → smoketest 18/18 → proces 1 568:568, `CapEff=0`, `CapBnd=0`, `NoNewPrivs=1` → web-client op `/web/` → `docker restart` en nieuwe container met dezelfde opslag: smoketest-herstart 20/20 (zelfde gebruiker en item-ID) → negatieve tests geweigerd, media ongemoeid |
| Entrypoint extra | gesimuleerde `/dev/dri/renderD128` (gid 107) → groep toegevoegd, `card0` (gid 0) geweigerd; start als Custom User 568 → niets aangepast, plugin geïnstalleerd |

**Gevonden en gerepareerd**

1. *Upstream-sync (veiligheid):* `JL_SYNC_PUSH_TOKEN` stond in dezelfde job waarin upstream-build- en testcode draait
   (die kon via git-hooks/`PATH`/`GITHUB_ENV` het token onderscheppen). Nu een aparte job `push` zonder upstream-code,
   alleen voor volledig geslaagde legs, met tagvalidatie, uitgeschakelde hooks en zonder overschrijven (ADR-0006).
2. *Entrypoint (dataverlies):* de basisimage declareert `VOLUME /config /cache`; zonder opslagregel startte de app op een
   anoniem volume (de melding "bestaat niet" kon nooit optreden). Nu: weigeren met NL-melding (ADR-0008).
3. *Entrypoint (root):* `JELLYFIN_DATA_DIR`/`JELLYFIN_CACHE_DIR` uit het formulier konden `chown -R` als root op elke map
   laten uitvoeren (ook de media). Nu: alleen `/config`/`/cache` (na het oplossen van symlinks). De pluginmap wordt pas
   na `setpriv` als 568 bijgewerkt.
4. *Tests:* geen dekking voor "herstart zonder dataverlies", de image-levenscyclus, de smoketest zelf (kon die ten
   onrechte slagen?) en het OpenAPI-schema van de plugin. Toegevoegd: herstartmodus + wizard-afsluitcontrole,
   `image_lifecycle.py` (ook als CI-job `image`), simulatortests met een nep-Jellyfin, `OpenApiContractTests`.
5. *Upstream-sync:* een al bestaande lokale `upstream-<tag>` liet een herhaalde sync falen; nu idempotent bij dezelfde
   commit en een duidelijke stop bij een verplaatste tag.
6. *Eerlijkheid/docs:* `validatie` in `EVIDENCE.json` noemt nu ook wat NIET GEVALIDEERD is; voorbeeldversie als tag in
   `CUSTOM_APP.md` vervangen door de vorm; tegenstrijdige zin over de v12.4-syncproef rechtgezet.

**Niet gerepareerd (buiten P0 of gebruikersbesluit):** anoniem streamen (ADR-0009), `/healthz`/`/readyz`, Hub-JWT en
platformfoutformaat (P1), echte web-build en release-workflow (P4), echte NAS/clients/GPU (NIET GEVALIDEERD).

## 11. P0-afronding op de Ubuntu-machine en GitHub Actions (2026-11-09)

Omgeving: eigen Ubuntu 26.04-machine van de gebruiker (22 CPU, 14,5 GiB RAM, gedeeld), Docker 29, **geen proxy en geen
eigen CA**. .NET-stappen in `mcr.microsoft.com/dotnet/sdk:9.0.320@sha256:07ed28d9…` (`--cpus 4 --memory 8g`, `-m:4`,
`nice -n 10`, standaard bridge-netwerk zonder `--add-host`), zware stappen onder `flock .lokaal/docker-build.lock`.
Bron telkens een `git archive`-export (geen lokale bouwresten). Ruwe uitvoer: `test-evidence/p0-afronding-*.{txt,json}`.

### 11.1 GitHub-CI gerepareerd (ADR-0010)

| Probleem | Oorzaak | Reparatie |
|---|---|---|
| Jobs *server*/*plugins* rood: "Could not find .NET Core SDK with version = 9.0.0" (runs 42595226924, 42595990869, 42605533435) | `setup-dotnet` met `global-json-file`; upstream-global.json noemt 9.0.0 als ondergrens (rollForward), die versie is niet te downloaden | `tools/jelly-leon/dotnet_sdk_kanaal.py` → kanaal `9.0.x` uit global.json; global.json blijft ongewijzigd (geen core-patch). Ook in `upstream-sync.yml` (12.x → `10.0.x`) |
| OpenAPI-drift zou rood/groen afhangen van de machine | upstream laadt XML-docbestanden in bestandssysteemvolgorde → andere `description`-teksten (zie 11.3) | `tools/jelly-leon/openapi_drift.py`: structureel vergelijken, beschrijvingen alleen als waarschuwing |

**Eerste groene run: [42619401596](https://github.com/lvos04/jelly-leon/actions/runs/42619401596)** (commit `5150dab15`,
alle 5 jobs groen): forkregels 79 tool-tests + ruff/shellcheck/actionlint; server `dotnet --version` = 9.0.320, build,
**2 555 tests: 2 548 geslaagd, 7 overgeslagen, 0 mislukt**, OpenAPI structureel gelijk (4 beschrijvingen anders →
waarschuwing); plugins 16/16; image (web-stage = upstream-web-dist) levenscyclus 16/16; stock-client-smoketest 18/18.
Run [42620955712](https://github.com/lvos04/jelly-leon/actions/runs/42620955712) (commit `3256a645a`, met de nieuwe
bundelcontrole en herkomst-build-arg): opnieuw 5/5 jobs groen — forkregels 84 tool-tests, server 2 548 geslaagd /
7 overgeslagen / 0 mislukt, plugins 16/16, image-levenscyclus 17/17 (incl. alle bundels uit index.html), stock-client-
smoketest 18/18. Latere runs: `gh run list -R lvos04/jelly-leon -b ccr-c133d7a0-kuz1cv`.

### 11.2 Lokale build en tests (zelfde 4 tests als in §3 herhaald)

| Commando | Resultaat | Duur |
|---|---|---|
| `dotnet restore Jellyfin.sln` | geslaagd | 44 s |
| `dotnet build Jellyfin.sln -c Release --no-restore -m:4` | **0 waarschuwingen, 0 fouten** | 59 s |
| `dotnet test Jellyfin.sln -c Release --no-build -m:4` | **2 555 tests: 2 548 geslaagd, 7 overgeslagen (upstream `Skip`), 0 mislukt** | 1 min 48 s |
| `dotnet build` + `dotnet test plugins/JellyLeon.Plugins.sln -c Release` | 0/0, **16/16** | 6 s |

De 4 tests die in de sandbox faalden, slagen hier (uit de TRX-bestanden, `test-evidence/p0-afronding-dotnet-build-test.txt`):

| Test | Sandbox | Ubuntu-machine | GitHub (42619401596) |
|---|---|---|---|
| `NetworkParseTests.TestBindInterfaceOverrides(source: "jellyfin.org", bindAddresses: "eth16", …)` | mislukt (geen DNS) | **geslaagd** | geslaagd (Networking 119/119) |
| `NetworkParseTests.TestBindInterfaceOverrides(source: "jellyfin.org", bindAddresses: "", …)` | mislukt (geen DNS) | **geslaagd** | geslaagd |
| `ParseNetworkTests.TestNetworks(ip4: False, ip6: True, hostList: ["localhost"], …)` | mislukt (geen IPv6) | **geslaagd** | geslaagd (Server.Tests 7/7) |
| `ParseNetworkTests.TestNetworks(ip4: True, ip6: True, hostList: ["localhost"], …)` | mislukt (geen IPv6) | **geslaagd** | geslaagd |

Conclusie: de 4 fouten waren omgevingsfouten van de sandbox (bevestigd), geen forkwijziging.

### 11.3 OpenAPI: byte-gelijkheid is omgevingsafhankelijk (gemeten)

`OpenApiSpecTests` gaf hier `openapi.json` sha256 `4bd2d710549c…` (volledige testrun én 2× alleen deze test), niet de
vastgelegde `f0580e74a4e4…` uit de sandbox. Verschil: 22 `description`-teksten, verder identiek. Proef op tmpfs met
dezelfde bin-map en de XML-docbestanden in oplopende resp. aflopende aanmaakvolgorde: `94be85990695…` (9 verschillen)
resp. `4bd2d710549c…` (22) → de volgorde van `Directory.EnumerateFiles` in upstream-code bepaalt de beschrijvingen.
Op GitHub: 4 verschillen. `openapi_drift.py` geeft in alle gevallen "structureel gelijk"; mutaties (pad, operationId,
summary, enum, required, nullable, parameter, voorbeeldwaarde) laten hem falen (`tests/test_openapi_drift.py`).
`docs/openapi/jelly-leon.openapi.json` blijft ongewijzigd. Upstream-PR-kans (sorteren): followup.

### 11.4 Volledige alles-in-één image mét echte web-build (ADR-0008)

| Stap | Resultaat |
|---|---|
| `docker buildx build -f deploy/allinone/Dockerfile --build-context jelly-leon-web=<git archive jelly-leon-web 2795f3365> --build-arg BUILD_JOBS=4 …` (commit `5a0eebcdf`) | geslaagd; `npm ci` 24 s (**`classList.js`-archief nu bereikbaar**), webpack-productiebuild 78 s (2 waarschuwingen over bundelgrootte), server-publish + plugin 34 s; image 801 MB, niet gepubliceerd |
| Herkomst | labels `org.opencontainers.image.revision=5a0eebcdf…`, `io.github.lvos04.jelly-leon.web.revision=2795f3365…`; `/usr/share/doc/jelly-leon/SOURCE_REVISIONS`; url/documentation naar de fork |
| Web-client in de image | 2 317 bestanden; 4 verschillen met de upstream-web-dist 10.11.11 (webpack-hash/commit-info) → de eigen build |
| `tools/jelly-leon/e2e/image_lifecycle.py --verwacht-web-ref 2795f3365…` | **18/18** (`test-evidence/p0-afronding-image-lifecycle-volledig.json`): lege opslag → *healthy* → smoketest 18/18 → proces 1 568:568, `CapEff=0`, `CapBnd=0`, `NoNewPrivs=1` → web-client + **31/31 bundels uit index.html** → herkomst klopt → `docker restart` en nieuwe container met dezelfde opslag: smoketest-herstart 20/20 → mediamap onaangeroerd → anoniem volume en cachemap naar de media geweigerd |
| Web-smoketest van `jelly-leon-web` (`web_smoke.py --modus fork --url … --zonder-herstart`, headless Chromium 153, alleen gelezen/uitgevoerd) tegen dezelfde image, gestart zoals het formulier | **21/21** (`test-evidence/p0-afronding-web-smoke-volledige-image.json`): NL-aanmeldpagina, fout wachtwoord geweigerd, inloggen, startscherm, zoeken, afspelen (stream 200), kinderprofiel ziet niets, 360/390/768/1440 px zonder horizontale overloop |

In GitHub-CI bouwt de job *image* dezelfde Dockerfile, maar met de upstream-web-dist als stage `web`: `jelly-leon-web`
is een privé-repo en `GITHUB_TOKEN` mag die niet lezen (een leestoken of publiek maken is een gebruikersbesluit).

### 11.5 Besluit gebruiker 2 vastgelegd, niet uitgevoerd

Server naar de nieuwste stabiele 12.x (.NET 10) vóór P4: `docs/adr/ADR-0011-upgrade-12x-voor-p4.md`, FORK_STRATEGIE §6a.
Gemeten (alleen lezen): nieuwste stabiele tag `v12.4` (server en web), `global.json` van v12.4 vraagt SDK 10.0.0,
`jellyfin-web` v12.4 vraagt Node ≥ 24 / npm ≥ 11; `jellyfin/jellyfin:12.4` en `dotnet/sdk:10.0` bestaan in de
registries. **De upgrade zelf is in deze ronde niet uitgevoerd** (basis blijft v10.11.11).

### 11.6 Nog steeds NIET GEVALIDEERD

Echte NAS en het echte TrueNAS-formulier, A310/UHD 770, echte clients/tv's, Swiftfin (Mac/Xcode), upstream-sync.yml op
GitHub (scheduled alleen op de standaardbranch; push vraagt `JL_SYNC_PUSH_TOKEN`), publicatie naar GHCR (P4).

## 12. QA-review van de P0-afronding (2026-11-09)

Onafhankelijke controle op de Ubuntu-machine (zelfde omgeving als §11), op HEAD `d4bc20d6a`. Ruwe uitvoer:
`test-evidence/p0-qa-*.{txt,json}`.

### 12.1 Opnieuw gedraaid zoals de CI

| Commando | Resultaat |
|---|---|
| `check_fork_consistency.py`, `patch_register_check.py`, `pytest tools/jelly-leon/tests`, `ruff check`, `shellcheck -s sh entrypoint.sh`, `actionlint jelly-leon-ci.yml upstream-sync.yml` | in orde; vóór de reparaties 84 tool-tests geslaagd, erna **89** (5 nieuwe voor de terugzetproef) |
| `dotnet restore/build/test Jellyfin.sln -c Release -m:4` in `dotnet/sdk:9.0.320@sha256:07ed28d9…` (`git archive d4bc20d6a`, lege NuGet-cache) | build **0 waarschuwingen, 0 fouten**; **2 555 tests: 2 548 geslaagd, 7 overgeslagen (upstream), 0 mislukt** (`test-evidence/p0-qa-dotnet-build-test.txt`) |
| `dotnet build/test plugins/JellyLeon.Plugins.sln` | 0/0, **16/16** |
| `openapi_drift.py` op de gegenereerde `openapi.json` | exit 0: structureel gelijk, 22 `description`-teksten anders (sha256 `4bd2d710549c…`, zelfde als §11.3) |
| Digests `dotnet/sdk:9.0.320`, `node:22.23.4-bookworm-slim`, `jellyfin/jellyfin:10.11.11` (`docker buildx imagetools inspect`) | gelijk aan de gepinde waarden |
| GitHub Actions: laatste runs 42619401596, 42620955712, 42622088484 | elk 5/5 jobs groen; de genoemde aantallen (79/84 tool-tests, 2 548/7/0, 16/16, levenscyclus 16/16 resp. 17/17, stock-client 18/18) kloppen met de logs |

### 12.2 Gevonden en gerepareerd

| Bevinding | Gemeten | Reparatie |
|---|---|---|
| **`/config` op tmpfs werd geaccepteerd.** Het Custom App-formulier biedt opslagtype *tmpfs*. De container werd *healthy* met een lege database; na elke herstart stond de startwizard weer **anoniem open** (HTTP 200 op `/Startup/Configuration`, `StartupWizardCompleted=false`) — de eerste bezoeker op het netwerk wordt dan beheerder, en alle gegevens zijn weg. | `docker run --tmpfs /config …` met de image van HEAD | `entrypoint.sh` zoekt de mount waarop datamap en instellingenmap liggen en weigert (ook als niet-root): anoniem volume, tmpfs/ramfs, de container zelf en NFS/SMB (SQLite). `/cache` mag tmpfs blijven. ADR-0008 §4, CUSTOM_APP.md |
| `JELLYFIN_CONFIG_DIR` of een padoptie in het veld *Command* (`--datadir`, `--configdir`, …) kon de datamapcontrole omzeilen | code-review | instellingenmap valt onder dezelfde controle; padopties in *Command* worden geweigerd |
| B03-013 ("terug te zetten met DB-back-up + binary, streaming blijft werken") had geen enkele simulatortest | — | nieuwe terugzetproef `tools/jelly-leon/e2e/rollback_sim.py` (+ 5 unit-tests met nep-Docker, ook voor een stille terugzetfout) en een stap in de CI-job *image* |
| De levenscyclustest liet een werkmap met bestanden van 568 achter (zonder sudo niet op te ruimen) | lokaal | werkmap wordt na succes via een wegwerpcontainer opgeruimd (`--behoud-werkmap` om hem te houden) |
| `README.jelly-leon.md` noemde `10.11.11-jl.1` als eerste release, strijdig met besluit 2 (eerst naar 12.x) | — | tekst rechtgezet |

### 12.3 Na de reparaties gemeten (Sim-getest, geen echte NAS)

Image opnieuw gebouwd met de productie-Dockerfile uit de werkboom (server en plugin opnieuw; de web-stage van
`jelly-leon-web` `2795f3365` kwam uit de BuildKit-cache, identieke invoer).

| Proef | Resultaat |
|---|---|
| `image_lifecycle.py --verwacht-web-ref 2795f3365…` | **21/21** (`test-evidence/p0-qa-image-lifecycle.json`): de 18 stappen uit §11.4 plus geweigerd: `/config` als tmpfs, `JELLYFIN_CONFIG_DIR` in de container, `--datadir` in *Command* |
| `rollback_sim.py --upstream-image jellyfin/jellyfin:10.11.11@sha256:aefb67e6…` | **10/10** (`test-evidence/p0-qa-rollback-sim.json`): upstream op lege opslag (smoketest 16/16) → koude back-up van `/config` → Jelly Leon op dezelfde opslag (20/20, zelfde gebruiker/item, plugin `compatibel`) → back-up + oude binary terug (merkteken: pluginmap van de fork weer weg; smoketest 18/18, streamen byte-gelijk) → media onaangeroerd |
| Los: start als `--user 568:568`; `/cache` als tmpfs; `/config` als tmpfs als niet-root | *healthy*; *healthy*; geweigerd |
| Web-smoketest van `jelly-leon-web` (`web_smoke.py --modus fork --url … --zonder-herstart`, headless Chromium 153) tegen de nieuwe image, gestart zoals het formulier | **21/21** (`test-evidence/p0-qa-web-smoke-volledige-image.json`; `--dist` is de web-client uit dezelfde image, de vergelijking van `index.html` is dus een zelfvergelijking) |

**GitHub Actions na de reparaties:** run [42626839277](https://github.com/lvos04/jelly-leon/actions/runs/42626839277)
(commit `7b764194e`): 5/5 jobs groen — forkregels 89 tool-tests, server 2 548 geslaagd / 7 overgeslagen / 0 mislukt,
plugins 16/16, image-levenscyclus 20/20 (zonder herkomststap: de CI-web-stage is de upstream-web-dist) inclusief de
drie nieuwe weigeringen, terugzetproef 10/10, stock-client-smoketest 18/18.

**Niet getest:** de weigering van NFS/SMB (geen NFS/SMB-server in de testomgeving); in P0 zijn fork en upstream dezelfde
versie, dus de terugzetproef bevat nog geen databasemigratie (onderscheidend pas bij 12.x, ADR-0011). Echte NAS,
TrueNAS-formulier, ZFS-snapshot, echte clients en hardware: NIET GEVALIDEERD.

## 13. Contract 1.2-ronde (2026-11-09)

Op de Ubuntu-machine (zelfde omgeving als §11/§12) en in GitHub Actions. Alleen de punten die in deze ronde horen
(`CONTRACT_1.2_CONFORMITEIT.md` §0 en §9): A1, A4, A6, JL2, JL3 uitgevoerd; JL4 alleen gedocumenteerd (ADR-0012);
**JL1 (12.x-upgrade) niet** — aparte fase (ADR-0011); **JL5 niets gewijzigd** (`upstream-sync.yml` ongemoeid); JL6 n.v.t.
Ruwe uitvoer: `test-evidence/c12-*.json`.

### 13.1 Wat er veranderd is

| Punt | Wijziging | Commit |
|---|---|---|
| A1 | `PLATFORM_CONTRACTEN.md` (`contracts 1.2`) en `CONTRACT_1.2_CONFORMITEIT.md` byte-gelijk uit `ai-server-manager` `8b54f39`; drifttest `tools/jelly-leon/contract_drift.py` (offline sha256-pin; `--online` tegen de publieke bron, ook als CI-stap; bron later gewijzigd = alleen waarschuwing) | `daa283809` |
| A4 | `tools/jelly-leon/tests/test_evidence_contract.py`: EVIDENCE.json volgens §11 | `c0a91a0e2` |
| JL2 | Manifest: `custom_app.ports` en `network.joins_platform_network` weg; GPU als wizardparameter `gpu` (D08, niet verplicht) met `privileges.gpu: intel_render` als maximum; CI-job `manifest` met de validator van `appstore-en-fork` (vaste commit `bd33052`) | `78bd2c90b` |
| A6 / §2.2 | Rooktest controleert elk proces; nieuwe run met *Custom User* 568 en weigering van een niet-schrijfbare `/config`; entrypoint zet bij *Custom User* zelf `no_new_privs` (zie 13.3) | `58b481dff` |
| CI | Job `image` bouwt de **echte** `jelly-leon-web`-build op `baseline.json` `web_fork_commit` (`2795f3365`) i.p.v. de upstream-web-dist; `web_bron.py` controleert de checkout (ADR-0013) | `ce980c25d` |
| JL3 / JL4 | `deploy/truenas/CUSTOM_APP.md` (tag met digest, publieke image, registry-login als terugval, stock-Jellyfin op eigen poort, terugzetten zonder `app.rollback`); ADR-0012, ADR-0013 | `e38b8285e` |

### 13.2 Lokaal gedraaid (Sim-getest, geen echte NAS)

| Commando | Resultaat |
|---|---|
| `python -m pytest -q tools/jelly-leon/tests` (venv buiten de repo; pytest 8.4.2) | **145 geslaagd** (89 eerder + 56 nieuw: drifttest 9, EVIDENCE §11 10, manifest 1.2 13, manifestrapport 6, rooktest per proces 5, web-bron 13) |
| `ruff check --config tools/jelly-leon/ruff.toml tools/jelly-leon`; `shellcheck -s sh deploy/allinone/entrypoint.sh`; `actionlint jelly-leon-ci.yml upstream-sync.yml` | in orde |
| `check_fork_consistency.py`; `patch_register_check.py` | in orde (geen nieuwe core-patch: alle wijzigingen in fork-eigen paden) |
| `contract_drift.py`, `--bron-map ../ai-server-manager`, `--online --github` | alle drie in orde (2 bestanden byte-gelijk aan `8b54f39`) |
| Validator van `appstore-en-fork` `bd33052` (`git archive`, eigen venv, `pip install --require-hashes --no-deps -r apps/api/requirements.lock`), `python -m appstore.manifest.cli validate … --format json` + `manifest_rapport.py` | nieuw manifest **geldig, 0 fouten**, alleen `digest_pending_release` (nog geen release) → conform (`test-evidence/c12-manifest-validator.json`); het manifest van vóór JL2 geeft 2× `deprecated_field` → niet conform |
| Vertaler van dezelfde commit (`translate()`, proefwaarden, `ix_app_version` 1.4.8) | `gpu` leeg of `none` → `use_all_gpus: false`; `intel_render` met gemeten render-node → `use_all_gpus: true` + waarschuwing `gpu_all_render_devices`; zonder meting → fout `gpu_not_measured`; poorten alleen uit `network.ports` (30460 → 8096); altijd `digest_not_pinned` (eigen image zonder release) → niet installeerbaar (`test-evidence/c12-manifest-vertaling-gpu.json`) |
| Digests `dotnet/sdk:9.0.320`, `node:22.23.4-bookworm-slim`, `jellyfin/jellyfin:10.11.11` (`docker buildx imagetools inspect`) | gelijk aan de gepinde waarden |
| `docker buildx build -f deploy/allinone/Dockerfile --build-context jelly-leon-web=<git archive jelly-leon-web 2795f3365> --build-arg BUILD_JOBS=4 …` op een `git archive` van `ce980c25d` (flock, nice) | geslaagd in 1 min 44 s (`npm ci` 17 s, webpack-productiebuild 75 s met 2 bundelgrootte-waarschuwingen); image 801 MB, niet gepubliceerd |
| `image_lifecycle.py --verwacht-web-ref 2795f3365…` | **27/27** (`test-evidence/c12-image-lifecycle.json`): de 21 stappen uit §12.3 plus: elk proces 568/`CapEff 0`/`NoNewPrivs 1` (eerste start en nieuwe container), *Custom User* 568:568 → *healthy* → smoketest 20/20 (zelfde gebruiker en item-ID) → elk proces in orde, en geweigerd: *Custom User* met een `/config` die niet van 568 is (NL-melding) |
| `rollback_sim.py --upstream-image jellyfin/jellyfin:10.11.11@sha256:aefb67e6…` | **10/10** (`test-evidence/c12-rollback-sim.json`) |
| `ghcr.io/lvos04/jelly-leon` anoniem (`docker buildx imagetools inspect …:10.11.11-jl.0`, GHCR-token zonder login) | `403 DENIED`: er is nog geen (publiek) pakket — klopt, er is nog geen release |

Niet opnieuw gedraaid: `dotnet test Jellyfin.sln` lokaal (geen C#-wijziging in deze ronde; de CI-job *server* draait de
volledige suite) en de Chromium-web-smoketest van `jelly-leon-web` (zelfde web-commit en Dockerfile als §12.3, 21/21).

**GitHub Actions:** run [42653328502](https://github.com/lvos04/jelly-leon/actions/runs/42653328502) (commit
`ce980c25d`): **6/6 jobs groen** — *manifest* (validator `appstore-en-fork` `bd33052`: geldig, alleen
`digest_pending_release`), *forkregels* (145 tool-tests, contractkopie online byte-gelijk aan `8b54f39`), *server*
(2 555 tests: 2 548 geslaagd, 7 overgeslagen (upstream), 0 mislukt; OpenAPI structureel gelijk, 4 `description`-teksten
anders zoals ADR-0010), *plugins* 16/16, *image* mét de **echte web-build** van `jelly-leon-web` `2795f3365` (bouwen
4 min 6 s; web-bron gecontroleerd; levenscyclus **27/27** incl. herkomst, elk proces 568 en *Custom User*;
terugzetproef **10/10**), *stock-client-smoketest* 18/18. Rapporten als artefacten van de run.

### 13.3 Gevonden en gerepareerd

| Bevinding | Gemeten | Reparatie |
|---|---|---|
| **Bij *Custom User* (start als 568) draaide de server zonder `no_new_privs`.** Contract 1.2 §2.2: het formulier zet geen `no-new-privileges`, dus de image moet het zelf zetten vóór de eerste `execve`. Bij een root-start gebeurde dat al (`setpriv`), bij een niet-root-start niet (`exec /jellyfin/jellyfin`). | nagebootst met de nieuwe image en `--entrypoint /jellyfin/jellyfin --user 568:568` (= het oude pad): `NoNewPrivs 0`, `CapBnd 00000000a80425fb`; met de nieuwe entrypoint `--user 568:568`: `NoNewPrivs 1` | entrypoint: eerst schrijfbaarheid van `/config`/`/cache` controleren (anders NL-fout), dan `setpriv --no-new-privs --inh-caps=-all`; de markering van de tweede fase telt alleen als `NoNewPrivs` echt 1 is (ADR-0012 punt 3) |
| De rooktest keek alleen naar PID 1 (A6 vraagt elk proces) | code-review | `image_lifecycle.py` leest elk `/proc/<pid>/status` en sluit alleen de bomen uit die Docker van buiten start (`docker exec`, healthcheck: PPid 0) |

### 13.4 Nog steeds NIET GEVALIDEERD / open

- Echte NAS, TrueNAS-formulier (of `@sha256:` in het tagveld werkt), digest-readback, ZFS-snapshot, D07-meting van een
  stock-Jellyfin, D08-meting en GPU-doorgifte (`use_all_gpus`), echte clients en hardware.
- Geen gepubliceerde image (P4, na de 12.x-upgrade); de release-CI moet `image.digest` vullen en dan `--strict` halen.
- Contract-issue: de Docker-healthcheck draait in alle alles-in-één images als de containergebruiker (root zonder
  *Custom User*), met standaard-capabilities en zonder `no_new_privs` (ADR-0012, Gevolgen (a)).
- `GET /media/v1/version` als niet-admin-gebruiker (Hub-adapter v1) is alleen uit de upstream-code afgeleid, niet getest.
