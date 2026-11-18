# S-G1-16 deel 1f — herstel na de veiligheids- en HARDE-EIS-review

Status: **Bezig**; **Sim-getest**; **NIET GEVALIDEERD (echte NAS)**. Nog nodig op de echte NAS: de modus en ACL van de
preset Apps, de modus die het opslagtype tmpfs van TrueNAS geeft, NFSv4-ACL's en `fs.protected_hardlinks`. Besluit B1
(optie A1 met A3) wordt de gebruiker opnieuw voorgelegd met het gemeten gevolg. B03-017 als geheel, zijn bewijsrij en de
lokale image blijven onderdeel van deel 2. Bronbasis: `81e9c4a260d32bd71318be851397d970e2602521`. Besluit en grenzen:
ADR-0032, "Opslagdreigingen, deel 1f".

## Eerst herhaald (rood op de basis)

Alle proeven met synthetische bestanden, in netwerkloze wegwerpcontainers op de gepinde runtime-image; de proefscripts van
de reviewers zijn als kopie hergebruikt (extern, in de ketenmap).

- **R-VEILIG-1.** Hele keten (entrypoint van de basis, echte stock-server 12.4, plugin van de basis, Custom User): een
  andere uid legt in een voor iedereen beschrijfbare `plugins/configurations` de koppeling
  `Jellyfin.Plugin.JellyLeon.xml` → `/config/data/jellyfin.db`; de start ging door en na `GET /media/v1/modules` begon de
  synthetische serverdatabase (SQLite, 544768 bytes) met `<?xml`.
- **R-HARDE-EIS-1.** Update als Custom User 568 met `/cache` als tmpfs: de start weigerde ("/cache is van gebruiker 0 …
  Datasets → Permissions"), terwijl de vorige image die combinatie startte.
- **R-HARDE-EIS-2 en R-VEILIG-4.** Een harde koppeling van de DLL of `meta.json` naar een kopie, en een tweede naam binnen
  de pluginmap: de start weigerde en legde de hele mediaserver stil; de melding raadde een snapshot aan zonder waarschuwing.
- **R-VEILIG-3.** `/config` 0755 met alleen een overerfbare ACL-regel: de start weigerde pas na `chown -R` en `mkdir`
  (`/config` daarna gewijzigd), met de tekst "Er is niets gewijzigd".
- **R-VEILIG-2 / R-HARDE-EIS-3 (A3).** Zelfde uid, alleen `plugins/configurations` gemount: na de start legt een andere
  app de koppeling; de plugin schreef via `PUT /media/v1/modules/devices` (200) door de koppeling in de serverdatabase.

## Regressie: start van de container

`tools/jelly-leon/tests/test_entrypoint_opslaggrens.py` (functies en tweede fase letterlijk uit de entrypoint, dash, umask
0022, een synthetische mounttabel waar dat nodig is). Op de basis rood, na het herstel groen:

- pluginconfiguratie: koppeling, dode en harde koppeling, FIFO, map, gedeelde en gekoppelde `plugins/configurations`, ook
  in de rootfase vóór de eigenaarswissel; elke ingang en de serverdatabase gelijk. Correcte installatie met een eigen XML
  en een koppeling van een andere plugin start;
- tmpfs-cache: een eigen, lege tmpfs op het koppelpunt `/cache` start met modus 1777, 0777 of 0755; een gekoppelde map van
  een host-tmpfs, een map ín een tmpfs, een gevulde tmpfs, een gewone map 1777 en `/config` als tmpfs worden geweigerd,
  bij een tmpfs met een melding zonder verwijzing naar een dataset;
- zelfherstel: negen soorten vreemde ingangen in de eigen pluginmap worden verwijderd zonder te volgen (doel en andere naam
  byte-gelijk, één logregel, nieuwe DLL); een map met inhoud blijft een weigering vóór elke wijziging (ook als root); de
  rootfase volgt niets; elke melding met een snapshot noemt eerst een veilige weg en waarschuwt;
- overerfbare ACL (echte default-ACL via het xattr): weigering vóór elke wijziging als root en als app-gebruiker, met
  modus, eigenaar, groep, inhoud en ACL byte-gelijk en geen proefmap achter; een ACL zonder schrijfrecht en een bestaande
  installatie starten;
- de twee verplichte gebruiksregels staan bovenaan `deploy/truenas/CUSTOM_APP.md`.

Volledige start (proeven van de reviewers op de eindstand): R-VEILIG-startproef 26 gevallen zoals verwacht (onder meer
herstel van DLL- en `meta.json`-koppelingen als root en Custom User met serverdatabase byte-gelijk; weigering van de
pluginconfiguratie en van een map met inhoud zonder wijziging; ACL-overerving zonder wijziging); R-HARDE-EIS-startproef
13/13 (zonder imagebouw: de gepinde image met de entrypoint erin gekoppeld; tmpfs-modus per profiel nagebootst); eigen
tmpfs-proef 5/5 (Custom User met tmpfs 1777 en root met tmpfs 0777 starten; tmpfs 0755 en de host-`/dev/shm` weigeren met
de tmpfs-melding).

## Regressie: plugin

- `OpslagTests.TmpfsCache_*`: de mounttabel wordt ontleed (koppelpunt, wortel `/`, laatste mount telt, ontsnapte spaties);
  een eigen tmpfs als cachemap wordt aanvaard met modus 1777 of een vreemde eigenaar; zonder tmpfs, als map ín een tmpfs of
  als datamap blijft het streng. Een mutatie zonder de uitzondering is rood.
- `PluginGrensTests.Configuratie_*` (A3): bestand of map als koppeling, gedeelde map of een map op de bestandsnaam: modules
  uit, ETag en opslaan 503, de server-serializer niet aangeroepen, doel byte-gelijk; tegenproef met een gewoon bestand. Het
  afgeleide pad is gelijk aan `ConfigurationFilePath`. Een mutatie zonder de toets is rood (4 van 4).
- Echte server (stock 12.4, netwerkloos): Custom User 568 met `/cache` als tmpfs van 4096 MiB (1777): plugin van deze stap
  aan (modules 200, geen opslagmelding), plugin van de basis teruggevallen (503). Zelfde uid na de start: plugin van de basis
  schreef via `PUT` door de koppeling, plugin van deze stap 503 en serverdatabase byte-gelijk; de serverroute
  `POST /Plugins/<id>/Configuration` overschreef nog steeds (niet afgedekt, B1).

## Levenscyclus van de echte image (CI-job image)

Nieuw in `tools/jelly-leon/e2e/image_lifecycle.py`: imagemodi (`/config` 568:568 0755, `/cache` 568:568 1777, tmpfs 0:0
1777); echte start met `/cache` als tmpfs van 4096 MiB als root en als Custom User (healthy, rooktest, plugin aan); herstel
van een DLL-koppeling en een `meta.json`-harde koppeling als root en als Custom User (nep-server, database en back-up
byte-gelijk); weigering van de pluginconfiguratie als koppeling als root en als Custom User; de teruggevallen plugin met de
echte server (server gezond, kijkgegevens en afspelen, 503/401/403, Hub 401, gebruiker verwijderen 204, één melding, geen
schrijfactie; na herstel plugin aan en kijkgegevens gelijk). De beoordeling van elke stap is zonder Docker getest in
`test_image_lifecycle_processes.py`. Gemeten in CI (run 44205112539): met een tmpfs van 500 MiB weigert de server zelf te
starten (2 GiB vrij vereist); `CUSTOM_APP.md` noemde toen minstens 2048 MiB. Dat start zelf niet (correctie deel 1g: minstens
2560 MiB; `s-g1-16-deel1g-herstel-herreview.md`).

## Uitvoering en grenzen

Commando's, exitcodes en letterlijke slotregels staan in het externe rapport `RAPPORT-A-BOUW-1f.md`, met de ruwe logs in de
ketenmap `bouw1f/`. Geen bestaande test is overgeslagen of afgezwakt (de 1e-weigering van vreemde ingangen is volgens
besluit BN-2 een herstel geworden); de analyzer en zijn lege uitzonderingslijst zijn ongewijzigd, geen nieuw lid van de
server-ABI, en de negatieve analyzerbouw geeft nog precies de 323 verwachte fouten. De echte image wordt alleen in CI
gebouwd. Grenzen: de serverroute voor pluginconfiguratie, een harde koppeling of FIFO op dat bestand na de start, en een
koppeling van het hele wortelpunt van een host-tmpfs die bij de start leeg is (ADR-0032, deel 1f). Correctie deel 1g:
de container kan een eigen tmpfs niet sluitend onderscheiden van een lege gedeelde tmpfs; zie deel 1g en *Verplicht 3* in
`CUSTOM_APP.md`.
