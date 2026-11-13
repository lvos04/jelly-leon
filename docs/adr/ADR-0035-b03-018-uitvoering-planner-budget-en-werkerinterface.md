# ADR-0035 — B03-018: uitvoering planner, budget en werkerinterface (stand na ronde 3)

- **Status:** Aanvaard (2026-11-13). Legt vast wat er van B03-018 in de code staat; de besluiten zelf staan in ADR-0017
  (analysewerker) en ADR-0018 (planner en GPU-budget) en worden hier niet gewijzigd.
- **Werkpakket:** B03-018 (alleen het deel planner, budgetbeslisser en werkerinterface). De rest van B03-018 wordt
  afgemaakt in latere stappen: de werkerbewaker en de socket, de wachtrij en grenzen van de planner, en de regels G1–G10
  van het budget.
- **Bewijs:** `plugins/JellyLeon/tests/…/Core/PlannerTests.cs` en `plugins/JellyLeon/tests/…/Core/BudgetBeslisserTests.cs`
  (xunit, met mutatieproef), de drifttest van het OpenAPI-document en de analyzerproef (JL0004). Alleen unit-getest; geen
  Sim-test, en de echte NAS is NIET GEVALIDEERD.

## Context

In ronde 3 is aan B03-018 gewerkt, maar dat werk is niet vastgelegd: een planner, een budgetbeslisser, een
werkerinterface en een beheerroute stonden ongevolgd in de werkboom, zonder tests, en de registratie verwees al naar
"ADR-0035", die niet bestond. Deze ADR maakt die verwijzing waar en beschrijft precies wat er staat en wat nog open is,
zodat de vervolgstappen erop kunnen bouwen zonder iets te raden.

## Besluit

1. **Eén planner** (`Core/Planner/BatchPlanner`, een hosted service) meet elke 2 seconden (de controletik):
   kijksessies en software-transcodes (alleen via `ISessionManager`, `Core/Planner/ServerSessies`), het MediaGuard-beeld
   van de ene viewerclient (ADR-0034), de mediamappen (`MountCheck`), de werker, de leesfoutonderbreker en de
   cgroup-marge. Hij beslist niets zelf, maar laat `PlannerRegels` beslissen en stuurt de werker alleen pauze of hervat.
   Bij elke `PlaybackStart` meet hij niet, maar seint hij meteen pauze, ook bij Direct Play; dat hangt aan geen
   schakelaar. Een controleronde die niet kan meten of beslissen (een fout in de meting) is fail-closed: de werker
   krijgt het pauzesein en nooit een hervat-sein.
2. **Regels zonder toestand** (`Core/Planner/PlannerRegels.Beslis`): dezelfde stand geeft altijd hetzelfde besluit, en
   onbekend is nooit "in orde". Vaste grenzen: hooguit 1 zware taak, 2 threads en 1 GiB voor al het batchwerk samen,
   pauze binnen 5 s, hervatten pas na 10 minuten zonder kijken, nachtvenster 23:00–07:00 (lokale tijd van de server).
   Stilstand voor al het batchwerk bij: open leesfoutonderbreker, schrijfbare of onbekende mediamap, MediaGuard niet
   `ok` of gepauzeerd, een software-transcode, een kijksessie of minder dan 10 minuten rust. Alleen zwaar werk staat
   ook stil zonder werker (`werker_niet_beschikbaar`), met onbekende of bezette CPU-lane van MediaGuard, en buiten het
   nachtvenster. De enige uitzondering op "kijksessie = pauze" is het uitdrukkelijke verzoek van een beheerder, en alleen
   met een cgroup-marge van minstens 1024 MiB en zonder software-transcode. Zo'n beheerdersverzoek slaat ook de
   10 minuten rust na het kijken en het nachtvenster over; zonder kijksessie geldt er dan geen margevoorwaarde. Alle
   andere stilstandredenen (leesfouten, mediamap, MediaGuard, software-transcode, werker, CPU-lane) blijven gelden.
   Kostenklassen: `quality.inventory` kost niets, `rec.rebuild` is licht, al het andere telt als zwaar.
3. **Leesfoutonderbreker** (`Core/Planner/LeesfoutBreker`): 3 verschillende bestanden (ondoorzichtige sleutel, nooit een
   pad of titel) met een leesfout binnen 60 minuten openen hem; dezelfde sleutel telt één keer. Hij gaat niet vanzelf
   dicht, alleen via `Herstel()`. Bij het openen gaat het event `media.storage.read_failed` naar de outbox, met alleen
   aantal, vlag en tijdstip.
4. **Cgroup-marge** (`Core/Planner/CgroupMarge`): `memory.max − memory.current` (cgroup v2); zonder grens
   `MemAvailable`; niet te lezen is `null`, en dan is er geen beheerdersuitzondering.
5. **Werkerinterface** (`Core/Werker/IWerker`): wat de planner van de werker vraagt (klaar, stand, reden, pauze
   bevestigd, pauzeren en hervatten van de hele procesgroep, ADR-0017). De standaardregistratie is `GeenWerker`: nooit
   klaar, stand `afwezig`, reden `werker_niet_beschikbaar`. Er draait dus geen zwaar werk. Processtarts mogen alleen in
   de namespace `Core.Werker` (JL0004, ADR-0032); er staat er nu geen enkele.
6. **Eén budgetbeslisser** (`Core/Budget/BudgetBeslisser`): batch krijgt nooit een GPU. De CPU alleen als MediaGuard
   `ok` is en zijn CPU-lane niets draait; anders nergens (`mediaguard_niet_gemeten`, `mediaguard_lanes_onbekend`,
   `mediaguard_cpu_bezig`). De topologie staat vast op `onbekend` (de hardware van de NAS, D08, is niet gemeten); de
   vijf standen uit ADR-0018 besluit 4 bestaan als woorden, maar het besluit kijkt nog niet naar de topologie. Daarnaast
   houdt hij lane-reserveringen per sessiesleutel bij (30 minuten, `GroupPauseLaneHoldMinutes`), alleen als boekhouding.
7. **Beheerroute** `GET /media/v1/planner` (`planner.status`): één rij in de routetabel, alleen een beheerderssessie,
   geen idempotentiesleutel, fouten in de vorm van de foutcatalogus (401 `unauthorized`, ook met een Hub-token; 403
   `forbidden` met `admin_required` of `kid_profile`). Het antwoord (schema `Planner` in
   `docs/openapi/jelly-leon-plugin.openapi.json`) bevat alleen aantallen, tijden en vaste woorden.

## Wat nog open is

- **Werker:** geen bewaker, geen kindproces, geen socket, geen health-ping; `GeenWerker` blijft de standaard tot de
  bewaker er is.
- **Planner:** geen wachtrij en geen taakstart (de planner start nu zelf nooit iets); geen `nice 19`/`ionice idle`;
  geen meting van threads en geheugen per procesgroep; geen noodstop van MediaGuard; geen voorwaarde Δ-MG-AUTH;
  geen vensterinstellingen in de plugin-configuratie; geen pauzemeting in een container.
  `Mag()` en de beheerdersuitzondering hebben nog geen aanroeper.
- **Leesfouten:** `Meld()` en `Herstel()` hebben nog geen aanroeper (geen werker, geen herstelroute).
- **Budget:** geen live-transcodes (`ITranscodeManager` en `/proc`), geen meting per werkklasse, geen regels G1–G10,
  geen gemeten topologie; `Houd()` en `GeefVrij()` hebben nog geen aanroeper; geen health- of connectoruitvoer.
- **Gedrag om op te letten:** de controletik stuurt elke ronde opnieuw pauze of hervat, ook als de stand niet wisselde.
- **Aangevuld na de review van S-G1-15** (bevindingen R-TECH en R-VEILIG; open, met de stap die het oppakt):
  - Het hervat-pad heeft geen test: geen test brengt de planner in de stand "zwaar mag" (werker klaar, MediaGuard
    gemeten, alleen-lezen mediamap, nacht, 10 minuten rust) en toetst dat `Tik()` dan alleen hervat seint (S-G1-36).
  - Elke ronde opnieuw seinen en de volgorde: het sein wordt niet afgewacht, dus een hervat uit een tik die vlak vóór
    een `PlaybackStart` mat, kan na het pauzesein van die start bij de werker aankomen (tot de volgende tik, 2 s).
    Werkerkant idempotent maken en de volgorde vastleggen, of alleen bij een standwisseling seinen (S-G1-32 en
    S-G1-36); de test `BatchPlanner_ZonderWerkerStartNietsEnSeintAlleenPauze` legt het herhalen nu vast en moet dan mee.
  - Nachtvenster in lokale tijd: het venster gebruikt de tijdzone van de server; in een container zonder ingestelde
    tijdzone is dat UTC (S-G1-36, vensterinstellingen).
  - Prioriteit en kostenklasse per codec van de modules: `PlannerRegels.Kosten()` kent alleen het jobtype (S-G1-36).
  - Achterstandsschatting per module en het event `media.gpu_lane.saturated` ontbreken (S-G1-38).
  - De velden `werker` en `werker_reden` in schema `Planner` zijn vrije tekst; bij de echte werker beperken tot vaste
    woorden of een patroon, zodat via de beheerroute nooit een pad of melding lekt (S-G1-32).
  - De kosten van de controletik op de NAS zijn niet gemeten: elke 2 s `ILibraryManager.GetVirtualFolders` en het
    lezen van `/proc/self/mountinfo` per bibliotheekpad (S-G1-36).

## Gevolgen

- De verwijzing "ADR-0035" in `PluginServiceRegistrator` wijst naar deze ADR.
- Op elke installatie draait nu geen batchwerk: er is geen werker en MediaGuard staat op `onbekend` (ADR-0034).
- Wie een open punt afmaakt, vult ADR-0018 (kop "Verificatie") aan en past deze ADR niet met terugwerkende kracht aan.

## Alternatieven

- **Het halve werk weggooien en opnieuw beginnen:** afgewezen; het werk is nagelezen, hoort bij B03-018 en is nu getest.
- **De verwijzing in de code naar ADR-0018 laten wijzen:** afgewezen; ADR-0018 is het besluit, niet de stand van de
  uitvoering.
