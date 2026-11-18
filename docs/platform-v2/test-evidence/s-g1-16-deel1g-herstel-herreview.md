# S-G1-16 deel 1g — herstel na de herreview van deel 1f

Status: **Bezig**; **Sim-getest**; **NIET GEVALIDEERD (echte NAS)**. Nog nodig op de echte NAS:
- is `/dev/shm` bij de start leeg?
- welke modus, eigenaar en grootte geeft het opslagtype tmpfs aan `/cache`?
- de modus en ACL van de preset Apps, NFSv4-ACL's en `fs.protected_hardlinks`.

B03-017 als geheel, zijn bewijsrij en de lokale image blijven onderdeel van deel 2. Bronbasis:
`02ae7d4a5d999d38361c40ccae558e693cadcd96`. Besluit en grenzen: ADR-0032, "Opslagdreigingen, deel 1g".

## Eerst herhaald (rood op de basis)

Alle proeven zijn gedaan in netwerkloze wegwerpcontainers, met alleen synthetische bestanden. Daarvoor is een lichte
proefimage gebruikt: de gepinde runtime-image 12.4 met daarin de entrypoint, de plugin-DLL, `VERSION` en de modi van
`/config` en `/cache` uit de runtimefase. De stock-server 12.4 is de echte server, niet de fork-server.

- **R-VEILIG-1f-1.** Een gedeeld tmpfs-volume als hele wortel op `/cache` (`volume-nocopy`), vastgehouden door een andere
  app (uid 65534). Na een start als root was de wortel `1777 568:568`; vóór de start was hij `1777 0:0`. Met een eigen
  tmpfs als root gaf de stub-server `/cache` 568:568.
- **R-VEILIG-1f-2.** Echte gepinde stock-server 12.4 (eigen entrypoint van de image, Custom User 568): met een tmpfs van
  2048 MiB stopt de server ("The path `/cache` has insufficient free space. Available: 2GiB, Required: 2GiB."); met 2560 MiB
  start hij. Met de entrypoint van de basis: bij 2048 MiB dezelfde Engelse fout, bij 2049 en 2560 MiB een start.
- **R-VEILIG-1f-3.** Lege proefmappen van root in `/config` en `/config/plugins` bleven na een start staan, als root en als
  Custom User. In de test bleef ook na een echte afgebroken start (kill -9 in het proefvenster) de rest staan.
- **Punt 4 (besluit).** Echte server, `Jellyfin.Plugin.JellyLeon.xml` als harde koppeling op een synthetische
  serverdatabase: de start weigerde als root en als Custom User; de server bleef stil.
- **Punt 5 (vervolgpunt).** Eerst startte de entrypoint van de vorige image (`0783c1987`); daarna kwam
  `JellyLeon_Extra_2.0.0.0` erbij, een andere plugin met een submap. Bij de update weigerde de start de hele server ("map met
  inhoud in de eigen pluginmap"). Zonder submap haalde `rm -rf` de andere plugin weg (meting van de review; hier in de test
  ook rood).

## Regressie: start van de container

`tools/jelly-leon/tests/test_entrypoint_opslaggrens.py`. De functies en de fasen staan letterlijk zo in de entrypoint. De
tests draaien met dash, umask 0022, en waar nodig met een synthetische mounttabel. Elke test faalt zonder het herstel (zie
"Mutaties"); na het herstel zijn ze groen:

- de rootfase met een eigen tmpfs (modus 1777 of 0777): de eigenaarswissel raakt alleen `/config`, `/cache` behoudt
  eigenaar en modus. Een tmpfs-`/cache` die geen eigen, lege tmpfs is en niet van 568, weigert als root vóór de
  eigenaarswissel, zonder wijziging;
- de doctest: de drie verplichte regels staan bovenaan `CUSTOM_APP.md`, met in de derde `/dev/shm`, `/run`, `/tmp`,
  "gedeeld", het gevolg en "niet sluitend onderscheiden"; geen zin belooft nog dat de container een gedeelde tmpfs herkent;
- te weinig ruimte: een tmpfs van 500 en 2048 MiB weigert met één Nederlandse regel ("minstens 2560 MiB", "Er is niets
  gewijzigd"); 2049 en 2560 MiB gaan door, net als een dataset. De grens komt uit `StorageHelper.cs` (de test vergelijkt de
  constante), en het advies van 2560 MiB staat gelijk in de melding, `CUSTOM_APP.md` en de CI-proef;
- een echte afgebroken start: de volgende start ruimt de lege proefmap in `/config` en in `plugins/` op. Een rest met
  inhoud, een koppeling of bestand met die naam, een andere naam en een diepere map blijven staan;
- een harde koppeling op het eigen XML (op een kopie van de instellingen, op de serverdatabase, precies 1 MiB): de app-fase
  zet een eigen kopie neer. De instellingen blijven, de andere naam is byte-gelijk (zelfde inode, één naam) en er blijft geen
  tijdelijk bestand achter. De rootfase laat het geval ongewijzigd door. Een harde koppeling groter dan 1 MiB en een FIFO
  weigeren zonder wijziging (time-out 30 s: de start blijft niet hangen);
- alleen de eigen plugin: een oudere eigen versie wordt vervangen. `JellyLeon_Extra_2.0.0.0` (0775, met een harde en een
  symbolische koppeling, een submap met inhoud en een lege map) blijft byte-gelijk.

`tools/jelly-leon/tests/test_image_lifecycle_processes.py`: de levenscyclus is rood als de tmpfs-`/cache` na een start niet
meer `0:0 1777` is, en de CI-proef start met 2560 MiB.

### Mutaties (V-003)

- Punten 1 t/m 4: de nieuwe tests zijn eerst gedraaid op de stand vóór het herstel. Uitkomsten:
  - punt 1: 5 failed;
  - punt 2: 6 failed;
  - punt 3: 1 failed;
  - punt 4: 4 failed. De weigering bij een te groot bestand was al groen; die test bewaakt dat de weigering blijft.
- Punt 5: de test is eerst op de vorige stand gedraaid: 1 failed. Daarna is elk van de vier filters apart weggehaald
  (controle, weigering bij een map met inhoud, herstel, verwijderen). Elke keer: 1 failed.

## Volledige start (lichte proefimage, eindstand)

- `proef_1g.py eind tmpfs proefmap update`: alle 7 gevallen zoals verwacht.
  - De wortel van een gedeelde tmpfs blijft `1777 0:0`, als root en als Custom User.
  - Een eigen tmpfs blijft `1777 0:0`, als root en als Custom User.
  - Lege proefmappen van root worden opgeruimd; een rest met inhoud en een koppeling blijven staan.
  - Update vanaf de vorige image: `JellyLeon_0.0.9.0` wordt vervangen door `JellyLeon_0.1.0.0`, de andere plugin blijft
    byte-gelijk. Het vervangen van een oudere eigen pluginversie bewijzen alleen deze lokale proef en de pytest-test
    `test_alleen_de_eigen_plugin_wordt_bijgewerkt_een_andere_jellyleon_map_blijft_ongemoeid` (ook in CI, job Forkregels).
    De CI-upgradeproef gaat van stock 10.11.11 naar de image, zonder oudere eigen pluginmap, en toetst dit niet (deel 1h,
    R-EERLIJK-2).
- `proef_1g.py eind ruimte xml`, met de echte stock-server: alle 8 gevallen zoals verwacht.
  - Stock-entrypoint: 2048 MiB weigert, 2560 MiB start.
  - Entrypoint van deze stap: 2048 MiB weigert in het Nederlands zonder serverstart. 2049 MiB start, en 2560 MiB start als
    root en als Custom User.
  - XML als harde koppeling op een synthetische serverdatabase, als root en als Custom User: de server start,
    `GET /media/v1/modules` geeft 200, de database blijft byte-gelijk en de XML heeft één naam.
- De startproef van R-HARDE-EIS (de kopie van de review, met de entrypoint van deze stap en tmpfs 2560 MiB): 13/13 in orde.
  Een bestaande installatie start na de update als root en als Custom User, met en zonder tmpfs. De serverdatabase blijft
  byte-gelijk, en een weigering wijzigt niets.

## Levenscyclus van de echte image (CI-job image)

Nieuw of gewijzigd in `tools/jelly-leon/e2e/image_lifecycle.py`:
- de tmpfs-`/cache` heeft nu 2560 MiB;
- na de start als root en als Custom User moet `/cache` nog `0:0 1777` zijn;
- een tmpfs van 2048 MiB moet weigeren met "minstens 2560 MiB".

De uitkomst op de eind-commit staat in het externe rapport.

## Aanvulling deel 1h (na de slotcontrole R-EERLIJK)

Status ongewijzigd: **Bezig**; **Sim-getest**; **NIET GEVALIDEERD (echte NAS)**. Bronbasis
`1c1cf919640bf7a01cf0b1774b0874056d50f93a`; uitvoering in het externe rapport `RAPPORT-A-HERSTEL-1h.md` (logs in `bouw1h/`).
- R-EERLIJK-5: eerst gemeten met de echte gepinde stock-server 12.4 in een lichte proefimage met de entrypoint van de
  bronbasis, als root met een eigen tmpfs `mode=0755` (eigenaar 0:0): de server stopt met
  "Access to the path '/cache/.jellyfin-cache' is denied" (exit 139), zonder Nederlandse melding. Herstel: de app-fase
  toetst of een tmpfs-`/cache` voor de app-gebruiker schrijfbaar is; zo niet, één Nederlandse regel en stoppen, zonder iets te
  wijzigen (eigenaar en modus van de tmpfs blijven ongewijzigd, zoals in deel 1g besloten). Met de entrypoint van 1h, echte
  server: 0755 als root weigert in het Nederlands met `/config` ongewijzigd; zonder eigen modus (1777) als root en als Custom
  User, en `mode=1777` als root, start de server. Test
  `test_eigen_tmpfs_als_cache_waarin_de_app_niet_schrijft_weigert_met_een_nederlandse_regel` (rood zonder het herstel: 2
  failed); de CI-levenscyclus weigert nu ook een tmpfs met `mode=0755` als root. `CUSTOM_APP.md` noemt het geval onder
  *Problemen*.
- R-EERLIJK-3: de opruimtest heeft nu ook een leeg bestand met precies het naampatroon; dat blijft staan. De mutatie die
  `-type d` weghaalt, is nu rood (1 failed).

## Uitvoering en grenzen

Commando's, exitcodes en letterlijke slotregels staan in het externe rapport `RAPPORT-A-HERSTEL-1g.md`, met de ruwe logs in
de ketenmap `bouw1g/`. Geen bestaande test is overgeslagen of afgezwakt. Twee tests zijn met de besluiten meeveranderd:
- de doctest gaat nu over drie regels;
- het geval "XML als harde koppeling" is volgens besluit 4 een herstel geworden; de weigering geldt nu voor een harde
  koppeling groter dan 1 MiB.

De analyzer en zijn lege uitzonderingslijst zijn ongewijzigd, en de negatieve analyzerbouw geeft nog precies de 323
verwachte fouten. De echte image wordt alleen in CI gebouwd.

Grenzen:
- een lege gedeelde tmpfs blijft aanvaard; daartegen beschermt alleen *Verplicht 3*;
- of een schrijfactie van de echte server een koppeling in een gedeelde `/cache` volgt, is niet gemeten;
- `chown -R` bij de eerste start wijzigt de eigenaar (nooit de inhoud) van een harde koppeling op het XML-bestand, ook van
  een andere naam buiten `/config` op hetzelfde bestandssysteem als `/config` een submap van een dataset is (deel 1h);
- een wissel door dezelfde gebruiker tussen toetsen en handelen valt onder B1 (ADR-0032, deel 1g).
