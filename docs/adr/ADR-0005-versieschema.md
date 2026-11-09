# ADR-0005 — Versieschema `<upstream>-jl.N`

- **Status:** Aanvaard (P0, 2026-11-09)

## Besluit

- **Forkversie** = `<upstream-versie>-jl.<N>`, bv. `10.11.11-jl.1`. `N` is een teller per upstream-basis:
  - `N = 0`: ontwikkelstand op een nieuwe basis, **nooit** als release/image-tag gepubliceerd;
  - `N ≥ 1`: releases; een nieuwe upstream-basis (na sync) begint weer bij `-jl.0`/`-jl.1`.
- **Git-tags:** eigen releases `v<forkversie>` (bv. `v10.11.11-jl.1`). Upstream-tags staan in deze repo in een eigen
  naamruimte `upstream-v<x>` (bv. `upstream-v10.11.11`) zodat ze nooit met eigen tags verward worden.
- **Image-tags:** `ghcr.io/lvos04/jelly-leon:<forkversie>` (bv. `10.11.11-jl.1`); nooit `latest`, nooit een
  zwevende tag (`10.11`, `stable`). De release-CI vult de digest in het manifest.
- **Wat de server zelf rapporteert blijft de upstream-versie** (`/System/Info` → `10.11.11`, `SharedVersion.cs`
  ongewijzigd) — clients en plugins (`targetAbi`) rekenen daarop (ADR-0003). De forkversie is zichtbaar via de
  image-label `org.opencontainers.image.version`, het bestand `/usr/share/doc/jelly-leon/VERSION` in de image en
  `GET /media/v1/version` van de plugin `Jellyfin.Plugin.JellyLeon`.
- **Bron van waarheid:** `tools/jelly-leon/baseline.json` (`upstream_tag`, `upstream_version`, `upstream_commit`,
  `fork_version`, `web_upstream_tag`, `web_upstream_commit`). `check_fork_consistency.py` controleert dat dit klopt met `SharedVersion.cs`,
  `plugins/Directory.Build.props` en `deploy/manifest/jelly-leon.manifest.yaml`.

## Let op: sortering

Volgens SemVer is `10.11.11-jl.1` een *pre-release* van `10.11.11` en sorteert dus vóór `10.11.11`. Tools mogen
forkversies daarom niet met SemVer-precedentie tegen upstream vergelijken: vergelijk het paar
`(upstream-versie, N)`. Docker-tags staan geen `+` toe, daarom geen build-metadata (`10.11.11+jl.1`).
