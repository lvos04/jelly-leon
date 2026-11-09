# ADR-0007 — Upstream-GitHub-workflows in de fork: wat draait, repository-guards

- **Status:** Aanvaard (P0, 2026-11-09)
- **Context:** De volledige upstream-historie is samengevoegd, inclusief `.github/workflows/*`. Sommige upstream-workflows
  hebben `secrets.JF_BOT_TOKEN` of upstream-servers nodig, of handelen (versie ophogen en pushen). Opdracht: niet
  stilletjes uitzetten, wél documenteren en waar nodig een repository-guard.

## Besluit — overzicht

| Workflow | Trigger in de fork | Gedrag in `lvos04/jelly-leon` | Wijziging |
|---|---|---|---|
| `ci-tests.yml` (Tests) | push naar `master` (bestaat hier niet), pull requests | draait op PR's (ubuntu/macos/windows); geen geheimen nodig | geen |
| `ci-openapi.yml` (OpenAPI) | push `master`, tags `v*`, PR's | draait op PR's en op onze tags `v*-jl.*`; publicatie naar upstream-server al begrensd op eigenaar `jellyfin` | geen |
| `ci-compat.yml` (ABI) | PR's | ApiCompat draait; bot-commentaar vereist `JF_BOT_TOKEN` | **JL-0001:** commentaarstappen alleen in upstream, resultaat in job-samenvatting |
| `ci-codeql-analysis.yml` | push/PR `master`, wekelijks | wekelijks op de standaardbranch; op een privé-repo zonder GitHub Code Security kan de upload falen | geen (documenteren; gebruikersbesluit over zichtbaarheid, ADR-0004) |
| `commands.yml` (`@jellyfin-bot rebase/rename`) | commentaar, PR-labels | zou falen zonder `JF_BOT_TOKEN` | **JL-0001:** alleen in `jellyfin/jellyfin` |
| `issue-template-check.yml` | nieuw issue | zou falen (token + upstream-triagescript) | **JL-0001:** alleen in `jellyfin/jellyfin` |
| `release-bump-version.yaml` | GitHub-release, handmatig | zou de **serverversie ophogen en pushen** (strijdig met ADR-0005) | **JL-0001:** alleen in `jellyfin/jellyfin` |
| `issue-stale.yml`, `pull-request-stale.yaml` | schema | upstream al begrensd (`contains(github.repository, 'jellyfin/')`) → overgeslagen | geen |
| `project-automation.yml`, `pull-request-conflict.yml` | push/PR/commentaar | upstream al begrensd (`github.repository == 'jellyfin/jellyfin'`) → overgeslagen | geen |
| `jelly-leon-ci.yml` (eigen) | push `main`/`ccr-**`/`sync/**`/`release/**`, tags `v*-jl.*`, PR's, handmatig | forkregels, volledige build+test, OpenAPI-drift, plugins, stock-client-smoketest | nieuw |
| `upstream-sync.yml` (eigen) | wekelijks + handmatig | ADR-0006 | nieuw |

Overige upstream-config: `.github/renovate.json` (alleen actief als de Renovate-app is geïnstalleerd),
`.github/CODEOWNERS` (verwijst naar een upstream-account; in de fork zonder effect). Beide ongewijzigd.

## Gevolgen

- Guards zijn een geregistreerde core-patch (JL-0001 in `docs/platform-v2/PATCHES.md`); bij een upstream-sync kunnen
  deze bestanden conflicteren → de sync faalt zichtbaar en de guard wordt opnieuw toegepast.
- Geen enkele upstream-workflow is via de GitHub-UI uitgeschakeld; alles staat in de repo.
- Echte runs op GitHub: **NIET GEVALIDEERD** in P0 (lokaal alleen `actionlint` op de gewijzigde/nieuwe workflows).
