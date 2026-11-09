# Architectuurbesluiten (ADR) — jelly-leon

Elke keuze in deze fork die afwijkt van "upstream Jellyfin ongewijzigd laten" of die het platformcontract
(`docs/platform-v2/PLATFORM_CONTRACTEN.md`, versie 1.2) interpreteert, staat hier als ADR.
Status: `Voorgesteld` → `Aanvaard` → (`Vervangen door ADR-xxxx`).

| ADR | Titel | Status |
|---|---|---|
| [ADR-0001](ADR-0001-plugin-voor-core-patch.md) | Plugin/extensie vóór core-patch; core-patches alleen via patchregister | Aanvaard |
| [ADR-0002](ADR-0002-plugins-los-van-upstream-solution.md) | Plugins in `plugins/<Naam>/`, eigen solution, tegen dezelfde Jellyfin-versie | Aanvaard |
| [ADR-0003](ADR-0003-branding-zichtbare-naam.md) | Branding: alleen zichtbare naam "Jelly Leon", technische identiteit blijft "Jellyfin" | Aanvaard |
| [ADR-0004](ADR-0004-gpl-verplichtingen.md) | GPL-2.0-verplichtingen (bron, LICENSE, credits) | Aanvaard |
| [ADR-0005](ADR-0005-versieschema.md) | Versieschema `<upstream>-jl.N` | Aanvaard |
| [ADR-0006](ADR-0006-upstream-sync.md) | Upstream-sync via `sync/<tag>`, nooit automatisch naar productie (EX48) | Aanvaard |
| [ADR-0007](ADR-0007-upstream-workflows-in-fork.md) | Upstream-GitHub-workflows in de fork: wat draait, repository-guards | Aanvaard |
| [ADR-0008](ADR-0008-alles-in-een-image.md) | Alles-in-één image `ghcr.io/lvos04/jelly-leon` als standaard Custom App | Voorgesteld (lokaal volledig gebouwd en Sim-getest) |
| [ADR-0009](ADR-0009-upstream-risicos-niet-patchen-in-p0.md) | Bekende upstream-risico's (anoniem streamen, één GPU) vastleggen, niet patchen in P0 | Aanvaard |
| [ADR-0010](ADR-0010-ci-sdk-kanaal-en-openapi-drift.md) | CI: .NET-SDK-kanaal uit global.json en structurele OpenAPI-driftcontrole | Aanvaard |
| [ADR-0011](ADR-0011-upgrade-12x-voor-p4.md) | Server naar de nieuwste stabiele Jellyfin 12.x (.NET 10) vóór P4, als aparte fase (besluit gebruiker) | Aanvaard (uitvoering later) |
| [ADR-0012](ADR-0012-contract-1-2.md) | Contract 1.2: manifest §9 (GPU-parameter), Custom App-instructie, Custom User met no_new_privs, Hub-adapter v1 | Aanvaard (Sim-getest) |
| [ADR-0013](ADR-0013-ci-echte-web-build.md) | CI bouwt de image met de echte jelly-leon-web-build op een vaste commit | Aanvaard |
