# Jelly Leon

Jelly Leon is de mediaserver van het TrueNAS Home Platform V2 (bouwplan **B03**): een fork van
[Jellyfin](https://github.com/jellyfin/jellyfin) **v12.4** (sinds P4-0, B03-014; daarvoor v10.11.11), gelicenseerd onder **GPL-2.0** (zie `LICENSE`;
upstream-credits in `CONTRIBUTORS.md`). De technische identiteit blijft *Jellyfin* zodat alle bestaande Jellyfin-apps
blijven werken; alleen de zichtbare naam is *Jelly Leon*. Jelly Leon is geen officiële Jellyfin-release.

De upstream-README staat ongewijzigd in `README.md`.

## Waar staat wat

| Pad | Inhoud |
|---|---|
| `docs/platform-v2/FORK_STRATEGIE.md` | forkstrategie (plugin vóór patch, branding, GPL, versies, sync) |
| `docs/platform-v2/PATCHES.md` | patchregister: elke afwijking van upstream (CI dwingt dit af) |
| `docs/platform-v2/UPSTREAM_GEDRAG.md` | register van upstream-gedrag waarop Jelly Leon steunt (UG-GEM-…), met anker- en runtime-tests (B03-019) |
| `docs/platform-v2/INVENTARIS.md` | wat upstream al kan + delta-matrix B03 |
| `docs/platform-v2/CLIENT_COMPAT_MATRIX.md` | compatibiliteit server ↔ clients |
| `docs/platform-v2/BOUWVERIFICATIE_*.md`, `test-evidence/` | gemeten bouw- en testresultaten (P0, B03-015, B03-016, P4-0) |
| `docs/platform-v2/EVIDENCE.json` | status per Excel-taak (nooit "Gereed" zonder echte acceptatie) |
| `docs/adr/` | architectuurbesluiten ADR-0001…0028 (ADR-0011: vóór P4 naar Jellyfin 12.x, besluit gebruiker; ADR-0025: eigen overnametool uit Emby; ADR-0026: B03-016-harnas; ADR-0027: P4-0 uitgevoerd op v12.4; ADR-0028: contract 1.3) |
| `docs/openapi/` | upstream-API (gegenereerd) en de fork-eigen pluginroutes |
| `plugins/` | eigen Jellyfin-plugins (eigen solution, tegen dezelfde Jellyfin-versie) |
| `tools/b03-harnas/` | B03-016: corpusgenerator (recepten F1–F6, bevroren sha256-manifesten), CI-guard testdatalicenties, clientmatrix-rooktest, baselines van stock Jellyfin en de differentiële controle-run (ADR-0026; procedure in `docs/platform-v2/B03-016_HARNAS.md`) |
| `tools/emby-overname/` | overname van de kijkgeschiedenis uit Emby (B03-015 deel A): alleen-lezen-tool, tests en E2E-proefrun met een echte Emby-container (ADR-0025; procedure in `docs/platform-v2/OVERNAME_EMBY.md`) |
| `tools/jelly-leon/` | `baseline.json` (bron van waarheid), patchregister-/consistentiecontrole, upstream-sync (herbasis per core-patch), register-controle upstream-gedrag, OpenAPI-upgraderapport; `e2e/`: smoketest, levenscyclus- en terugzetproef, upgradeproef 10.11.11 → 12.x, API-regressie tegen stock, UG-runtimetests |
| `deploy/` | alles-in-één image (lokaal volledig gebouwd en getest; publicatie in P4), TrueNAS Custom App-formulier, manifest |
| `.github/workflows/jelly-leon-ci.yml`, `upstream-sync.yml` | eigen CI en upstream-sync (nooit automatisch naar productie) |

## Ontwikkelen

- Server: `dotnet build Jellyfin.sln -c Release` en `dotnet test Jellyfin.sln -c Release` (.NET 10 SDK; lokaal in
  `mcr.microsoft.com/dotnet/sdk:10.0.403@sha256:212fe4cb…` met `-m:4`, zie `BOUWVERIFICATIE_P4-0.md` §3).
- Plugins: `dotnet build plugins/JellyLeon.Plugins.sln -c Release` en `dotnet test …`.
- Forkregels: `python3 tools/jelly-leon/check_fork_consistency.py`, `python3 tools/jelly-leon/patch_register_check.py`,
  `python3 -m pytest tools/jelly-leon/tests` (venv in `tools/jelly-leon/.venv`, niet committen).

## Installeren

Alleen als **standaard TrueNAS Custom App** (geen YAML, geen compose, geen terminal): zie
`deploy/truenas/CUSTOM_APP.md`. Er is nog geen gepubliceerde image. De basis staat sinds P4-0 op Jellyfin 12.4
(ADR-0011/ADR-0027); de eerste release (`12.4.0-jl.1` of later) is een aparte R2-stap van de gebruiker (BG-02).
