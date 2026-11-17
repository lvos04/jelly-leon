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
  Bijgewerkt 2026-11-17 na herreview 5 (S-G1-17 herstelronde 6, R-HARDE-EIS-13): ook bestanden zijn nu generiek geregeld,
  op namespace- en typeniveau in plaats van een opsomming. Buiten de opslagnamespaces is elk gebruik van een type uit
  System.IO (met de subnamespaces, zoals Compression, MemoryMappedFiles, Pipes en IsolatedStorage), System.Formats.Tar en
  de bestandslaag van Visual Basic JL0002, behalve een kleine witte lijst; daarbij de schrijvende delen van System.Xml en
  System.Data. De server-ABI die zelf een bestand schrijft, wist of verplaatst of een proces start, is nergens toegestaan
  (ook niet in `Core.Storage`). P/Invoke, `unsafe`, reflectie die een lid aanroept of een type uit een tekst haalt, code
  laden en `dynamic` zijn overal JL0002. Het dreigingsmodel staat nu uitdrukkelijk onder "Dreigingsmodel".
  Bijgewerkt 2026-11-17 na herreview 6 (S-G1-17 herstelronde 7, R-HARDE-EIS-14, -15 en -16; besluit van de regisseur): de
  server-ABI is omgedraaid naar een witte lijst. Elk lid van een servertype is JL0001, behalve de lezende leden die de
  plugin echt gebruikt, per klasse; een eigenschap of veld van een servertype zetten is altijd JL0001; een implementatie of
  afleiding van een servertype is JL0001 buiten de witte lijst van uitbreidingspunten per namespace; het pad van de
  pluginconfiguratie verleggen is JL0002 nergens. `WebClient`, `WebRequest` en de trace-laag zijn buiten de opslaglaag
  helemaal JL0002, en een constructor met `FileStreamOptions` staat nooit op de witte lijst. Zie "Server-ABI: witte lijst".
  Bijgewerkt 2026-11-17 na herreview 7 (S-G1-17 herstelronde 8, R-HARDE-EIS-17 en de grenzen 1 tot en met 5; besluit van de
  regisseur): de HTTP-laag van de server is JL0001 buiten een witte lijst per klasse (middleware, filters, claimsomzetting,
  autorisatie, de instellingen van MVC, autorisatie en authenticatie, het verzoek, de gebruiker, de routewaarden en de
  argumenten van een actie), een netwerkclient mag alleen in een benoemde transportklasse (de lijst is leeg), en
  `ConfigurationBinder.Bind`/`Get`, `TypeDescriptor` met `PropertyDescriptor.SetValue`, `DispatchProxy`, System.Linq.Expressions
  en `Unsafe` zijn omwegen (JL0002). De grenzen staan eerlijk onder "Grenzen". Zie "HTTP-laag en netwerk".
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
| **JL0001** | **de server-ABI buiten de witte lijst** (sinds herstelronde 7; zie "Server-ABI: witte lijst"): elk lid van een servertype (aanroepen, lezen, een event, aanmaken), behalve de lezende leden op de witte lijst van die klasse; elke toewijzing aan een eigenschap of veld van een servertype; elke implementatie of afleiding van een servertype buiten de witte lijst van uitbreidingspunten. **De HTTP-laag van de server en netwerkclients** (sinds herstelronde 8; zie "HTTP-laag en netwerk"): een middleware, filter, claimsomzetting of ander uitbreidingspunt van de HTTP-laag, de pijplijn opbouwen, de instellingen van MVC, autorisatie en authenticatie, routering en features, het verzoek of de gebruiker zetten, de verzoekkoppen anders dan lezen, de argumenten van een actie, en elke HTTP-, socket- of websocketclient. Daaronder, met een eigen melding: schrijvende server-API. Per interface geldt "alles verboden behalve lezen" (voorvoegsels `Get`, `Find`, `Query`, `Is`, `Has`, `Can`, `To`, alleen als heel woord: `CanRefresh` is lezen, `CancelTimer` niet): `ILibraryManager`, `IItemRepository`, `IItemPersistenceService`, `IPlaylistManager`, `ICollectionManager` (ook `GetCollectionsFolder`, want die kan aanmaken), `IUserManager`, `IDeviceManager`, `IUserDataManager`, `IProviderManager`, `ISubtitleManager`, `IMediaSegmentManager`, `ISessionManager`, `IServerConfigurationManager`/`IConfigurationManager`, plus de diensten uit "Wat JL0001 bewaakt" hieronder; op `BaseItem` en afgeleiden de wijzigende methoden (`Update*`, `Delete*`, `Refresh*`, `Save*`, `Add*`, `Remove*`, `Set*`, `Swap*`, `Changed*`, `Mark*`, `Validate*`). Ook het schrijven van een eigenschap (toewijzing, `++`, `--`) op een bewaakt type telt: `item.Name = …` op een `BaseItem` is JL0001. Bij een bewaakte interface tellen van een eigen klasse die de interface implementeert alleen de leden die een lid van die interface implementeren (zie "Wat JL0001 bewaakt") | witte lijst van de server-ABI: per lid en per klasse, alleen in `Regels.cs` en in deze ADR; uitbreidingspunten per namespace. HTTP-laag: alleen per klasse op de witte lijst van de HTTP-laag (nu de spike van ADR-0033 en `JlRouteAttribute`, alleen voor de eigen pluginpaden en acties). Netwerkclients: alleen in een benoemde transportklasse (de lijst is leeg). Schrijvende server-API: bibliotheek, opslag van items, afspeellijsten, collecties, gebruikers, apparaten en alle diensten uit "Wat JL0001 bewaakt": **nergens**. De overige alleen in één met naam genoemde klasse per API (witte lijst) |
| **JL0002** | **bestanden**: elk gebruik van een type uit System.IO (met alle subnamespaces), System.Formats.Tar en Microsoft.VisualBasic.FileIO (plus `Microsoft.VisualBasic.FileSystem`), behalve de kleine witte lijst (padbewerking, lezen, en een stroom of lezer/schrijver die de code al heeft); het schrijvende deel van System.Xml/System.Xml.Linq (`Save`, `WriteTo`, `WriteContentTo`, `Transform`, `Serialize` en een XmlWriter maken, met een pad of stroom), `DataSet`/`DataTable.WriteXml*`, `WebClient`, `WebRequest` en de trace-laag helemaal (sinds herstelronde 7), `ResourceWriter` met een pad en `ProfileOptimization`; een constructor met `FileStreamOptions`; wijzigende methoden van `IFileSystem` (zie "Bestanden (JL0002)"). **Het pad van de pluginconfiguratie verleggen** (een override van `BasePlugin<T>.ConfigurationFileName`, `SaveConfiguration` of `UpdateConfiguration`; zie "Server-ABI: witte lijst"): nergens. **Server-ABI die zelf schrijft of een proces start** (`IPluginManager`, `new LocalPlugin`, `IXmlSerializer.SerializeTo…`, `ITranscodeManager`, `IMediaEncoder` en de rest van de lijst onder "Bestanden (JL0002)"). **Omwegen**: P/Invoke, `unsafe`, `NativeLibrary`/`Marshal`, reflectie die een lid aanroept of een type uit een tekst haalt, code laden, `Activator`, `dynamic`, System.Reflection.Emit, en sinds herstelronde 8 `ConfigurationBinder.Bind`/`Get`, `TypeDescriptor` en `PropertyDescriptor.SetValue`/`GetValue`, `DispatchProxy`, System.Linq.Expressions, `Unsafe` en `TryUpdateModelAsync` (zie "Dreigingsmodel"). Daarnaast **databasetoegang**: elke operatie die een databaseverbinding of -bron oplevert of gebruikt (`new SqliteConnection`, `SqliteFactory`, `DbProviderFactory`/`DbProviderFactories`, `DbDataSource`, `IDbConnection`, SQLitePCL en de bouwers van Entity Framework Core; zie "Databasetoegang (JL0002)") | bestanden: alleen in `Core.Storage` en `Core.Secrets` (die bewaken de schrijfgrens `<DataPath>/jelly-leon/**` en `/cache/jelly-leon/**` zelf); `File`/`Directory`/`FileInfo`/`DirectoryInfo`/`IFileSystem`-methoden daarnaast in één genoemde klasse per API; voor de andere bestandsleden bestaat geen uitzondering. Server-ABI die zelf schrijft en de omwegen: **nergens**, ook niet in `Core.Storage`, geen uitzondering. Databasetoegang: **alleen in `Core.Storage`** (`JlDatabase`), geen uitzondering mogelijk |
| **JL0003** | de database van de server: elk gebruik van de typenaam `JellyfinDbContext`, `IJellyfinDatabaseProvider` (een dienst in de container van de server: `DbContextFactory` geeft een context, `PurgeDatabase` wist elke tabel en `RestoreBackupFast` overschrijft `jellyfin.db`), `IEntityFrameworkCoreLockingBehavior` of `IItemQueryHelpers` (die twee nemen een context als argument), en van een type dat er een implementeert of ervan afleidt. Elk gebruik is: een parameter, een veld, een lokale variabele, `GetService<T>`, `typeof`, een alias, een typeargument (`IDbContextFactory<JellyfinDbContext>`), een elementtype en `var` dat naar zo'n type verwijst (`var f = provider.DbContextFactory`). Ook de niet-generieke `Microsoft.EntityFrameworkCore.DbContextOptions` (precies dat type, niet een afgeleid type) is JL0003 bij elk gebruik van de naam: na `AddPooledDbContextFactory<JellyfinDbContext>` staat hij in de container van de server en draagt hij de verbindingstekst van `jellyfin.db` (resolven met `GetRequiredService<DbContextOptions>()`, injecteren als parameter, `typeof`). Zonder die naam krijgt plugincode de dienst niet: de container geeft hem alleen op type, en volgens een scan van de plugin-ABI is `IJellyfinDatabaseProvider.DbContextFactory` het enige publieke lid dat een context of een fabriek ervan teruggeeft (herhaald in herstelronde 5 met een scan over alle compile-assets: zie "Databasetoegang (JL0002)"). Verder elke tekst met `jellyfin.db` of `library.db` (hoofdletters tellen niet). "Tekst" is elke letterlijke tekst, elke UTF-8-tekst (`"…"u8`), elke constante (ook uit een andere assembly, en de constante waarde van een omzetting: `(char)46` en `(char)0x2E` zijn een punt, `(int)'.'` is geen tekst) en elke samenstelling met `+` of `$"…"`, ook een optelling van UTF-8-teksten (`"jellyfin"u8 + ".db"u8`): de bekende stukken die direct op elkaar volgen worden aaneengeschreven (`"jellyfin" + ".db"`, `Naam + ".db"` met een constante, `$"{map}/jellyfin.d" + "b"`, `$"{map}/{Naam}.db"`); een uitlijning `{x,n}` met een bekend stuk vult met spaties aan tot \|n\| tekens (n positief ervoor, negatief erna; een kortere n vult niets aan, dus `$"jellyfin{".db",3}"` is JL0003); een stuk dat pas bij het draaien bekend is, breekt de reeks | **nergens**, geen uitzondering mogelijk |
| **JL0004** | processen starten (`Process.Start`, `new Process`, `new ProcessStartInfo`, `Microsoft.VisualBasic.Interaction.Shell`). Het besluit van herstelronde 6 noemt processen starten bij JL0002; de regel blijft JL0004, want die is strenger (ook in `Core.Storage` en `Core.Secrets` verboden) en houdt de werkerbewaker van B03-018 in `Core.Werker` mogelijk. Een proces dat de server start (`ITranscodeManager.StartFfMpeg`, `IMediaEncoder`, de keyframe-extractors) is JL0002 (server-ABI) | alleen in `Core.Werker` (de werkerbewaker van B03-018); geen uitzondering per klasse |
| **JL0009** | een ongeldige regel in de witte lijst | — |

Verboden is "aanroepen én ernaar verwijzen": een methodegroep (`Action<string> f = File.Delete`) telt als aanroep.
Gegenereerde code wordt ook gecontroleerd.

#### Server-ABI: witte lijst (JL0001)

Sinds herstelronde 7 (herreview 6, R-HARDE-EIS-14, -15 en -16; besluit van de regisseur) is de server-ABI omgedraaid naar
een witte lijst, net als System.IO in herstelronde 6. Aanleiding: wegen naar `jellyfin.db` en de bibliotheek die de
opsomming van herstelronde 6 miste. Een override van `BasePlugin<T>.ConfigurationFileName` (al `plugin.Configuration` lezen
maakte van `jellyfin.db` een XML-bestand), `IServerApplicationHost.RestoreBackupPath` zetten (de server zet bij de volgende
start een back-up terug), `IApplicationHost.GetExports<ILibraryPostScanTask>()` met `Run`, en uitbreidingspunten die de
server zelf in de pluginassembly zoekt (een eigen `IResolverIgnoreRule` laat de volgende scan items wissen). Daarbij
`SessionInfo`: wie `NowPlayingItem` of `LastPlaybackCheckIn` zet, laat de server voor die sessie `OnPlaybackStopped` doen,
dat `PlayCount`, `Played` en `PlaybackPositionTicks` opslaat. Binnen de server-ABI vond herreview 7 met deze regel geen
nieuwe weg meer (lid voor lid nagelopen, en de pluginbouw met een lege lijst gaf precies de gebruikte leden). Dat geldt alleen
voor de server-ABI. Buiten de server-ABI om vond dezelfde herreview wel een weg: de HTTP-laag van de server, met alleen
Microsoft- en BCL-typen (R-HARDE-EIS-17, zie "HTTP-laag en netwerk"). Wat de analyzer daarna nog niet ziet, staat onder
"Grenzen"; een nieuwe scan kan daar nog wegen vinden.

**Servertype** = elk type uit een namespace of assembly `MediaBrowser.*`, `Jellyfin.*` of `Emby.*`, behalve de eigen plugin
(`Jellyfin.Plugin.JellyLeon.*`).

1. **Leden.** Elk gebruik van een lid van een servertype is JL0001: aanroepen (ook een extensiemethode en een
   basisconstructor), als methodegroep nemen, een eigenschap, indexer of veld lezen, een event (abonneren of afmelden),
   aanmaken en een eigen operator of omzetting. Behalve wat voor die klasse op de witte lijst hieronder staat: alleen
   lezende leden die de plugin echt gebruikt, elk in precies één klasse (de buitenste klasse met volledige naam; een lambda
   of geneste klasse telt mee). Vrij blijven een constante of enumwaarde (de compiler zet de waarde in de plugin, er draait
   geen servercode), een typenaam (parameter, veld, `typeof`, typeargument, `GetService<T>`) en een lid van `System.Object`
   dat het servertype niet zelf overschrijft. Wat een specifieke regel al meldt of per klasse vrijgeeft (de bewaakte typen
   hieronder, de server-ABI die zelf schrijft, databasetoegang, de bestandsregel, JL0003), meldt deze regel niet nog eens.
   De regel geldt in elke namespace, ook in `Core.Storage`, `Core.Secrets` en `Core.Werker`.
2. **Zetten.** Een eigenschap of veld van een servertype zetten (toewijzing, ook samengesteld, `++`/`--`, deconstructie,
   `ref`/`out`) is altijd JL0001, ook in een klasse met leesrechten op dat lid. Voorbeelden: `SessionInfo.NowPlayingItem`,
   `LastPlaybackCheckIn`, `RestoreBackupPath`, `ItemImageInfo.Path`, `LinkedChild.Path` en de eigenschappen van entiteiten
   als `User` en `UserItemData`. Eén vorm mag: de objectinitialisatie (`new T { P = … }`) van een aanmaak die voor die klasse
   op de lijst staat, met precies de daar genoemde eigenschappen. Dat object is nieuw en van niemand anders (de
   configuratiepagina van de plugin); de toewijzing staat dus niet als lid op de lijst.
3. **Uitbreidingspunten.** Een type van de plugin dat een servertype implementeert of ervan afleidt, ook via een eigen
   tussentype of een eigen interface, is JL0001 (een symboolactie op elk type), behalve de witte lijst van
   uitbreidingspunten, per namespace (exact, niet de namespaces eronder). Wat een toegestaan servertype zelf meebrengt
   (`IPlugin`, `IHasPluginConfiguration` en `IPluginAssembly` via `BasePlugin<T>`) mag mee; een servertype dat het plugintype
   zelf (opnieuw) noemt, moet er zelf op staan. Zo ontstaat geen eigen `IResolverIgnoreRule`, `ILibraryPostScanTask`,
   `IScheduledTask`, metadataleverancier of vervanger van een serverdienst zonder bouwfout (`AddSingleton<IUserDataManager, X>`
   vraagt een klasse die `IUserDataManager` implementeert).
4. **Pluginconfiguratie.** De server schrijft de pluginconfiguratie naar
   `ConfigurationFilePath = Path.Combine(PluginConfigurationsPath, ConfigurationFileName)`, ook als hij hem alleen leest en
   dat faalt (`LoadConfiguration` vangt de leesfout en roept `SaveConfiguration` aan). Een override van
   `BasePlugin<T>.ConfigurationFileName`, `SaveConfiguration` (beide) of `UpdateConfiguration`, of een expliciete implementatie
   van een lid van `IHasPluginConfiguration`, is JL0002 en nergens toegestaan. De test
   `PluginGrensTests.Configuratie_WordtAlleenInHetVasteBestandVanDePluginGeschreven` legt het pad vast:
   `Path.Combine(PluginConfigurationsPath, "Jellyfin.Plugin.JellyLeon.xml")`, ook bij lezen met een leesfout.

Inventaris: de plugin zonder lijst gebouwd gaf 61 JL0001-meldingen in 10 klassen. Met de lijst hieronder bouwt hij zonder
één JL-fout. Elk lid is in de serverbron (v12.4) nagelopen: een automatische eigenschap, of een getter of extensiemethode
die niets schrijft, behalve de drie regels die in de motivatie "niet zuiver lezen" heten. Die drie gebruikte de plugin al
vóór dit besluit; zonder hen werken de moduleschakelaars, de mountcontrole en de sessiecontrole niet.

Witte lijst van leden (`Regels.ServerAbiWitteLijst`; `ServerAbiWitteLijstTests.WitteLijsten_ElkeRegelStaatInAdr0032` eist dat
elke regel in deze tabel staat):

| Type | Lid | Klasse (onder `Jellyfin.Plugin.JellyLeon`) | Motivatie |
|---|---|---|---|
| `BasePlugin` (met `T` = `PluginConfiguration`) | `new` (de basisconstructor) | `Plugin` | De server maakt de plugin; de constructor slaat de paden en de serializer op en zet de eigen attributen in het geheugen. |
| `PluginPageInfo` | `new`, met `Name`, `DisplayName` en `EmbeddedResourcePath` in de objectinitialisatie | `Plugin` | De configuratiepagina (`IHasWebPages.GetPages`): een nieuw object dat de server alleen leest om de ingebedde pagina te tonen. |
| `IApplicationPaths` | `DataPath`, `CachePath` | `PluginServiceRegistrator` | Twee paden lezen om de eigen schrijfmappen (`JlPaths`) te bepalen. |
| `IApplicationHost` | `ApplicationVersionString`, `Name` | `Api.JellyLeonVersionController` | Versie en naam van de server tonen (B03-001); twee getters. |
| `ILibraryManager` | `GetVirtualFolders` | `Core.BibliotheekMappen` | De mediamappen voor de alleen-lezencontrole van de mount. Niet zuiver lezen: maakt de hoofdmap van de server aan als die ontbreekt, net als elke opvraging van een gewone client (zie "Grenzen"); raakt geen kijkgegevens. |
| `VirtualFolderInfo` | `Locations` | `Core.BibliotheekMappen` | Automatische eigenschap van het resultaat. |
| `IAuthService` | `Authenticate` | `Core.Http.JellyfinSessionAuthenticator` | De sessiecontrole van de pluginroutes. Niet zuiver lezen: werkt de apparaatregel bij, zoals elk verzoek aan de server (zie "Grenzen"); raakt geen kijkgegevens. |
| `AuthorizationInfo` | `IsApiKey`, `IsAuthenticated`, `User` | `Core.Http.JellyfinSessionAuthenticator` | Automatische eigenschappen van het resultaat van de sessiecontrole. |
| `User` | `Id` | `Core.Http.JellyfinSessionAuthenticator` | Het ID van de aangemelde gebruiker. |
| `UserEntityExtensions` | `HasPermission` | `Core.Http.JellyfinSessionAuthenticator` | Leest één recht (beheerder) uit de lijst van de entiteit. |
| `User` | `MaxParentalRatingScore`, `AccessSchedules` | `Core.Privacy.KidPolicy` | Kind-signalen: kijken of er een leeftijdsgrens is en de schema's tellen. |
| `UserEntityExtensions` | `GetPreference` | `Core.Privacy.KidPolicy` | Leest de geblokkeerde tags uit de voorkeuren van de entiteit. |
| `GenericEventArgs` | `Argument` | `Core.Privacy.UserDeletedConsumer` | De verwijderde gebruiker uit het event. |
| `User` | `Id` | `Core.Privacy.UserDeletedConsumer` | Het ID, om de eigen gegevens van die gebruiker te wissen (c09698f09). |
| `BasePlugin` (met `T` = `PluginConfiguration`) | `Configuration` (lezen) en `SaveConfiguration` | `Core.Modules.PluginModuleSwitches` | De eigen moduleschakelaars, via de officiële route. Niet zuiver lezen, en de enige schrijvende regel: de server schrijft dan alleen het eigen XML-bestand, omdat het pad vastligt (punt 4). Ook `Configuration` lezen kan dat bestand schrijven (bij een leesfout). |
| `ISessionManager` | `PlaybackStart`, `PlaybackStopped` (abonneren en afmelden), `Sessions` | `Core.Planner.ServerSessies` | De planner pauzeert zwaar werk zodra er wordt afgespeeld en telt de sessies. Een event abonneren laat de server alleen de handler aanroepen. |
| `SessionInfo` | `NowPlayingItem`, `TranscodingInfo` | `Core.Planner.ServerSessies` | Automatische eigenschappen, alleen gelezen (zetten blijft JL0001). |
| `TranscodingInfo` | `IsVideoDirect`, `HardwareAccelerationType` | `Core.Planner.ServerSessies` | Software- of hardwaretranscode herkennen (regel G6a). |
| `ISessionManager` | `PlaybackStart`, `PlaybackStopped` (abonneren en afmelden) | `Modules.Devices.DevicesListener` | Module Devices legt per apparaat de afspeelwijze vast in een eigen tabel. |
| `PlaybackProgressEventArgs` | `Users`, `Session`, `DeviceId`, `MediaSourceId`, `PlaySessionId` | `Modules.Devices.DevicesListener` | Automatische eigenschappen van het event. |
| `SessionInfo` | `Id`, `PlayState`, `TranscodingInfo` | `Modules.Devices.DevicesListener` | Automatische eigenschappen, alleen gelezen. |
| `TranscodingInfo` | `IsVideoDirect`, `HardwareAccelerationType` | `Modules.Devices.DevicesListener` | Zoals bij de planner. |
| `PlayerStateInfo` | `PlayMethod` | `Modules.Devices.DevicesListener` | Direct Play, Direct Stream of Transcode. |
| `User` | `Id` | `Modules.Devices.DevicesListener` | Het ID van de kijker, voor de eigen tabel. |

Witte lijst van uitbreidingspunten (`Regels.UitbreidingWitteLijst`):

| Servertype | Namespace (exact) | Motivatie |
|---|---|---|
| `BasePlugin<T>` | `Jellyfin.Plugin.JellyLeon` | De ene pluginklasse (`Plugin`, ADR-0016). |
| `IHasWebPages` | `Jellyfin.Plugin.JellyLeon` | De configuratiepagina van `Plugin`. |
| `IPluginServiceRegistrator` | `Jellyfin.Plugin.JellyLeon` | De registratie van Core en de modules. |
| `BasePluginConfiguration` | `Jellyfin.Plugin.JellyLeon.Configuration` | `PluginConfiguration` (alleen schakelaars en instellingen, nooit een geheim). |
| `IEventConsumer<UserDeletedEventArgs>` | `Jellyfin.Plugin.JellyLeon.Core.Privacy` | `UserDeletedConsumer` wist de eigen gegevens van een verwijderde gebruiker (c09698f09). Alleen dit typeargument; een consumer van een ander event is JL0001. Stond niet in het voorstel van herreview 6, maar de plugin gebruikt het al sinds golf 1. |

Microsoft-typen zijn geen server-ABI en vallen niet onder deze regel: `IHostedService` (`DevicesListener`, `MediaGuardPoller`,
`BatchPlanner`); zie "Grenzen". `IStartupFilter` (de spike van ADR-0033) en de andere uitbreidingspunten van de HTTP-laag vallen
sinds herstelronde 8 onder een eigen regel met een eigen witte lijst (zie "HTTP-laag en netwerk"). Later, elk met een eigen ADR en een regel in
`Regels.UitbreidingWitteLijst`: `IScheduledTask` (de ingang naar de batchplanner) en `IMediaSegmentProvider` (alleen in
`Modules.Segments`, B03-07x). Nu geven beide JL0001.

In dezelfde ronde, als JL0002 buiten de opslaglaag (`Core.Storage`, `Core.Secrets`), zonder uitzondering per klasse:
`WebClient` en `WebRequest` met elk afgeleid type (`FileWebRequest`) helemaal, ook lezen: met een file:-adres schrijven
`UploadData`, `UploadString`, `OpenWrite` en een PUT met `GetRequestStream` in elk bestand. De trace-laag ook: `Trace`,
`TraceSource`, `Debug`, `TraceListener` met elk afgeleid type en `TraceListenerCollection` (`DefaultTraceListener.LogFileName`
voegt tekst toe aan een zelfgekozen bestand). Listeners aanmaken, instellen en via de trace-laag schrijven kan dus alleen in de
opslaglaag. `Debug` staat erbij omdat zijn uitvoer via de listeners kan lopen; dat is niet gemeten, de regel kiest de veilige
kant. En een constructor met `FileStreamOptions` staat nooit op de witte lijst van de bestandsnamespaces: ook `StreamReader`
maakt met `Mode = Truncate` en `Access = ReadWrite` een bestand leeg. Dat geldt ook als de opties als parameter binnenkomen.

Tests: `ServerAbiWitteLijstTests` (de proef Punt2 van herreview 6 nagebouwd: elk van de 20 regels die geen melding gaven,
geeft nu een JL-fout; lezen per klasse; zetten; uitbreidingspunten; de pluginconfiguratie; WebClient, WebRequest en trace;
`StreamReader` met opties; elk type en lid op de lijsten bestaat; elke regel staat in deze ADR), `PluginGrensTests` (het pad
van de configuratie en de typen in de vrijgestelde namespaces) en de proefregels in `VerbodenAanroepen.cs`. De oudere
analyzertests toetsen hun specifieke regel zoals voorheen en markeren met `/*WL*/` waar de witte lijst daarnaast JL0001 geeft.

#### HTTP-laag en netwerk (JL0001)

Sinds herstelronde 8 (herreview 7, R-HARDE-EIS-17; besluit van de regisseur). Aanleiding: de REST-API van de server schrijft
ook kijkgegevens, en plugincode bereikte die zonder één lid van de server-ABI, met alleen Microsoft- en BCL-typen. Vier vormen
gaven geen JL-fout en de echte pluginbouw slaagde: (A) een `IStartupFilter` met een middleware vóór routing en authenticatie
die `GET /Items?ParentId=<bibliotheek>` omzet naar `DELETE /UserPlayedItems/<bibliotheek>`; (B) een globaal MVC-filter
(`MvcOptions.Filters`) dat `ActionArguments` van een serveractie wijzigt; (C) `HttpClient` naar de eigen server via loopback,
met het token uit een binnenkomend verzoek; (D) een `IClaimsTransformation` die de claim `Jellyfin-UserId` vervangt. Eén verzoek
`DELETE /UserPlayedItems/<bibliotheek-ID>` zet in de serverbron (v12.4) voor die gebruiker van elk item in de bibliotheek
`Played`, `PlayCount`, `PlaybackPositionTicks` en `LastPlayedDate` terug (`PlaystateController.MarkUnplayedItem` →
`Folder.MarkUnplayed` met `Recursive = true` → `BaseItem.ResetPlayedState` → `SaveUserData`). Met een beheerderstoken en
`?userId=` kan dat ook voor een andere gebruiker.

**De regel (JL0001, eigen melding "raakt de HTTP-laag van de server").** Buiten de witte lijst hieronder is verboden, in elke
namespace (ook `Core.Storage`, `Core.Secrets` en `Core.Werker`):

1. **Uitbreidingspunten** (een symboolactie op elk type van de plugin, ook via een eigen tussentype of interface): een type dat
   `IStartupFilter`, `IHostingStartup`, `IMiddleware`, `IMiddlewareFactory`, `IHttpContextFactory`, `IHttpContextAccessor`,
   `IEndpointFilter` of `Endpoint` implementeert of ervan afleidt, of een type uit Microsoft.AspNetCore.Authentication
   (`IClaimsTransformation`, een eigen schema), .Authorization (`IAuthorizationHandler`, `IAuthorizationPolicyProvider`),
   .Mvc.Filters (elk filter), .Mvc.ApplicationModels (conventies), .Mvc.ApplicationParts, .Mvc.ModelBinding (een binder of
   waardebron voor de argumenten van een serveractie), .Mvc.Formatters, .Mvc.Routing, .Mvc.Abstractions, .Mvc.Infrastructure,
   .Mvc.Controllers, .Routing, .Http.Features of .Rewrite (met alle namespaces eronder).
2. **De pijplijn opbouwen**: elk lid van `IApplicationBuilder` en `IEndpointRouteBuilder`, en elke extensiemethode die erop
   werkt (`Use`, `UseMiddleware`, `Map`, `MapWhen`, `UseWhen`, `Run`, `UseRouting`, `MapGet`, …).
3. **De instellingen die voor alle routes gelden**: elk lid van `MvcOptions` (filters, conventies, waardebronnen, binders,
   formatters), `ApplicationPartManager`, `AuthorizationOptions` en `AuthorizationBuilder` (een policy toevoegen of vervangen, de
   standaard- of terugvalpolicy), `AuthenticationOptions` en `AuthenticationBuilder` (een schema of het standaardschema). De
   registratie (`Configure<T>`, `AddMvc`, `AddAuthorization`) is een typenaam; het lid in de lambda telt.
4. **Elk lid** (ook lezen, behalve een constante) van een type uit Microsoft.AspNetCore.Authentication, .Authorization,
   .Routing (ook `RouteValueDictionary` en de endpoints van de server), .Http.Features (`IHttpRequestFeature.Path` zetten gaat
   langs `HttpRequest` heen), .Rewrite, .Mvc.ApplicationModels, .Mvc.ApplicationParts, .Mvc.Infrastructure, .Mvc.Abstractions
   en .Mvc.Controllers (met `IActionDescriptorCollectionProvider` en `IActionInvokerFactory` voert plugincode een actie van de
   server in het proces uit, langs authenticatie en autorisatie heen); en een waarde uit die namespaces als ander type
   doorgeven (`IDictionary<string, object> d = http.Request.RouteValues`).
5. **Losse leden**: `ActionExecutingContext.ActionArguments` (ook lezen: het is een gewone, wijzigbare lijst),
   `Endpoint.RequestDelegate` (een endpoint van de server rechtstreeks uitvoeren gaat langs authenticatie en autorisatie heen),
   `SetEndpoint`, `GetTypedHeaders` (getypeerde koppen met setters), en `ClaimsPrincipal.AddIdentity`/`AddIdentities`,
   `ClaimsIdentity.AddClaim`/`AddClaims`/`RemoveClaim`/`TryRemoveClaim`.
6. **Het verzoek of de gebruiker zetten**: een eigenschap van `HttpRequest` (`Path`, `PathBase`, `Method`, `QueryString`,
   `Query`, `Body`, `RouteValues`, …), `HttpContext` (`User`, `RequestServices`, `Items`, …) of `IHttpContextAccessor` zetten.
7. **De verzoekkoppen**: `HttpRequest.Headers` mag alleen rechtstreeks gelezen worden (een kop, een getypeerde kop lezen,
   `TryGetValue`, `ContainsKey`). Een kop zetten, `Append`, `Remove`, de koppen in een variabele opslaan of doorgeven is JL0001.
   De antwoordkoppen (`HttpResponse.Headers`) vallen er niet onder.

Attributen op eigen code (`[Authorize]`, `[Route]`) tellen niet: die gelden alleen voor die code.

Witte lijst van de HTTP-laag (`Regels.HttpWitteLijst`, per klasse; `HttpLaagTests.WitteLijst_ElkeRegelStaatInAdr0032` eist dat
elke regel in deze tabel staat). Een plugin zonder deze lijst gebouwd gaf precies deze drie meldingen:

| Type | Lid | Klasse (onder `Jellyfin.Plugin.JellyLeon`) | Motivatie |
|---|---|---|---|
| `IStartupFilter` | implementeert | `Core.Http.JlStartupFilterSpike` | De spike van ADR-0033 (standaard uit): een laag vóór routing en authenticatie die alleen een verzoek van meer dan 1 MiB aan `/media/v1` of `/connector/v1` met 413 weigert. Alle andere verzoeken gaan ongewijzigd door; `StartupFilterSpikeTests.In_een_echte_host_komt_een_verzoek_buiten_de_pluginpaden_ongewijzigd_aan` legt dat vast. |
| `UseExtensions` | `Use` | `Core.Http.JlStartupFilterSpike` | De ene middleware van de spike in de pijplijn zetten; `Map`, `UseMiddleware` en andere leden blijven ook in deze klasse JL0001. |
| `IAsyncActionFilter` | implementeert | `Core.Http.JlRouteAttribute` | Het attribuut op de eigen acties dat de ene pipeline laat lopen. Het werkt alleen op de acties die het dragen; een globaal filter vraagt `MvcOptions` en is JL0001. |

**Netwerkclients (JL0001, eigen melding "is een netwerkclient").** Elk lid van een type uit System.Net.Http (ook
`IHttpClientFactory`, `HttpMessageInvoker`, `SocketsHttpHandler` en de headers), System.Net.Sockets (`Socket`, `TcpClient`,
`UdpClient`), System.Net.WebSockets (`ClientWebSocket`) en System.Net.Quic, ook aanmaken en ook een eigen type dat ervan afleidt
(een `DelegatingHandler`), is JL0001 in elke namespace, behalve in een klasse uit `Regels.NetwerkKlassen`. `WebClient` en
`WebRequest` zijn buiten de opslaglaag al JL0002 (bestanden); in de opslaglaag zijn ze nu JL0001 als netwerkclient. Een enumwaarde
mag. **De lijst met transportklassen is leeg**: de plugin heeft er nu geen nodig (`GeenMediaGuardVervoer` maakt geen
verbinding). Een klasse komt er alleen op met een eigen ADR (straks de MediaGuard-vervoerder, B03-009/ADR-0034), en die klasse
moet bij het draaien loopback (127/8 en ::1), het eigen serveradres en link-local (169.254/16 en fe80::/10) weigeren, ook na
het oplossen van de naam en na een omleiding, fail-closed, met een test daarop. `HttpLaagTests.Netwerk_TransportlijstIsLeegEnElkeClientIsOveralJL0001`
eist dat de lijst leeg is; wie er een klasse op zet, past die test bewust aan.

Tests: `HttpLaagTests.Herreview7Punt3_VormenAtotD_GevenNuEenJLFout` (de vormen A tot en met D van herreview 7, nagebouwd),
`.Varianten_ElkeWegLangsDeHttpLaagOfHetNetwerkIsJL0001` (34 vormen: andere uitbreidingspunten, policies en schema's, features,
koppen, routewaarden, gebruiker, endpoint, een actie in het proces, sockets, websockets, `IHttpClientFactory`, een eigen handler; met de toegestane
tegenvormen; ook in `Core.Storage`), `.WitteLijst_GeldtPerKlasseEnPerLid`, `.Netwerk_TransportlijstIsLeegEnElkeClientIsOveralJL0001`,
`.Tabellen_ElkTypeEnLidBestaat`, `.WitteLijst_ElkeRegelStaatInAdr0032`, de runtime-test van de spike in een echte host (Kestrel op
loopback; methode, pad, query, Authorization, body en routewaarde blijven gelijk, en 413 op een te groot verzoek aan een pluginpad
bewijst dat de spike in de pijplijn zit) en de proefregels in `VerbodenAanroepen.cs`.

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

Sinds herstelronde 6 ook `BaseItemExtensions` (alles behalve lezen): `SetImagePath` en `DeepCopy` naar een bestaand item
wijzigen een item van de server net als de `Set…`-leden van `BaseItem` zelf, maar staan in een eigen statische klasse
(gevonden met de padscan onder "Bestanden (JL0002)"). `GetImagePath`, `HasImage` en `HasChanged` zijn lezen.

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

Van de bewaakte serverdiensten gebruikt de plugin alleen `ILibraryManager` (`GetVirtualFolders`) en `ISessionManager` (de
events `PlaybackStart` en `PlaybackStopped` en de lijst `Sessions`). Sinds herstelronde 7 staat elk gebruikt lid van de
server per klasse op de witte lijst (zie "Server-ABI: witte lijst"); de plugin bouwt zonder één JL-fout.

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
| Als object ophalen | `GetService(typeof(…))`, `ServiceDescriptor.ImplementationInstance`, `Activator.CreateInstance(Type)`, `Type.GetType("…")` | `typeof` en de omzetting naar een databasetype zijn JL0002; zonder die twee blijft het een object. Sinds herstelronde 6 zijn `Activator` en `Type.GetType(tekst)` zelf JL0002 (omweg, zie "Dreigingsmodel") |
| Bestanden van de server | `jellyfin.db` kopiëren, verplaatsen, overschrijven of wissen, ook met een naam die pas bij het draaien ontstaat | JL0002 (de bestandsregel op namespace- en typeniveau en de server-ABI, zie "Bestanden (JL0002)"), JL0003 (een bekende naam) |
| Teksten uit de configuratie | `IConfiguration.GetConnectionString`, `CustomDatabaseOptions.ConnectionString` | geen verbinding zonder een van de wegen hierboven |

Buiten de databasetypen noemt alleen Jellyfin.Database.Implementations/MediaBrowser.Controller (de typen van JL0003) en
System.Data.Common (`…Connection` van een opdracht of transactie) een databasetype; geen enkel lid van de plugin-ABI of van
ASP.NET Core geeft een verbinding terug of geeft er een aan een terugroep. Tests:
`VerbodenApiAnalyzerTests.DatabaseverbindingBuitenDeOpslag_ProevenH15EnH16_IsJL0002OfJL0003` (de vormen van proef H15 en
H16 van herreview 4), `.Databasetoegang_ElkeWegIsBuitenCoreStorageJL0002` (elke weg hierboven; dezelfde bron in
`Core.Storage` geeft geen databasemelding, alleen de omweg `Activator.CreateInstance`; in `Core.Secrets` hetzelfde als in
een module) en de proefregels in `VerbodenAanroepen.cs`.

#### Bestanden (JL0002)

Sinds herstelronde 6 (R-HARDE-EIS-13) is de bestandsgrens net zo generiek als de databasegrens: geen opsomming van
schrijvende methoden meer, maar een regel op namespace en type. Aanleiding: proef SlippendeRoutes van herreview 5. Buiten
`Core.Storage` konden tien regels `jellyfin.db` als bestand overschrijven of wissen zonder één JL-fout: `ZipFile`- en
`TarFile.ExtractToDirectory` met overschrijven, `XmlWriter.Create`, `XDocument.Save`, `DataSet.WriteXml`, `MemoryMappedFile`,
`IPluginManager.RemovePlugin(new LocalPlugin(<data>, …))` (de server wist de map recursief), `IXmlSerializer.SerializeToFile`,
`ITranscodeManager.StartFfMpeg` (de server start ffmpeg op een gekozen uitvoerpad) en `[DllImport] unlink`. Elke regel
geeft nu JL0002 (test `VerbodenApiAnalyzerTests.SlippendeBestandsroutes_ProefHerreview5_ElkeRegelIsJL0002`, de vorm van de
proef; op f7df40d2b gaf hij alleen de tegenproef).

**De regel.** Buiten de opslagnamespaces (`Core.Storage`, `Core.Secrets`) is elk lid van een type uit **System.IO** (met alle
subnamespaces: Compression, MemoryMappedFiles, Pipes, IsolatedStorage, Enumeration), **System.Formats.Tar** en
**Microsoft.VisualBasic.FileIO** (plus het type `Microsoft.VisualBasic.FileSystem`) JL0002: aanroepen, als methodegroep nemen,
een eigenschap of veld lezen of zetten, een event, en het aanmaken. Een eigen of upstream-type dat van zo'n type afleidt, telt
bij aanmaken als het eerste bestandstype in zijn keten (`new FormattingStreamWriter(pad, …)` uit Jellyfin.Extensions telt als
`new StreamWriter(pad)`), en een aanroep van de basisconstructor (`: base(pad)`) ook. Alleen wat op de witte lijst staat mag:

| Type | Mag buiten de opslaglaag |
|---|---|
| `Path` | alle leden behalve `GetTempFileName` (die maakt een leeg bestand aan) |
| `File`, `Directory` | de leesleden (`Exists`, `Read…`, `OpenRead`, `OpenText`, `Get…`; `Enumerate…` bij `Directory`), zoals voorheen; per klasse een uitzondering (witte lijst, hoofdstuk 2) |
| `FileSystemInfo` (`FileInfo`, `DirectoryInfo`) | aanmaken met een pad, een eigenschap lezen, de leesleden (`OpenRead`, `OpenText`, `Get…`, `Enumerate…`, `Refresh`); zetten van een eigenschap is JL0002 |
| `Stream` en elk afgeleid type | elk lid (lezen of schrijven op een stroom die de code al heeft); zelf aanmaken alleen `MemoryStream` en `BufferedStream` (ook een type dat daarvan afleidt). Een ander type dat van `Stream` afleidt aanmaken (een eigen type, of een upstream-stroom die zelf bestanden opent zoals `ProgressiveFileStream` of `FileBufferingReadStream`) is JL0002 buiten de opslaglaag |
| `TextReader`/`TextWriter` en afgeleiden, `BinaryReader`/`BinaryWriter` | elk lid; aanmaken: `StreamReader` (lezen; niet met `FileStreamOptions`, zie "Server-ABI: witte lijst"), `StringReader`, `StringWriter`, `BinaryReader`/`BinaryWriter` en `StreamWriter` alleen zonder tekst (pad) als parameter (ook een type dat daarvan afleidt) |
| elke enum en elke uitzondering uit die namespaces | alles (`FileMode.Create`, `new IOException`, vangen) |

Waarom schrijven op een stroom mag: een stroom naar een bestand krijgen is zelf al JL0002 (`File.Open…`/`Create`/`OpenWrite`,
`FileInfo.Open…`, `new FileStream`, `new StreamWriter(pad)`, `RandomAccess`, `File.OpenHandle`, `MemoryMappedFile`,
`IsolatedStorageFile`, een named pipe, `AsyncFile.Create`/`OpenWrite`, `Activator.CreateInstance(typeof(FileStream), …)`), en
de plugin schrijft zijn HTTP-antwoorden zo (`response.Body.WriteAsync`). Een `FileStream` uit `File.OpenRead` is alleen-lezen.

Daarnaast, buiten de opslagnamespaces, de schrijvende delen buiten System.IO: in **System.Xml** en **System.Xml.Linq** elk lid
dat `Save`, `WriteTo`, `WriteContentTo`, `Transform` of `Serialize` heet (als heel woord) met een pad (tekst) of stroom als
parameter, en een XmlWriter maken met een pad of stroom (`XmlWriter.Create(pad)`, `new XmlTextWriter(pad, …)`; met een
`StringBuilder`, `TextWriter` of `XmlWriter` mag het, die naar een bestand krijgen is al JL0002); **`DataSet`/`DataTable`
`WriteXml…`** (alle varianten); en de BCL-schrijvers die de scan hieronder vond: `ResourceWriter` met een pad en
`ProfileOptimization` (schrijft een JIT-profiel met een zelfgekozen naam in een zelfgekozen map, volgens de documentatie van
.NET; niet gemeten). `WebClient`, `WebRequest` en de trace-laag zijn sinds herstelronde 7 helemaal JL0002 (zie "Server-ABI:
witte lijst"); de scan had alleen `WebClient.DownloadFile…` en `TextWriterTraceListener` met een pad gevonden.

De plugin bouwt hiermee zonder één JL-fout. Het huidige gebruik buiten de opslaglaag valt helemaal binnen de witte lijst,
zonder verhuizing of gedragswijziging: `Core.Planner.CgroupMarge` (`File.Exists`, `File.ReadAllText`, `File.ReadLines`,
`Path.Combine`), `Core.Media.MountCheck` (`File.Exists`, `File.ReadAllLines`, `Path.GetFullPath`),
`Core.Connector.ConnectorService` (`new DirectoryInfo`, `Exists`, `GetFiles`, `Length`, `LastWriteTimeUtc`), `Core.Http.JlPipeline`
(`Stream.ReadAsync`, `new MemoryStream`) en `Core.Http.JlResult` (`response.Body.WriteAsync`).

**Server-ABI die zelf schrijft of een proces start: nergens.** Die loopt langs de padgrens van `Core.Storage` heen (de server
opent het pad zelf), dus hier helpt ook de opslaglaag niet: JL0002 in elke namespace, zonder uitzondering. Gevonden met twee
scans (wegwerptests buiten de repo): (1) een **padscan** over elk publiek lid van de compile-assets van de plugin
(MediaBrowser.Common, .Controller, .Model, Jellyfin.Data, .Database.Implementations, .Extensions, .MediaEncoding.Keyframes,
Emby.Naming, ICU4N, J2N, NEbml, Polly, Diacritics: 1686 publieke typen) op een tekstparameter met een padnaam (path, file,
folder, dir, output, target, dest, location, root, uri), een bestandsobject (`FileSystemMetadata`, `FileInfo`, `LocalPlugin`,
`SafeFileHandle`) of een stroom als resultaat: 361 treffers, waarvan 250 methoden of constructors; (2) een **bronscan** van
de server (elke plek met `File.`/`Directory.`-schrijven, `new FileStream`, `AsyncFile.Create`, `XmlWriter.Create`,
`SerializeToFile`, de schrijvende `IFileSystem`-leden of een processtart), teruggeleid naar het publieke lid. Opgenomen
(JL0002, nergens):

| Type | Verboden | Waarom |
|---|---|---|
| `IPluginManager` | alles behalve lezen (`GetPlugin`, `Plugins`) | `RemovePlugin` wist `LocalPlugin.Path` recursief; `SaveManifest`/`PopulateManifest` schrijven een manifest op een gekozen pad; `ImportPluginFrom`, `Enable`/`Disable`/`FailPlugin` schrijven het manifest; `LoadAssemblies`/`CreatePlugins` laden code |
| `LocalPlugin` | aanmaken | de constructor neemt elk pad zonder controle; samen met `RemovePlugin`/`UninstallPlugin` een recursieve wis |
| `IInstallationManager` | alles behalve lezen (`Get…`, `FilterPackages`) | `UninstallPlugin` wist de pluginmap, `InstallPackage` wist en pakt een zip uit |
| `IApplicationPaths` | alles behalve lezen (de padeigenschappen) | `CreateAndCheckMarker` maakt een map en een markeerbestand op een gekozen pad; `MakeSanityCheckOrThrow` doet dat in de mappen van de server |
| `IXmlSerializer` | alles behalve `Deserialize…` | `SerializeToFile` doet `new FileStream(pad, FileMode.Create)` |
| `AsyncFile` | `Create`, `OpenWrite` (`OpenRead` mag) | geven een schrijfbare `FileStream` op een gekozen pad |
| `IShortcutHandler` | `Create` (`Resolve` mag) | schrijft een snelkoppelingsbestand op een gekozen pad |
| `FileSystemHelper` | `DeleteFile`, `DeleteEmptyFolders` (`Get…`, `Resolve…` mag) | wissen op een gekozen pad |
| `Jellyfin.Extensions.FileHelper` | alles (`CreateEmpty`) | maakt een bestand aan of **maakt het leeg** (`FileMode.Create`) |
| `IDirectoryService` | alles behalve lezen en `Invalidate` | `Move` doet `Directory.Move` |
| `IMetadataSaver` | alles behalve lezen (`IsEnabledFor`, `GetSavePath`) | `SaveAsync` schrijft nfo/xml naast de media |
| `IMetadataProvider`, `IImageProvider` (en elke leverancier die ervan afleidt) | alles behalve `Supports…`, `GetSupported…`, `Is…`, `Has…`, `Can…`, `To…` | `GetMetadata`/`GetImages` schrijven de cache (AudioDb, Omdb, StudioImages), `GetImage` haalt via ffmpeg een afbeelding uit een bestand, `FetchAsync` wijzigt het item en schrijft een collage |
| `ITranscodeManager` | alles behalve lezen (`GetTranscodingJob`) | `StartFfMpeg` start ffmpeg op een gekozen uitvoerpad en argumenten; `KillTranscodingJobs`, `OnTranscodeEndRequest` wissen de bestanden van een taak |
| `TranscodingJob` | aanmaken, een eigenschap zetten, alles behalve lezen | de server wist bij het stoppen `job.Path`: een eigen taak of een gewijzigd pad wist een gekozen bestand |
| `TranscodingSegmentCleaner`, `ProgressiveFileStream` | aanmaken (en alle leden van de cleaner) | wissen segmenten van een meegegeven taak; de stroom roept bij het sluiten `OnTranscodeEndRequest` aan met een meegegeven taak |
| `IMediaEncoder` | alles behalve lezen (`Get…`, `Supports…`, `EscapeSubtitleFilterPath`), en ook `GetMediaInfo` | `ConvertImage` (uitvoerpad), `Extract…Image…`, `GenerateConcatConfig` (schrijft op een gekozen pad), `SetFFmpegPath`; `GetMediaInfo` start ffprobe |
| `ISubtitleEncoder`, `IAttachmentExtractor`, `EncodingHelper` | alles | halen met ffmpeg ondertitels en bijlagen uit en schrijven de cache; `EncodingHelper.GetInputArgument` schrijft een concat-bestand |
| `IImageProcessor`, `IImageEncoder` | alles behalve lezen (`Get…`, `Supports…`) | `ProcessImage`, `CreateImageCollage` (uitvoerpad in de opties), `EncodeImage` (uitvoerpad), `CreateSplashscreen`, `CreateTrickplayTile` |
| `IClientEventLogger` | alles | schrijft een logbestand (`WriteDocumentAsync`) |
| `FfProbeKeyframeExtractor`, `FfToolKeyframeExtractor` | alles | `GetKeyframeData(ffProbePath, …)` start een **zelfgekozen programma** (langs JL0004 heen) |
| `IListingsProvider`, `ITunerHost`, `ILiveStream` | alles (`ILiveStream`: behalve lezen, `GetStream` mag) | schrijven gids- en kanaalcaches en tijdelijke opnamebestanden |

Gemotiveerd niet opgenomen (scan-treffers die niets schrijven of al bewaakt zijn): Emby.Naming (alleen padnamen ontleden),
`MimeTypes`, `ContainerHelper`, `ConditionProcessor`/`StreamBuilder`, `EncodingJobInfo.GetMimeType`, `PathHelper`,
`IPathManager` (bouwen alleen een pad), `GetInternalMetadataPath`/`GetMappedPath` (rekenen), `ImageProcessingOptions`,
`Playlist.IsPlaylistFile`, `ItemResolveArgs`, `IServerApplicationHost.Expand/ReverseVirtualPath`, de constructors van
DTO's en entiteiten (`ImageInfo`, `Artwork`, `Library`, `MediaFile`, `MediaPathInfo`, `FileSystemEntryInfo`, `VideoFileInfo`:
alleen in het geheugen; opslaan kan alleen via de context, JL0003); lezen: `IBlurayExaminer.GetDiscInfo`,
`MatroskaKeyframeExtractor`, `StreamExtensions.IsFileIdenticalAsync`, `IXmlSerializer.Deserialize…`, de `DirectoryService`-leesleden,
ICU4N (ingebedde gegevens), NEbml (schrijft naar een meegegeven stroom), J2N, Polly, Diacritics; `IImageEncoder.GetImageSize`
en `IImageProcessor.GetImageDimensions` maken hooguit een eigen tijdelijke kopie met een naam van de server.
`ISimilarItemsManager` schrijft zijn cache in de cachemap met een naam uit het item-ID (net als bij elke opvraging van een
gewone client) en `ISchedulesDirectService.GetAvailableCountries` haalt alleen over het netwerk op. Al bewaakt: `IFileSystem`
(JL0002 hierboven), `CollectionFolder.SaveLibraryOptions` en de `Set…`/`Delete…`/`Swap…`-leden van `BaseItem` (JL0001),
`ILibraryManager`, `ILibraryMonitor`, `ITrickplayManager.CreateTiles`, `IBackupService`, `IProviderManager.SaveImage`,
`ISubtitleManager`, `ILyricManager`, `IChapterManager`, `IMediaSourceManager` en de live-tv-beheerders (JL0001; voor
`IProviderManager` alleen een uitzondering per API met een eigen ADR). Hier stond tot herstelronde 7 dat de officiële route
voor de **eigen** plugininstellingen (`BasePlugin<T>.SaveConfiguration`/`UpdateConfiguration`) alleen
`plugins/configurations/<assembly>.xml` schrijft. Dat klopte niet: `ConfigurationFilePath` is
`Path.Combine(PluginConfigurationsPath, ConfigurationFileName)` en `ConfigurationFileName` is virtueel. Eén override liet de
server, al bij het lezen van `Configuration`, een gekozen bestand overschrijven, ook `jellyfin.db` (herreview 6,
R-HARDE-EIS-14a). Nu is zo'n override JL0002 nergens, staat `SaveConfiguration` alleen voor `PluginModuleSwitches` op de witte
lijst, mag `UpdateConfiguration` nergens, en legt `PluginGrensTests` het pad vast (zie "Server-ABI: witte lijst", punt 4).
`BasePlugin.SetAttributes` (de server roept hem bij het laden aan) zet alleen paden in het geheugen; plugincode roept hem niet
aan (JL0001).

De BCL-scan (dezelfde aanpak over de gedeelde frameworks, alleen leden buiten de bestandsnamespaces met een schrijvende naam
en een padparameter: 377 treffers) leverde de BCL-schrijvers hierboven op (`WebClient`, de trace-listeners, `ResourceWriter`,
`ProfileOptimization`, Visual Basic) en `Microsoft.VisualBasic.Interaction.Shell` (JL0004). Niet opgenomen: lezen
(`X509Certificate2` uit een bestand, `PhysicalFileProvider`, de configuratiebronnen, `FileVersionInfo`), Windows-only
(`EventLogSession.ExportLog`, `IPersistFile`), tijdelijke bestanden met een willekeurige naam
(`FileBufferingReadStream`/`WriteStream`) en `SmtpClient` met een ophaalmap (een `<guid>.eml`). Die scan miste eigenschappen
en leden met een Uri-parameter: herreview 6 vond zo `WebClient.Upload…`/`OpenWrite…`, `WebRequest` met een file:-adres en
`DefaultTraceListener.LogFileName` (sinds herstelronde 7 JL0002, zie hierboven). Volgens herreview 6 gaf een scan op zetbare
eigenschappen met een padnaam en schrijvende leden met een Uri-parameter daarbuiten alleen `SmtpClient.PickupDirectoryLocation`,
`W3CLoggerOptions`, de Windows-eventlog en de inhoudsmappen van de hosting; die raken `jellyfin.db` niet.

Tests: `VerbodenApiAnalyzerTests.SlippendeBestandsroutes_ProefHerreview5_ElkeRegelIsJL0002` (de tien routes; in `Core.Storage`
blijven alleen de server-ABI en P/Invoke JL0002), `.Bestandsnamespaces_ElkGebruikBuitenDeWitteLijstIsJL0002` (24 vormen
buiten de witte lijst en de toegestane tegenvormen; in `Core.Storage` niets), `.ServerAbiDieZelfSchrijftOfStart_IsNergensToegestaan`
(31 vormen, ook in `Core.Storage`, met de leesleden ernaast), de ongeldige uitzonderingsregels en de proefregels in
`VerbodenAanroepen.cs`.

#### Dreigingsmodel

De analyzer beschermt de HARDE EIS tegen **fouten in onze eigen plugincode**: een module die per ongeluk een bestand op een
verkeerde plek schrijft, een server-API gebruikt die zelf schrijft, of een databaseverbinding opent. Hij is **geen zandbak**
en geen verdediging tegen kwaadaardige code: wie de grens opzettelijk wil omzeilen, kan dat met een tweede assembly of een
pakket dat zelf schrijft. Binnen dat model zijn de omwegen die triviaal te verbieden zijn nu verboden, **nergens toegestaan**
(ook niet in `Core.Storage`, geen uitzondering), met JL0002 en de melding "omzeilt de bouwgrens":

- native code: een methode met `[DllImport]`, `[LibraryImport]` of `extern` (de declaratie en elke aanroep), `unsafe` (op
  een type, lid, lokale functie, blok of using-alias; pointers, `fixed` en functiewijzers `delegate*` kunnen alleen daarin
  bestaan), `NativeLibrary` en `Marshal`;
- reflectie die een lid aanroept of een type uit een tekst haalt: `MethodBase.Invoke` (ook `ConstructorInfo.Invoke`),
  `MethodInfo`/`Delegate.CreateDelegate`, `PropertyInfo`/`FieldInfo.SetValue`/`GetValue`, `EventInfo.Add`/`RemoveEventHandler`,
  `Type.InvokeMember`, `Type.GetType` en `Assembly.GetType`, `Delegate.DynamicInvoke`, `LambdaExpression.Compile`;
- code laden of maken: `Assembly.Load…`/`LoadFrom`/`LoadFile`/`UnsafeLoadFrom`/`CreateInstance`, `AssemblyLoadContext`,
  `AppDomain.Load`/`ExecuteAssembly`/`CreateInstance…`, System.Reflection.Emit;
- een object van een willekeurig type maken: `Activator`, `ActivatorUtilities`;
- `dynamic` (een lid, aanroep, index of aanmaak die pas bij het draaien wordt gebonden);
- sinds herstelronde 8 (herreview 7, grenzen 2 en 3): reflectie in een Microsoft- of BCL-bibliotheek die een eigenschap van een
  willekeurig (ook een levend server)object zet of leest: `ConfigurationBinder.Bind` en `Get`, `TypeDescriptor` (elk lid) en
  `PropertyDescriptor.SetValue`/`GetValue`/`ResetValue`, `EventDescriptor.AddEventHandler`/`RemoveEventHandler`;
  `DispatchProxy` (`Create` maakt bij het draaien een implementatie van een serverinterface zonder eigen klasse, langs de regel
  voor uitbreidingspunten heen); System.Linq.Expressions (elk lid: een boom met een aanroep, aanmaak of toewijzing opbouwen en
  compileren of via een `IQueryable`-provider laten uitvoeren roept een lid aan buiten de analyzer om; een lambda die de compiler
  naar een expressieboom omzet, ziet de analyzer gewoon); `Unsafe` (het beheerde equivalent van `unsafe`: `Unsafe.As` geeft een
  serverobject onder een eigen type met dezelfde velden); en modelbinding op een bestaand object
  (`ControllerBase.TryUpdateModelAsync`, `ModelBindingHelper`), net als `ConfigurationBinder.Bind`. Wat deze lijst niet dekt:
  reflectie binnen een andere bibliotheek die een bestaand object vult (bijvoorbeeld een serializer die een eigenschap van een
  bestaand object vult); zie "Grenzen".

De plugin gebruikt geen van deze (gecontroleerd met grep en met de build: geen `DllImport`, `LibraryImport`, `unsafe`,
`delegate*`, `Marshal`, `NativeLibrary`, `Activator`, `dynamic` of `Assembly.Load` in `plugins/JellyLeon/src`), dus er is geen
uitzondering nodig. Wat de plugin wel aan reflectie gebruikt blijft toegestaan, omdat het alleen metadata leest: de versie en
de kenmerken van de eigen assembly (`Assembly.GetName`, `GetCustomAttributes`), `typeof(…).Namespace`, `GetType().Name` en
`GetService(typeof(…))`. Test: `VerbodenApiAnalyzerTests.Omwegen_NativeCodeReflectieEnDynamic_ZijnNergensToegestaan` (23
vormen, buiten en binnen `Core.Storage`, plus de toegestane reflectie) en, voor de omwegen van herstelronde 8,
`HttpLaagTests.Omwegen_ReflectieInBibliotheken_DispatchProxyEnExpressies_ZijnNergensToegestaan` (de vormen van grens 2 en 3 van
herreview 7 en de varianten, buiten en binnen `Core.Storage`). Ook die gebruikt de plugin niet (grep op `ConfigurationBinder`,
`TypeDescriptor`, `DispatchProxy`, `System.Linq.Expressions` en `Unsafe` in `plugins/JellyLeon/src`, en de pluginbouw).

### 2. Witte lijst: één API in één klasse

`JellyLeon.AnalyzerUitzonderingen.txt` naast het pluginproject, één regel per uitzondering:
`<regel-id> <Type.Methode> <volledige klassenaam>`. Geen jokertekens en geen namespaces; de klasse moet onder
`Jellyfin.Plugin.JellyLeon.Modules` liggen. Een regel die niet past (onbekende API, een API die nergens mag, een klasse
buiten de modules, een dubbele regel, een verkeerde vorm) is zelf een bouwfout en staat niets toe. Zo volgt de lijst de
tabel uit het plan: F3 krijgt straks precies `ResetPlaybackStreamSelections`/`SaveUserData` in `SelectionGuard`,
`QueueRefresh` in `PublishTransaction` en `File.Delete` in `Depublisher`; Quality krijgt niets. Voor JL0002 kan een
uitzondering alleen op `File`, `Directory`, `FileInfo`/`DirectoryInfo` en `IFileSystem`; een ander lid uit de
bestandsnamespaces, de server-ABI die zelf schrijft, een omweg en databasetoegang kennen er geen (JL0009).

**Stand golf 1: de lijst is leeg.** Kern, Devices en Quality bouwen zonder één uitzondering. Elke latere regel hoort
bij een taak uit het plan en een eigen ADR.

### 3. Drie soorten bewijs

1. **De plugin bouwt** met de analyzer aan: er staat geen verboden aanroep in.
2. **De proefassembly faalt**: `VerbodenAanroepen.cs` bevat 295 verboden aanroepen, elk gemarkeerd met
   `// VERWACHT: JLxxxx`, afgewisseld met toegestane aanroepen (sinds herstelronde 7 is lezen van de server-ABI buiten de
   witte lijst ook verboden en dus gemarkeerd; toegestaan zijn bestanden lezen, constanten, typenamen en een lid dat in die
   klasse op de witte lijst staat). `analyzer_proef.py` bouwt het project echt en eist
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

- Een analyzer is **geen zandbak** (zie "Dreigingsmodel"): hij beschermt tegen fouten in onze eigen code, niet tegen
  opzet. Reflectie die een lid aanroept, `dynamic`, eigen P/Invoke, `unsafe`, code laden en `Activator` zijn sinds
  herstelronde 6 JL0002, maar wat hij niet ziet blijft: een **tweede assembly** of een **pakket** dat zelf een bestand
  schrijft (elke nieuwe `PackageReference` van de plugin hoort daarom in een review; nu alleen de plugin-ABI en
  Microsoft.Data.Sqlite.Core), en een bestandsschrijver in de BCL buiten de bestandsnamespaces die de scan niet vond (de scan zocht op schrijvende namen
  met een padparameter; zie "Bestanden (JL0002)"), en reflectie binnen een bibliotheek die niet als omweg op de lijst staat
  (bijvoorbeeld een serializer die een eigenschap van een bestaand object vult; `ConfigurationBinder`, `TypeDescriptor`,
  `DispatchProxy`, System.Linq.Expressions, `Unsafe` en `TryUpdateModelAsync` staan er sinds herstelronde 8 wel op). Daarom
  blijven de andere lagen bestaan: de schrijfgrens in `Core.Storage` tijdens het draaien (`InternalWriteScope` voor
  bestanden en `JlDatabase` voor SQLite weigeren elk pad buiten `<DataPath>/jelly-leon/**`, `/cache/jelly-leon/**` en
  `/run/jelly-leon/**` (`JlPaths.MagSchrijven`), voordat er iets geopend of aangemaakt is), de alleen-lezen mediamount,
  en JLT-65 (stock en fork naast elkaar; de 12.x-tabellen mogen alleen op de toegestane lijst afwijken).
- JL0003 op de databasedienst van de server werkt op de typenaam: de grens ligt waar de dienst de klasse binnenkomt
  (veld, parameter, `GetService<T>`). Regels die daarna een eenmaal gekregen object gebruiken zonder de naam te noemen
  (`_db.PurgeDatabase(…)`), gaven zelf geen tweede melding; sinds herstelronde 7 zijn ze JL0001 (een lid van een servertype
  buiten de witte lijst). Gebruiken ze daarbij een lid van Entity Framework Core
  (`….CreateDbContext().Database.ExecuteSqlRaw(…)`, `SaveChanges`), dan is die regel sinds herstelronde 5 wel JL0002
  (databasetoegang). Wie de dienst zonder de naam ophaalt (reflectie,
  `GetService(Type)` met een type uit een tekst, `dynamic`), is sinds herstelronde 6 JL0002 (omweg); de padgrens van
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
  waarde uit de configuratie. Daarvoor is de padgrens van `JlDatabase` en `InternalWriteScope` er; `jellyfin.db` en
  `library.db` liggen buiten de eigen mappen. Dat houdt alleen omdat elke verbinding via `JlDatabase` loopt en elk
  bestand via de opslaglaag wordt geschreven: elke andere weg naar een verbinding is buiten `Core.Storage` JL0002 (zie
  "Databasetoegang (JL0002)"), elk ander bestandslid buiten de witte lijst ook (zie "Bestanden (JL0002)"), de server-ABI
  die zelf schrijft is nergens toegestaan, en de verbinding van `JlDatabase` kan met SQL geen tweede database koppelen
  (`ATTACH`, `VACUUM INTO`). Code in `Core.Storage` en `Core.Secrets` zelf valt niet onder de bestandsregel (wel onder de
  server-ABI- en omwegregel) en hoort daarom alleen de opslaglaag te bevatten (`JlDatabase`, `CoreDatabase`, `JlPaths`,
  `InternalWriteScope`, `SecretStore`). Of code vrijgesteld is, hangt af van de namespace in de broncode (herreview 6, nieuwe
  grens 1): een bestand waar dan ook in de plugin met `namespace …Core.Storage` (of `Core.Secrets`, `Core.Werker`) krijgt de
  vrijstelling. Daarom legt `PluginGrensTests.VrijgesteldeNamespaces_BevattenPreciesDeOpslaglaagEnDeWerkerinterface` de typen
  in die drie namespaces vast (`JlDatabase`, `CoreDatabase`, `JlPaths`, `InternalWriteScope`, `SecretStore`, `IWerker`,
  `GeenWerker`); een nieuw type faalt die test tot het in een review is bekeken.
- **Kindproces uit `Core.Werker`** (herreview 6, nieuwe grens 2): JL0004 staat processen alleen in `Core.Werker` toe. Zo'n
  proces valt buiten de bestandsregel en de padgrens en schrijft waar zijn argumenten zeggen (bijvoorbeeld `-y <pad>`). Nu
  start `Core.Werker` niets (alleen `GeenWerker`). De werkerbewaker van B03-018 moet dit bij het draaien dragen: zie ADR-0035,
  kop "Grens: een kindproces schrijft buiten de analyzer om".
- Hij bewaakt methoden **en** het schrijven van eigenschappen: `item.Name = …` op een `BaseItem` is JL0001 (proefregels in
  `VerbodenAanroepen.cs`), omdat een `BaseItem` gedeeld is met de cache van de server en de server het item later zelf kan
  opslaan. Tot herstelronde 7 stond hier dat eigenschappen van **entiteiten** die een server-API teruggeeft (`User`,
  `UserItemData`, `DisplayPreferences`, de rijen in `BaseItem.UserData`) niet bewaakt werden, met een open besluit. Dat is
  gesloten: een eigenschap of veld van elk servertype zetten is nu JL0001, ook van entiteiten en van `SessionInfo` (zie
  "Server-ABI: witte lijst", punt 2). Wat blijft (herreview 7, grens 4): een lijst of object van de server dat plugincode via
  een BCL-lid wijzigt. `gebruiker.AccessSchedules.Clear()` in `KidPolicy` en `e.Users.Clear()` in `DevicesListener` geven geen
  melding: `Clear` is een lid van `ICollection<T>`, geen servertype. In v12.4 is er geen pad dat zo'n wijziging opslaat, maar dat
  leunt op twee dingen in de serverbron: de `User` in `KidPolicy` komt via `AuthorizationContext` uit `UserManager.GetUserById`,
  dat elke keer een nieuwe kopie geeft (`AsNoTracking`) die de server nooit aan `UpdateUserAsync` doorgeeft; en
  `UpdateUserAsync` neemt `AccessSchedules` wel uit het object in het geheugen over (`dbUser.AccessSchedules.Clear()` en opnieuw
  toevoegen). `e.Users` gebruikt de server na `QueueEventIfNotNull` niet meer. Komt er een regel op de witte lijst die een
  `User` of ander serverobject geeft dat de server daarna zelf opslaat, of verandert een van die twee dingen bij een
  upstream-sync, dan is dit een weg. De plugin wijzigt zulke lijsten niet; JLT-65 vangt het bij het draaien.
- De witte lijst van de server-ABI ziet operaties met een lid. Een impliciete aanroep op een servertype ziet hij niet: de
  enumerator van `foreach` over een eigen collectietype van de server, `Dispose` via `using`, `Deconstruct`, een eigen
  `await`er. Ook een expliciete aanroep van een lid van een Microsoft- of BCL-interface die een servertype implementeert, ziet
  hij niet (herreview 7, grens 1): het lid hoort bij `IHostedService` of `IAsyncDisposable`, niet bij het servertype.
  `h.StopAsync(stop)` op `GetServices<IHostedService>()` en `((IAsyncDisposable)sessies).DisposeAsync()` geven geen melding.
  Nagelopen in v12.4: de hosted services van de server (`DeviceAccessHost`, `NfoUserDataSaver`, `RecordingsHost`,
  `RecordingNotifier`, `UserDataChangeNotifier`, `LibraryChangedNotifier`, `AutoDiscoveryHost`) melden events aan of af of doen
  wat elke start doet, en `SessionManager.DisposeAsync` ruimt sessies en timers op. Er is geen pad gevonden dat kijkgegevens
  schrijft of wist; wel gaat functie verloren (nieuwe kijkgegevens worden dan niet meer vastgelegd). De lijst geldt per
  klassenaam: een `partial` deel van een klasse op de lijst krijgt dezelfde rechten (dat hoort in de review). Plugincode kan via
  `RegisterServices` Microsoft-uitbreidingspunten registreren die niet bij de HTTP-laag horen (`IHostedService`,
  `IConfigureOptions<T>` op andere instellingen); dat zijn geen servertypen. `IStartupFilter` en de andere uitbreidingspunten van
  de HTTP-laag vallen sinds herstelronde 8 onder "HTTP-laag en netwerk". Een serverdienst vervangen vraagt een eigen implementatie
  van de serverinterface en is dus JL0001; zonder eigen klasse kon dat alleen met `DispatchProxy`, en dat is sinds herstelronde 8
  een omweg (JL0002).
- De regel voor de HTTP-laag (sinds herstelronde 8) noemt de uitbreidingspunten, leden en namespaces waarlangs een verzoek aan de
  server, de gebruiker of de argumenten van een serveractie te wijzigen zijn; het is een opsomming, geen witte lijst van heel
  ASP.NET Core. Wat hij niet dekt: het antwoord van de server (koppen, status en body van een antwoord zetten mag, de plugin
  schrijft zo zijn eigen antwoorden), een lid dat alleen leest (`HttpRequest.Path`, `Query`, `Form`, `IHttpContextAccessor`
  lezen), attributen op eigen code, de instellingen van Kestrel, doorgestuurde koppen en andere hosting (geen kijkgegevens), en
  een netwerkclient buiten System.Net.Http, .Sockets, .WebSockets en .Quic en buiten `WebClient`/`WebRequest` (bijvoorbeeld
  `SmtpClient`, `Ping`). Een klasse op de witte lijst van de HTTP-laag heeft alleen het genoemde lid of uitbreidingspunt; wat zij
  daarbinnen doet (de spike roept na de controle `volgende(http)` aan) bewaakt de runtime-test van de spike, niet de analyzer.
- Ongewijzigd (herreview 7, grens 5): een tweede assembly of een pakket dat zelf schrijft (zie de eerste grens), een kindproces
  uit `Core.Werker` (zie de grens daarover hierboven en ADR-0035), een koppeling die tussen de controle en het openen ontstaat (TOCTOU) en een
  harde koppeling (zie de padgrens hierboven).
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
- De officiële route om **eigen** plugininstellingen op te slaan (`BasePlugin<T>.SaveConfiguration`) staat alleen voor
  `PluginModuleSwitches` op de witte lijst, en het pad ligt vast (een override is JL0002, `PluginGrensTests` toetst het pad);
  er staan geen geheimen in (ADR-0031).

## Gevolgen

- Elke nieuwe module begint zonder één lid van de server: ook lezen vraagt een regel op de witte lijst van de server-ABI,
  met motivatie in deze ADR en een review; een schrijfuitzondering kost een regel, een ADR en een review.
- B03-018 plaatst de werkerbewaker in `Core.Werker`; nergens anders kan plugincode een proces starten.
- Een nieuwe middleware, een filter of een ander uitbreidingspunt van de HTTP-laag vraagt een regel op de witte lijst van de
  HTTP-laag, alleen voor eigen pluginpaden, met motivatie in deze ADR, een runtime-test en een review. Een netwerkclient (straks
  de MediaGuard-vervoerder) vraagt een transportklasse met een eigen ADR en een test dat zij loopback, het eigen serveradres en
  link-local weigert.
- CI: de job "Plugins bouwen en testen" draait de solution (plugin schoon), de tests en `analyzer_proef.py --bouw`.

## Alternatieven

- **`Microsoft.CodeAnalysis.BannedApiAnalyzers`**: kent geen "alles behalve lezen" per interface en geen uitzondering
  per klasse; elke nieuwe upstream-methode zou vanzelf toegestaan zijn. Afgewezen.
- **Alleen een test die de IL doorzoekt**: vindt het pas na de build en geeft geen regelnummer. Afgewezen als enige
  laag.
- **Generator in Python in de runtime-image**: de runtime-image heeft geen Python buiten de werker; de web-bouwstap
  heeft Node al. Afgewezen.
