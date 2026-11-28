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
  Bijgewerkt 2026-11-17 na herreview 8 (S-G1-17 herstelronde 9, R-HARDE-EIS-18 en -19; besluit van de regisseur, optie A): de
  browser als tussenpersoon staat onder "Dreigingsmodel" en "Grenzen". Een ingebedde webbron vraagt alleen eigen paden via een
  fail-closed `vraag()`, een antwoord dat de browser doorstuurt (redirect, Location-kop, 3xx) is JL0001, en elk optietype van de
  host (zoals `JsonOptions`, ook als typeargument en als eigen `IPostConfigureOptions<T>`) is JL0001 met een lege witte lijst.
  Bijgewerkt 2026-11-17 na herreview 9 (S-G1-17 herstelronde 10, R-HARDE-EIS-20; besluit van de regisseur, optie A): een eigen
  actie kon de browser nog doorsturen met een status uit een variabele en de kopnaam uit System.Net, zonder één JL-fout. Nu
  weigert de wacht tegen doorsturen (`DoorstuurWacht`) bij het draaien elk antwoord met een 3xx of een kop Location, ongeacht het
  type resultaat: op elke actie met `[JlRoute]`, en met de spike op elk pluginpad. System.Net valt onder punt 8 (ook elke
  3xx-waarde van `HttpStatusCode`). De zin onder "Grenzen" over een kopnaam die pas bij het draaien ontstaat is gecorrigeerd, en
  er staan twee grenzen bij: een open generieke registratie van de optie-infrastructuur en `fetch` zonder `fetch(` in een webbron.
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
| `User` | `Id` | `Core.Privacy.KidPolicy` | Identificeert de profielbeslissing via het bestaande accountpseudoniem. |
| `UserEntityExtensions` | `GetPreference` | `Core.Privacy.KidPolicy` | Leest de geblokkeerde tags uit de voorkeuren van de entiteit. |
| `IUserManager` | `GetUserById` | `Core.Privacy.KidPolicy` | Leest één bestaand account bij het beoordelen van een voorstel. De serverquery gebruikt `AsNoTracking`. |
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

| `SimilarItemsQuery` | `User`, `Limit` | `Modules.Recommendations.SimilarProvider` | Controleert de gebruikerscontext en de gevraagde limiet. |
| `BaseItem` | `Id` | `Modules.Recommendations.SimilarProvider` | Controleert of de bron een bibliotheekitem is. |
| `User` | `Id` | `Modules.Recommendations.AanbevelingsBibliotheek` | Identificeert uitsluitend de vrager voor de smaaktoestand en de vaste exploratieplek. |
| `SimilarItemsQuery` | `User`, `Limit`, `ExcludeItemIds` | `Modules.Recommendations.AanbevelingsBibliotheek` | Leest de vrager, paginagrens en uitsluitingen uit het hostverzoek. |
| `ILibraryManager` | `GetVirtualFolders`, `GetItemById`, `GetItemList`, `GetPeopleByItems`, `GetLibraryOptions` | `Modules.Recommendations.AanbevelingsBibliotheek` | Leest de providerkeuze voor de bron, controleert de map met de vrager en leest zichtbare items en hun betrokken personen. |
| `LibraryOptions` | `GetTypeOptions` | `Modules.Recommendations.AanbevelingsBibliotheek` | Zoekt de configuratie van het mediatype van de bron. |
| `TypeOptions` | `SimilarItemProviderOrder`, `SimilarItemProviders` | `Modules.Recommendations.AanbevelingsBibliotheek` | Leest de expliciete volgorde of de gebruikte selectielijst vóór een metadatalezing. |
| `VirtualFolderInfo` | `CollectionType`, `ItemId` | `Modules.Recommendations.AanbevelingsBibliotheek` | Selecteert film-, serie- en collectiemappen. |
| `BaseItem` | `Id`, `Genres`, `Tags`, `Studios`, `OfficialRating`, `CommunityRating`, `ProductionLocations`, `ProductionYear`, `DateCreated`, `RunTimeTicks` | `Modules.Recommendations.AanbevelingsBibliotheek` | Leest kenmerken, identiteit, versheid en duur voor de fractie van het hervatpunt. |
| `Movie` | `CollectionName` | `Modules.Recommendations.AanbevelingsBibliotheek` | Leest de bestaande metadatanaam van een filmcollectie. |
| `PersonInfo` | `IsType`, `Name`, `SortOrder` | `Modules.Recommendations.AanbevelingsBibliotheek` | Onderscheidt regisseurs, schrijvers en acteurs en bepaalt de eerste vijf acteurs. |
| `Folder` | `GetLinkedChildren` | `Modules.Recommendations.AanbevelingsBibliotheek` | Leest per zichtbare collectie de voor de vrager toegankelijke leden. |
| `IUserDataManager` | `GetUserDataBatch`, `GetUserDataDto` | `Modules.Recommendations.AanbevelingsBibliotheek` | Leest de huidige toestand per item voor de vrager en de door Jellyfin berekende seriestatus. |
| `UserItemData` | `Played`, `IsFavorite`, `Rating`, `Likes`, `PlaybackPositionTicks`, `LastPlayedDate` | `Modules.Recommendations.AanbevelingsBibliotheek` | Leest bestaande signalen en het tijdstip voor verval, zonder de toestand te bewaren. |
| `UserItemDataDto` | `Played` | `Modules.Recommendations.AanbevelingsBibliotheek` | Leest of de vrager een serie volledig heeft bekeken. |
| `ITVSeriesManager` | `GetNextUp` | `Modules.Recommendations.AanbevelingsBibliotheek` | Leest volgende afleveringen uit de expliciet toegankelijke seriemappen. |
| `QueryResult` | `Items` | `Modules.Recommendations.AanbevelingsBibliotheek` | Leest de door de host gevonden volgende afleveringen. |
| `Episode` | `SeriesId` | `Modules.Recommendations.AanbevelingsBibliotheek` | Sluit de bijbehorende serie uit de aanbevelingen uit. |
| `DtoOptions` | `new` met `EnableImages` | `Modules.Recommendations.AanbevelingsBibliotheek` | Vraagt metadata zonder afbeeldingen. Alleen de initialisatie van een nieuw queryobject is toegestaan. |
| `InternalItemsQuery` | `new` met `ParentId`, `Recursive`, `IncludeItemTypes`, `EnableTotalRecordCount`, `DtoOptions` | `Modules.Recommendations.AanbevelingsBibliotheek` | Vraagt films en series binnen één geautoriseerde bibliotheek. Alleen de initialisatie van een nieuw queryobject is toegestaan. |
| `NextUpQuery` | `new` met `User` | `Modules.Recommendations.AanbevelingsBibliotheek` | Bindt een nieuwe Next Up-leesvraag aan de vrager. Alleen de initialisatie van een nieuw queryobject is toegestaan. |
| `BaseItem` | `Genres` | `SimilarProefRegistrator` | Alleen de proefbouw leest het bronkenmerk voor de synthetische foutinjectie. |
| `IUserDataManager` | `UserDataSaved` | `SimilarProefRegistrator` | In SimilarProef luistert de waarnemer naar bewaargebeurtenissen op de wegwerpserver. |
| `UserDataSaveEventArgs` | `SaveReason` | `SimilarProefRegistrator` | In SimilarProef noteert de waarnemer uitsluitend de reden van de gebeurtenis. |
| `BaseExtensions` | `GetMD5` | `Modules.Segments.SegmentProvider` | F6-S1, ADR-0037. |
| `ILibraryManager` | `GetCollectionFolders` | `Modules.Segments.SegmentProvider` | F6-S1, ADR-0037. |
| `BaseItem` | `Id` | `Modules.Segments.SegmentProvider` | F6-S1, ADR-0037. |
| `MediaSegmentGenerationRequest` | `ItemId` | `Modules.Segments.SegmentProvider` | F6-S1, ADR-0037. |
| `MediaSegmentDto` | `new` | `Modules.Segments.SegmentProvider` | F6-S1, ADR-0037. |
| `IMediaSegmentManager` | `GetSupportedProviders`, `GetSegmentsAsync` | `Modules.Segments.SegmentPublicatie` | F6-S1, ADR-0037. |
| `LibraryOptions` | `new` | `Modules.Segments.SegmentPublicatie` | F6-S1, ADR-0037. |
| `MediaSegmentDto` | `Type`, `StartTicks`, `EndTicks`, `Id` | `Modules.Segments.SegmentPublicatie` | F6-S1, ADR-0037. |
| `BaseItem` | `Id` | `Modules.Segments.SegmentPublicatie` | F6-S1, ADR-0037. |
| `IUserManager` | `GetUserById` | `Modules.Segments.SegmentBibliotheek` | Vereist het bestaande account voor de itemrechten. |
| `Episode` | `SeriesId` | `Modules.Segments.SegmentBibliotheek` | F6-S1, ADR-0037. |
| `ILibraryManager` | `GetItemById`, `GetCollectionFolders`, `GetVirtualFolders`, `GetItemList`, `ItemAdded`, `ItemUpdated`, `ItemRemoved` | `Modules.Segments.SegmentBibliotheek` | F6-S1, ADR-0037. |
| `BaseItem` | `Id`, `RunTimeTicks`, `ParentIndexNumber`, `IndexNumber`, `DateModified`, `ProviderIds` | `Modules.Segments.SegmentBibliotheek` | F6-S1, ADR-0037. |
| `VirtualFolderInfo` | `ItemId`, `Locations` | `Modules.Segments.SegmentBibliotheek` | F6-S1, ADR-0037. |
| `InternalItemsQuery` | `new` | `Modules.Segments.SegmentBibliotheek` | F6-S1, ADR-0037. |
| `IChapterRepository` | `GetChapters` | `Modules.Segments.SegmentBibliotheek` | F6-S1, ADR-0037. |
| `ChapterInfo` | `StartPositionTicks`, `Name` | `Modules.Segments.SegmentBibliotheek` | F6-S1, ADR-0037. |

WT-1 voegt de volgende klassegebonden leden toe. De drie groepsmutaties en het afspeelverzoek geven de argumenten van upstream door. Alleen de server beheert de afspeelstatus.

| Type | Leden | Klasse | Gebruik |
|---|---|---|---|
| `ISyncPlayManager` | `NewGroup`, `JoinGroup`, `LeaveGroup`, `GetGroup`, `ListGroups`, `HandleRequest`, `IsUserActive` | `Modules.WatchTogether.WatchDecorator` | Verwerkt uitsluitend het oorspronkelijke sessieverzoek. |
| `ISessionManager` | `Sessions` | `Modules.WatchTogether.WatchDecorator` | Leest de servertoestand voor lidmaatschap, de zelftest of de gebruikersroute. |
| `SessionInfo` | `Id`, `UserId`, `UserName` | `Modules.WatchTogether.WatchDecorator` | Leest de servertoestand voor lidmaatschap, de zelftest of de gebruikersroute. |
| `GroupInfoDto` | `GroupId`, `Participants` | `Modules.WatchTogether.WatchDecorator` | Leest de servertoestand voor lidmaatschap, de zelftest of de gebruikersroute. |
| `JoinGroupRequest` | `GroupId` | `Modules.WatchTogether.WatchDecorator` | Leest de servertoestand voor lidmaatschap, de zelftest of de gebruikersroute. |
| `ISyncPlayManager` | `GetGroup`, `ListGroups`, `IsUserActive` | `Modules.WatchTogether.WatchController` | Leest de servertoestand voor lidmaatschap, de zelftest of de gebruikersroute. |
| `ISessionManager` | `Sessions` | `Modules.WatchTogether.WatchController` | Leest de servertoestand voor lidmaatschap, de zelftest of de gebruikersroute. |
| `SessionInfo` | `new`, `UserId`, `UserName` | `Modules.WatchTogether.WatchController` | Geeft een leesvraag de geauthenticeerde identiteit, ook vóór de eerste afspeelsessie na een herstart. Alleen het eigen tijdelijke object krijgt deze velden bij de initialisatie. |
| `ListGroupsRequest` | `new` | `Modules.WatchTogether.WatchController` | Leest de servertoestand voor lidmaatschap, de zelftest of de gebruikersroute. |
| `GroupInfoDto` | `GroupId`, `GroupName`, `Participants`, `State` | `Modules.WatchTogether.WatchController` | Leest de servertoestand voor lidmaatschap, de zelftest of de gebruikersroute. |
| `IUserManager` | `GetUsers` | `Modules.WatchTogether.WatchBewaking` | Leest de servertoestand voor lidmaatschap, de zelftest of de gebruikersroute. |
| `ISessionManager` | `SessionEnded` | `Modules.WatchTogether.WatchBewaking` | Leest de servertoestand voor lidmaatschap, de zelftest of de gebruikersroute. |
| `SessionEventArgs` | `SessionInfo` | `Modules.WatchTogether.WatchBewaking` | Leest de servertoestand voor lidmaatschap, de zelftest of de gebruikersroute. |
| `User` | `Username`, `SyncPlayAccess` | `Core.Http.JellyfinSessionAuthenticator` | Leest de servertoestand voor lidmaatschap, de zelftest of de gebruikersroute. |

Witte lijst van uitbreidingspunten (`Regels.UitbreidingWitteLijst`):

| Servertype | Namespace (exact) | Motivatie |
|---|---|---|
| `ISyncPlayManager` | `Jellyfin.Plugin.JellyLeon.Modules.WatchTogether` | WT-1 omhult uitsluitend de bestaande SyncPlay-singleton. |
| `BasePlugin<T>` | `Jellyfin.Plugin.JellyLeon` | De ene pluginklasse (`Plugin`, ADR-0016). |
| `IHasWebPages` | `Jellyfin.Plugin.JellyLeon` | De configuratiepagina van `Plugin`. |
| `IPluginServiceRegistrator` | `Jellyfin.Plugin.JellyLeon` | De registratie van Core en de modules. |
| `BasePluginConfiguration` | `Jellyfin.Plugin.JellyLeon.Configuration` | `PluginConfiguration` (alleen schakelaars en instellingen, nooit een geheim). |
| `IEventConsumer<UserDeletedEventArgs>` | `Jellyfin.Plugin.JellyLeon.Core.Privacy` | `UserDeletedConsumer` wist de eigen gegevens van een verwijderde gebruiker (c09698f09). Alleen dit typeargument; een consumer van een ander event is JL0001. Stond niet in het voorstel van herreview 6, maar de plugin gebruikt het al sinds golf 1. |

| `ILocalSimilarItemsProvider<T>` | `Jellyfin.Plugin.JellyLeon.Modules.Recommendations` | Lokale aanbevelingen voor `Movie` en `Series`. |
| `IMediaSegmentProvider` | `Jellyfin.Plugin.JellyLeon.Modules.Segments` | De extractietaak leest de vrijgegeven set (ADR-0037). |

Microsoft-typen zijn geen server-ABI en vallen niet onder deze regel: `IHostedService` (`DevicesListener`, `MediaGuardPoller`,
`BatchPlanner`); zie "Grenzen". `IStartupFilter` (de spike van ADR-0033) en de andere uitbreidingspunten van de HTTP-laag vallen
sinds herstelronde 8 onder een eigen regel met een eigen witte lijst (zie "HTTP-laag en netwerk"). Een toekomstig uitbreidingspunt voor de planner (`IScheduledTask`) vraagt een eigen ADR.

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
   standaard- of terugvalpolicy), `AuthenticationOptions` en `AuthenticationBuilder` (een schema of het standaardschema). Het lid
   in de lambda telt; sinds herstelronde 9 is ook de registratie `Configure<T>` met zo'n optietype JL0001 (punt 9).
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
   De antwoordkoppen (`HttpResponse.Headers`) vallen er niet onder, behalve de kop Location (punt 8).
8. **Een antwoord dat de browser doorstuurt** (sinds herstelronde 9, R-HARDE-EIS-18; eigen melding "stuurt de browser door"), in
   elke namespace, zonder witte lijst: elk lid of elke aanmaak van een type uit Microsoft.AspNetCore of Microsoft.Net.Http.Headers
   waarvan de naam van het lid of van het type `Redirect`, `Location`, `Created` of `Accepted` bevat (`Redirect`,
   `RedirectPreserveMethod`, `RedirectPermanentPreserveMethod`, `LocalRedirect…`, `RedirectTo…PreserveMethod`,
   `HttpResponse.Redirect(…, preserveMethod: true)`, `Results.Redirect`, `RedirectResult` en `PreserveMethod`,
   `IHeaderDictionary.Location`, `HeaderNames.Location`, `Created…`, `Accepted…`), een constante `StatusCodes.Status3…`, een
   constante statuscode van 300 tot en met 399 op een eigenschap `StatusCode` of een parameter `statusCode` (`StatusCode = 307`,
   `StatusCode(308)`, `new StatusCodeResult(307)`), en de tekst `Location` als constante (hoofdletters tellen niet, ook
   samengesteld of met `nameof`; zo krijgt ook een eigen woordenboek of `JlResult.Headers` die kop niet). Niet alleen de varianten
   "PreserveMethod": Chrome volgde in een proef (2026-11-17, eigen stand-in op loopback) bij `DELETE` een 301, 302, 307 en 308
   met `DELETE` en hetzelfde Authorization-token, en een 303 met `GET` en hetzelfde token. Sinds herstelronde 10 (herreview 9,
   R-HARDE-EIS-20) valt ook System.Net (met alles eronder) onder deze regel: `HttpResponseHeader.Location` (het BCL-equivalent van
   `HeaderNames.Location`), en elke waarde van 300 tot en met 399 van `HttpStatusCode` (`Regels.DoorstuurStatusEnums`), ook
   `Found`, `SeeOther` en `MultipleChoices`, waarvan de naam geen van de woorden bevat. Wat de analyzer niet ziet, is een status of
   kopnaam die pas bij het draaien ontstaat (`StatusCode((int)status)` met `status` uit een variabele, `int code = 307`, een
   samengestelde kopnaam). Daarvoor is er een tweede laag bij het draaien, fail-closed. `JlResult` weigert een 3xx-status voordat
   er iets geschreven is. De **wacht tegen doorsturen** (`Core.Http.DoorstuurWacht`) kijkt naar het antwoord zelf, vlak voordat de
   koppen vertrekken (`Response.OnStarting`), ongeacht het type resultaat (`StatusCodeResult`, `ObjectResult`, `RedirectResult`,
   zelf geschreven). `JlRouteAttribute` zet die wacht op elke eigen actie en is daarvoor ook resultaatfilter; de spike van ADR-0033
   zet hem op elk pluginpad als die aan staat. Een status van 300 tot en met 399 of een kop Location wordt de vaste fout 503
   `dependency_unavailable` met `Cache-Control: no-store`, zonder Location en zonder de body van de actie: als JSON uit de
   foutcatalogus als de actie nog niets schreef, anders zonder body (de wacht zet Content-Length 0, Kestrel weigert daarom de body
   van de actie voordat de koppen vertrekken, en neemt daarna geen tweede body aan). Alleen de wacht mag `HeaderNames.Location`
   gebruiken, en alleen als argument van `ContainsKey` of `Remove` op `HttpResponse.Headers` (`Regels.DoorstuurWitteLijst`, zie de
   tabel hieronder); zetten, toevoegen of teruggeven blijft ook daar JL0001. De plugin gebruikt geen van deze vormen.
9. **De instellingen van de host** (sinds herstelronde 9, R-HARDE-EIS-19; eigen melding "gebruikt een instelling van de host"), in
   elke namespace: elk type uit Microsoft.AspNetCore (met alles eronder) waarvan de naam op `Options` eindigt, plus
   `Microsoft.Extensions.Hosting.HostOptions`. Daaronder vallen `Mvc.JsonOptions` (de JSON-invoer van elke serveractie),
   `Http.Json.JsonOptions`, `ApiBehaviorOptions`, `ForwardedHeadersOptions`, `KestrelServerOptions`, `MvcOptions`,
   `AuthorizationOptions` en `AuthenticationOptions`. JL0001 is: elk lid ervan (ook lezen, ook aanmaken, ook van een type dat
   ervan afleidt), elke aanroep of elk type met zo'n type als typeargument (`Configure<JsonOptions>`, `PostConfigure<JsonOptions>`,
   `Configure<T>(configuratie)` en `AddOptions<T>().Bind(…)`, die zonder één lid binden, `IOptions<JsonOptions>.Value`,
   `new ConfigureOptions<T>(…)`, `typeof(IConfigureOptions<JsonOptions>)`), en een eigen type dat zo'n type implementeert of ervan
   afleidt, ook als typeargument (`IConfigureOptions<T>`, `IPostConfigureOptions<T>`, `IConfigureNamedOptions<T>`). Behalve wat
   op `Regels.HostOptieWitteLijst` staat (per klasse); **die lijst is leeg** en een test eist dat. Aanleiding (herreview 8):
   `PostConfigure<JsonOptions>` met een eigen converter gaf geen JL-fout, en bij het draaien kreeg een actie met de handtekening van
   `PlaystateController.ReportPlaybackStopped` `PositionTicks` 360000000000000000 in plaats van 36000000000. Een `PostConfigure`
   komt na de instelling van de server (`AddJellyfinApi`, met `Converters.Clear()`), een gewone `Configure` ervoor. In de serverbron
   zet `UserDataManager.UpdatePlayState` het item dan bij elke stop- of voortgangsmelding op gezien en wist het hervatpunt.
   Sinds S-G1-16 geldt dit ook voor open generieke optie-infrastructuur uit `Microsoft.Extensions.Options`:
   `typeof(IOptionsFactory<>)`, `typeof(IPostConfigureOptions<>)` en de andere open optiediensten, een open Microsoft-klasse
   zoals `ConfigureFromConfigurationOptions<>`, en een generieke implementatie zoals `Alles<T> : IOptionsFactory<T>` zijn
   JL0001 in elke namespace. Een typeparameter in een typeargument telt ook als open. De runtimeproef bevestigt dat een
   fabriek met `new T()` een ingestelde `JsonOptions` terugzet, zonder reflectie of dynamic in de proefcode. Gesloten
   optiediensten voor eigen opties blijven toegestaan; de witte lijst en de overige verboden zijn niet verruimd.
   Tests: `BrowserEnHostOptiesTests.HostOpties_OpenInfrastructuurEnGeneriekeImplementatieZijnJL0001` (12 vormen in drie
   namespaces met toegestane tegenvormen) en
   `HostOptiesDraaienTests.OpenFabriek_IsJL0001_EnZetZonderAnalyzerDeHostinstellingTerug`.

Attributen op eigen code (`[Authorize]`, `[Route]`) tellen niet: die gelden alleen voor die code.

Witte lijst van de HTTP-laag (`Regels.HttpWitteLijst`, per klasse) en, sinds herstelronde 10, van punt 8
(`Regels.DoorstuurWitteLijst`); `HttpLaagTests.WitteLijst_ElkeRegelStaatInAdr0032` eist dat elke regel in deze tabel staat. Een plugin zonder beide
lijsten gebouwd gaf precies vijf meldingen (gemeten in herstelronde 10): `IStartupFilter` en `Use` in de spike, één melding op
`JlRouteAttribute` (met `IAsyncActionFilter` en `IAsyncAlwaysRunResultFilter` samen) en de twee regels met `HeaderNames.Location`
in `DoorstuurWacht` (`ContainsKey` en `Remove`):

| Type | Lid | Klasse (onder `Jellyfin.Plugin.JellyLeon`) | Motivatie |
|---|---|---|---|
| `IStartupFilter` | implementeert | `Core.Http.JlStartupFilterSpike` | De spike van ADR-0033 (standaard uit): een laag vóór routing en authenticatie die alleen een verzoek van meer dan 1 MiB aan `/media/v1` of `/connector/v1` met 413 weigert. Alle andere verzoeken gaan ongewijzigd door; `StartupFilterSpikeTests.In_een_echte_host_komt_een_verzoek_buiten_de_pluginpaden_ongewijzigd_aan` legt dat vast. |
| `UseExtensions` | `Use` | `Core.Http.JlStartupFilterSpike` | De ene middleware van de spike in de pijplijn zetten; `Map`, `UseMiddleware` en andere leden blijven ook in deze klasse JL0001. |
| `IAsyncAlwaysRunResultFilter` | implementeert | `Core.Http.JlRouteAttribute` | Sinds herstelronde 10: hetzelfde attribuut als resultaatfilter, alleen op de eigen acties. Na het resultaat schrijft de wacht tegen doorsturen de vaste fout als het antwoord een 3xx of Location had; een antwoord dat niet doorstuurt gaat ongewijzigd door (`DoorstuurWachtTests`). |
| `HeaderNames` | `Location` | `Core.Http.DoorstuurWacht` | Punt 8 (`Regels.DoorstuurWitteLijst`, sinds herstelronde 10): alleen als argument van `ContainsKey` of `Remove` op `HttpResponse.Headers`, om de kop te zien en weg te halen. Zetten, toevoegen, teruggeven, een ander woordenboek en de verzoekkoppen blijven ook in deze klasse JL0001 (`BrowserEnHostOptiesTests.Doorsturen_SystemNetIsJL0001_EnAlleenDeWachtMagLocationZienEnWeghalen`). |
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
bewijst dat de spike in de pijplijn zit) en de proefregels in `VerbodenAanroepen.cs`. Sinds herstelronde 9 ook
`BrowserEnHostOptiesTests.Doorsturen_RedirectsLocationEn3xxZijnOveralJL0001` (30 vormen, met toegestane tegenvormen, ook in
`Core.Http` en `Core.Storage`), `.HostOpties_ElkLidTypeargumentEnImplementatieIsJL0001` (14 vormen),
`.Tabellen_WitteLijstLeegEnElkTypeBestaat`, `BrowserTussenpersoonTests.JlResult_WeigertEen3xxStatus` en de runtime-test
`HostOptiesDraaienTests.Vormen_GevenElkJL0001_MaarZonderAnalyzerWijzigtPostConfigureHetArgumentVanEenServeractie`: dezelfde bron geeft
met de analyzer op elke vorm JL0001, en zonder analyzer in een echte host (Kestrel op loopback, de JSON-instelling van de server
letterlijk, eerst de registratie van de plugin) komt bij `PostConfigure<JsonOptions>` en bij een eigen `IPostConfigureOptions`
360000000000000000 aan in plaats van 36000000000, en bij een gewone `Configure` 36000000000. Sinds herstelronde 10 ook
`BrowserEnHostOptiesTests.Doorsturen_SystemNetIsJL0001_EnAlleenDeWachtMagLocationZienEnWeghalen` (18 vormen: de vorm van herreview 9,
System.Net en de grenzen van de uitzondering voor de wacht), de runtime-tests
`DoorstuurWachtTests.ElkDoorsturendAntwoordVanEenEigenActie_WordtInDeEchtePipelineDeVasteFout` en
`.MetDeSpike_WordtElkDoorsturendAntwoordOpEenPluginpadDeVasteFout_EnDaarbuitenNiets` (Kestrel op loopback, het echte
`JlRouteAttribute` en de echte `JlPipeline`; de vorm van herreview 9 en varianten met elk type resultaat; een tegenproef zonder
wacht geeft in dezelfde host 307 met Location) en `RoutetabelTests.ElkeController_LooptViaDeWacht_BehalveDeEneVersieactie`.

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

**De browser als tussenpersoon** (sinds herstelronde 9, herreview 8, R-HARDE-EIS-18). Niet alle plugincode draait in het
serverproces. Een ingebedde webbron (nu alleen `Configuration/configPage.html`, via `PluginPageInfo.EmbeddedResourcePath`) draait
in de browser van de beheerder, en `ApiClient.fetch` zet daar het token van de beheerder op elk verzoek; met `?userId=` kan dat ook
een andere gebruiker raken. Ook een antwoord van een eigen actie kan de browser laten handelen: een browser volgt een 301, 302, 307
of 308 met dezelfde methode en hetzelfde token naar elke route van de server (bijvoorbeeld `DELETE /UserPlayedItems/<bibliotheek>`,
dat voor die gebruiker de kijkgegevens van de hele bibliotheek wist). De analyzer ziet alleen C#; daarom:

- een ingebedde webbron vraagt alleen eigen paden: één functie `vraag()`, die als eerste opdracht elk pad buiten `media/v1/` en
  `connector/v1/` (alleen kleine letters, cijfers en `-` per segment; dus geen `..`, `%`, `\`, `?` of `#`) en elke andere methode
  weigert vóór `ApiClient.fetch`. `BrowserTussenpersoonTests.ElkeIngebeddeWebbron_VraagtAlleenEigenPaden` controleert elke
  manifestbron van de plugin (ook een bron die er later bij komt; alleen `.html` en `.js` zijn toegestaan): elke `vraag(…)` begint
  met een letterlijk eigen pad, `ApiClient` alleen met `fetch` en `getUrl` (elk precies één keer, in `vraag()`), en geen `fetch(`,
  `XMLHttpRequest`, `$.ajax`, `<script src>`, locatiewissel, ander lid van `window`, HTML invoegen of element met een adres.
  `BrowserTussenpersoonTests.Configuratiepagina_VraagWeigertElkAnderPadVoorApiClientFetch` toetst de eerste opdracht en het patroon;
  `tools/jelly-leon/tests/test_config_pagina.py` voert de echte pagina in Node uit (alle knoppen vragen alleen eigen paden, en
  `vraag()` weigert vreemde paden zonder verzoek);
- een antwoord dat de browser doorstuurt is JL0001 (zie "HTTP-laag en netwerk", punt 8). Bij het draaien weigert `JlResult` een
  3xx-status, en sinds herstelronde 10 weigert de wacht tegen doorsturen (`DoorstuurWacht`) elk antwoord met een 3xx of een kop
  Location op een eigen actie, ongeacht het type resultaat (met de spike aan op elk pluginpad).

#### Opslagdreigingen, deel 1b (onderzoek 2026-11-17)

Bronbasis: `b257c5403a6da940be7b157f32f82333bcd88797`. Dit is een aanvulling op het bestaande
foutenmodel, geen veiligheidsuitzondering. Bronnen: `deploy/allinone/Dockerfile`, runtimefase;
`deploy/allinone/entrypoint.sh`, `assert_owned_mount`, de gebruikerswissel en `record_datamap_version`;
`PluginServiceRegistrator.RegisterServices`, `JlPaths`, `SecretStore` en `JlDatabase.Open`.

- De plugin is één assembly in het serverproces, zonder eigen OS-gebruiker. Het entrypoint wisselt normaal naar
  568:568, zonder capabilities en met `no_new_privs`; Custom User gebruikt de gekozen gebruiker. Een ander proces
  met dezelfde effectieve gebruiker kan de serverdatabase rechtstreeks wijzigen. Dat is actor **(a)**:
  de padcontrole vormt binnen die identiteit geen OS-beveiligingsgrens. Dat rechtvaardigt geen schrijfroute in de plugin.
  (Correctie deel 1c: dat geldt alleen als dat proces ook de serverdata ziet; zie "Opslagdreigingen, deel 1c".)
- De runtimebasis is zonder server en zonder netwerk geïnspecteerd: `/config` en `/cache` zijn daar root:root 0777;
  `/` en `/run` root:root 0755, `/tmp` root:root 1777. De fork-Dockerfile geeft de twee opslagmappen aan 568:568,
  maar verandert hun modus niet (tot deel 1c: nu 0755). Een mount heeft de eigenaar, modus en ACL van de aangeleverde opslag.
  Het entrypoint geeft bij de eerste start eigenaarschap door, maar trekt groeps-/wereldschrijfrechten niet in.
  Onderliggende nieuwe mappen hadden de proces-umask; `SecretStore` maakte alleen de geheimenmap expliciet 0700.
- Actor **(b)** omvat een andere gebruiker/proces die door groepsrechten, wereldschrijfrechten of een ACL in een
  opslagmap of haar vervangbare ouder kan schrijven. Een gegevensmap 0700 onder een niet-sticky gedeelde ouder
  beschermt niet tegen het vervangen van die hele gegevensmap. Ook hostprocessen met toegangsrechten tot de
  gemounte dataset tellen mee. Containerroot, hostroot en een proces met dezelfde UID zijn technisch machtiger,
  maar een door hen teruggezet *onvertrouwd* bestand is niet vanzelf betrouwbare plugininvoer.
- Een beheerder kan met de serverconfiguratie of omgevingsvariabelen DataPath/CachePath kiezen. De plugin voegt
  zelf `jelly-leon` toe; er is geen plugineigen instelling die de opslagwortel verlegt. De image weigert
  opdrachtregelopties voor andere paden; als root weigert zij echte paden buiten `/config` of `/cache`.
  Custom User heeft die root-controle niet. Daarom moeten de opslagcontroles ook in de plugin gelden.
- In `Core/Http/RouteTable.cs`, `Configuration` en `Core/Connector/ConnectorService.cs` is geen route gevonden
  die een geüpload archief als bestanden uitpakt of een gekozen databasepad accepteert. Exports leveren modulegegevens;
  import met `preview_hash` is nog vervolgwerk. Dat is geen bewijs voor een toekomstige import of een externe hersteller.
  Een offline snapshot kan bestaande koppelingen behouden; een externe archiefhersteller kan ze aanmaken. Die aanvoer
  moet afzonderlijk op betrouwbaarheid worden getoetst. Een ontbrekende aanvoercontrole mag niet als actor (a) worden afgedaan.

**Beheerd herstel en eigendomsproef.** `JlPaths` weigert niet-Linux, root, verschillende echte/effectieve/saved/fs-UIDs
of effectieve capabilities, met een Nederlandse melding. Iedere map wordt vanaf de wortel gecontroleerd op koppelingen
en groeps-/wereldschrijfrechten. `File.SetUnixFileMode` zet uitsluitend de zojuist gelezen, veilige modus terug: zonder
CAP_FOWNER kan alleen de eigenaar dat doen. Er worden geen onveilige rechten gerepareerd; ctime kan veranderen.
Dit is een beheerde OS-autorisatieproef, geen uitlezen van een UID en geen eigen native aanroep. Een onleesbare of
niet te controleren map faalt dicht. De vaste systeemouders `/`, `/run` en sticky `/tmp` komen uit de vertrouwde
containerimage; zij mogen alleen ouder zijn, nooit de gekozen data- of cachemap. Elke andere ouder moet van de eigen
gebruiker zijn. Een extra root-beheerde tussenmap wordt dus eveneens geweigerd, ook met 0755. Buiten deze gecontroleerde
Linux-opzet is opslag niet beschikbaar. Bestaande koppelingen in een configuratiepad worden voortaan geweigerd.

Bron voor de eigendomsproef: [Linux chmod(2)](https://man7.org/linux/man-pages/man2/chmod.2.html), DESCRIPTION.
De normale image verliest haar capabilities vóór de server start; de plugin controleert dat opnieuw.
`InternalWriteScope` gebruikt 128 willekeurige bits in een tijdelijke naam en `FileMode.CreateNew`. Dat weigert
bestaande namen, ook symbolische/harde koppelingen. Bestanden ontstaan met 0600; mappen met 0700. Na openen worden
naam en rechten via `/proc/self/fd/<fd>` en `File.GetUnixFileMode(SafeFileHandle)` gecontroleerd vóór de inhoud wordt
gebruikt. Geheimen, migratiekopieën, mapaanmaak en verwijderen lopen langs dezelfde controles. Bestaande databases
krijgen geen reparatie of kopie-omweg; WAL-herstel en migratiekopieën blijven behouden.

De publieke [.NET 10 FileOptions](https://github.com/dotnet/runtime/blob/v10.0.0/src/libraries/System.Private.CoreLib/src/System/IO/FileOptions.cs)
bieden geen NOFOLLOW. De gebruikte [Microsoft.Data.Sqlite.Open](https://github.com/dotnet/efcore/blob/v10.0.0/src/Microsoft.Data.Sqlite.Core/SqliteConnectionInternal.cs)
biedt evenmin een NOFOLLOW-optie, bestandsdescriptor of linkaantal in de beheerde verbindingsopties. Er is geen
ongedocumenteerde vlag, reflectie of nieuwe SQLitePCL-aanroep toegevoegd. Exclusieve nieuwe aanmaak en hercontrole
vóór de eerste databasebewerking zijn wel gebouwd. Bij een nieuwe database wordt eerst exclusief een bestand 0600 gemaakt.

**Aanvoer van soort (b).** `Start_GedeeldeGegevensmapWordtGeweigerd`, `Start_VervangbareBovenliggendeMapWordtGeweigerd`,
`Start_VreemdeEigenaarWordtGeweigerd`, de tests op koppelingen en onveilige bestandsrechten en de hercontrole bij elke
bewerking dekken de huidige configuratie- en maproutes. Een synthetische containerproef met UID 65534 kan in de map
van UID 1000 geen koppeling leggen of de map vervangen (beide Permission denied). POSIX-ACL-schrijfmaskers komen in
de groepsmodus terecht; onbekende opslagsemantiek op de echte NAS is hiermee niet gevalideerd.

De server heeft wél een beheerdersroute voor back-ups: `Jellyfin.Api/Controllers/BackupController.cs`,
`StartRestoreBackup`, vereist `RequiresElevation` en kiest alleen een archief onder `BackupPath`.
`Jellyfin.Server.Implementations/FullSystemBackup/BackupService.cs`, `RestoreBackupAsync`, herstelt ZIP-items
met `ExtractToFile`, zonder harde of symbolische koppelingen uit archiefmetadata aan te maken.
`OpslagGrensTests.Herstel_ZipKoppelingskenmerkMaaktGeenHardeOfSymbolischeKoppeling` bewaakt die aanname met een
synthetische database: ook met het Unix-koppelingskenmerk ontstaat een gewoon bestand, waarvan migratie het origineel
byte-gelijk laat. Dit is een proef van de gebruikte extractor, geen uitvoering van de hele serverhersteldienst.
De gedocumenteerde NAS-terugval (`deploy/truenas/CUSTOM_APP.md`, "Updaten en terugdraaien") is de vooraf bewaarde
config-snapshot met de vorige image. Die kan bestaande koppelingen behouden; hij introduceert niet uit zichzelf een
nieuwe koppeling. Een willekeurige externe TAR-hersteller, een gedeelde dataset of een ander hostproces dat met de
service-UID schrijft, is niet door deze ZIP-proef bewezen veilig. Herstel van onbetrouwbare bestandsstructuren mag
daarom niet stilzwijgend als actor (a) worden geclassificeerd. De regisseur moet dit aanvoerbereik expliciet beoordelen.

**Gemeten restgrens; besluit nodig, niet aanvaard.** Op de oude bron zijn alle vijf proeven rood. Na herstel blijven
`hardlink-database` (buitenbestand gewijzigd) en `padwissel-bestand` (buitenbestand byte-gelijk, maar buitenmap heeft
één leeg tijdelijk bestand erbij) rood. De twee haken voeren de wissel uit na de laatste voorafcontrole en vóór openen,
uitsluitend in gegenereerde kopieën; de plugin bevat geen proefhaken. Beide resterende opzetten gebruiken dezelfde
OS-gebruiker als de server en schrijven in vooraf particuliere, eigen mappen. Zij zijn daarmee in de uitgevoerde
proeven actor (a): die gebruiker kan het buitenbestand al rechtstreeks schrijven. Voor de gecontroleerde huidige
configuratie-, ZIP- en maproutes is geen bereikbare aanmaak door een minder bevoegde actor aangetoond. Dat is geen
bewijs dat elke mogelijke externe hersteller betrouwbaar is. (Correctie deel 1c: dit gold voor de plugin; de start van de
container had wél een weg van soort (b), nu hersteld. Zie "Opslagdreigingen, deel 1c".)

Een native `fstat` op de geopende database kan `st_nlink > 1` weigeren; een descriptor-gebonden open met bijvoorbeeld
`openat2` en RESOLVE_BENEATH/NO_SYMLINKS kan het wisselen van ouders tijdens openen voorkomen. Alleen een linkaantal
op een *pad* of alleen O_NOFOLLOW op het laatste deel sluit dat tweede gat niet. SQLite zou dezelfde gebonden
bestandsidentiteit voor hoofdbestand én naastbestanden moeten blijven gebruiken. Daarvoor bestaat in de gebruikte
beheerde provider geen volledige voorziening. Deze ADR geeft daarvoor geen uitzondering en verlaagt de HARDE EIS niet.
De regisseur moet na R-TECH, R-VEILIG en R-HARDE-EIS beslissen of het aantoonbare actor-(a)-bereik formeel het
foutenmodel afbakent, of een afzonderlijk opslagontwerp met een echte OS-grens nodig is. Zolang het vertrouwen in
vooraf bestaande en extern teruggezette opslag niet is vastgesteld, is deel 1b **NIET KLAAR**. Een aangetoonde route
van soort (b) blijft blokkerend en vraagt herstel, nooit alleen een tekstuele uitzondering.

De echte NAS, Emby en accounts zijn niet benaderd.

#### Opslagdreigingen, deel 1c (start van de container, 2026-11-17)

Bronbasis: `6c1deb9a79552575b9e88fb322d0a25f47b8a124`. Deel 1b beoordeelde de plugin. De start van de container
(`deploy/allinone/entrypoint.sh`) schrijft eerder in dezelfde datamap en had een weg van soort (b).

**Gevonden weg (b): blokkerend, hersteld.** `record_datamap_version` schreef met `>` naar
`"$DATAMAP_VERSION_FILE.tmp.$$"`. In de container is de start PID 1 (`exec setpriv … "$SELF"` houdt de PID), dus de
naam was altijd `datamap-versie.tmp.1`, en `>` volgt een symbolische koppeling. Wie in `/config` of `/config/jelly-leon`
mag schrijven zonder de app-gebruiker te zijn, legt vóór de start een koppeling op die naam; de start schrijft als 568 in
het doel, bijvoorbeeld `/config/data/jellyfin.db`, en `mv` maakt van de koppeling `datamap-versie`. Gemeten met de echte
entrypoint als PID 1 in de gepinde runtime-basis, `/config` 0777 van een andere gebruiker (uid 1000; de app is 568): de
synthetische serverdatabase is overschreven, en de eenmalige `chown -R` als root nam eerst ook de bestanden van de
aanvaller over. Werkelijke situaties: (1) een dataset of hostpad dat de gebruiker te ruim deelt (0777, schrijfrecht voor
de groep, een ACL-regel voor een andere gebruiker of app); (2) de image zelf: `/config` en `/cache` zijn in de basisimage
0777 en de fork-Dockerfile wijzigde alleen de eigenaar. Een tmpfs of nieuw Docker-volume neemt de modus van de imagemap
over (gemeten: `--tmpfs /cache` en een benoemd volume op de basisimage gaven 0777; een tmpfs op een nieuw pad 1777), dus
ook de gedocumenteerde tmpfs-`/cache` was 0777. Het entrypoint maakt zelf geen te ruime map: de container-umask is 0022.

**Herstel, zonder native aanroep en zonder uitzondering.**
- `assert_private_storage` weigert vóór elke schrijfactie (als root vóór de eenmalige eigenaarswissel, als app-gebruiker
  vóór het vastleggen van de versie en vóór de pluginmap) een data- of cachemap, een ouder daarvan, `jelly-leon/`,
  `plugins/` of `plugins/JellyLeon_*` die een symbolische koppeling is of voor groep of anderen beschrijfbaar; als
  app-gebruiker ook een map van een andere eigenaar. Een ouder mag van root zijn, en voor iedereen beschrijfbaar alleen
  met sticky-bit (zoals `/tmp`). Na `mkdir` van `jelly-leon/`, `plugins/` en `plugins/JellyLeon_<versie>` volgt dezelfde
  controle vóór het schrijven. De melding is Nederlands, zegt "Er is niets gewijzigd" en noemt wat in TrueNAS na te kijken
  is (Datasets → Permissions, de opslag van de app, een snapshot of de Hub); geen terminalstappen.
- Het tijdelijke bestand komt van `mktemp`: exclusief nieuw, willekeurige naam, 0600.
- De Dockerfile zet `/config` en `/cache` op 0755.

Tests: `tools/jelly-leon/tests/test_entrypoint_opslaggrens.py` leest de functies en de tweede fase letterlijk uit het
entrypoint en voert ze met dash uit: de koppelingsproef van deel 1b, gedeelde en gekoppelde mappen, een vreemde eigenaar,
en twee gevallen waarin een correcte installatie blijft starten. Op de oude code waren 11 van de 13 rood; de twee
startgevallen waren op oud en nieuw groen. `tools/jelly-leon/e2e/image_lifecycle.py`, `check_storage_modes` en
`expect_shared_config_refusal`, draait in de CI-job image met de echte image; de testgebruiker is daar de andere gebruiker.

**Gevolg voor een bestaande installatie.** Een correcte installatie (map van de app-gebruiker, geen schrijfrecht voor groep
of anderen) start ongewijzigd, ook met tmpfs-`/cache` (gemeten met de echte entrypoint en in de tests). Een weigering
wijzigt niets. (Correctie deel 1f, R-VEILIG-3: bij een overerfbare ACL weigerde de start pas na de eenmalige `chown -R` en
een `mkdir`; dat is hersteld, zie "Opslagdreigingen, deel 1f".) De plugin weigert dezelfde mappen al sinds deel 1b; dat gebeurt in de constructor van `JlPaths`,
waarvan een hosted service afhangt, zodat de hele server stopt met een Engelse foutmelding. De start meldt het nu eerder en
in het Nederlands. **Niet vastgesteld, alleen op de echte NAS te meten:** welke modusbits de preset Apps uit
`deploy/truenas/CUSTOM_APP.md` geeft, en hoe het opslagtype tmpfs van TrueNAS de modus zet. Geeft de preset schrijfrecht
voor de groep, dan weigeren start en plugin elke installatie volgens dat document. Verder ziet `stat` alleen modusbits: bij
een NFSv4-ACL telt een extra regel voor een benoemde gebruiker niet mee in de modus, dus zo'n ACL met schrijfrecht ziet de
controle niet. Beide horen bij de NAS-test en het besluit hieronder.

**Correctie op de redenering voor actor (a).** Deel 1b stelt dat een proces met dezelfde gebruiker de serverdatabase ook
rechtstreeks kan wijzigen. Dat klopt alleen als dat proces ook de serverdata ziet. Op TrueNAS draaien apps standaard als
568; een andere app met alleen een submap van de config-dataset gemount, heeft dezelfde gebruiker maar niet dezelfde
toegang. Per restgrens:
- `hardlink-database` blijft actor (a). Een harde koppeling kan niet over mounts heen (link(2): EXDEV; gemeten: "Invalid
  cross-device link" met alleen de eigen map gemount), en met `fs.protected_hardlinks=1` (gemeten op de bouwmachine; op de
  NAS onbekend) alleen naar een bestand dat de aanvaller zelf mag schrijven. Wie de koppeling naar de serverdatabase kan
  leggen, kan die database dus ook rechtstreeks schrijven. Niet onder (a) valt een terugzetting die een archief met harde
  koppelingen uit een onbetrouwbare bron terugzet (deel 1b, "Aanvoer van soort (b)").
- `padwissel-bestand` valt niet volledig onder (a). Een app met dezelfde gebruiker en alleen een deel van de pluginmap
  gemount, kan daarin een map tussen controle en openen vervangen door een symbolische koppeling met een pad uit de
  servercontainer. De plugin maakt dan een leeg bestand met willekeurige naam in een map die die app zelf niet ziet. Er
  wordt niets overschreven (CreateNew) en de controle na openen weigert de bewerking; de lege ingang blijft staan.
  Bereikbaar alleen als een beheerder een deel van de Jelly Leon-config in een andere app mount. **Correctie deel 1f
  (R-VEILIG-2):** dat "niets overschreven" geldt alleen voor de eigen schrijfroute van de plugin. In precies dit scenario
  laat de server wél de serverdatabase overschrijven, via de pluginconfiguratie (gemeten; zie deel 1f, B1).

Een native controle zou toevoegen: `fstat` op de geopende database met weigering bij `st_nlink > 1`, en openen gebonden
aan een mapdescriptor (`openat2` met RESOLVE_BENEATH en RESOLVE_NO_SYMLINKS), zodat een wissel tijdens het openen
faalt. SQLite opent zijn naastbestanden zelf op naam; dat blijft ook dan buiten zo'n binding. Er is geen native controle
en geen uitzondering gebouwd; de HARDE EIS is niet verlaagd. Of deze twee grenzen het foutenmodel formeel afbakenen, is
een besluit van de regisseur.

#### Opslagdreigingen, deel 1d (beschikbaarheid, 2026-11-17)

Besluit regisseur B3, optie B: **beschikbaarheid van de mediaserver gaat boven uitval van de hele server door de
plugin**. De controles uit deel 1b blijven onverminderd streng. `JlPaths` blijft onveilige opslag weigeren;
`PluginOpslag` vangt die weigering één keer op en houdt de plugin uitgeschakeld tot de volgende serverstart.
`OpslagDienst<T>` maakt dan geen Devices-listener, MediaGuard-poller of planner aan. De moduleschakelaars melden uit,
weigeren inschakelen en lezen geen pluginconfiguratie. `UserDeletedConsumer` doet zonder beschikbare opslag niets;
hij opent geen database en beïnvloedt de gebruikersafhandeling van de server niet. De configuratie wordt niet aangepast.

De vier opslagafhankelijke controllers halen hun diensten pas in de actie op, zodat `JlRouteAttribute` de weigering
vóór elke opslagafhankelijke constructor kan afhandelen. Een aangemelde beheerder krijgt 503 `storage_unavailable`,
een anonieme bezoeker 401 en een onbevoegd account 403. **Geen onveilige pin lezen om een Hub-token te controleren:**
Hub-routes blijven 401 `unauthorized` / `not_linked` (contract §4.7). Hun Nederlandse melding legt de opslaguitval uit.
De weigering bevat `details.health.status=down`, `reason_code=storage_unavailable`, `modules_enabled=false` en
`restart_required=true`; ook de connector-healthroute geeft zo de toestand door. Alleen vaste diagnosevelden, geen
bestandsinhoud of paden. Het serverlog krijgt één Nederlandse opslagmelding met herstel via TrueNAS
(Apps → Edit → Storage en Datasets → Permissions → Edit), zonder terminalstappen. `/media/v1/version` en de eigen
routes van de mediaserver blijven werken. De normale pipeline en connector-health blijven bij veilige opslag ongewijzigd.

Dit maakt een onveilige map niet bruikbaar: er zijn geen bestandsbewerkingen, sleutelpinlezingen of databases via die
map zolang de plugin uit staat. De bestaande eigendomsproef van deel 1b zet tijdens de controle uitsluitend dezelfde
veilige modus terug (ctime kan veranderen); er wordt geen recht gerepareerd of verruimd. Na de weigering is er geen
stille hercontrole. `JlPaths`, de analyzer en zijn uitzonderingslijst zijn niet gewijzigd; geen native aanroep toegevoegd.
De containerstart blijft zijn eigen gedeelde `/config` of `/cache` weigeren vóór schrijven; dit beschikbaarheidsherstel
betreft de opslag van de plugin (bijvoorbeeld onder `/config/data/jelly-leon`), niet de bestaande startwaarborgen.

Klein herstel van deel 1c: `assert_not_downgrade` controleert de mappen en het versiepad vóór de eerste versielezing,
ook in de rootfase vóór de eigenaarswissel. Een gekoppeld versiepad (ook een dode koppeling), FIFO of ander bijzonder
bestand wordt geweigerd; een gewoon bestand met groeps-/wereldschrijfrecht eveneens. De bestaande downgradeweigering
blijft gelden. Tests lezen de echte functies uit de entrypoint; een onderschepte leesaanroep voorkomt een hangende
FIFO-proef en bewijst dat de weigering vóór die leesaanroep valt.

Bewijs: `OpslagTerugvalTests` start een echte tijdelijke Kestrel-host met de echte pluginregistratie, MVC, achtergrondtaken
en alle routes uit de routetabel. Eigenaar, groeps-/wereldschrijfrechten, gekoppelde eigen mappen en onveilige ouders
laten de host doorstarten, zonder gewijzigde mapinhoud binnen of buiten de opslag. De eigenaarfixture is een lege,
tijdelijke map van een andere UID, gemaakt in een wegwerpcontainer zonder netwerk; geen ACL, native proefhaak of
verzwakte opslagtest. Herstel tijdens dezelfde host blijft geweigerd; na herstart starten de gewone diensten weer.
`test_entrypoint_opslaggrens.py` bewaakt de vroege leesgrens. Uitvoering en tegenproeven staan in
`docs/platform-v2/test-evidence/s-g1-16-deel1d-beschikbaarheid.md`.

B1 optie A (regisseur): de harde databasekoppeling en de lege ingang na padwissel blijven de vastgelegde grenzen van
het foutenmodel; geen herstel in dit deel. Alleen eigen snapshots of back-ups terugzetten en nooit een deel van de
Jelly Leon-config aan een andere app koppelen. Dit besluit wordt nog aan de gebruiker voorgelegd (sinds deel 1f met het
gemeten gevolg en met de regels verplicht in `CUSTOM_APP.md`; zie deel 1f, B1). B2 blijft strikt:
rechten en ACL-werking op de echte NAS moeten door de gebruiker worden gemeten. Geen NAS, Emby of accounts benaderd.

#### Opslagdreigingen, deel 1e (installatiebestanden en startbestanden, 2026-11-17)

Bronbasis: `6525d9819e51579e03e62c6847d37cb45ec2fec9`. Herstel van R-TECH-1 en R-TECH-2 uit de technische review over
deel 1 t/m 1d; beide eerst herhaald en rood gezien.

**Start van de container (R-TECH-1).** `assert_private_storage` controleerde de mappen, niet de bestanden erin. Was de
bestaande plugin-DLL een koppeling naar `/config/data/jellyfin.db`, dan las `cmp` en schreef `cp` erdoorheen: gemeten met
de hele entrypoint in een netwerkloze wegwerpcontainer op de gepinde runtime-image, als Custom User én als root (na de
eigenaarswissel), was de synthetische serverdatabase overschreven; een harde koppeling gaf hetzelfde, een FIFO liet `cmp`
wachten. Herstel: `assert_private_storage` (als root vóór de eigenaarswissel en vóór de eerste versielezing, als
app-gebruiker vóór het vastleggen van de versie) weigert in elke `plugins/JellyLeon_*` elke ingang die geen gewoon bestand
met één naam is (symbolische of harde koppeling, map, FIFO, ander bijzonder bestand), met een Nederlandse melding en zonder
iets te wijzigen. Dat dekt ook `meta.json`, dat de server zelf bij de start leest en zo nodig schrijft
(`PluginManager.SaveManifest`, `File.WriteAllText` volgt een koppeling). De DLL komt daarna als nieuw bestand naast het
doel (`mktemp`) en wordt hernoemd (`mv -f -T`): ook zonder die weigering wordt een bestaande ingang vervangen, nooit
beschreven. Elke andere lees- of schrijfactie van de start is nagelopen:

| Plek | Bevinding |
|---|---|
| `datamap-versie` lezen (`assert_not_downgrade`) en schrijven (`record_datamap_version`) | geen nieuw gat: koppeling, FIFO en bijzonder bestand worden sinds deel 1d vóór het lezen geweigerd; schrijven via `mktemp` en hernoemen (deel 1c) vervangt een (harde) koppeling |
| oude `JellyLeon_*`-mappen (`rm -rf`) | `rm` volgt geen koppeling; nu ook daar alleen gewone bestanden (strenger, geen gat) |
| DLL vergelijken en plaatsen, `meta.json` van de server | **gat, hersteld** (hierboven) |
| eigenaarswissel `chown -R` als root | GNU `chown -R` volgt standaard (`-P`) geen koppeling; de weigering staat er nu vóór |
| `CONFIG_DIR`, `/proc/self/mountinfo`, `/proc/self/status`, `/dev/dri`, image-`VERSION` | alleen mountcontrole of lezen buiten de gebruikersopslag; geen gat |
| generator van de web-`config.json` | draait alleen bij de imagebouw (Dockerfile, webfase), nooit bij de start |
| `healthcheck.sh` | leest alleen `/proc/self/status` en vraagt `/health` op; schrijft niets |

**Plugin (R-TECH-2).** De terugval van deel 1d ving alleen de weigering van `JlPaths` op. `core/core.db` als koppeling,
`core.db` 0660 of `core/` 0770 lieten `Host.StartAsync` falen in `JlDatabase.EisEigenPlek` via `OpslagDienst<T>`. Nu neemt
`PluginOpslag` in dezelfde eenmalige beslissing, vóór elke afhankelijke dienst of achtergrondtaak, elke database van Core
en van elke module (de lijst met moduleschakelaars) mee: `JlDatabase.EisVeiligBijStart` voert precies de controle van de
constructor uit (eigen plek, geen koppeling, de vier namen inclusief `-wal`, `-shm`, `-journal`, mappen tot de wortel,
groeps-/wereldschrijfrecht) en daarnaast de bestaande eigendomsproef van de mappen ook op elk bestaand bestand
(`JlPaths.EisEigenBestand`: dezelfde modus terugzetten; ctime kan veranderen). Een weigering doet wat deel 1d doet: alleen
de plugin uit, geen schrijfactie, niets geopend, geen reparatie, één vaste melding, 503/401/403, pas weer aan na een
herstart met veilige opslag. De strengheid van de controles, de analyzer en zijn lege uitzonderingslijst zijn ongewijzigd;
geen native aanroep. De geheimenmap hoort niet bij de start (pas bij gebruik gelezen) en zit dus niet in de beslissing.

**Later dan de start.** Nagelopen: verzoek, achtergrondtaak, gebeurtenis van de server, afsluiten. Twee plekken konden een
ruwe fout in de server gooien en zijn hersteld. (1) `EventManager.PublishInternal` van de server maakt alle
`IEventConsumer<UserDeletedEventArgs>` aan vóór zijn try/catch; de fabriek haalde `PrivacyService` op en daarmee elke
module. Een opslagfout gaf de server dan een fout bij het verwijderen van een gebruiker (`UserManager.DeleteUserAsync`
publiceert na het wissen in de database) en sloeg de eigen afhandelaars van de server (activiteitenlog, melding) over. `UserDeletedConsumer` haalt de dienst nu pas in `OnEvent` op (binnen de foutafhandeling van de server).
(2) `SecretStore` gaf weigeringen ruw door, en de Devices-listener vangt alleen `JlException`: een fout in een
sessiegebeurtenis brak dan de aanroep van de overige luisteraars van de server af (`EventHelper` roept ze als één
multicast aan). `SecretStore` maakt van een opslagfout nu 503 `storage_unavailable`, net als `JlDatabase.Met`; een
onveilige Hub-pin geeft zo 503 uit de foutcatalogus in plaats van een ruwe 500. De planner en de MediaGuard-poller vangen
al elke fout; afsluiten opent geen opslag. (3) `JlRouteAttribute` maakte de pijplijn buiten zijn foutafhandeling aan: na een
opslagwijziging tijdens het draaien gaf het eerste verzoek een ruwe 500 uit een weigerende constructor (gemeten met een
Hub-route). Het aanmaken valt nu binnen dezelfde try; zo'n weigering wordt 503 `storage_unavailable`. **Restgrenzen
(gemeld, geen uitzondering):** wie met dezelfde gebruiker tussen de eenmalige beslissing en de constructors (dezelfde
start) een bestand verwisselt, kan de constructor nog laten weigeren (actor (a), zoals B1). Een FIFO op een databasenaam
is in beheerde code niet te herkennen; SQLite faalt dan bij het lezen (503). B1 en B2 blijven ongewijzigd.

Bewijs: `test_entrypoint_opslaggrens.py` (acht soorten pluginbestanden, de rootfase vóór de eigenaarswissel, plaatsen
zonder volgen, correcte installatie), de levenscyclus van de echte image in CI (`expect_plugin_link_refusal`, als root en
als Custom User) en `OpslagTerugvalTests` (de drie hostproeven van de review plus elk naastbestand, onveilige moduledirs,
een moduledatabase als koppeling, een bestand van een andere eigenaar, en het latere moment). Uitvoering en tegenproeven:
`docs/platform-v2/test-evidence/s-g1-16-deel1e-startbestanden.md`.

#### Opslagdreigingen, deel 1f (pluginconfiguratie, tmpfs-cache, zelfherstel, ACL-overerving, 2026-11-18)

Bronbasis: `81e9c4a260d32bd71318be851397d970e2602521`. Herstel na de veiligheidsreview (R-VEILIG) en de HARDE-EIS-review
over deel 1 t/m 1e, met de besluiten van de regisseur van 2026-11-18. Elke bevinding is eerst zelf herhaald en rood gezien.

**Pluginconfiguratie van de server (R-VEILIG-1, blokkerend).** De server leest `plugins/configurations/Jellyfin.Plugin.JellyLeon.xml`
bij de eerste lezing van de configuratie (`MediaBrowser.Common/Plugins/BasePluginOfT.cs`, `LoadConfiguration`) en schrijft
er bij een mislukte lezing direct een nieuwe configuratie in (`SaveConfiguration`; `MyXmlSerializer.SerializeToFile` met
`FileMode.Create` volgt een symbolische koppeling en beschrijft een harde koppeling). Die map en dat bestand vielen buiten
de startgrens. Herhaald met de hele keten (entrypoint van `81e9c4a26`, stock-server 12.4 op digest, plugin van `81e9c4a26`,
Custom User, netwerkloos): een andere uid legt in een voor iedereen beschrijfbare `plugins/configurations` de koppeling
`Jellyfin.Plugin.JellyLeon.xml` → `/config/data/jellyfin.db`; de start ging door, en na `GET /media/v1/modules` begon de
synthetische serverdatabase (SQLite, 544768 bytes) met `<?xml`. Herstel: `assert_private_storage` (als root vóór de eerste
versielezing en de eigenaarswissel, als app-gebruiker vóór het vastleggen) neemt `plugins/configurations` op als eigen map
(geen koppeling, niet voor groep of anderen beschrijfbaar, als app-gebruiker van die gebruiker) en aanvaardt het eigen
XML-bestand alleen als het ontbreekt of een gewoon bestand met één naam is. Bestanden van andere plugins in die map blijven
buiten beschouwing (ook een koppeling daar is geen reden om te weigeren). Een weigering wijzigt niets; de melding noemt
dat het bestand alleen moduleschakelaars bevat en als veilige weg: andere apps zonder toegang tot de config-dataset en
alleen dit ene bestand laten weghalen. Zelfde keten na herstel: de start weigert, de server start niet, het doel blijft
byte-gelijk. Dit bestand wordt geweigerd en niet zelf hersteld (besluit van de regisseur, punt 1): het is instelling van de
gebruiker, niet door de image beheerd. (Deel 1g, besluit 4: een harde koppeling tot 1 MiB wordt nu wel een eigen kopie.)

**Alle lees- en schrijfacties voor of namens de plugin** (start, server en plugin; nagelopen in `entrypoint.sh`,
`Emby.Server.Implementations/Plugins/PluginManager.cs`, `BasePluginOfT.cs`, `BaseApplicationPaths.cs`,
`Jellyfin.Api/Controllers/PluginsController.cs` en de opslaglaag van de plugin):

| Plek | Wie en wanneer | Volgt een koppeling? | Bewaking |
|---|---|---|---|
| `plugins/` | server: `CreateAndCheckMarker` maakt bij elke start `.jellyfin-plugin` als die ontbreekt (`File.Exists` volgt, `File.Create`); start: `mkdir` | marker: ja | start: map zonder koppeling, niet voor groep of anderen beschrijfbaar, van de app-gebruiker; de marker kan alleen leggen wie in die map schrijft (B1) |
| `plugins/JellyLeon_<versie>/` | start: `mkdir`, oude versies `rm -rf`; server: `Directory.Delete` van oudere versies en bij verwijderen | nee | start: zoals `plugins/` |
| `.../Jellyfin.Plugin.JellyLeon.dll` | start: `cmp`, daarna nieuw bestand naast het doel en hernoemen (deel 1e); server: laden | nee | start: een vreemde ingang wordt eerst zelf verwijderd (deel 1f) |
| `.../meta.json` | server: `LoadManifest` (`File.ReadAllBytes`) bij elke start; `SaveManifest` (`File.WriteAllText`) bij de eerste start, een versie- of statuswijziging | ja | start: een vreemde ingang wordt eerst zelf verwijderd (deel 1f); daarna schrijft de server een nieuw, gewoon bestand |
| `.../<afbeelding>` | server: `DownloadImage` alleen voor een plugin uit een catalogus (tijdelijke willekeurige naam, dan `File.Move` met overschrijven); `GET /Plugins/<id>/<versie>/Image` leest alleen een pad binnen de pluginmap | nee | de meegeleverde plugin staat in geen catalogus; lezen alleen van een gewoon bestand in de eigen map |
| `plugins/configurations/` | server: `Directory.CreateDirectory` bij opslaan | n.v.t. | **start (deel 1f)**: zoals `plugins/` |
| `plugins/configurations/Jellyfin.Plugin.JellyLeon.xml` | server: lezen bij de eerste lezing (eigen route van de plugin, of de serverroute `GET /Plugins/<id>/Configuration`), schrijven bij een mislukte lezing, bij `POST /Plugins/<id>/Configuration` en bij een moduleschakelaar van de plugin | ja | **start (deel 1f)**: ontbreekt of gewoon bestand met één naam; **plugin (deel 1f, A3)**: bestand en map opnieuw getoetst vóór elke eigen lezing of opslag; de serverroute niet (B1, regels in `CUSTOM_APP.md`) |
| `<data>/jelly-leon/**` en `<cache>/jelly-leon/**` | plugin (`JlPaths`, `InternalWriteScope`, `JlDatabase`, `SecretStore`) | nee (deel 1b) | plugin; bij weigering alleen de plugin uit (deel 1d en 1e) |
| `<config>/jelly-leon/datamap-versie` | start: lezen, schrijven via `mktemp` en hernoemen | nee | start (deel 1c en 1d) |
| serverlog onder `<config>/log` | server, ook voor de meldingen van de plugin (`ILogger`) | eigen logbestanden van de server | geen eigen logbestand van de plugin; meldingen zonder paden of inhoud |
| overige bestanden onder `/cache` | server (afbeeldingen, transcodes, `CACHEDIR.TAG`, marker) | ja | geen schrijfactie namens de plugin; de start controleert `/cache` zelf |

Geen andere plek: de plugin gebruikt `DataFolderPath` niet, heeft geen eigen logbestand, en de server schrijft voor de plugin
niets in `/cache`.

**`/cache` als tmpfs met Custom User (R-HARDE-EIS-1, blokkerend; besluit BN-1 optie B).** `CUSTOM_APP.md` staat Custom User
(568) en `/cache` als tmpfs allebei toe, en de vorige image startte zo. Sinds deel 1c weigerde de start dat: Docker geeft een
tmpfs zonder opties de modus van de imagemap (0755 sinds 1c) en eigenaar root (gemeten), dus `/cache` was niet van 568 en niet
schrijfbaar, en de melding wees naar een dataset die bij een tmpfs niet bestaat. Herhaald en rood gezien. Besluit: een
tmpfs-`/cache` uit het formulier bestaat alleen in deze container. (Correctie deel 1g: de start kan dat niet sluitend
vaststellen; een lege gedeelde tmpfs ziet er hetzelfde uit, en daar kan een ander wel iets in neerleggen.) Herstel:
- De start (`own_tmpfs`) stelt uit `/proc/self/mountinfo` vast, niet uit de naam, dat `/cache` zelf het koppelpunt is van een
  heel tmpfs-bestandssysteem (wortel `/`; een gekoppelde map van de host heeft een andere wortel) en dat die bij de start leeg
  is (Docker maakt de tmpfs bij elke start nieuw en leeg; gemeten met `docker restart` en stop/start). Alleen dan aanvaardt zij
  voor `/cache` de eigenaar en modus die Docker of TrueNAS geeft (root, 1777 of 0777). Een gekoppelde map, een al gevulde tmpfs
  en een gewone map met 1777 blijven geweigerd; `/config` en een `/cache` op een dataset of hostpad blijven even streng.
- De plugin (`JlPaths.IsEigenTmpfs`, `EigenTmpfs`) slaat voor precies die cachemap de modus- en eigenaarscontrole over, met
  dezelfde vaststelling uit de mounttabel (de leegte heeft de start al gecontroleerd); de datamap blijft streng, ook als tmpfs.
- De image zet `/cache` op 1777: een tmpfs krijgt die modus mee, zodat ook een Custom User erin kan schrijven. Een nieuw
  Docker-volume neemt de modus van de imagemap ook over (deel 1c) en is geen eigen tmpfs, dus geweigerd; het formulier kent
  geen gewoon Docker-volume (alleen Host Path, ixVolume, SMB/NFS-share en tmpfs; openbare bron `ix-dev/stable/ix-app/questions.yaml`)
  en een anoniem volume weigert de start al. Een SMB/NFS-share als `/cache` is niet gemeten.
- De meldingen bij een tmpfs verwijzen niet meer naar Datasets → Permissions, maar naar het opslagtype in het formulier.
Gemeten met de echte entrypoint in netwerkloze wegwerpcontainers: Custom User 568 met een tmpfs 1777 (zoals de nieuwe image)
en root met een tmpfs 0777 (basisimage) starten; Custom User met een tmpfs 0755 weigert met de tmpfs-melding; de host-`/dev/shm`
(gevuld) als `/cache` weigert, als root en als Custom User. **Grens (eerlijk):** binnen de container is een koppeling van het
héle wortelpunt van een tmpfs van de host (bijvoorbeeld Host Path `/dev/shm`, dat de TrueNAS-appbibliotheek niet uitsluit) niet
te onderscheiden van een eigen tmpfs als die bij de start toevallig leeg is. Daarom zegt `CUSTOM_APP.md`: voor `/cache` alleen
het opslagtype tmpfs of een eigen dataset, nooit een Host Path naar een map buiten je datasets. Of TrueNAS bij een tmpfs ook
1777 of een andere modus geeft, blijft een NAS-meting. **Gemeten in de CI-levenscyclus van de echte image:** met een tmpfs
van 500 MiB (de standaardgrootte van het formulier, en de grootte in de proef van de review, die een nep-server gebruikte)
start de entrypoint nu wel, maar weigert de server zelf: `StorageHelper.TestCommonPathsForStorageCapacity` eist 2 GiB vrij in
`/cache` ("The path `/cache` has insufficient free space. Available: 500MiB, Required: 2GiB"). Dat gold ook voor de vorige
image met dezelfde server; `CUSTOM_APP.md` noemde daarom minstens 2048 MiB (voorstel 4096 MiB). Dat minimum start zelf niet
(correctie deel 1g: minstens 2560 MiB). Met 4096 MiB en Custom User
568 startte de echte stock-server 12.4 met de entrypoint en de plugin van deze stap (netwerkloos, synthetisch): gezond,
`GET /media/v1/modules` 200, geen opslagmelding; met de plugin van `81e9c4a26` viel de plugin daar terug (503).

**Zelfherstel in de eigen pluginmap (R-HARDE-EIS-2 en R-VEILIG-4; besluit BN-2 optie B).** Sinds deel 1e weigerde de start
elke ingang in `plugins/JellyLeon_*` die geen gewoon bestand met één naam is. Een goedaardige harde koppeling (ontdubbelen, of
terugzetten met behoud van koppelingen) legde zo de hele mediaserver stil, en de melding bood als enige UI-weg het terugzetten
van een snapshot, zonder te zeggen dat kijkgegevens van na die snapshot dan verloren gaan. Herhaald en rood gezien (harde
koppeling op de DLL en op `meta.json` naar een kopie in `/config/backup`, tweede naam binnen de map). Herstel: deze map wordt
door de image beheerd. De app-fase (`repair_plugin_dirs`, vóór het vastleggen van de versie, vóór `cmp` en vóór elke
schrijfactie) verwijdert er zelf elke ingang die geen gewoon bestand met één naam is: een symbolische of harde koppeling, een
FIFO of ander bijzonder bestand (`find -delete`: unlink volgt niets), en een lege map (rmdir). Het doel van een koppeling en de
andere naam van een harde koppeling worden niet gelezen of beschreven. Daarna plaatst de start de DLL als nieuw bestand (deel
1e) en schrijft de server een nieuwe `meta.json` (een eerder in het dashboard uitgezette plugin staat dan weer aan). Eén
logregel per herstelde map. De rootfase laat zulke ingangen staan (zij leest of schrijft er niet doorheen; `chown -R` volgt
geen koppeling en een harde koppeling over mounts heen bestaat niet). Wat de start niet veilig kan opruimen, een map met inhoud,
blijft een weigering vóór elke wijziging. Alle meldingen die een snapshot noemen, geven nu eerst een veilige weg en zeggen
dat kijkgegevens van na die snapshot verloren gaan (ook de bestaande meldingen over `datamap-versie`, de downgradeweigering en
een gekoppelde opslagmap). Bewijs met de proeven van de reviewers op de entrypoint van deze stap: de serverdatabase en de
andere naam blijven byte-gelijk en de start gaat door (DLL en `meta.json` als harde koppeling, DLL als symbolische koppeling
als root en als Custom User, `meta.json` als koppeling, FIFO, lege map, tweede naam, koppeling in een oude versie).

**Overerfbare ACL (R-VEILIG-3).** Bij `/config` 0755 met alleen een overerfbare ACL-regel (default-ACL `g::rwx`) weigerde de
start pas nadat de rootfase `chown -R` had gedaan en de app-fase `jelly-leon/` had aangemaakt (die kreeg 0775 door de
overerving), terwijl de melding en deze ADR zeiden dat er niets was gewijzigd. Herhaald en rood gezien. De modus van de
bestaande map verraadt zo'n regel niet, en `getfacl` zit niet in de runtime-image. Herstel (`assert_new_dirs_private`): vóór
elke wijziging, als root vóór de eigenaarswissel en als app-gebruiker vóór herstel en vastleggen, maakt de start in elke map
waarin zij zelf een map gaat aanmaken (`/config` voor `jelly-leon/` en `plugins/`, `plugins/` voor de pluginmap) één proefmap
met een onvoorspelbare naam (`mktemp -u` en een exclusieve `mkdir`, zoals de echte `mkdir`), leest de modus en verwijdert
haar direct. Krijgt die schrijfrecht voor groep of anderen, dan weigert zij met een melding over de ACL-regels voor
onderliggende mappen; eigenaar, rechten, ACL en inhoud blijven byte-gelijk, alleen de wijzigingstijd van die ene map
verandert. Dit meet het werkelijke resultaat, ook bij NFSv4-overerving, zonder native code. Een bestaande installatie waarin
de start geen map meer aanmaakt, wordt niet geproefd (geen nieuwe strengheid); mappen die de server later zelf aanmaakt,
vallen buiten deze startcontrole (zie de vervolgpunten van de review).

**B1 met het gemeten gevolg (R-VEILIG-2 en R-HARDE-EIS-3; besluit B1 optie A1, met A3; wordt de gebruiker opnieuw
voorgelegd).** De eerdere tekst (deel 1c en 1d) zei dat in het scenario "een andere app met dezelfde gebruiker en een deel
van de Jelly Leon-config gemount" niets wordt overschreven. Dat klopt niet. Gemeten door de review en hier herhaald (echte
stock-server 12.4, netwerkloos, synthetisch): na de start vervangt een tweede container met dezelfde uid en alleen
`plugins/configurations` gemount het gewone configuratiebestand door een koppeling naar `/config/data/jellyfin.db`; slaat de
beheerder daarna de pluginconfiguratie op, dan begint de serverdatabase met XML. Een startcontrole kan dat na de start niet
tegenhouden. Het gevolg is dus vernietiging van de database met kijkgegevens, niet alleen een lege ingang. Besluit: de grens
blijft zonder native uitzondering (geen fstat of openat2, de analyzer en zijn lege uitzonderingslijst ongewijzigd), en de
twee gebruiksregels zijn nu **verplicht** en staan bovenaan `deploy/truenas/CUSTOM_APP.md`, met de reden in gewone taal:
(a) koppel de config-dataset of een map daarin (ook `plugins/configurations`) nooit aan een andere app; (b) zet alleen
eigen snapshots of back-ups terug. Daarnaast is in beheerde code gebouwd wat kan (optie A3): `PluginModuleSwitches` toetst
vóór elke lezing en opslag van de eigen configuratie het bestand en zijn map opnieuw (`JlPaths.EisVeiligConfiguratiebestand`:
de map en haar ouders zoals de eigen opslag, het bestand geen symbolische koppeling of map). Bij een onveilig bestand of
onveilige map leest of schrijft de plugin niets: modules staan uit, `GET` en `PUT /media/v1/modules` geven 503
`storage_unavailable`; een fout van de server bij het lezen of opslaan wordt geen ruwe fout meer in een gebeurtenis. Het pad
leidt de plugin af uit `DataPath` (de server: `PluginConfigurationsPath` = `<ProgramDataPath>/plugins/configurations`,
`DataPath` = `<ProgramDataPath>/data`), zonder nieuw lid van de server-ABI; een test legt vast dat het gelijk is aan
`ConfigurationFilePath`. Gemeten op de echte server in hetzelfde scenario, maar via de route van de plugin: met de plugin van
`81e9c4a26` schreef `PUT /media/v1/modules/devices` (200) door de koppeling in de serverdatabase; met de plugin van deze stap
geven `GET` en `PUT` 503 en blijft de serverdatabase byte-gelijk. **Eerlijke aantekening:** de serverroute
`GET`/`POST /Plugins/<id>/Configuration` (dashboard van de server) gaat niet langs de plugin; in dezelfde proef overschreef
`POST` (204) de serverdatabase nog steeds. Ook een harde koppeling of FIFO op dit bestand is in beheerde code niet te zien
(de start weigert ze), en tussen toetsen en opslaan blijft een wissel door dezelfde gebruiker mogelijk. Daarom blijven de
twee regels verplicht; de bescherming hangt daar af van de gebruiker.

**Teruggevallen plugin met de echte server in CI (R-HARDE-EIS-4).** De terugval van deel 1d werd alleen in de testhost
bewezen. De levenscyclus van de echte image (CI-job image, `image_lifecycle.py`, `check_storage_fallback`, naar de proef van de
review) start nu op dezelfde opslag met `data/jelly-leon` 0775 en controleert: server gezond; gezien, favoriet en hervatpunt
zetten en lezen; statisch afspelen; `GET /media/v1/modules` 503 `storage_unavailable` als beheerder, 401 anoniem, 403 voor de
niet-beheerder van de rooktest; Hub-route zonder token 401; een gebruiker aanmaken en verwijderen (204); precies één
opslagmelding; de eigen opslag van de plugin (data en cache: soort, modus, eigenaar, grootte, mtime, sha256) ongewijzigd.
Daarna herstel (0755) en herstart: modules 200 en dezelfde kijkgegevens. Valt de plugin terug naar de oude registratie, dan
start de server niet en is de stap rood; de beoordeling zelf is zonder Docker getest (`test_image_lifecycle_processes.py`).
Geen extra imagebouw: de stap gebruikt de image die de job al bouwt. Lokaal draaide de proef van de review op de stock-server
12.4 met de plugin van deze stap: 15/15.

Uitvoering, rode herhalingen en tegenproeven van deel 1f: `docs/platform-v2/test-evidence/s-g1-16-deel1f-herstel-reviews.md`.
De echte NAS, Emby en accounts zijn niet benaderd.

#### Opslagdreigingen, deel 1g (tmpfs-grens, ruimte, proefmap, pluginconfiguratie, eigen pluginmappen, 2026-11-18)

Bronbasis: `02ae7d4a5d999d38361c40ccae558e693cadcd96`. Klein, gericht herstel na de herreview van deel 1f (R-VEILIG), met de
besluiten van de regisseur van 2026-11-18. Deel 1 tot en met 1f zijn niet omgebouwd. Elke bevinding is eerst zelf herhaald
en rood gezien, in netwerkloze wegwerpcontainers met alleen synthetische bestanden.

**Tmpfs-`/cache` (R-VEILIG-1f-1, belangrijk; besluit optie A: houden en afdekken).** `own_tmpfs` aanvaardt een tmpfs met
`/cache` als eigen koppelpunt (wortel `/`) die bij de start leeg is. Een lege tmpfs van de NAS die als héle wortel is gekoppeld
(Host Path `/dev/shm`; de TrueNAS-appbibliotheek 2.3.20 sluit dat pad niet uit) of een met een andere app gedeelde lege tmpfs
ziet er in de mounttabel precies zo uit. De container kan een eigen tmpfs dus **niet sluitend** onderscheiden van een lege
gedeelde tmpfs. Meting van de review (gedeeld lokaal Docker-tmpfs-volume op de hele wortel, `volume-nocopy`): de start nam het
aan als root en als Custom User, ook terwijl een andere app het vasthield. Daarna maakte een andere uid in die `/cache` een map
met een koppeling naar `/config/data`, en las een proces als 568 in de Jelly Leon-container daardoorheen de synthetische
serverdatabase. Of een schrijfactie van de echte server zo'n koppeling volgt, is niet gemeten. Bovendien maakte de rootfase
de wortel van de gedeelde tmpfs eigenaar 568:568. Hier herhaald met een houdercontainer: de wortel was `1777 0:0` vóór en
`1777 568:568` na een start als root. Herstel:
- De rootfase wisselt een tmpfs-`/cache` nooit meer van eigenaar of modus (de eigenaarswissel slaat `/cache` over als het
  bestandssysteem tmpfs is). Een tmpfs uit het formulier houdt `0:0 1777` van Docker en de image en blijft zo voor 568
  schrijfbaar; root en Custom User starten (CI-levenscyclus: `/cache` na de start `0:0 1777`, healthy, plugin aan).
- Goedkope extra drempel die geen correcte opzet weigert: een tmpfs-`/cache` die geen eigen, lege tmpfs is (een map ín een
  tmpfs, of een al gevulde tmpfs), moet nu ook als root al van 568 zijn. Anders weigert de start vóór de eigenaarswissel van
  `/config`, zonder iets te wijzigen; eerder volgde daar `chown -R`. De weigering van een gevulde tmpfs bestond al. Er is
  bewust geen herkenning op grootte of modus.
- `CUSTOM_APP.md` heeft nu drie verplichte regels. **Verplicht 3:** `/cache` is een eigen dataset van alleen deze app, of het
  opslagtype tmpfs van deze app. Nooit een Host Path naar een tmpfs van de NAS (`/dev/shm`, `/run`, `/tmp`) en nooit een met
  een andere app gedeelde map of dataset. Het gemeten gevolg staat erbij, in gewone taal. Zinnen die meer beloofden, zijn
  geschrapt of gecorrigeerd: in `CUSTOM_APP.md` ("bestaat alleen in deze container", "aanvaardt hem alleen als het een eigen
  … tmpfs is", de Problemen-rij), in deel 1f van deze ADR, in de entrypoint, de Dockerfile en `JlPaths`.
- **Restgrens (eerlijk):** een lege gedeelde tmpfs blijft aanvaard. De bescherming hangt daar af van Verplicht 3. Nog te meten
  op de echte NAS: is `/dev/shm` van de NAS bij de start leeg (`ls -A /dev/shm` in de TrueNAS-shell vlak vóór de start)? Welke
  modus, eigenaar en grootte geeft het opslagtype tmpfs aan `/cache` (`stat -c '%a %u:%g' /cache` en `df -B1 /cache` in de
  shell van de app)? Gelezen in de openbare bron (`library/2.3.20/tmpfs.py`, `ix-dev/stable/ix-app/questions.yaml`): het
  formulier vraagt alleen een grootte in MiB (standaard 500), die als bytes wordt gerenderd, en geen modus. Gemeten in
  Docker: zo'n tmpfs krijgt de modus van de imagemap, dus 1777.

**Te kleine tmpfs (R-VEILIG-1f-2, belangrijk).** Herhaald met de echte gepinde stock-server 12.4 (eigen entrypoint van de
image, Custom User 568): een tmpfs van 2048 MiB weigert ("The path `/cache` has insufficient free space. Available: 2GiB,
Required: 2GiB"); 2560 MiB start. Met de entrypoint van de basis: 2048 MiB dezelfde Engelse fout, 2049 en 2560 MiB starten.
Oorzaak: `StorageHelper.TwoGigabyte` (2147483647 bytes) wordt gemeten nadat `MakeSanityCheckOrThrow` zelf `CACHEDIR.TAG` in
`/cache` heeft gezet (op tmpfs één pagina). Herstel:
- Overal staat nu **minstens 2560 MiB**, met de reden: 2 GiB plus marge, want 2048 MiB start niet. Dat geldt voor
  `CUSTOM_APP.md` (Datasets en Problemen) en de CI-levenscyclus (`TMPFS_CACHE`).
- De start weigert een tmpfs-`/cache` met minder vrije ruimte dan de server eist (`assert_cache_space`, vóór elke schrijfactie,
  in beide fasen). Dat gebeurt met één Nederlandse regel (wat, waarom, welke waarde) in plaats van de Engelse fout met
  herstartlus. De grens komt uit één plek: de constante van de server plus die ene pagina. Een test vergelijkt de waarde met
  `StorageHelper.cs`. Gemeten op de lichte proefimage met de stock-server: 2048 MiB geeft de Nederlandse weigering zonder
  serverstart; 2049 MiB en 2560 MiB (root en Custom User) starten. De start weigert dus geen tmpfs die de server zou aanvaarden.
  Een dataset met te weinig ruimte meldt de server zelf (ook voor `/config`).

**Lege proefmap na een afgebroken start (R-VEILIG-1f-3, klein).** Herhaald: een start die precies tussen `mkdir` en `rmdir`
van de ACL-proefmap (deel 1f) wordt afgebroken, laat `.jelly-leon-proef.*` achter. Een rest van root bleef ook na een tweede
start staan. Herstel (`remove_probe_leftovers`, app-fase, na alle weigeringen): alleen een lege, echte map met precies het
naampatroon van `mktemp` (tien letters of cijfers), direct in `/config` of `plugins/`, wordt verwijderd. `find -type d` volgt
geen koppeling en `-delete` is `rmdir`, dus nooit `rm -r`. Er volgt één logregel per map. Gemeten met resten van root, als root
en als Custom User: de lege resten verdwijnen, een rest met inhoud en een koppeling met die naam blijven staan.

**Harde koppeling op het eigen configuratie-XML (besluit 4).** Sinds deel 1f legde een harde koppeling op
`plugins/configurations/Jellyfin.Plugin.JellyLeon.xml` de hele server stil, ook een goedaardige (ontdubbelen, terugzetten
met behoud van koppelingen). Het herstel volgt de voorwaarden van de review:
- alleen in de app-fase, ná de toets van `plugins/configurations` met de app-gebruiker;
- alleen een gewoon bestand met meer dan één naam van hooguit 1 MiB (`stat` opent niets). Een symbolische koppeling, FIFO,
  map of ander type, en een groter bestand, blijven een weigering met de bestaande veilige melding;
- een verse kopie met `mktemp` in dezelfde map, daarna hernoemen over de ingang (`place_file`). Er wordt nooit door de
  koppeling geschreven;
- één logregel.

De rootfase laat precies dit geval door en blijft voor al het andere even streng. Gemeten met de echte stock-server
(XML als harde koppeling op een synthetische serverdatabase, root en Custom User): de server start, `GET /media/v1/modules`
geeft 200, de database blijft byte-gelijk met één naam, en de XML heeft één naam. De server schreef daarna zelf een nieuwe
standaardconfiguratie in het eigen bestand. **Aantekening:** is `/config` bij de eerste start nog niet van 568, dan wijzigt
`chown -R` van de rootfase de eigenaar van de inode, en dus ook van de andere naam. Die andere naam ligt altijd binnen
hetzelfde bestandssysteem. Is `/config` een submap van een dataset (Host Path naar een submap), dan kan die andere naam
buiten `/config` liggen; ook dan wisselt alleen de eigenaar, nooit de inhoud (deel 1h, R-EERLIJK-4, gemeten). Dat gold al
voor elk bestand onder `/config` (ook vóór deel 1g, bijvoorbeeld een harde koppeling in `metadata/`) en voor de pluginmap
(deel 1f). Een wissel door dezelfde gebruiker tussen toetsen en kopiëren valt onder B1.

**Alleen de eigen pluginmappen (vervolgpunt van de review, punt 5).** `install_plugins` verwijderde met `rm -rf` elke map
`JellyLeon_*` van een andere versie, ook `JellyLeon_Extra_2.0.0.0` van een andere plugin. Herhaald, met nog een gevolg: had zo'n
andere plugin een submap met inhoud (bijvoorbeeld `runtimes/`), dan weigerde de start de hele server ("map met inhoud in de
eigen pluginmap"). Herstel (`own_plugin_dir`): een eigen pluginmap is `<naam>_<versie>` van een plugin die de image zelf
meelevert. De naam komt exact uit `/usr/share/jelly-leon/plugins`; de versie bestaat alleen uit cijfers en punten.
Controle, herstel (`repair_plugin_dirs`) en verwijderen gelden alleen nog voor die mappen. Een onbekende `JellyLeon_*`-map
blijft byte-gelijk (getest met een harde en een symbolische koppeling, een submap met inhoud en modus 0775); elk van de vier
filters apart weghalen maakt de test rood. Proef met de entrypoint van de vorige image (`0783c1987`) en daarna die van deze
stap: `JellyLeon_0.0.9.0` wordt vervangen door `JellyLeon_0.1.0.0`, de andere plugin blijft byte-gelijk.

Status: Bezig; Sim-getest; NIET GEVALIDEERD (echte NAS). Uitvoering, rode herhalingen en tegenproeven:
`docs/platform-v2/test-evidence/s-g1-16-deel1g-herstel-herreview.md`. De echte NAS, Emby en accounts zijn niet benaderd.

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
2. **De proefassembly faalt**: `VerbodenAanroepen.cs` bevat verboden aanroepen, elk gemarkeerd met
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
- De opslaggrens controleert het tekstuele en echte pad en weigert sinds S-G1-16 deel 1b bovendien **alle symbolische
  koppelingen** in een opslagbestand of oudermap, ook een koppeling die binnen de eigen map blijft. Bij de start en
  elke bewerking worden eigenaar en groeps-/wereldschrijfrechten van de mappen gecontroleerd; nieuwe mappen zijn 0700.
  `JlDatabase` controleert hoofdbestand, WAL, SHM en journal vóór én na openen, voordat een PRAGMA of migratie wordt uitgevoerd.
  Bestaande opslagbestanden met groeps-/wereldschrijfrechten worden geweigerd; nieuwe bestanden zijn 0600.
  `InternalWriteScope` gebruikt een cryptografisch willekeurige tijdelijke naam en `CreateNew`; een bestaand bestand
  wordt nooit als tijdelijk bestand hergebruikt. De geopende stream krijgt een controle via de bestandsdescriptor.
  De oude weigering van een onveilig `<doel>.tmp` blijft bestaan, hoewel die naam niet meer gebruikt wordt.
  Bestaande negatieve opslagtests blijven bestaan. Eerdere positieve gevallen voor koppelingen zijn aangescherpt naar
  weigeren, met een gewone database als positieve tegenproef; geen weigertest is versoepeld.
  **Dit sluit niet elke alias of race:** een vooraf gelegde harde databasekoppeling verandert nog het buitenbestand,
  en een eigen UID kan tijdens openen een map wisselen zodat een leeg tijdelijk bestand buiten de eigen map ontstaat.
  De zelfstandige regressieproef blijft hiervoor rood; zie "Opslagdreigingen, deel 1b" en
  `docs/platform-v2/test-evidence/s-g1-16-deel1b-opslaggrens.md`. Er is geen native aanroep, analyzerverruiming of
  aanvaarde veiligheidsuitzondering toegevoegd. De absolute HARDE EIS is hiermee niet als volledig bewezen gemeld.
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
  lezen) en attributen op eigen code (zie de grens over een eigen route hieronder). De instellingen van de host (Kestrel,
  doorgestuurde koppen, JSON en andere optietypen van ASP.NET Core) zijn sinds herstelronde 9 wel JL0001, op naam: een
  instelling van de host die niet op `Options` eindigt en geen `HostOptions` is (bijvoorbeeld een eigen `IServer`, `IHostLifetime`
  of `IHostedService`), valt er niet onder. De eerder gemelde **open generieke registratie** is in S-G1-16 gesloten binnen
  de bestaande hostoptiecategorie: onder meer `typeof(IPostConfigureOptions<>)`, `typeof(IOptionsFactory<>)` en generieke
  implementaties zijn nu JL0001 (zie punt 9 en de bijbehorende tests). De proef zonder analyzer zet aantoonbaar een ingestelde
  hostoptie terug naar de standaard. Dit is geen algemene vrijgave van andere Microsoft-uitbreidingspunten.
  Ook niet gedekt: een netwerkclient buiten System.Net.Http, .Sockets, .WebSockets en .Quic en buiten `WebClient`/`WebRequest` (bijvoorbeeld
  `SmtpClient`, `Ping`). Een klasse op de witte lijst van de HTTP-laag heeft alleen het genoemde lid of uitbreidingspunt; wat zij
  daarbinnen doet (de spike roept na de controle `volgende(http)` aan) bewaakt de runtime-test van de spike, niet de analyzer.
- **Een eigen route boven een serverroute** (herreview 8, grens 5): attributen op eigen code tellen in de analyzer niet, dus
  `[HttpDelete("/UserPlayedItems/{id}")]` of een route met een hogere voorrang zou een serverroute kunnen overnemen. Dat de zin
  "die gelden alleen voor die code" voor routes klopt, rust op tests, niet op de analyzer:
  `RoutetabelTests.ElkeActie_LooptViaDePipelineEnKomtOvereenMetDeTabel` eist dat elke eigen actie `[JlRoute]` draagt en dat het
  pad gelijk is aan de routetabel, `RoutetabelTests.ElkeRoute_BestaatPreciesEenKeer` eist dat elk pad met `/media/v1/` of
  `/connector/v1/` begint, en `VersionControllerTests.Routes_MatchPublishedOpenApi` dekt `JellyLeonVersionController`. Geen
  serverroute begint met `media` of `connector`.
- **De browser als tussenpersoon** (herreview 8, R-HARDE-EIS-18; zie "Dreigingsmodel"): wat blijft, is wat de controle van de
  webbronnen niet als tekst ziet. Een pad dat bij het draaien wordt samengesteld, houdt `vraag()` tegen; een omweg die opzettelijk
  langs de tekstcontrole gaat (bijvoorbeeld een naam die uit stukken wordt samengesteld) valt buiten het dreigingsmodel. Een eigen
  actie die HTML of script als antwoord geeft, draait in de browser op de herkomst van de server; de plugin geeft alleen JSON
  (`JlResult`), maar de analyzer verbiedt een ander inhoudstype niet. Een status of kopnaam die pas bij het draaien ontstaat (een
  variabele, een samengestelde naam), ziet de analyzer niet. Dat dekt sinds herstelronde 10 (herreview 9, R-HARDE-EIS-20)
  de wacht tegen doorsturen bij het draaien, niet alleen `JlResult`: elk antwoord met een 3xx of een kop Location op een actie met
  `[JlRoute]` wordt 503, van welk type resultaat ook (zie "HTTP-laag en netwerk", punt 8); met de spike aan geldt dat op elk
  pluginpad. Wat de wacht niet ziet: een eigen actie zonder `[JlRoute]`. De enige is `JellyLeonVersionController.GetVersion` (een
  vast 200-antwoord met JSON); `RoutetabelTests.ElkeController_LooptViaDeWacht_BehalveDeEneVersieactie` faalt bij elke andere
  controller of actie zonder `[JlRoute]`. De tekstcontrole van de webbronnen herkent `fetch` alleen als `fetch(` (herreview 9):
  `fetch.call(…)`, `fetch.apply(…)` en `var f = fetch; f(…)` komen erdoor. Zo'n verzoek draagt geen token van de gebruiker (dat is
  alleen via `ApiClient` bereikbaar, en `ApiClient` buiten `fetch` en `getUrl` is een testfout); er is geen schrijfpad gevonden.
  Dichten hoort bij S-G1-12 (webbronnen en de Hub-koppeling). De **webplugins van jelly-leon-web**
  (zie "4. Generator voor de web-`config.json`", `jlHook`) draaien ook in de browser met het token van de gebruiker en vallen in dezelfde categorie, maar horen
  bij een andere repo; daar hoort dezelfde vraag (alleen eigen paden, geen andere API-client).
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
