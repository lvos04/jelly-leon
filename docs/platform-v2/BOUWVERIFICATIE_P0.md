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

## 9. Niet uitgevoerd (eerlijk)

- Geen run op GitHub Actions (workflows nog niet op de standaardbranch en niet uitgevoerd).
- Geen echte NAS, geen TrueNAS-formulier, geen A310/UHD 770, geen echte clients/tv's, geen echte upstream-sync naar v12.4.
