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
| [ADR-0014](ADR-0014-healthcheck-zonder-root.md) | Docker-healthcheck zonder root-rechten (curl als 568, no_new_privs) | Aanvaard (Sim-getest) |
| [ADR-0015](ADR-0015-b03-basis-12x-en-overname-emby.md) | B03: Jellyfin 12.x als basis en overname van de bestaande mediaserver (Emby; ook Jellyfin als D07 dat meet); vult ADR-0011 aan | Aanvaard (plan goedgekeurd 2026-11-09; uitvoering later) |
| [ADR-0016](ADR-0016-b03-een-plugin-met-modules.md) | B03: één serverplugin `Jellyfin.Plugin.JellyLeon` met modules | Aanvaard (plan goedgekeurd 2026-11-09; uitvoering later) |
| [ADR-0017](ADR-0017-b03-analysewerker-en-bestandspas.md) | B03: één analysewerker, één Python-omgeving, één bestandspas | Aanvaard (plan goedgekeurd 2026-11-09; uitvoering later) |
| [ADR-0018](ADR-0018-b03-planner-en-gpu-budget.md) | B03: globale batchplanner en GPU-budget A310 / UHD 770 | Aanvaard (plan goedgekeurd 2026-11-09; uitvoering later) |
| [ADR-0019](ADR-0019-b03-upstream-gedrag-en-haken.md) | B03: register van upstream-gedrag (`UPSTREAM_GEDRAG.md`), patches en webhaken | Aanvaard (plan goedgekeurd 2026-11-09; uitvoering later) |
| [ADR-0020](ADR-0020-b03-opslag-en-gegevensbescherming.md) | B03: eigen opslag en gegevensbescherming; kijkgeschiedenis blijft altijd beschikbaar (HARDE EIS) | Aanvaard (plan goedgekeurd 2026-11-09; uitvoering later) |
| [ADR-0021](ADR-0021-b03-mediaguard-grens.md) | B03: MediaGuard — één viewerclient, geen mutaties; MediaGuard volgt Emby én Jelly Leon (Δ-MG-DUAL) | Aanvaard (plan goedgekeurd 2026-11-09; uitvoering later) |
| [ADR-0022](ADR-0022-b03-post-credit-bescherming.md) | B03: post-credit-scènes beschermen met segmentgrenzen, zonder nieuw segmenttype | Aanvaard (plan goedgekeurd 2026-11-09; uitvoering later) |
| [ADR-0023](ADR-0023-b03-licenties.md) | B03: licentiebeleid voor code, modellen en testdata | Aanvaard (plan goedgekeurd 2026-11-09; uitvoering later) |
| [ADR-0024](ADR-0024-b03-clientrollen.md) | B03: clientrollen; stock-clients nooit geweigerd of aangepast zonder opt-in | Aanvaard (plan goedgekeurd 2026-11-09; uitvoering later) |

## B03 2.0 — herkomst van de ADR's

Het bouwplan `docs/platform-v2/02_BOUWPLANNEN/B03_UNIVERSELE_MEDIASERVER.md` (versie 2.0, door de gebruiker goedgekeurd op
2026-11-09) bevat dertien ADR-voorstellen ADR-B03-01…13. De voorstellen die deze fork raken staan hier als ADR-0015…0024,
inhoudelijk letterlijk (met de aanvullingen van 2026-11-09: Emby, HARDE EIS en Δ-MG-DUAL). Aangepast zijn alleen de kop
(nummer, status, herkomst), de testverwijzingen in de kop van ADR-0015 en ADR-0020 (JLT-70…74), bestandspaden naar deze repo
en de onderlinge verwijzingen; ADR-0015 heeft één slotregel over het vervolgbesluit JellyPlex-Watched. De overige
voorstellen zijn platformbesluiten van ai-server-manager.

| Voorstel | Onderwerp | Hier | Elders |
|---|---|---|---|
| ADR-B03-01 | 12.x-basis en overname (Emby; Jellyfin als D07 dat meet) | ADR-0015 (vult ADR-0011 aan) | ai-server-manager ADR-0020 (HARDE EIS en Emby-overname op platformniveau) |
| ADR-B03-02 | één plugin met modules | ADR-0016 | — |
| ADR-B03-03 | analysewerker en bestandspas | ADR-0017 | — |
| ADR-B03-04 | planner en GPU-budget | ADR-0018 | — |
| ADR-B03-05 | foutcatalogus; 1 MiB per route | — (uitvoering in B03-017) | ai-server-manager ADR-0016 |
| ADR-B03-06 | Hub-koppeling (JL4) en privacy | — (uitvoering in B03-017) | ai-server-manager ADR-0017 |
| ADR-B03-07 | upstream-gedrag, patches en webhaken | ADR-0019 | webdeel in jelly-leon-web |
| ADR-B03-08 | opslag en gegevensbescherming (HARDE EIS) | ADR-0020 | ai-server-manager ADR-0020 |
| ADR-B03-09 | MediaGuard-grens (Δ-MG-AUTH per server, Δ-MG-DUAL) | ADR-0021 | ai-server-manager ADR-0018 (contractkant); media-guard-ultimate |
| ADR-B03-10 | post-credit-bescherming | ADR-0022 | — |
| ADR-B03-11 | licenties | ADR-0023 | geldt voor alle B03-repos |
| ADR-B03-12 | clientrollen | ADR-0024 | jelly-leon-web, jelly-leon-clients (verwijzing) |
| ADR-B03-13 | optionele model-apps | — | ai-server-manager ADR-0019 |

Let op: ADR-nummers in de byte-gelijke kopieën uit het pakket (`docs/platform-v2/`, o.a. "ADR-0016…0020 in `docs/adr/`" in
het bouwplan en "ADR-0020" in `04_BESTAANDE_APPS/A02_EMBY.md`) verwijzen naar ai-server-manager; ADR-0001…0011 in het
bouwplan zijn de ADR's van deze repo. Na de beoordeling van JellyPlex-Watched (B03-015 stap A2) volgt een eigen ADR over
hergebruik of een eigen overnametool.
