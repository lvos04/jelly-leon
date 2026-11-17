# ADR-0032 — B03-017: bouwwachters — analyzer voor verboden API's en generator voor de web-`config.json`

- **Status:** Aanvaard (2026-11-11). Uitvoering van ADR-0016 (één plugin met modules) en ADR-0019 (haken en generator).
  Bijgewerkt 2026-11-16 na de review van golf 1 (S-G1-17, bevindingen R-HARDE-EIS-1, -2 en -4): meer bewaakte
  servertypen, JL0003 ook op samengestelde tekst, een padgrens in `JlDatabase` en de kop "Grenzen" gelijk aan de code.
  Bijgewerkt 2026-11-17 na de herreview (S-G1-17 herstelronde 2, R-HARDE-EIS-1 rest, -5, -6 en -7): het taakobject van
  een servertaak, leesleden die kanaalitems verversen of wissen, JL0003 op omzettingen, UTF-8-tekst en uitlijning, en een
  padgrens die symbolische koppelingen volgt.
  Bijgewerkt 2026-11-17 na herreview 2 (S-G1-17 herstelronde 3, R-HARDE-EIS-8 en -9 en de vervolgpunten): JL0003 ook op
  een optelling van UTF-8-teksten, bij een bewaakte interface alleen de leden die de interface implementeren,
  `Folder.GetChildren` en `GetRecursiveChildren` verboden (de grens "basistype" is weg) en de bestanden naast een
  database ook naast het echte pad gecontroleerd.
  Bijgewerkt 2026-11-17 na herreview 3 (S-G1-17 herstelronde 4, R-HARDE-EIS-10 en -11): JL0003 ook op de databasedienst
  van de server (`IJellyfinDatabaseProvider`) en de twee typen die een context gebruiken, ook als typeargument of via
  `var`; onder de interfaceregel telt ook een override van de implementatie.
  Bijgewerkt 2026-11-17 na herreview 4 (S-G1-17 herstelronde 5, R-HARDE-EIS-12): databasetoegang is nu generiek geregeld.
  Buiten `Core.Storage` is elke operatie die een databaseverbinding of -bron oplevert of gebruikt JL0002 (ook in
  `Core.Secrets`), de niet-generieke `DbContextOptions` van de server resolven of injecteren is JL0003, en een verbinding
  van `JlDatabase` kan geen tweede database koppelen. De volledige lijst van gevonden wegen en de grenzen staan onder
  "Databasetoegang (JL0002)".
- **Werkpakket:** B03-017; raakt de HARDE EIS (kijkgeschiedenis, bibliotheek, metadata en gebruikersgegevens blijven
  behouden) en JLT-65.
- **Bewijs:** `plugins/JellyLeon/tests/…/Analyzer/VerbodenApiAnalyzerTests.cs` (xunit), de proefassembly
  `plugins/JellyLeon/analyzers/Jellyfin.Plugin.JellyLeon.VerbodenProef` met `tools/jelly-leon/analyzer_proef.py` (een
  echte build die moet falen) en `tools/jelly-leon/tests/test_web_config.py`. Alles op de ontwikkelmachine en in CI.

## Context

Het plan eist "een analyzer voor verboden API's per namespace met een witte lijst van uitzonderingsklassen" en "een
testassembly met elke verboden aanroep moet de build laten falen". De modules van latere golven (ondertitels,
aanbevelingen, segmenten) werken dicht tegen de bibliotheek aan; één vergeten `UpdateItemAsync` of `SaveUserData` zou
gegevens van de gebruiker wijzigen zonder officiële route en zonder back-up. Een afspraak in een document houdt dat
niet tegen; een bouwfout wel.

Daarnaast vraagt het plan "één generator" voor de `config.json` van de webclient in de image, met een controle dat
geen upstream-plugin ontbreekt.

## Besluit

### 1. Eén analyzer, vier regels, elke overtreding een bouwfout

Project `plugins/JellyLeon/analyzers/Jellyfin.Plugin.JellyLeon.Analyzers` (netstandard2.0, alleen bouwhulp). De plugin
verwijst ernaar als analyzer; de assembly gaat niet mee in de plugin of de image. De regels zijn `Error` en niet
configureerbaar (`NotConfigurable`): een `.editorconfig`, `NoWarn` of `#pragma` zet ze niet uit.

| Regel | Verboden | Waar wel |
|---|---|---|
| **JL0001** | schrijvende server-API. Per interface geldt "alles verboden behalve lezen" (voorvoegsels `Get`, `Find`, `Query`, `Is`, `Has`, `Can`, `To`, alleen als heel woord: `CanRefresh` is lezen, `CancelTimer` niet): `ILibraryManager`, `IItemRepository`, `IItemPersistenceService`, `IPlaylistManager`, `ICollectionManager` (ook `GetCollectionsFolder`, want die kan aanmaken), `IUserManager`, `IDeviceManager`, `IUserDataManager`, `IProviderManager`, `ISubtitleManager`, `IMediaSegmentManager`, `ISessionManager`, `IServerConfigurationManager`/`IConfigurationManager`, plus de diensten uit "Wat JL0001 bewaakt" hieronder; op `BaseItem` en afgeleiden de wijzigende methoden (`Update*`, `Delete*`, `Refresh*`, `Save*`, `Add*`, `Remove*`, `Set*`, `Swap*`, `Changed*`, `Mark*`, `Validate*`). Ook het schrijven van een eigenschap (toewijzing, `++`, `--`) op een bewaakt type telt: `item.Name = …` op een `BaseItem` is JL0001. Bij een bewaakte interface tellen van een eigen klasse die de interface implementeert alleen de leden die een lid van die interface implementeren (zie "Wat JL0001 bewaakt") | bibliotheek, opslag van items, afspeellijsten, collecties, gebruikers, apparaten en alle diensten uit "Wat JL0001 bewaakt": **nergens**. De overige alleen in één met naam genoemde klasse per API (witte lijst) |
| **JL0002** | bestanden schrijven, verplaatsen of verwijderen: `System.IO.File` en `Directory` (alles behalve lezen), wijzigende methoden en eigenschappen van `FileInfo`/`DirectoryInfo`, `new FileStream`, `new StreamWriter(pad)`, wijzigende methoden van `IFileSystem`. Daarnaast **databasetoegang**: elke operatie die een databaseverbinding of -bron oplevert of gebruikt (`new SqliteConnection`, `SqliteFactory`, `DbProviderFactory`/`DbProviderFactories`, `DbDataSource`, `IDbConnection`, SQLitePCL en de bouwers van Entity Framework Core; zie "Databasetoegang (JL0002)") | bestanden: alleen in `Core.Storage` en `Core.Secrets` (die bewaken de schrijfgrens `<DataPath>/jelly-leon/**` en `/cache/jelly-leon/**` zelf); `File`/`Directory`/`IFileSystem`-methoden daarnaast in één genoemde klasse per API. Databasetoegang: **alleen in `Core.Storage`** (`JlDatabase`), geen uitzondering mogelijk |
| **JL0003** | de database van de server: elk gebruik van de typenaam `JellyfinDbContext`, `IJellyfinDatabaseProvider` (een dienst in de container van de server: `DbContextFactory` geeft een context, `PurgeDatabase` wist elke tabel en `RestoreBackupFast` overschrijft `jellyfin.db`), `IEntityFrameworkCoreLockingBehavior` of `IItemQueryHelpers` (die twee nemen een context als argument), en van een type dat er een implementeert of ervan afleidt. Elk gebruik is: een parameter, een veld, een lokale variabele, `GetService<T>`, `typeof`, een alias, een typeargument (`IDbContextFactory<JellyfinDbContext>`), een elementtype en `var` dat naar zo'n type verwijst (`var f = provider.DbContextFactory`). Ook de niet-generieke `Microsoft.EntityFrameworkCore.DbContextOptions` (precies dat type, niet een afgeleid type) is JL0003 bij elk gebruik van de naam: na `AddPooledDbContextFactory<JellyfinDbContext>` staat hij in de container van de server en draagt hij de verbindingstekst van `jellyfin.db` (resolven met `GetRequiredService<DbContextOptions>()`, injecteren als parameter, `typeof`). Zonder die naam krijgt plugincode de dienst niet: de container geeft hem alleen op type, en volgens een scan van de plugin-ABI is `IJellyfinDatabaseProvider.DbContextFactory` het enige publieke lid dat een context of een fabriek ervan teruggeeft (herhaald in herstelronde 5 met een scan over alle compile-assets: zie "Databasetoegang (JL0002)"). Verder elke tekst met `jellyfin.db` of `library.db` (hoofdletters tellen niet). "Tekst" is elke letterlijke tekst, elke UTF-8-tekst (`"…"u8`), elke constante (ook uit een andere assembly, en de constante waarde van een omzetting: `(char)46` en `(char)0x2E` zijn een punt, `(int)'.'` is geen tekst) en elke samenstelling met `+` of `$"…"`, ook een optelling van UTF-8-teksten (`"jellyfin"u8 + ".db"u8`): de bekende stukken die direct op elkaar volgen worden aaneengeschreven (`"jellyfin" + ".db"`, `Naam + ".db"` met een constante, `$"{map}/jellyfin.d" + "b"`, `$"{map}/{Naam}.db"`); een uitlijning `{x,n}` met een bekend stuk vult met spaties aan tot \|n\| tekens (n positief ervoor, negatief erna; een kortere n vult niets aan, dus `$"jellyfin{".db",3}"` is JL0003); een stuk dat pas bij het draaien bekend is, breekt de reeks | **nergens**, geen uitzondering mogelijk |
| **JL0004** | processen starten (`Process.Start`, `new Process`, `new ProcessStartInfo`) | alleen in `Core.Werker` (de werkerbewaker van B03-018); geen uitzondering per klasse |
| **JL0009** | een ongeldige regel in de witte lijst | — |

Verboden is "aanroepen én ernaar verwijzen": een methodegroep (`Action<string> f = File.Delete`) telt als aanroep.
Gegenereerde code wordt ook gecontroleerd.

#### Wat JL0001 bewaakt

Naast de typen hierboven bewaakt JL0001 elke dienst uit de plugin-ABI (`Jellyfin.Controller`, `Jellyfin.Model`) die in
v12.4 zelf in `jellyfin.db` schrijft. Gevonden door in de serverbron van de fork te zoeken naar `SaveChanges`,
`ExecuteDelete` en `ExecuteUpdate` en elke klasse met zo'n aanroep terug te leiden naar haar interface:
`IDisplayPreferencesManager` (ook `GetDisplayPreferences` en `GetItemDisplayPreferences`: die maken de rij aan als die
ontbreekt; `List…` is lezen), `IChapterRepository`, `IChapterManager` (`Supports` is lezen), `IMediaStreamRepository`,
`IMediaAttachmentRepository`, `IPeopleRepository`, `IKeyframeRepository`, `IKeyframeManager`, `ITrickplayManager`,
`ILinkedChildrenService`, `IExternalDataManager`, `IActivityManager`, `IAuthenticationManager` (API-sleutels) en
`IBackupService` (terugzetten overschrijft de hele database; `Enumerate…` is lezen).

Daarnaast de diensten die via een al bewaakte API de bibliotheek, metadata, gebruikers of instellingen wijzigen, of een
servertaak of verversing starten (gevonden door te zoeken naar aanroepen van de verboden leden in de serverbron):
`ITaskManager` (een taak als "kijkgegevens van ontbrekende items opruimen" starten), `ILibraryMonitor`,
`IMetadataService`, `IMediaSourceManager` (`GetPlaybackMediaSources` ververst met `allowMediaProbe` de metadata),
`ILyricManager` (`Search…` is lezen), `IChannelManager` (de `Get…`-leden die kanaalitems aanmaken of wissen staan met naam
bij de verboden leden), `ILiveTvManager`, `IGuideManager`, `IRecordingsManager`, `IListingsManager`,
`ITunerHostManager`, `IQuickConnect` (een aanmelding goedkeuren), `IAuthenticationProvider` en
`IPasswordResetProvider` (wachtwoorden) en `IEventManager` (een serverevent publiceren laat de server zelf schrijven,
bijvoorbeeld in het activiteitenlog). Voor geen van deze typen bestaat een uitzondering.

Een servertaak start ook via het taakobject zelf, niet alleen via `ITaskManager`: `ITaskManager.ScheduledTasks` en
`IApplicationHost.GetExports<IScheduledTask>()` geven dat object. Daarom zijn ook `IScheduledTask` (`ExecuteAsync`;
`GetDefaultTriggers` is lezen) en `IScheduledTaskWorker` (`ReloadTriggerEvents` en het zetten van `Triggers`, dat de
planning op schijf wijzigt) bewaakt, zonder uitzondering. Voorbeeld van wat dit tegenhoudt: `CleanupUserDataTask` wist
losgekoppelde kijkgegevens ouder dan 90 dagen en draait alleen als iemand hem start.

Bij een bewaakte interface tellen van een eigen klasse of struct die de interface implementeert alleen de leden die een
lid van die interface (of van een interface die ervan afgeleid is) implementeren (Roslyn
`FindImplementationForInterfaceMember`), onder de naam van dat interfacelid. Een eigen servertaak van de plugin (het
B03-plan wil een taak als ingang naar de batchplanner) mag dus eigen hulpmethoden en eigenschappen hebben; de eigen
`ExecuteAsync` aanroepen, ook via een methodeverwijzing, een afgeleide klasse of de interface, blijft JL0001 en de
melding noemt `IScheduledTask.ExecuteAsync`. Hetzelfde geldt voor de planning van een eigen werker (`Triggers` zetten,
`ReloadTriggerEvents`). Ook een lid dat die implementatie (herhaald) overschrijft, telt mee: `FindImplementationForInterfaceMember`
geeft bij een afgeleide klasse het virtuele lid van de basisklasse, en een `override ExecuteAsync` in een afgeleide klasse
aanroepen is daarom ook JL0001 (methoden, eigenschappen en events). Een met `new` verborgen lid overschrijft niets en telt
niet. Een aanroep via de interface zelf of een afgeleide interface telt zoals altijd. Voor de regels op
klassen (`BaseItem`, `Folder` en afgeleiden) verandert niets. Test:
`VerbodenApiAnalyzerTests.EigenServertaak_AlleenDeLedenVanDeInterfaceTellen`.

Kanaalitems: de `Get…`-leden van `IChannelManager` die kanaalitems aanmaken, verversen of de verdwenen items wissen
(waarbij de server de kijkgegevens van zo'n item verplaatst), zijn verboden. Hetzelfde geldt voor elk lid dat dat via
`IChannelManager` doet (in v12.4 nagelopen vanaf elke aanroep van `GetChannelItemsInternal`, `GetLatestChannelItemsInternal`
en `GetChannelsInternalAsync` in de serverbron): `ILiveTvManager.GetRecordingsAsync` (ververst de kanalen met het kenmerk
"Recordings") en `GetRecordingFoldersAsync` (maakt een ontbrekend kanaalitem aan), `IUserViewManager.GetLatestItems`
(ververst een kanaal als bovenliggend item) en op de items van de server zelf: `Folder.GetItems`, `GetItemList`,
`GetChildCount`, `GetRecursiveChildCount`, `GetChildren` en `GetRecursiveChildren`, `Season.GetEpisodes` en `GetChildren`, `Series.GetSeasonEpisodes`,
`UserView.GetChildren` en `GetRecursiveChildren` en `Playlist.GetChildren`, `GetRecursiveChildren` en
`GetPlaylistItems`. Op naam: ook een override in een afgeleid type is verboden, ook als die zelf geen kanaal raakt (bijvoorbeeld
`Series.GetChildCount`). De bibliotheek lezen kan via `ILibraryManager.GetItemList`/`GetItemsResult` (die vragen de
database rechtstreeks). `Folder.GetChildren` en `GetRecursiveChildren` zijn ook op een gewone map verboden: een variabele
van het basistype (`Folder f = seizoen; f.GetChildren(…)`) kan bij het draaien een `Season`, `UserView` of `Playlist`
zijn, en de plugin heeft voor deze leden geen gebruiker.

Van de bewaakte serverdiensten gebruikt de plugin op 2026-11-16 alleen `ILibraryManager` (`GetVirtualFolders`) en
`ISessionManager` (de events `PlaybackStart` en `PlaybackStopped` en de lijst `Sessions`); de plugin bouwt zonder
één JL-fout.

#### Databasetoegang (JL0002)

Elke verbinding met een SQLite-bestand loopt via `JlDatabase` in `Core.Storage`: alleen daar gelden de padgrens
(`JlPaths.MagSchrijven`, ook na het volgen van koppelingen) en het verbod op koppelen. Buiten `Core.Storage` (dus ook in
`Core.Secrets`, Core en de modules) is daarom **elke operatie die een databaseverbinding of -bron oplevert of gebruikt**
JL0002, zonder uitzondering. Geen lijst van routes maar een regel op het type, zodat een nieuwe route er vanzelf onder valt:

- **Databasetype** = een verbinding of bron (`System.Data.Common.DbConnection`, `System.Data.IDbConnection`,
  `DbDataSource`, `DbProviderFactory`, `DbProviderFactories`, en elk type dat ervan afleidt of ze implementeert) en elk
  type uit de assemblies Microsoft.Data.Sqlite, SQLitePCLRaw.* en Microsoft.EntityFrameworkCore* (ook als basistype,
  interface of beperking van een typeparameter).
- **Verboden operatie**: een lid van een databasetype aanroepen, lezen, zetten of als methodegroep nemen (ook statisch,
  zoals `SqliteFactory.Instance`, en een extensiemethode uit die assemblies, zoals `GetDbConnection` of `AddDbContext`);
  een aanroep of een lid van buiten de plugin waarvan het resultaat een databasetype is of bevat (ook `Task<…>`, een
  typeargument, een `out`-parameter of de terugkeer van een gedelegeerde: `GetService<DbProviderFactory>()`,
  `Activator.CreateInstance<SqliteConnection>()`, `DbCommand.Connection`); een databasetype aanmaken (`new`); `typeof`; en
  een omzetting, `as`, `is` of patroon naar een databasetype (vanuit `object` of een ander type, ook een expliciete
  omzetting tussen twee databasetypen).
- **Toegestaan**: een verbinding die als parameter binnenkomt doorgeven (`JlDatabase.Met(v => JlDatabase.Voer(v, …))`, een
  eigen methode met een parameter `SqliteConnection`), een databasetype als parameter- of veldtype, en een impliciete
  omzetting tussen twee databasetypen. Een verbinding uit de terugroep halen (`Met(v => v)`) is wel JL0002: het resultaat
  van de aanroep is dan een verbinding.
- Per keten één melding: is de ontvanger zelf al een melding (`SqliteFactory.Instance.CreateConnection()`), dan volgt er
  geen tweede. Wat de naam van de serverdatabase noemt of draagt, meldt JL0003 (zie hieronder); daarvoor geeft deze regel
  geen tweede melding.

De regel kwam uit een zoektocht naar alle wegen om vanuit plugincode een verbinding met een SQLite-bestand of de
serverdatabase te krijgen. Bron: de compile-assets van de plugin (`project.assets.json`: Jellyfin.Controller, .Model,
.Common, .Data, .Database.Implementations, .Extensions, .Naming, .MediaEncoding.Keyframes, Microsoft.Data.Sqlite 10.0.14,
SQLitePCLRaw.core 2.1.13, Microsoft.EntityFrameworkCore, .Relational en .Abstractions 10.0.14, Polly, ICU4N, J2N, NEbml,
Diacritics) plus de gedeelde frameworks Microsoft.NETCore.App en Microsoft.AspNetCore.App: 333 assemblies, 11081 publieke
typen, gescand op elk lid dat een databasetype noemt (terugkeer, eigenschap, veld, parameter, `out`, typeargument,
gedelegeerde) en op namen met sqlite, connection, database, dbcontext, datasource of sql. Gevonden wegen en wat ze dekt:

| Weg | Voorbeeld | Gedekt door |
|---|---|---|
| Microsoft.Data.Sqlite | `new SqliteConnection(cs)`, `SqliteFactory.Instance.CreateConnection()` / `CreateDataSource(cs)` | JL0002 |
| System.Data.Common | `DbProviderFactories.GetFactory(…)` / `RegisterFactory`, `DbProviderFactory.CreateConnection`, `DbDataSource.CreateConnection` / `OpenConnectionAsync`, `DbCommand`/`DbBatch`/`DbTransaction`/`IDbCommand.Connection` | JL0002 |
| Een gekregen verbinding ombuigen | `ConnectionString` zetten, `Open`, `ChangeDatabase`, `BackupDatabase` (kopie naar een andere verbinding), `Handle`, `EnableExtensions`/`LoadExtension` (`Clone` bestaat niet in Microsoft.Data.Sqlite 10.0) | JL0002 |
| SQL op de eigen verbinding | `ATTACH DATABASE '<pad>'`, `VACUUM INTO '<pad>'`, `load_extension(…)`, met een pad dat pas bij het draaien ontstaat | `JlDatabase` zet `SQLITE_LIMIT_ATTACHED` op 0 via SQLitePCLRaw.core (2.1.13, dezelfde versie als in de stock-image 12.4, nagelezen in `jellyfin.deps.json`; ook `VACUUM INTO` koppelt intern) en leest de grens terug; `load_extension` geeft in SQLite al `not authorized` (gemeten). Test `OpslagTests.Database_EigenVerbindingKoppeltGeenAnderDatabasebestand` |
| SQLitePCLRaw.core | `raw.sqlite3_open(pad, out db)`, `sqlite3_open_v2`, `sqlite3_backup_init`, `sqlite3_limit` | JL0002 |
| Entity Framework Core | `new DbContextOptionsBuilder()`, `new DbContextOptions<T>(…)`, `opties.Extensions` / `FindExtension`, `RelationalOptionsExtension.Extract(opties).ConnectionString` / `.Connection`, `new DbContext(opties)`, `ctx.Database.GetDbConnection()`, `ExecuteSqlRaw`, `AddDbContext`/`AddPooledDbContextFactory`, een `DbConnectionInterceptor` registreren (die krijgt de verbinding van de server); `UseSqlite` (Microsoft.EntityFrameworkCore.Sqlite staat in de server, maar is geen compile-asset; komt hij erbij, dan valt hij onder dezelfde assemblyregel) | JL0002 |
| De opties van de server | `GetRequiredService<DbContextOptions>()`, een parameter `DbContextOptions`, `typeof(DbContextOptions)`; `IDbContextOptions` | JL0003; `IDbContextOptions` JL0002 |
| De databasedienst van de server | `JellyfinDbContext`, `IJellyfinDatabaseProvider` (`DbContextFactory`, `PurgeDatabase`, `RestoreBackupFast`), `IEntityFrameworkCoreLockingBehavior`, `IItemQueryHelpers`, `DescendantQueryHelper` en `JellyfinQueryHelperExtensions` (vragen een context) | JL0003 op de naam |
| Generiek ophalen | `GetService<T>`, `GetRequiredService<T>`, `IApplicationHost.Resolve<T>`/`GetExports<T>`, `ActivatorUtilities.CreateInstance<T>`, `Activator.CreateInstance<T>` met een databasetype | JL0002 (of JL0003 bij een servertype) |
| Als object ophalen | `GetService(typeof(…))`, `ServiceDescriptor.ImplementationInstance`, `Activator.CreateInstance(Type)` | `typeof` en de omzetting naar een databasetype zijn JL0002; zonder die twee blijft het een object |
| Bestanden van de server | `jellyfin.db` kopiëren, verplaatsen of overschrijven | JL0002 (bestanden), JL0003 (de naam) |
| Teksten uit de configuratie | `IConfiguration.GetConnectionString`, `CustomDatabaseOptions.ConnectionString` | geen verbinding zonder een van de wegen hierboven |

Buiten de databasetypen noemt alleen Jellyfin.Database.Implementations/MediaBrowser.Controller (de typen van JL0003) en
System.Data.Common (`…Connection` van een opdracht of transactie) een databasetype; geen enkel lid van de plugin-ABI of van
ASP.NET Core geeft een verbinding terug of geeft er een aan een terugroep. Tests:
`VerbodenApiAnalyzerTests.DatabaseverbindingBuitenDeOpslag_ProevenH15EnH16_IsJL0002OfJL0003` (de vormen van proef H15 en
H16 van herreview 4), `.Databasetoegang_ElkeWegIsBuitenCoreStorageJL0002` (elke weg hierboven; dezelfde bron in
`Core.Storage` geeft niets, in `Core.Secrets` hetzelfde als in een module) en de proefregels in `VerbodenAanroepen.cs`.

### 2. Witte lijst: één API in één klasse

`JellyLeon.AnalyzerUitzonderingen.txt` naast het pluginproject, één regel per uitzondering:
`<regel-id> <Type.Methode> <volledige klassenaam>`. Geen jokertekens en geen namespaces; de klasse moet onder
`Jellyfin.Plugin.JellyLeon.Modules` liggen. Een regel die niet past (onbekende API, een API die nergens mag, een klasse
buiten de modules, een dubbele regel, een verkeerde vorm) is zelf een bouwfout en staat niets toe. Zo volgt de lijst de
tabel uit het plan: F3 krijgt straks precies `ResetPlaybackStreamSelections`/`SaveUserData` in `SelectionGuard`,
`QueueRefresh` in `PublishTransaction` en `File.Delete` in `Depublisher`; Quality krijgt niets.

**Stand golf 1: de lijst is leeg.** Kern, Devices en Quality bouwen zonder één uitzondering. Elke latere regel hoort
bij een taak uit het plan en een eigen ADR.

### 3. Drie soorten bewijs

1. **De plugin bouwt** met de analyzer aan: er staat geen verboden aanroep in.
2. **De proefassembly faalt**: `VerbodenAanroepen.cs` bevat 176 verboden aanroepen, elk gemarkeerd met
   `// VERWACHT: JLxxxx`, afgewisseld met toegestane leesaanroepen. `analyzer_proef.py` bouwt het project echt en eist
   dat precies de gemarkeerde regels die bouwfout geven, dat geen enkele andere regel een JL-fout geeft en dat de build
   om geen andere reden faalt. De proefassembly staat bewust niet in de solution.
3. **xunit** draait dezelfde bron door de analyzer en test de vaste namespaces, de witte lijst (ook lambda en geneste
   klasse), elke soort ongeldige regel en dat **elk bewaakt type in deze Jellyfin-versie bestaat**. Dat laatste is de
   wacht bij een upstream-sync: een hernoemde interface zou de regel anders stil uitschakelen.

### 4. Generator voor de web-`config.json`

`deploy/allinone/web-config.mjs` draait in de web-bouwstap van de image (Node is daar al aanwezig; de runtime-image
krijgt er niets bij). Invoer: de upstream-`src/config.json` en `deploy/allinone/web-config.jellyleon.json` met alleen
de eigen webplugins (`jellyLeon/<naam>/plugin`, bron onder `src/plugins/jellyLeon/` in jelly-leon-web). Regels:

- upstream-items worden nooit weggelaten, herschikt of overschreven; eigen plugins komen achteraan;
- het eigen bestand mag alleen `plugins` bevatten; een eigen plugin zonder bronbestand is een fout;
- **zonder eigen plugins is het resultaat byte-gelijk aan upstream** (alles uit = stock-gedrag);
- na het schrijven draait dezelfde generator met `--controleer` op het resultaat: geen upstream-plugin ontbreekt,
  volgorde gelijk, geen onbekende plugin, overige sleutels gelijk.

Stand golf 1: geen eigen webplugins; de `config.json` van de image is byte-gelijk aan upstream. De haakmodule
`src/jelly-leon/hooks` (`jlHook('naam', ctx)`) leeft in jelly-leon-web en is daar een eigen werkpakket.

## Grenzen (eerlijk)

- Een analyzer is **geen zandbak**. Reflectie, `dynamic`, eigen P/Invoke of een tweede assembly ziet hij niet. Voor
  databasetoegang betekent dat: een type uit een tekst (`Type.GetType("…SqliteConnection, …")`) met `Activator` of
  `GetService(Type)` geeft alleen een object; dat als verbinding gebruiken kan dan alleen via reflectie of `dynamic`, of
  eigen P/Invoke naar de SQLite-bibliotheek (`DllImport`, `NativeLibrary` met functiewijzers). Dat valt buiten de
  analyzer. Daarom
  blijven de andere lagen bestaan: de schrijfgrens in `Core.Storage` tijdens het draaien (`InternalWriteScope` voor
  bestanden en `JlDatabase` voor SQLite weigeren elk pad buiten `<DataPath>/jelly-leon/**`, `/cache/jelly-leon/**` en
  `/run/jelly-leon/**` (`JlPaths.MagSchrijven`), voordat er iets geopend of aangemaakt is), de alleen-lezen mediamount,
  en JLT-65 (stock en fork naast elkaar; de 12.x-tabellen mogen alleen op de toegestane lijst afwijken).
- JL0003 op de databasedienst van de server werkt op de typenaam: de grens ligt waar de dienst de klasse binnenkomt
  (veld, parameter, `GetService<T>`). Regels die daarna een eenmaal gekregen object gebruiken zonder de naam te noemen
  (`_db.PurgeDatabase(…)`), geven zelf geen tweede melding. Gebruiken ze daarbij een lid van Entity Framework Core
  (`….CreateDbContext().Database.ExecuteSqlRaw(…)`, `SaveChanges`), dan is die regel sinds herstelronde 5 wel JL0002
  (databasetoegang). Wie de dienst zonder de naam ophaalt (reflectie,
  `GetService(Type)` met een type uit een tekst, `dynamic`), valt onder de eerste grens hierboven; de padgrens van
  `JlDatabase` helpt daar niet, want de server opent zijn eigen database. Test:
  `VerbodenApiAnalyzerTests.DatabasedienstVanDeServer_ElkGebruikVanDeTypenaamIsJL0003` (de vorm van proef H12).
- De padgrens kijkt naar het pad zoals het er staat én naar het echte pad: elke symbolische koppeling (het bestand zelf
  en elke bovenliggende map, relatief of in een keten) wordt gevolgd zoals het besturingssysteem dat doet, en `..` geldt
  na het volgen. Een eigen map die zelf een koppeling is (bijvoorbeeld `<data>/jelly-leon` -> `<data>`) telt niet als
  eigen plek; een datamap van de server achter een gekoppelde map blijft wel bruikbaar. `JlDatabase` eist dit ook voor
  `-wal`, `-shm` en `-journal` (die schrijft SQLite ernaast), naast de opgegeven naam én naast het echte pad (SQLite zet
  ze naast het echte bestand: bij een koppeling `a.db` -> `b.db` naast `b.db`), en controleert het bij elke opening
  opnieuw (dan 503 `storage_unavailable`); `InternalWriteScope` ook voor het tijdelijke bestand `<doel>.tmp`. SQLite
  opent zelf geen naastbestand dat een symbolische koppeling is (fout 14); `OpslagTests.Sqlite_OpentGeenKoppelingAlsNaastbestand`
  bewaakt die aanname bij een upgrade van SQLite. Tests:
  `OpslagTests.Database_BuitenDeEigenMappenWordtGeweigerdZonderTeOpenen`,
  `.Database_SymbolischeKoppelingNaarBuitenWordtGeweigerdZonderTeOpenen`,
  `.Database_EigenMapAlsKoppelingWordtGeweigerd_DatamapAchterEenKoppelingWerkt`,
  `.Database_KoppelingNaHetAanmakenWordtBijHetOpenenGeweigerd`, `.Database_NaastbestandenNaastHetEchtePadWordenGecontroleerd`
  en `.Schrijfbereik_SymbolischeKoppelingNaarBuitenWordtGeweigerd`
  (jellyfin.db blijft byte-gelijk). Wat de padgrens niet ziet: een koppeling die precies tussen de controle en het
  openen ontstaat, en een harde koppeling (zelfde bestand onder twee namen). De plugin maakt zelf geen koppelingen en
  de entrypoint alleen mappen.
- JL0003 ziet een naam die pas bij het draaien ontstaat niet: een variabele, `string.Concat`, `StringBuilder`, een
  waarde uit de configuratie. Daarvoor is de padgrens van `JlDatabase` er; `jellyfin.db` en `library.db` liggen buiten
  de eigen mappen. Dat houdt alleen omdat elke verbinding via `JlDatabase` loopt: elke andere weg naar een verbinding is
  buiten `Core.Storage` JL0002 (zie "Databasetoegang (JL0002)"), en de verbinding van `JlDatabase` kan met SQL geen
  tweede database koppelen (`ATTACH`, `VACUUM INTO`). Code in `Core.Storage` zelf valt niet onder JL0002 en hoort daarom
  alleen `JlDatabase` en `InternalWriteScope` te bevatten.
- Hij bewaakt methoden **en** het schrijven van eigenschappen op elk bewaakt type: `item.Name = …` op een `BaseItem` is
  JL0001 (proefregels in `VerbodenAanroepen.cs`), omdat een `BaseItem` gedeeld is met de cache van de server en de
  server het item later zelf kan opslaan. Eigenschappen van **entiteiten** die een server-API teruggeeft (`User`,
  `UserItemData`, `DisplayPreferences`, de rijen in `BaseItem.UserData`) bewaakt hij niet. Een `User` uit
  `GetUserById` maakt de server per aanroep nieuw; daar blijft een wijziging in het geheugen. `UserItemData` uit de
  cache van `IUserDataManager` en de rijen in `BaseItem.UserData` zijn wel gedeeld met de server; of een wijziging
  daarin via een latere opslag door de server zelf in `jellyfin.db` belandt, is niet gemeten. De plugin zet geen
  eigenschap op zulke objecten (Kern, Devices, Quality); tot een besluit over een regel hiervoor vangt alleen JLT-65
  het.
- Niet bewaakt, met reden: diensten die bij gewoon lezen een map of item van de server zelf aanmaken als die ontbreekt
  (`IDtoService`, `IUserViewManager.GetUserViews` en `GetUserSubView`, `ITVSeriesManager`, `IMusicManager` en leesleden
  van `ILibraryManager` zoals `GetVirtualFolders` en van `ILiveTvManager` zoals `GetInternalLiveTvFolder` roepen intern
  `GetUserRootFolder`, `GetNamedView` of `GetMusicGenre` aan; `GetUserViews` met externe inhoud maakt ook een ontbrekend
  kanaalitem aan, zonder de kanaalitems te verversen). Dat doet de server bij elke opvraging van een gewone client ook;
  kijkgegevens raakt het niet. De directe aanroep van die leden blijft verboden. Verversen of wissen van kanaalitems is
  wel verboden (zie "Wat JL0001 bewaakt"). Ook `IAuthService` (de sessiecontrole van de plugin) werkt bij elk verzoek
  de apparaatregel bij, net als bij elk ander verzoek aan de server; in JLT-65 valt die rij onder het ruismasker
  (kolommen die al tussen twee runs zonder plugin verschillen).
- De kanaalregel werkt op naam en op het type waarop de code het lid aanroept; omdat de verboden leden ook op `Folder`
  staan, telt een aanroep via een variabele van het basistype ook. Wat de analyzer niet ziet: servercode buiten de
  bewaakte typen die deze leden aanroept (bijvoorbeeld `UserViewBuilder.GetUserItems`). De server doet hetzelfde bij elke
  opvraging van een gewone client; de plugin gebruikt geen van deze typen (alleen `ILibraryManager.GetVirtualFolders`).
- "Lezen" is op naam bepaald, en dat is in upstream geen garantie: bij het nalopen van v12.4 bleken
  `ILibraryManager.GetGenre`/`GetStudio`/`GetArtist`/`GetYear`/`GetMusicGenre`/`GetOrCreatePerson`, `GetNamedView`,
  `GetShadowView` en `GetUserRootFolder` een item of map aan te maken als die ontbreekt,
  `ISessionManager.GetSessionByAuthenticationToken` sessieactiviteit vast te leggen en `BaseItem.ReattachUserDataAsync`
  kijkgegevens te verplaatsen. Die staan nu met naam bij de verboden leden, net als `GetCollectionsFolder` en
  `GetPlaylistsFolder`, en sinds herstelronde 2 de leden die kanaalitems verversen of wissen (sinds herstelronde 3 ook
  `Folder.GetChildren` en `GetRecursiveChildren`). Om dit bij een sync niet
  opnieuw te missen ligt de **hele ledenlijst** van de bewaakte servertypen vast in `Analyzer/BewaakteLeden.txt` (614
  leden met het oordeel `lezen` of `verboden`; een afgeleid type erft de verboden leden van zijn basistype). Een nieuw,
  verdwenen of anders beoordeeld lid laat de test falen tot iemand het oordeel heeft bekeken. Het oordeel zelf blijft
  mensenwerk op basis van de upstream-bron; een methode die via een omweg schrijft kan gemist zijn.
- Aanroepen naar buiten (`IProviderManager.GetRemoteSearchResults`, `ISubtitleManager.SearchSubtitles`) schrijven niet
  en vallen niet onder deze regels; het netwerkbeleid van een module is een eigen onderwerp (F3, F5).
- De officiële route om **eigen** plugininstellingen op te slaan (`BasePlugin.SaveConfiguration`) blijft toegestaan;
  daar staan geen geheimen in (ADR-0031).

## Gevolgen

- Elke nieuwe module begint zonder schrijfrechten op de server; een uitzondering kost een regel, een ADR en een
  review.
- B03-018 plaatst de werkerbewaker in `Core.Werker`; nergens anders kan plugincode een proces starten.
- CI: de job "Plugins bouwen en testen" draait de solution (plugin schoon), de tests en `analyzer_proef.py --bouw`.

## Alternatieven

- **`Microsoft.CodeAnalysis.BannedApiAnalyzers`**: kent geen "alles behalve lezen" per interface en geen uitzondering
  per klasse; elke nieuwe upstream-methode zou vanzelf toegestaan zijn. Afgewezen.
- **Alleen een test die de IL doorzoekt**: vindt het pas na de build en geeft geen regelnummer. Afgewezen als enige
  laag.
- **Generator in Python in de runtime-image**: de runtime-image heeft geen Python buiten de werker; de web-bouwstap
  heeft Node al. Afgewezen.
