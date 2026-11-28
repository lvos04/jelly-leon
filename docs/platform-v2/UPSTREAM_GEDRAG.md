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
  *stock-client-e2e* en de sync-job draaien hem. Voor F2 start `e2e/similar_proef.py` stock en de plugin op
  kopieën van dezelfde synthetische bibliotheek. De sync gebruikt de digest van de nieuwe tag. De expliciete
  proefbouw registreert de aanroepteller, foutinjectie en gebeurteniswaarnemer uitsluitend op de testserver.

Basis: upstream `jellyfin/jellyfin` v12.4 (`83d0d0e7f76e`), runtime `jellyfin/jellyfin:12.4@sha256:fea863d0…1771`.
Bronnen in de plankopie (`02_BOUWPLANNEN/`, `EXCEL_TAKEN.json`) noemen de geplande F-reeksen; dat zijn plantekst en geen
claims van deze repo, dus de verwijzingscontrole slaat die kopieën over.

| ID | Gedrag | Bestand | Anker | Gebruikt door | Test |
|---|---|---|---|---|---|
| UG-F1-1 | Na de hostregistratie kan de plugin de SyncPlay-singleton omhullen. De draaiende server meldt met Watch Together aan `decorator_active=true` | `Emby.Server.Implementations/ApplicationHost.cs` | `AddSingleton<ISyncPlayManager, SyncPlayManager>\(\)` | B03-021, WT-1 | anker + runtime:watch_decorator |
| UG-GEM-1 | Bij uitgeschakelde legacy-auth geeft `/Users/Me` HTTP 401 voor X-Emby-Authorization, X-Emby-Token, X-MediaBrowser-Token en `?api_key=`. Aanmelden met X-Emby-Authorization geeft HTTP 400. De migratie zet legacy-auth uit | `Jellyfin.Server/Migrations/Routines/20260531160000_DisableLegacyAuthorization.cs` | `Configuration\.EnableLegacyAuthorization = false;` | BG-01, Δ-MG-AUTH, stock-client-smoketest, overnametool B03-015, JLT-63 (derden-client) | anker + runtime:legacy_auth_uit |
| UG-GEM-2 | Statische streamroutes van Audio/Videos hebben geen `[Authorize]` op klasseniveau. De rooktest leest met `?static=true` audiobytes zonder token | `Jellyfin.Api/Controllers/AudioController.cs` | `(?<!\[Authorize\]\n)public class AudioController : BaseJellyfinApiController` | INVENTARIS §7, B03-010 (vervolg streamroutes), ADR-0009 | anker + runtime:stream_zonder_token |
| UG-GEM-3 | HLS-playlists (`master.m3u8`, `main.m3u8`, …) staan niet meer in de OpenAPI (`IgnoreApi`), maar de routes bestaan en vragen aanmelding | `Jellyfin.Api/Controllers/DynamicHlsController.cs` | `\[Route\(""\)\]\n\[Authorize\]\n\[ApiExplorerSettings\(IgnoreApi = true\)\]\npublic class DynamicHlsController` | OpenAPI-upgraderapport (B03-014), transcode in JLT-63, MediaGuard-afspeeltest | anker + runtime:hls_verborgen_maar_actief |
| UG-GEM-4 | Segmenttypen ongewijzigd (Unknown, Commercial, Preview, Recap, Outro, Intro); MediaSegments-REST is alleen GET | `src/Jellyfin.Database/Jellyfin.Database.Implementations/Enums/MediaSegmentType.cs` | `public enum MediaSegmentType\s*\{` | F6 (geen nieuw type, eigen opslag), B03-017 | anker + runtime:mediasegmenten_alleen_lezen |
| UG-GEM-5 | SyncPlay-groepswacht 30 s; 22 SyncPlay-routes | `Emby.Server.Implementations/SyncPlay/Group.cs` | `internal const long DefaultGroupWaitTimeout = 30000;` | F1 (decorator, haperbeleid) | anker + runtime:syncplay_routes |
| UG-GEM-6 | Hardwareversnelling staat standaard uit (`none` = 0) | `MediaBrowser.Model/Entities/HardwareAccelerationType.cs` | `public enum HardwareAccelerationType\s*\{[^}]*?none = 0,` | F5 hardwareversnelling-assistent (B03-062), manifest (GPU optioneel) | anker + runtime:hardwareversnelling_standaard_uit |
| UG-GEM-7 | Elke plugin laadt in een eigen `PluginLoadContext` | `Emby.Server.Implementations/Plugins/PluginManager.cs` | `var assemblyLoadContext = new PluginLoadContext\(plugin\.Path\);` | B03-017 (één plugin met modules, ADR-0016) | anker |
| UG-GEM-8 | Een ABI-breuk (`TypeLoadException`) zet een plugin op NotSupported in plaats van de server te laten falen | `Emby.Server.Implementations/Plugins/PluginManager.cs` | `when \(ex is TypeLoadException or ReflectionTypeLoadException\)[\s\S]{0,600}?ChangePluginState\(plugin, PluginStatus\.NotSupported\);` | B03-019 ABI-test per sync, `GET /media/v1/version` | anker |
| UG-GEM-9 | Een gewijzigde bestandstijd (mtime) wist de geëxtraheerde gegevens van een video, o.a. mediasegmenten | `MediaBrowser.Providers/Manager/MetadataService.cs` | `File changed, pruning extracted data: \{Path\}[\s\S]{0,200}?DeleteExternalItemDataAsync\(video` | F6 (segmenten in eigen opslag, gerichte publicatie), B03-018 | anker |
| UG-GEM-10 | `forceOverwrite` wist alle segmenten van een item, ook die van andere providers | `Jellyfin.Server.Implementations/MediaSegments/MediaSegmentManager.cs` | `if \(forceOverwrite\)\s*\{[\s\S]{0,200}?db\.MediaSegments\.Where\(e => e\.ItemId\.Equals\(baseItem\.Id\)\)\.ExecuteDeleteAsync` | F6 (nooit forceOverwrite op andermans segmenten) | anker |
| UG-GEM-11 | Extensiepunt voor lokale similar-providers | `MediaBrowser.Controller/Library/ILocalSimilarItemsProvider.cs` | `public interface ILocalSimilarItemsProvider : ISimilarItemsProvider` | F2 (de providers voor films en series) | anker |
| UG-GEM-12 | Vóór een databasemigratie maakt 12.x zelf een kopie en zet die bij een fout terug; de back-up-API neemt de database niet mee (modelpariteit) | `Jellyfin.Server/Migrations/JellyfinMigrationService.cs` | `Database = false // database backups are explicitly handled by the provider itself as the backup service requires parity with the current model` | B03-013/014/015: terugzetten = snapshot + vorige image samen; downgradeweigering in het entrypoint | anker |
| UG-GEM-13 | PlaybackInfo zonder `MediaSourceId` en `AudioStreamIndex` kan Direct Play melden voor een film waarvoor expliciete selectie van het AC3-spoor transcode vereist. De proef gebruikt een film met AC3 en AAC en een profiel dat alleen AAC direct afspeelt | `Jellyfin.Api/Helpers/MediaInfoHelper.cs` | `options\.MediaSourceId = mediaSourceId;\s+options\.AudioStreamIndex = audioStreamIndex;` | B03-016 (PlaybackInfo zoals de webclient), JLT-63 | anker + runtime:playbackinfo_zonder_spoorselectie |
| UG-GEM-14 | De server zet de sessiesleutel als `ApiKey` in `TranscodingUrl`. De compat-proeven maskeren deze waarde vóór vergelijking, loguitvoer en rapportage | `MediaBrowser.Model/Dlna/StreamInfo.cs` | `sb\.Append\("&ApiKey="\);\s+sb\.Append\(accessToken\);` | B03-019 (compat-api en runtimerapport), JLT-64 | anker + runtime:transcode_sleutel_gemaskeerd |
| UG-F2-1 | De ingestelde volgorde per type gaat voor de lijst met aanbieders. Lokale aanbieders doen altijd mee tot de limiet | `Emby.Server.Implementations/Library/SimilarItems/SimilarItemsManager.cs` | `typeOptions\?\.SimilarItemProviderOrder is \{ Length: > 0 \} order\s*\? order\s*: typeOptions\?\.SimilarItemProviders` | F2 Meer zoals dit | anker + runtime:similar_volgorde |
| UG-F2-2 | Zonder volgorde bepaalt de exportvolgorde welke lokale provider eerst aan bod komt. De plugin controleert de bibliotheekkeuze vóór de metadatalezing. Bij een volle stockuitkomst blijft die lezing achterwege | `Emby.Server.Implementations/ApplicationHost.cs` | `AddParts\(GetExports<ISimilarItemsProvider>\(\)\)` | F2 standaardgedrag | anker + runtime:similar_exportvolgorde |
| UG-F2-3 | Alleen externe providers gebruiken de itemcache. Dezelfde lokale bron wordt per verzoek opnieuw opgevraagd | `Emby.Server.Implementations/Library/SimilarItems/SimilarItemsManager.cs` | `var cachedReferences = await TryReadSimilarItemsCacheAsync\(cachePath, cancellationToken\)` | F2 profielen | anker + runtime:similar_zonder_cache |
| UG-F2-4 | Movies/Recommendations gebruikt de eerste lokale batchprovider | `Emby.Server.Implementations/Library/SimilarItems/SimilarItemsManager.cs` | `\.OfType<IBatchLocalSimilarItemsProvider>\(\)\s*\.FirstOrDefault\(\)` | F2 stock-aanbevelingen | anker + runtime:similar_batch |
| UG-F2-5 | De lokale Similar-query krijgt de gebruiker van het verzoek mee | `Emby.Server.Implementations/Library/SimilarItems/SimilarItemsManager.cs` | `if \(provider is ILocalSimilarItemsProvider localProvider\)\s*\{\s*var query = new SimilarItemsQuery\s*\{\s*User = user,` | F2 bibliotheektoegang en gezien-filter | anker + runtime:similar_gebruiker |
| UG-F2-6 | De webclient uit WebPath gebruikt in Modern en Legacy dezelfde home-controller en loadSections met vier argumenten | `Jellyfin.Server/Startup.cs` | `new PhysicalFileProvider\(_serverConfigurationManager.ApplicationPaths.WebPath\)` | F2 startscherm, broncontrole op de webpin en browserproef in beide layouts | anker + runtime:similar_home |
| UG-F2-7 | SaveUserData meldt UserDataSaved met de reden van de wijziging | `Emby.Server.Implementations/Library/UserDataManager.cs` | `UserDataSaved\?\.Invoke\(this, new UserDataSaveEventArgs[\s\S]{0,200}?SaveReason = reason` | F2 invalidatie | anker + runtime:similar_bewaarreden |
| UG-F2-8 | Een bekende homesection wordt als enum opgeslagen. Een onbekende waarde valt terug op de standaardsectie | `Jellyfin.Api/Controllers/DisplayPreferencesController.cs` | `Enum.TryParse<HomeSectionType>\(displayPreferences.CustomPrefs\[key\], true, out var type\)` | F2 webhaak, herbeoordelen zodra een vrije extensiewaarde terugkomt | anker + runtime:similar_homevoorkeur |

Regels voor dit register:

- Elk upstream-gedrag waarop fork-eigen code, een plandeel of een test steunt, krijgt hier eerst een regel met een
  test; zonder test geen regel en geen verwijzing.
- Een gefaalde regel na een upstream-sync betekent: eerst het gedrag opnieuw beoordelen (en zo nodig de module of
  haak aanpassen), dan pas het anker of de test — nooit alleen "groen maken".
- Aanvullende waarnemingen zonder afhankelijkheid van het harnas of de fork staan in de clientmatrix (`CLIENT_COMPAT_MATRIX.md`).
