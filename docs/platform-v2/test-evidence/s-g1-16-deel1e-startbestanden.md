# S-G1-16 deel 1e — installatiebestanden en startbestanden

Status: **Bezig**; **Sim-getest**; **NIET GEVALIDEERD (echte NAS)**, alleen NAS-test nodig voor dit herstel.
Bronbasis: `6525d9819e51579e03e62c6847d37cb45ec2fec9`. Herstel van R-TECH-1 en R-TECH-2 uit de technische review over
deel 1 t/m 1d. B03-017 als geheel, zijn bewijsrij en de lokale image blijven onderdeel van deel 2. Besluit en grenzen:
ADR-0032, "Opslagdreigingen, deel 1e".

## Eerst herhaald (rood op de basis)

- **R-TECH-1.** De hele, ongewijzigde entrypoint in een netwerkloze wegwerpcontainer op de gepinde runtime-image, met
  verse synthetische mappen per geval. Met de bestaande plugin-DLL als koppeling naar de synthetische
  `/config/data/jellyfin.db` was die database na de start overschreven, als Custom User én als root (daar ook na de
  eigenaarswissel naar 568). Een harde koppeling gaf hetzelfde. Een dode koppeling, een map op de DLL-naam en een
  gekoppelde `meta.json` werden niet geweigerd (de start ging door). In de tests liet een FIFO `cmp` hangen tot de
  time-out.
- **R-TECH-2.** De drie hostproeven van de review (`core/core.db` als koppeling, `core.db` 0660, `core/` 0770): 3 van 3
  rood, `Host.StartAsync` faalde met `UnauthorizedAccessException` uit `JlDatabase.EisEigenPlek` via `OpslagDienst<T>`.

## Regressie: start van de container

`tools/jelly-leon/tests/test_entrypoint_opslaggrens.py` voert de functies en de tweede fase letterlijk uit de entrypoint
uit (dash, umask 0022):

- `test_pluginbestand_met_koppeling_weigert_voor_vergelijken_of_schrijven`: DLL als symbolische, dode of harde koppeling,
  als map en als FIFO, `meta.json` als symbolische of harde koppeling, en een koppeling in een oude pluginmap. Elk geval:
  weigering met "geen gewoon bestand zonder koppeling" en "Er is niets gewijzigd"; elke ingang (modus, inhoud,
  koppelingsdoel) en de synthetische serverdatabase blijven gelijk. Op de basis waren alle acht rood.
- `test_rootfase_weigert_een_gekoppeld_pluginbestand_voor_de_eigenaarswissel`: de controle van de rootfase stopt vóór
  de plek van `chown -R` (de bestaande volgordetest bewaakt waar die controle staat). Op de basis rood.
- `test_plaatsen_volgt_nooit_een_bestaande_ingang`: los van de weigering vervangt `place_file` een symbolische of harde
  koppeling op de doelnaam door een nieuw bestand; het buitenbestand blijft gelijk. Op de basis rood (functie ontbrak).
- `test_bestaande_pluginmap_van_deze_versie_blijft_starten`: een correcte installatie met gewone DLL en `meta.json`
  start door, met en zonder nieuwe DLL; geen tijdelijke bestanden achter. Op basis en herstel groen.

Volledige start: de proef van de review, uitgebreid, met de hele entrypoint in een netwerkloze wegwerpcontainer op de
gepinde runtime-image (extern proefscript in de ketenmap). Na het herstel: veilige installatie (oude en identieke DLL)
start; DLL als koppeling (Custom User en root), dode koppeling, map, gekoppelde `meta.json` en harde koppeling worden
geweigerd, met `/config` byte-, modus-, eigenaar- en koppelingsgelijk. In CI doet de levenscyclus van de echte image
hetzelfde (`expect_plugin_link_refusal`, als root en als Custom User);
`test_image_lifecycle_processes.py` toetst die stap zonder Docker, ook met een overschreven database als negatief geval.

## Regressie: plugin

`OpslagTerugvalTests.OnveiligeOpslag_HostStartDoorAllePluginroutesDichtEnNietsGeschreven` (echte Kestrel-host, echte
registratie, achtergrondtaken, MVC en alle routes) heeft er elf gevallen bij, met dezelfde controles als in deel 1d
(host start, serverproefroute werkt, geen abonnementen of timers, modules uit, 503/401/403 op elke route, één
opslagmelding, niets gewijzigd binnen of buiten de opslag):

- de drie hostproeven van de review: `core-koppeling`, `core-groep`, `submap-groep`;
- elk naastbestand van SQLite als koppeling (`wal`, `shm`, `journal`) en `core.db-wal` 0660;
- een onveilige map dieper in de boom die de start opent: `devices/` als koppeling naar buiten (de Devices-listener opent
  die database bij de start) en `quality/` 0770;
- `quality/quality.db` als koppeling (werd pas bij het eerste verzoek aangemaakt en gaf toen een onafgehandelde fout
  zonder antwoord uit de foutcatalogus);
- `core-eigenaar`: `core/core.db` (0644) van een andere UID in eigen, veilige mappen. De fixture maakt een wegwerpcontainer
  zonder netwerk (CI-stap "Tijdelijke opslag met een vreemde eigenaar"); de test bewaakt dat de wortels goedgekeurd worden
  en alleen het bestand vreemd is.

Op de oude bron waren alle elf nieuwe gevallen rood (`core-eigenaar` startte met de plugin aan; `moduledb-koppeling` gaf
een lege body in plaats van een antwoord uit de foutcatalogus). De tien gevallen van deel 1d bleven groen.

`NaDeStart_OnveiligeOpslagGooitGeenRuweFoutNaarDeServer`: na een veilige start worden `quality/quality.db`, het zout van
de pseudoniemen en de Hub-pin koppelingen. Het aanmaken van de UserDeleted-afhandelaars (zoals de server doet, buiten
zijn foutafhandeling) gooit niets; een pseudoniem en de Hub-pin geven `storage_unavailable` in plaats van een ruwe fout;
een Hub-route antwoordt 503 `storage_unavailable` uit de foutcatalogus; het buitenbestand blijft gelijk. Op de oude bron
rood; de Hub-route gaf ook na het herstel van `SecretStore` nog een ruwe 500 tot het aanmaken van de pijplijn in
`JlRouteAttribute` binnen de foutafhandeling viel.

## Uitvoering en grenzen

Commando's, exitcodes en letterlijke slotregels staan in het externe rapport `RAPPORT-A-BOUW-1e.md`, met de ruwe logs in
de bijbehorende ketenmap `bouw1e/`. De drie shelltestbestanden draaiden deze keer direct (geen zandbak), samen met de
overige forktooltests. Geen bestaande test is overgeslagen of afgezwakt; de analyzer en zijn lege uitzonderingslijst
zijn ongewijzigd en de negatieve analyzerbouw geeft nog precies de 323 verwachte fouten.

De echte image wordt uitsluitend in CI gebouwd; de levenscycluslog op de eindcommit wordt gelezen. Geen zware lokale
imagebouw. Alleen synthetische bestanden en netwerkloze wegwerpcontainers op de gepinde image. Niet getest: echte NAS,
NFSv4-ACL's, preset Apps, TrueNAS-tmpfs, echte Emby en accounts. B1 en B2 zijn ongewijzigd; de restgrenzen van deel 1e
staan in ADR-0032.
