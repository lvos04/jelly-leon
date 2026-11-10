# Register van upstream-gedrag — serverdeel (jelly-leon)

Bouwplan B03 §10.11 en B03-019 (a): elk upstream-gedrag waarop Jelly Leon steunt zonder dat het een vaste API of ABI
is, staat hier met een **sync-blokkerende test**. Het webdeel heeft een eigen register met de reeks `UG-WEB-<n>` in
`lvos04/jelly-leon-web` → `docs/platform-v2/UPSTREAM_GEDRAG.md`.

**Nummering.** `UG-<functie>-<n>` (§10.11, Bijlage B8). De functiereeksen `UG-F2-1…8`, `UG-F3-1…11` en `UG-F5-1…13`
zijn in het bouwplan al vergeven aan de regels van F2, F3 en F5; die komen hier pas als die functies gebouwd worden
(golf 2 en later), elk met een test. Gedrag waarop de gemeenschappelijke basis (P4-0, B03-013…019) en meerdere
functies steunen, krijgt de reeks **`UG-GEM-<n>`** (ADR-0027). Een nummer wordt nooit hergebruikt.

**Tests.**

- *anker* — `tools/jelly-leon/upstream_gedrag_check.py` zoekt per regel het anker (Python-regex, `re.MULTILINE`;
  `|` schrijf je als `\x7c`) in het genoemde upstream-bestand van de huidige boom. Verdwijnt of verhuist het, dan faalt
  de controle in de CI-job *forkregels* en in de sync-job van `upstream-sync.yml` (JLT-67, EX48). De controle faalt
  ook als een `UG-…`-verwijzing in eigen documentatie of code niet in dit register staat, of als een regel naar een
  onbekende runtime-test verwijst.
- *runtime:&lt;naam&gt;* — `tools/jelly-leon/e2e/upstream_gedrag_runtime.py` start een wegwerpcontainer van
  `JL_RUNTIME_IMAGE` (stock 12.x op digest; in de sync de runtime van de nieuwe tag) en meet het gedrag. CI-job
  *stock-client-e2e* en de sync-job draaien hem.

Basis: upstream `jellyfin/jellyfin` v12.4 (`83d0d0e7f76e`), runtime `jellyfin/jellyfin:12.4@sha256:fea863d0…1771`.
Bronnen in de plankopie (`02_BOUWPLANNEN/`, `EXCEL_TAKEN.json`) noemen de geplande F-reeksen; dat zijn plantekst en geen
claims van deze repo, dus de verwijzingscontrole slaat die kopieën over.

| ID | Gedrag | Bestand | Anker | Gebruikt door | Test |
|---|---|---|---|---|---|
| UG-GEM-1 | Oude aanmelding (X-Emby-Authorization, X-Emby-Token, `?api_key=`) staat in 12.x uit; een migratie zet hem bij de upgrade uit | `Jellyfin.Server/Migrations/Routines/20260531160000_DisableLegacyAuthorization.cs` | `Configuration\.EnableLegacyAuthorization = false;` | BG-01, Δ-MG-AUTH, stock-client-smoketest, overnametool B03-015, JLT-63 (derden-client) | anker + runtime:legacy_auth_uit |
| UG-GEM-2 | Statische stream-routes van Audio/Videos hebben geen `[Authorize]` op klasseniveau: wie een item-ID kent, streamt zonder token | `Jellyfin.Api/Controllers/AudioController.cs` | `(?<!\[Authorize\]\n)public class AudioController : BaseJellyfinApiController` | INVENTARIS §7, B03-010 (vervolg streamroutes), ADR-0009 | anker + runtime:stream_zonder_token |
| UG-GEM-3 | HLS-playlists (`master.m3u8`, `main.m3u8`, …) staan niet meer in de OpenAPI (`IgnoreApi`), maar de routes bestaan en vragen aanmelding | `Jellyfin.Api/Controllers/DynamicHlsController.cs` | `\[Route\(""\)\]\n\[Authorize\]\n\[ApiExplorerSettings\(IgnoreApi = true\)\]\npublic class DynamicHlsController` | OpenAPI-upgraderapport (B03-014), transcode in JLT-63, MediaGuard-afspeeltest | anker + runtime:hls_verborgen_maar_actief |
| UG-GEM-4 | Segmenttypen ongewijzigd (Unknown, Commercial, Preview, Recap, Outro, Intro); MediaSegments-REST is alleen GET | `src/Jellyfin.Database/Jellyfin.Database.Implementations/Enums/MediaSegmentType.cs` | `public enum MediaSegmentType\s*\{` | F6 (geen nieuw type, eigen opslag), B03-017 | anker + runtime:mediasegmenten_alleen_lezen |
| UG-GEM-5 | SyncPlay-groepswacht 30 s; 22 SyncPlay-routes | `Emby.Server.Implementations/SyncPlay/Group.cs` | `internal const long DefaultGroupWaitTimeout = 30000;` | F1 (decorator, haperbeleid) | anker + runtime:syncplay_routes |
| UG-GEM-6 | Hardwareversnelling staat standaard uit (`none` = 0) | `MediaBrowser.Model/Entities/HardwareAccelerationType.cs` | `public enum HardwareAccelerationType\s*\{[^}]*?none = 0,` | F5 hardwareversnelling-assistent (B03-062), manifest (GPU optioneel) | anker + runtime:hardwareversnelling_standaard_uit |
| UG-GEM-7 | Elke plugin laadt in een eigen `PluginLoadContext` | `Emby.Server.Implementations/Plugins/PluginManager.cs` | `var assemblyLoadContext = new PluginLoadContext\(plugin\.Path\);` | B03-017 (één plugin met modules, ADR-0016) | anker |
| UG-GEM-8 | Een ABI-breuk (`TypeLoadException`) zet een plugin op NotSupported in plaats van de server te laten falen | `Emby.Server.Implementations/Plugins/PluginManager.cs` | `when \(ex is TypeLoadException or ReflectionTypeLoadException\)[\s\S]{0,600}?ChangePluginState\(plugin, PluginStatus\.NotSupported\);` | B03-019 ABI-test per sync, `GET /media/v1/version` | anker |
| UG-GEM-9 | Een gewijzigde bestandstijd (mtime) wist de geëxtraheerde gegevens van een video, o.a. mediasegmenten | `MediaBrowser.Providers/Manager/MetadataService.cs` | `File changed, pruning extracted data: \{Path\}[\s\S]{0,200}?DeleteExternalItemDataAsync\(video` | F6 (segmenten in eigen opslag, gerichte publicatie), B03-018 | anker |
| UG-GEM-10 | `forceOverwrite` wist alle segmenten van een item, ook die van andere providers | `Jellyfin.Server.Implementations/MediaSegments/MediaSegmentManager.cs` | `if \(forceOverwrite\)\s*\{[\s\S]{0,200}?db\.MediaSegments\.Where\(e => e\.ItemId\.Equals\(baseItem\.Id\)\)\.ExecuteDeleteAsync` | F6 (nooit forceOverwrite op andermans segmenten) | anker |
| UG-GEM-11 | Extensiepunt voor lokale similar-providers | `MediaBrowser.Controller/Library/ILocalSimilarItemsProvider.cs` | `public interface ILocalSimilarItemsProvider : ISimilarItemsProvider` | F2 (UG-F2-1…8 volgen bij de bouw van F2) | anker |
| UG-GEM-12 | Vóór een databasemigratie maakt 12.x zelf een kopie en zet die bij een fout terug; de back-up-API neemt de database niet mee (modelpariteit) | `Jellyfin.Server/Migrations/JellyfinMigrationService.cs` | `Database = false // database backups are explicitly handled by the provider itself as the backup service requires parity with the current model` | B03-013/014/015: terugzetten = snapshot + vorige image samen; downgradeweigering in het entrypoint | anker |

Regels voor dit register:

- Elk upstream-gedrag waarop fork-eigen code, een plandeel of een test steunt, krijgt hier eerst een regel met een
  test; zonder test geen regel en geen verwijzing.
- Een gefaalde regel na een upstream-sync betekent: eerst het gedrag opnieuw beoordelen (en zo nodig de module of
  haak aanpassen), dan pas het anker of de test — nooit alleen "groen maken".
- Gemeten gedrag dat (nog) door geen code wordt gebruikt, staat in de compat-rooktest of de matrix
  (`CLIENT_COMPAT_MATRIX.md`), niet hier.
