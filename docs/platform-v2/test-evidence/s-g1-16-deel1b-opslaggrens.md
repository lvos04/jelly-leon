# S-G1-16 deel 1b — opslaggrens

Status: **Bezig; NIET KLAAR**. B03-017 in EVIDENCE en de lokale image blijven deel 2.
Bronbasis: `b257c5403a6da940be7b157f32f82333bcd88797`. Geen echte NAS, Emby of accounts benaderd.

## Gebouwd en gericht getoetst

`JlPaths` controleert Linux, de procesrechten, koppelingen, map-eigenaarschap en groeps-/wereldschrijfrechten,
ook boven de eigen map en bij latere bewerkingen. Geen automatische rechtenreparatie: onveilige opslag weigert.
Nieuwe mappen zijn 0700. De eigendomsproef zet met een beheerde BCL-aanroep alleen de veilige, bestaande modus terug;
zonder effectieve capabilities mag alleen de eigenaar dat doen. De vaste systeemouders uit de image zijn toegelicht
in ADR-0032, "Opslagdreigingen, deel 1b". Een systeemouder mag niet als gegevensmap worden gekozen.

`InternalWriteScope` maakt een tijdelijk bestand met 128 willekeurige bits, exclusief via CreateNew en met 0600.
Een botsing wordt geweigerd; het reeds aanwezige bestand wordt ook niet opgeruimd. De geopende stream wordt
gecontroleerd vóór de inhoud wordt geschreven. Geheimen en migratiekopieën gebruiken dezelfde bestandsgrens.
Mapaanmaak en verwijderen hercontroleren de grens. De oude weigering van een onveilig vast `.tmp`-pad blijft staan.

`JlDatabase` weigert iedere symbolische koppeling op de database, WAL, SHM of journal, ook binnen de eigen map,
en onveilige bestandsrechten. De controle wordt na openen herhaald vóór PRAGMA's en migratie. Nieuwe databases
worden eerst exclusief als 0600 gemaakt. Migratiekopieën, bewaren van drie kopieën, secure_delete, WAL-checkpoint
bij wissen en het verbod op ATTACH/VACUUM INTO blijven bestaan. Geen nieuwe native aanroep of analyzeruitzondering.

De nieuwe xunit-regressies zijn op de oude code of vóór hun herstel rood uitgevoerd: twaalf eerste gevallen,
drie systeemoudergevallen en vier gevallen met onveilige bestandsrechten. Een proef voor de gebruikte ZIP-extractor
bewaakt een bestaande aanname over archiefmetadata. Bestaande negatieve tests zijn behouden. Positieve gevallen
met koppelingen zijn aangescherpt naar weigering; gewone bestanden blijven als positieve tegenproef aanwezig.

## Zelfstandige regressieproef, inclusief rood bewijs

Bron in de repo: `tools/jelly-leon/opslag_grensproef.py` en `plugins/JellyLeon/proeven/OpslagGrensproef.cs`.
De generator kopieert precies de huidige drie opslagbestanden. Alleen de FileStream- en SqliteConnection-aanmaak
worden vervangen door een testwrapper met een eenmalige controle/openhaak. De foutvertaling in het harnas is een
IOException; de padcontroles en schrijfhandelingen blijven gelijk. Dit harnas komt niet in de pluginassembly.

Het oorspronkelijke deel-1-onderzoek is hiermee als herhaalbare regressieproef in de repo opgenomen en uitgebreid
met een botsing op de willekeurige tijdelijke naam. De beoordelaar vereist alle vijf uitslagen en geeft exitcode 1
als een buitenbestand óf de buitenmap verandert. De afzonderlijke grensproef blijft bewust buiten de normale
xunit-solution: een groene pluginbouw vervangt haar rode veiligheidsuitkomst niet. Er is geen CI-controle uitgezet.

| Proef | Basiscommit | Na beheerd herstel |
|---|---|---|
| Harde koppeling op vast tijdelijk bestand | Buitenbestand gewijzigd | Byte- en mapgelijk; oud tijdelijk bestand niet geopend |
| Harde koppeling op database | Buitenbestand gewijzigd | **Rood: buitenbestand gewijzigd** |
| Eigen map wisselen vóór FileStream | Buitenbestand gewijzigd | Buitenbestand byte-gelijk; **rood: leeg tijdelijk bestand buiten eigen map** |
| Databasepad wisselen vóór SqliteConnection | Buitenbestand gewijzigd | Geweigerd; buitenbestand en buitenmap gelijk |
| Botsing op werkelijk gekozen tijdelijk bestand | Buitenbestand gewijzigd | CreateNew weigert; buitenbestand en buitenmap gelijk |

Reproductie, vanuit de repo, met uitvoer buiten de repo (niet in een reeds bestaande proefmap):

```sh
python3 tools/jelly-leon/opslag_grensproef.py --maak <KETENMAP>/nieuwe-proef
JL_ENV='-v <KETENMAP>/nieuwe-proef:/proef' \
  flock <WERKMAP>/.lokaal/docker-build.lock nice -n 10 \
  <WERKMAP>/.lokaal/jl-dotnet.sh run --project /proef/OpslagGrensproef.csproj -c Release -m:4 \
  > <KETENMAP>/nieuwe-proef.log 2>&1
python3 tools/jelly-leon/opslag_grensproef.py --beoordeel <KETENMAP>/nieuwe-proef.log
```

De SDK-uitvoering geeft 0 voor uitgevoerd; de beoordelaar geeft nu **1: NIET KLAAR**.
De proef gebruikt `ln` uitsluitend voor synthetische bestanden buiten de repo; de plugin start geen proces.
Lokale logs en exacte commando's: `<KETENMAP>/bouw1b/commando-resultaten.jsonl`, `padgrenzen-basis.log` en de
laatste `padgrenzen-definitief.log`, met hun afzonderlijke beoordelingslogs. De basisproef gebruikt de drie
opslagbronnen uit de basiscommit met dezelfde testhaken; alle vijf controles kunnen aantoonbaar rood zijn.

## Wie kan de resterende proeven uitvoeren?

De uitgevoerde aanvaller heeft dezelfde UID als de opslag- en servergebruiker. Een aparte synthetische container
met een andere UID krijgt zowel bij koppelen in de particuliere map als bij het vervangen van die map
Permission denied. Dat bewijst de lokale POSIX-opzet, niet een echte NAS of onbekende NFSv4-ACL's.
Configuratie die de opslag verlegt naar onveilige mappen wordt geweigerd. De plugin heeft geen bestandsimport
of archief-upload. De bestaande serverhersteldienst gebruikt ZIP-extractie naar gewone bestanden; de aanname
is gericht getoetst. De gedocumenteerde snapshotterugval kan bestaande koppelingen bewaren.

Een externe hersteller of een andere toepassing met toegang tot dezelfde dataset is niet automatisch vertrouwd.
Een vooraf aangeleverde harde koppeling is na de rechtencontrole nog steeds niet detecteerbaar met de gebruikte
beheerde bestandsinformatie. Aanvaarden dat alleen actor (a) overblijft vereist daarom een expliciet oordeel over
de bestaande en teruggezette gegevensmap. Dat oordeel ligt bij de regisseur en de volledige reviewketen.
Een bereikbare aanvoer door actor (b) is blokkerend. Er is geen uitzondering aangevraagd om die route te laten bestaan.

## Nog nodig

De twee rode restgrenzen vragen een besluit over het dreigingsmodel of een afzonderlijk ontwerp met een echte
OS-grens. Native fstat met een linkaantal en descriptor-gebonden open zouden extra informatie en binding bieden;
alleen een nieuwe padcontrole of een NOFOLLOW-vlag op het laatste paddeel volstaat niet. ADR-0032 beschrijft waarom
hier geen native omweg is gebouwd. Geen absolute garantie over kijkgegevens afgeleid uit groene unit- of CI-tests.

Lokale imagebouw, levenscyclus, rollback, upgrade en image-harnasproeven zijn niet uitgevoerd in dit deel;
zij horen bij deel 2. De CI op de eindcommit wordt in het externe eindrapport afzonderlijk beoordeeld.
De overige grenzen uit deel 1, het bereik voor de reviewers en de taken S-G1-10/12/14/20/50/70 blijven open zoals
overgedragen. Niets op de echte NAS gevalideerd; niet de situatie "alleen NAS-test nodig" zolang deze grenzen open zijn.
