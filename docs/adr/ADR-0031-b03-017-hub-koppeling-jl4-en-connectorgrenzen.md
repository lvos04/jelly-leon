# ADR-0031 — B03-017: Hub-koppeling JL4 en de grenzen van de connector

- **Status:** Aanvaard (2026-11-11). Uitvoering van voorstel ADR-B03-06 (ai-server-manager ADR-0017) in deze repo.
- **Werkpakket:** B03-017; test JLT-68. Contract 1.3 §2.3 regel 9, §4 en §6.

## Context

Jelly Leon is een plugin in een bestaande server en geen eigen dienst met een eigen koppelstroom. Contract 1.3 kiest
daarom JL4: de beheerder plakt de publieke sleutelset van de Hub in het dashboard van de server en vergelijkt de
vingerafdruk. Het contract laat een aantal punten voor zo'n "geplakte sleutelset" open; die staan hieronder met de
veiligste uitleg.

## Besluit

1. **Koppelen in twee stappen.** `POST /media/v1/hub-link/verify` berekent de vingerafdruk van de geplakte set en
   bewaart niets. `PUT /media/v1/hub-link` pint de set alleen als de beheerder dezelfde vingerafdruk meestuurt en de
   `service_id` een UUID is. De vingerafdruk omvat alle JWT- en policy-sleutels volgens §4.5. De beheerder neemt de
   afzonderlijke `service_id` over uit de Hub-registratie. Bij rotatie vergelijkt de beheerder de nieuwe vingerafdruk
   opnieuw. `DELETE` verwijdert de pin. De vier beheerroutes vereisen een persoonlijke sessie van een volwassen
   serverbeheerder. Een API-sleutel zonder gebruiker en een kinderprofiel met beheerrecht krijgen geen toegang.
2. **Alleen publiek materiaal, en alleen in de geheimenmap.** De pin (`hub-pin.json`) staat onder
   `/config/data/jelly-leon/secrets/` (map 0700, bestand 0600). In de plugininstellingen (XML van de server), in
   exports, in antwoorden en in logregels staat geen sleutel. `PluginConfiguration` heeft geen veld voor een geheim;
   een test bewaakt dat. Iedere connectoraanroep controleert opnieuw de inhoud en rechten van het geopende bestand en
   de rechten van de geheimenmap. Een beschadigde, onleesbare of te ruim toegankelijke pin geeft de connector
   401 `unauthorized` met reden `not_linked`. De persoonlijke beheerroute meldt dan de status `not_linked` met reden
   `koppelstatus_onleesbaar`.
3. **Zonder pin**: elke connectorroute geeft 401 `unauthorized` met reden `not_linked`. Een token van een andere Hub
   → 401 `unknown_key`.
4. **Dienst-JWT**: een token met `token_use: hub_service` wordt alleen aanvaard als `service_id` gelijk is aan de
   gepinde `service_id`. Het contract noemt die controle niet uitdrukkelijk; dit is de strengste uitleg.
5. **Geen `/connector/v1/hub-link`.** Die route hoort bij diensten met een eigen koppelstroom; een geplakte set heeft
   geen handdruk met de Hub. De koppelstatus is voor de beheerder zichtbaar via `GET /media/v1/hub-link`. Om dezelfde
   reden is er geen health-check `hub_link`.
6. **De Hub haalt, de plugin stuurt niets.** `GET /connector/v1/events` is een polling-cursor over de outbox (30
   dagen). De plugin opent geen verbinding naar de Hub.
7. **Events**: precies drie segmenten, altijd in het domein `media.`; alleen aantallen, tijden en ondoorzichtige ID's.
   De plugin geeft **geen** `service.*`-events (starten en stoppen van de server zijn geen gebeurtenissen van de
   plugin; de Hub ziet dat aan `health`).
8. **Health** (`GET /connector/v1/health`): het totaal is de slechtste check in de volgorde
   `healthy` < `unknown` < `degraded` < `down`; een meting ouder dan 900 s wordt `unknown` met reden
   `meting_verouderd`. Vaste checks: `database`, `jobs`, `media_mount`, `module.<slug>` per actieve module en `worker`.
   - `worker` is `healthy` met `nodig: false` zolang geen actieve module een jobtype heeft, anders `unknown` met reden
     `werker_niet_beschikbaar` tot de werkerbewaker (B03-018) een echte meting levert. Nooit gespeeld groen.
   - `media_mount` is `degraded` zodra een mediamap van de server schrijfbaar gekoppeld is en `unknown` zolang de
     server geen mediamappen kent.
9. **Niet beschikbaar is niet beschikbaar**: `propose`, `apply`, `rollback` en `evidence/{id}` geven 501
   `capability_unavailable`; `capabilities` in `discover` is `["read"]`. Een itemtype van een uitgeschakelde module
   bestaat niet (422 `validation_error`, veld `type`).
10. **Back-ups**: het itemtype `backups` meldt per database de omvang en de migratiekopieën met `dekking: onbekend`.
    De plugin maakt zelf geen back-up van de server; of de map `/config` in de back-up van de NAS zit, weet de plugin
    niet en beweert ze dus ook niet.
11. **Herhaling van mutaties.** De plugin reserveert de `jti` in de kerndatabase vóór uitvoering. Na heropening
    geldt dezelfde reservering. Een identieke herhaling op een route met verplichte idempotentie kan uitsluitend het
    al bewaarde antwoord terugkrijgen. Een mislukte eerste uitvoering verleent geen tweede uitvoeringsrecht.

## Open punten voor het contract (gemeld, niet zelf beslist)

- BG-04: er is in de Hub nog geen route waarlangs Jelly Leon MediaGuard-gegevens met een dienst-JWT kan vragen. Tot
  die er is blijft de MediaGuard-status in Jelly Leon `onbekend` (ADR-0021; B03-009 bouwt tegen een simulator).
- De controle op `service_id` (punt 4), de betekenis van `worker` (punt 8) en het ontbreken van `hub_link` (punt 5)
  zijn uitleg van deze repo; het contract zou ze moeten vastleggen.
- Voor C1.3-JL-06 volgt de plugin §4.5 voor de vingerafdruk. Een dienst-JWT moet daarnaast dezelfde `service_id`
  bevatten als de lokale registratie. Het bewijs voor deze twee controles staat bij C1.3-JL-06 in EVIDENCE.

## Verificatie

De lokale Hub-simulator ondertekent testtokens met een onafhankelijke Ed25519-bibliotheek. `HubTokenTests`,
`HubSleutelTests` en `BeheerTests` toetsen onder meer het type van `aud`, de grens van 120 seconden met 30 seconden
klokspeling, rolvoorrang, pinrotatie, twee gelijktijdige verzoeken en herhaling na heropening van de echte SQLite-opslag.
`ConnectorTests` toetsen de zichtbare velden en de drie actieroutes. `PrivacyTests` doorzoeken de geserialiseerde
plugin-XML, module-exports en antwoorden op de waarden van testsleutels en een gebruikt token.

De afzonderlijke serverproef `tools/jelly-leon/e2e/plugin_proef.py --alleen-hub` gebruikt een lege bibliotheek,
wegwerpsessies en één lokale server. Zij herhaalt hetzelfde token na een procesherstart en doorzoekt de serverlog,
plugin-XML, instellingen en de beheerexports van Devices en Quality. EVIDENCE onderscheidt de metingen in het
pluginharnas van de uitvoering op een server.
De echte Hub en de echte NAS zijn **NIET GEVALIDEERD**.

## Eventnamen en versheid bij contract 1.3 (S-G1-14)

Bij de start controleert het moduleregister alle gedeclareerde eventtypen, ook voor uitgeschakelde modules. De outbox
controleert de naam opnieuw vóór opslag. Een module gebruikt drie segmenten in het domein `media`. Voor een opgegeven
`payload.ernst` gelden `kritiek`, `hoog`, `middel`, `laag` en `info`. Zonder bronwaarde bepaalt de Hub de ernst.

De namen van B03 §10.10 blijven behouden. Voor de afnemer geldt de indeling van contract §7.

| Functie | Probleem | Herstel | Informatie |
|---|---|---|---|
| F1, kijkgroepen | `watchgroup.degraded`, `.blocked` | — | Start en einde van de groep |
| F2, aanbevelingen | `recommender.degraded` | `recommender.recovered` | Herbouw, evaluatie en export |
| F3, ondertitels | `subtitle.rejected` | — | De overige ondertitelevents, `subtitle_engine.changed` en `subtitle_store.frozen` |
| F4, kwaliteit | `quality_repair.failed` | `quality_finding.resolved` | Alle overige F4-namen, ook `quality_finding.detected`, `quality_repair.verified` en `storage.read_failed` |
| F5, afspelen en GPU | `playback_attempt.failed`, `gpu_lane.degraded`, `gpu_lane.saturated`, `gpu_budget.conflict` | `gpu_lane.recovered` | De transcode- en profielevents en `gpu_lane.configured` |
| F6, segmenten | `segment_analysis.failed` | — | Voltooide analyse, correctie, beoordelingsverzoek en bevroren wezen |

Elke naam in de tabel heeft het voorvoegsel `media.`. `subtitle.rejected` beschrijft één afwijzing. De reeksregel
voor een melding hoort bij de Hub. `quality_finding.detected` registreert een bevinding als informatie.
`.resolved` kan daardoor zonder eerder probleem binnenkomen. Detectie en afhandeling gebruiken hetzelfde stabiele
onderwerp. `storage.read_failed` blijft informatie volgens de letterlijke werkwoordlijst. De eigenaar van Δ-HUB-2
kan deze drie gevallen meenemen bij de inboxregels.

Een health-antwoord geeft het oudste meettijdstip van de bijdragende checks door. Bij 900 seconden telt de bronstatus
nog mee. Daarna krijgt de check `unknown` met reden `meting_verouderd`. Is veroudering bepalend voor het totaal, dan
staat diezelfde reden ook in `reason_code`. Een verse `degraded` of `down` weegt zwaarder.
