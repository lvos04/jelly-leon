# ADR-0032 — B03-017: bouwwachters — analyzer voor verboden API's en generator voor de web-`config.json`

- **Status:** Aanvaard (2026-11-11). Uitvoering van ADR-0016 (één plugin met modules) en ADR-0019 (haken en generator).
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
| **JL0001** | schrijvende server-API. Per interface geldt "alles verboden behalve lezen" (voorvoegsels `Get`, `Find`, `Query`, `Is`, `Has`, `Can`, `To`): `ILibraryManager`, `IItemRepository`, `IItemPersistenceService`, `IPlaylistManager`, `ICollectionManager` (ook `GetCollectionsFolder`, want die kan aanmaken), `IUserManager`, `IDeviceManager`, `IUserDataManager`, `IProviderManager`, `ISubtitleManager`, `IMediaSegmentManager`, `ISessionManager`, `IServerConfigurationManager`/`IConfigurationManager`; op `BaseItem` en afgeleiden de wijzigende methoden (`Update*`, `Delete*`, `Refresh*`, `Save*`, `Add*`, `Remove*`, `Set*`, `Swap*`, `Changed*`, `Mark*`, `Validate*`) | bibliotheek, opslag van items, afspeellijsten, collecties, gebruikers en apparaten: **nergens**. De overige alleen in één met naam genoemde klasse per API (witte lijst) |
| **JL0002** | bestanden schrijven, verplaatsen of verwijderen: `System.IO.File` en `Directory` (alles behalve lezen), wijzigende methoden en eigenschappen van `FileInfo`/`DirectoryInfo`, `new FileStream`, `new StreamWriter(pad)`, `new SqliteConnection`, wijzigende methoden van `IFileSystem` | alleen in `Core.Storage` en `Core.Secrets` (die bewaken de schrijfgrens `<DataPath>/jelly-leon/**` en `/cache/jelly-leon/**` zelf); `File`/`Directory`/`IFileSystem`-methoden daarnaast in één genoemde klasse per API |
| **JL0003** | de database van de server: elk gebruik van `JellyfinDbContext` en elke tekst met `jellyfin.db` of `library.db` | **nergens**, geen uitzondering mogelijk |
| **JL0004** | processen starten (`Process.Start`, `new Process`, `new ProcessStartInfo`) | alleen in `Core.Werker` (de werkerbewaker van B03-018); geen uitzondering per klasse |
| **JL0009** | een ongeldige regel in de witte lijst | — |

Verboden is "aanroepen én ernaar verwijzen": een methodegroep (`Action<string> f = File.Delete`) telt als aanroep.
Gegenereerde code wordt ook gecontroleerd.

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
2. **De proefassembly faalt**: `VerbodenAanroepen.cs` bevat 61 verboden aanroepen, elk gemarkeerd met
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

- Een analyzer is **geen zandbak**. Reflectie, `dynamic`, eigen P/Invoke of een tweede assembly ziet hij niet. Daarom
  blijven de andere lagen bestaan: de schrijfgrens in `Core.Storage` (weigert elk pad buiten de eigen mappen tijdens
  het draaien), de alleen-lezen mediamount, en JLT-65 (stock en fork naast elkaar; de 12.x-tabellen mogen alleen op de
  toegestane lijst afwijken).
- Hij bewaakt **methoden**, niet het zetten van eigenschappen op serverobjecten (`item.Name = …`). Zo'n wijziging
  bereikt de database pas via een opslagaanroep, en die is verboden.
- "Lezen" is op naam bepaald, en dat is in upstream geen garantie: bij het nalopen van v12.4 bleken
  `ILibraryManager.GetGenre`/`GetStudio`/`GetArtist`/`GetYear`/`GetMusicGenre`/`GetOrCreatePerson`, `GetNamedView`,
  `GetShadowView` en `GetUserRootFolder` een item of map aan te maken als die ontbreekt,
  `ISessionManager.GetSessionByAuthenticationToken` sessieactiviteit vast te leggen en `BaseItem.ReattachUserDataAsync`
  kijkgegevens te verplaatsen. Die staan nu met naam bij de verboden leden, net als `GetCollectionsFolder` en
  `GetPlaylistsFolder`. Om dit bij een sync niet opnieuw te missen ligt de **hele ledenlijst** van de bewaakte
  servertypen vast in `Analyzer/BewaakteLeden.txt` (363 leden met het oordeel `lezen` of `verboden`). Een nieuw,
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
