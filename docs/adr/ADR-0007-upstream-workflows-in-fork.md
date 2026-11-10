# ADR-0007 — Upstream-GitHub-workflows in de fork: wat draait, repository-guards

- **Status:** Aanvaard (P0, 2026-11-09)
- **Context:** De volledige upstream-historie is samengevoegd, inclusief `.github/workflows/*`. Sommige upstream-workflows
  hebben `secrets.JF_BOT_TOKEN` of upstream-servers nodig, of handelen (versie ophogen en pushen). Opdracht: niet
  stilletjes uitzetten, wél documenteren en waar nodig een repository-guard.

## Besluit — overzicht

| Workflow | Trigger in de fork | Gedrag in `lvos04/jelly-leon` | Wijziging |
|---|---|---|---|
| `ci-tests.yml` (Tests) | push naar `master` (bestaat hier niet), pull requests | draait op PR's (ubuntu/macos/windows); geen geheimen nodig | geen |
| `ci-openapi.yml` (OpenAPI, t/m 10.11) | push `master`, tags `v*`, PR's | draait op PR's en op onze tags `v*-jl.*`; publicatie naar upstream-server al begrensd op eigenaar `jellyfin` | geen; **vervallen in 12.4** (opgesplitst, zie hieronder) |
| `openapi-generate.yml` (12.4) | `workflow_call` | bouwt de OpenAPI-spec als artefact; geen geheimen | geen |
| `openapi-pull-request.yml` (*OpenAPI Check*, 12.4) | PR's | vergelijkt de spec met de basis; geen geheimen | geen |
| `openapi-merge.yml` (*OpenAPI Publish*, 12.4) | push `master`, tags `v*` | publicatie naar de upstream-server al begrensd (`contains(github.repository_owner, 'jellyfin')`) | geen |
| `openapi-workflow-run.yml` (*OpenAPI Report*, 12.4) | `workflow_run` na *OpenAPI Check* | zou in de fork falen (PR-commentaar met `JF_BOT_TOKEN`) en draait met geheimen na een PR-workflow | **JL-0001:** beide jobs alleen in `jellyfin/jellyfin` |
| `ci-format.yml` (12.4) | push `master`, PR's | `dotnet format`-controle; geen geheimen | geen |
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
- Herbasis op v12.4 (2026-11-10, B03-014): tabel bijgewerkt voor de 12.4-workflows; `openapi-workflow-run.yml` kwam erbij
  in JL-0001. De workflowlijst is opnieuw nagelopen op `secrets.`-gebruik (alleen-upstream of begrensd).
