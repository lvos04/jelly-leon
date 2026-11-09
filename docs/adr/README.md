# Architectuurbesluiten (ADR) — jelly-leon

Elke keuze in deze fork die afwijkt van "upstream Jellyfin ongewijzigd laten" of die het platformcontract
(`docs/platform-v2/PLATFORM_CONTRACTEN.md`, versie 1.1) interpreteert, staat hier als ADR.
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
| [ADR-0008](ADR-0008-alles-in-een-image.md) | Alles-in-één image `ghcr.io/lvos04/jelly-leon` als standaard Custom App (schets P0) | Voorgesteld |
| [ADR-0009](ADR-0009-upstream-risicos-niet-patchen-in-p0.md) | Bekende upstream-risico's (anoniem streamen, één GPU) vastleggen, niet patchen in P0 | Aanvaard |
