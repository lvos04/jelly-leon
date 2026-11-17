# S-G1-16 deel 1d — alleen de plugin uit bij onveilige opslag

Status: **Bezig**; **Sim-getest**; **NIET GEVALIDEERD (echte NAS)**, alleen NAS-test nodig voor dit herstel.
Bronbasis: `afcb25b07e219eae2e4093198005591f38d58858`. B03-017 als geheel, zijn bewijsrij en de lokale image blijven
onderdeel van deel 2. De reviews over deel 1 t/m 1d volgen afzonderlijk. Besluit en grenzen: ADR-0032,
"Opslagdreigingen, deel 1d".

## Regressie en herstel

`OpslagTerugvalTests.OnveiligeOpslag_HostStartDoorAllePluginroutesDichtEnNietsGeschreven` start Kestrel met de echte
`PluginServiceRegistrator`, alle pluginachtergrondtaken en MVC-controllers. De toestanden zijn: vreemde eigenaar,
groepsschrijfrecht en schrijfrecht voor anderen op de eigen data- en cachemap, beide eigen mappen als symbolische
koppeling, een bovenliggende map met groeps-/wereldschrijfrecht en een gekoppelde ouder. De eigenaarfixture bestaat
uitsluitend uit tijdelijke mappen; de CI maakt de vreemde eigenaar via een wegwerpcontainer zonder netwerk.
De test controleert ook dat de fout echt de eigendomsproef betreft, geen read-only mount of ontbrekende fixture.

Bij elke toestand:

- de host start en een gewone serverproefroute blijft beschikbaar;
- de Devices-listener, planner en MediaGuard-poller worden niet aangemaakt: geen sessieabonnementen of timers;
- modules melden uit en inschakelen wordt geweigerd;
- iedere route uit `RouteTable.Alle` geeft een vaste Nederlandse opslagmelding met TrueNAS-UI-herstel, geen terminal;
- de beheerdersroutes geven 503, anonieme verzoeken 401 en onbevoegde accounts 403;
- Hub-routes blijven zonder veilig leesbare sleutelpin 401/not_linked, inclusief de healthroute; de foutdetails melden
  health `down`, modules uit en herstart vereist. De plugin leest daarvoor geen pin via de onveilige map;
- de UserDeleted-afhandeling is zonder opslag een lege handeling, zodat de servergebeurtenis niet op plugindata stukloopt;
- het serverlog bevat precies één opslagmelding, ook na alle routeaanroepen;
- mapingangen, rechten, koppelingsdoelen en bestandsinhoud vóór en na hoststart, requests, gebeurtenis en stop zijn gelijk,
  inclusief de synthetische buitenmap. De bestaande eigendomsproef kan uitsluitend ctime wijzigen (zelfde modus).

`RechtenHerstellen_ZetPluginPasNaHerstartWeerAan` herstelt de rechten tijdens de draaiende host: alle routes blijven
weigeren, zonder nieuw log of schrijfactie. Na een nieuwe hoststart werken de modulelijst en de gewone sessieluisteraars.
De bestaande opslag-, module-, privacy-, authenticatie- en analyzertests blijven aanwezig en worden volledig gedraaid.

Op de oude registratie faalden de hostproeven op `Host.StartAsync`: de onveilige opslag stopte de hele host.
De eerste rode eigenaarvariant miste nog de fixture en telt niet als eigendomsbewijs; de aanvullende mutatieproef
herhaalt die variant met de echte tijdelijke eigenaarfixture. De mutatie gaf 11 van 11 rode hostproeven, met ook de eigendomsfout op `Host.StartAsync`. Hij herstelt tijdelijk de oude directe
achtergrondtaakregistratie en de direct gooiende `JlPaths`-fabriek; daarna wordt de eigen bron exact teruggezet.

## Vroege versielezing

`test_downgradecontrole_leest_niet_voor_de_opslaggrens` voert de echte entrypointfuncties uit met een gedeelde map,
gekoppelde map, gekoppeld versiebestand, dode bestandskoppeling, FIFO en groeps-/wereldschrijfbaar versiebestand.
Een onderschepte `sed`-aanroep legt een marker vast: die mag nooit worden bereikt. De FIFO wordt dus niet echt geopend
en er blijft geen blokkerend proces achter. De eerste vijf gevallen waren rood vóór het herstel.
De bestaande correcte installatie- en downgradeproeven blijven intact.

## Uitvoering en grenzen

De lokale pluginsuite en forktooltests worden met afzonderlijke exitcodes en letterlijke slotregels vastgelegd in
het externe rapport `RAPPORT-A-BOUW-1d.md`, met de ruwe logs in de bijbehorende ketenmap `bouw1d/`.
De zandbak toont systeemouders als eigenaar 65534; daarom draaien de drie shelltestbestanden in een bestaande,
gepinde Python-container zonder netwerk, als gewone gebruiker, met alleen de repo en eigen tijdelijke proefmap gemount.
De overige forktooltests draaien lokaal. Er worden geen bestaande tests overgeslagen of afgezwakt.

Lokaal gemeten: 340 plugintests zonder overgeslagen tests; 305 forktooltests plus de 49 geïsoleerde shelltests,
samen 354 zonder overgeslagen tests. De negatieve analyzerbouw faalt op precies de 323 verwachte verboden aanroepen;
`analyzer_proef.py` controleert dat er geen andere bouwfouten meetellen. Alle bestaande opslagtests blijven onderdeel
van de pluginsuite. De tijdelijke mutatie liet alle 11 hostproeven falen; de herstelde registratie is weer groen.

De echte image wordt uitsluitend in CI gebouwd en de levenscycluslog op de eindcommit wordt gelezen. Geen zware
lokale imagebouw. De synthetische serverproefroute is geen bewijs voor afspelen op een echte NAS; de bestaande CI
beeld-, upgrade-, terugzet- en compatibiliteitsproeven blijven daarvoor de simulatieketen.
De NAS-rechten, NFSv4-ACL's, echte Emby en accounts zijn niet getest. Geen nieuwe veiligheidsuitzondering en geen
wijziging van de twee door B1 afgebakende restgrenzen.

## Afstemming van de echte levenscyclusproef

De eerste CI-run (`44177618186`, commit `5ea8f33c0`) mat 36/37: Custom User met een vreemde eigenaar stopte correct,
maar de proef verwachtte nog de latere tekst "niet schrijfbaar". De vervroegde opslagcontrole meldt nu eerder de
verkeerde eigenaar. De proef verwacht die specifieke eigenaarweigering en blijft eisen dat de container met een
foutcode stopt en de mediamap gelijk blijft. Daarbovenop bewaakt een extra controle dat de vreemde configmap leeg
blijft en eigenaar, groep en rechten gelijk blijven. Geen weigering of bewaarcontrole is versoepeld.
`test_image_lifecycle_processes.py` toetst deze extra controle met een ongewijzigde map en negatieve gevallen voor
nieuw aangemaakte inhoud en veranderde rechten. De drie nieuwe tests waren eerst rood en zijn daarna groen.
De vervolgproeven uit die rode imagejob waren overgeslagen en tellen niet als bewijs; de hele keten wordt opnieuw
op de eindcommit uitgevoerd.
