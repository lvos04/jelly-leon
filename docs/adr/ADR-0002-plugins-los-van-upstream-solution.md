# ADR-0002 — Plugins in `plugins/<Naam>/`, eigen solution, tegen dezelfde Jellyfin-versie

- **Status:** Aanvaard (P0, 2026-11-09)
- **Context:** Pakketregel ADR-0001. Upstream `Jellyfin.sln` en de root-`Directory.Build.props`/
  `Directory.Packages.props` gelden voor alle projecten onder de repo-root (MSBuild zoekt omhoog). Als we onze projecten
  daaraan toevoegen, raken we upstream-bestanden (merge-conflicten) en bouwen plugins per ongeluk tegen interne
  (niet-publieke) code.

## Besluit

- Elke plugin staat in `plugins/<Naam>/` met eigen `src/<Assembly>/<Assembly>.csproj` en
  `tests/<Assembly>.Tests/<Assembly>.Tests.csproj`.
- `plugins/JellyLeon.Plugins.sln` bevat alleen pluginprojecten; **niets** wordt aan `Jellyfin.sln` toegevoegd.
- `plugins/Directory.Build.props`, `plugins/Directory.Build.targets` en `plugins/Directory.Packages.props` **stoppen**
  de MSBuild-overerving van de root (ze importeren de root-bestanden niet). Daardoor geen analyzer-`ProjectReference` naar upstream-broncode en geen
  afhankelijkheid van upstream-pakketversies behalve de expliciet gekozen.
- Plugins verwijzen naar de **NuGet-pakketten** `Jellyfin.Controller`, `Jellyfin.Model` en `Jellyfin.Common` met exact de
  versie van de baseline (`JellyfinVersion` in `plugins/Directory.Build.props`, nu `10.11.11`) met
  `ExcludeAssets=runtime` — dus de publieke plugin-ABI, net als officiële plugins. De CI-controle
  `tools/jelly-leon/check_fork_consistency.py` faalt als `JellyfinVersion` ≠ `AssemblyVersion` in `SharedVersion.cs`
  ≠ `tools/jelly-leon/baseline.json`.
- Plugin-assemblies heten `Jellyfin.Plugin.<Naam>` (conventie upstream), de zichtbare pluginnaam mag "Jelly Leon …" zijn.

## Gevolgen

- Een plugin ziet geen core-patches (bewust: plugins moeten ook op stock Jellyfin draaien).
- Bij een upstream-sync naar een nieuwe versie moet `JellyfinVersion` mee (gebeurt in `upstream-sync.yml` via
  `tools/jelly-leon/upstream_sync.py merge`); bouwt een plugin dan niet meer, dan faalt de sync (EX48).
- Forkgegevens (`fork_version`, `upstream_tag`, `upstream_commit`) leest `plugins/Directory.Build.props` bij het bouwen
  uit `tools/jelly-leon/baseline.json` en zet ze als assembly-metadata in de plugin; zo kan de plugin niet met andere
  waarden rapporteren dan de bron van waarheid.
- Gemeten (P0, Sim-getest): de plugin laadt en antwoordt zowel in de fork-build als in de **stock** image
  `jellyfin/jellyfin:10.11.11` (`docs/platform-v2/test-evidence/p0-stock-client-smoke-*.json`).
- Eerste plugin: `plugins/JellyLeon/` (`Jellyfin.Plugin.JellyLeon`) met alleen `GET /media/v1/version`
  (versie-/compatinformatie voor de Hub-pagina "Versie en clientcompatibiliteit", B03-001). Overige B03-routes
  (`/media/v1/search`, `/media/v1/transcode/capabilities`, connectorcontract) volgen in latere fasen en antwoorden tot
  dan niet (geen gesimuleerd succes).

## Overwogen alternatieven

- *ProjectReference naar `MediaBrowser.Controller` in de repo* — verworpen: koppelt plugins aan interne wijzigingen en
  core-patches; plugin zou niet meer op stock Jellyfin passen.
- *Plugins in een aparte repo* — verworpen voor nu: de gebruiker koos één repo per component; sync en versiecheck zijn
  eenvoudiger als baseline en plugins samen versioneren.
