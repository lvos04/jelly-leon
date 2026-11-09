# Bouwverificatie P0 (B03-001 / B03-013) — gemeten op 2026-11-09

Omgeving: gedeelde bouwcontainer (4 CPU, 15 GB), Docker. Alle .NET-stappen in
`mcr.microsoft.com/dotnet/sdk:9.0.320@sha256:07ed28d9e7279248fcea27334880f6c415b42c631c39b8bc5b3caf13ec6fdaa2`
met `--network host`, `HTTPS_PROXY` en de proxy-CA alleen als runtime-mount (nooit in repo of Dockerfile),
`--cpus 2`, NuGet-cache als Docker-volume. Ruwe uitvoer (ingekort): `test-evidence/p0-dotnet-build-test.txt`.

**Niets hiervan is op de echte NAS, met echte GPU's of op echte clients uitgevoerd.**

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
