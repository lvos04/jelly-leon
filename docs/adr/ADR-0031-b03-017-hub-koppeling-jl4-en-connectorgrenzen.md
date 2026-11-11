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
   `service_id` een UUID is. `DELETE` verwijdert de pin. Alleen een beheerder van de server mag dit; een kinderprofiel
   nooit.
2. **Alleen publiek materiaal, en alleen in de geheimenmap.** De pin (`hub-pin.json`) staat onder
   `/config/data/jelly-leon/secrets/` (map 0700, bestand 0600). In de plugininstellingen (XML van de server), in
   exports, in antwoorden en in logregels staat geen sleutel. `PluginConfiguration` heeft geen veld voor een geheim;
   een test bewaakt dat.
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

## Open punten voor het contract (gemeld, niet zelf beslist)

- BG-04: er is in de Hub nog geen route waarlangs Jelly Leon MediaGuard-gegevens met een dienst-JWT kan vragen. Tot
  die er is blijft de MediaGuard-status in Jelly Leon `onbekend` (ADR-0021; B03-009 bouwt tegen een simulator).
- De controle op `service_id` (punt 4), de betekenis van `worker` (punt 8) en het ontbreken van `hub_link` (punt 5)
  zijn uitleg van deze repo; het contract zou ze moeten vastleggen.

## Verificatie

xunit (`BeheerTests`, `ConnectorTests`, `HubTokenTests`) en JLT-68 met een Hub-simulator die echte Ed25519-tokens
tekent: zonder pin, gepinde set, rol kind, herhaald `jti`, verlopen token. De echte Hub en de echte NAS zijn
**NIET GEVALIDEERD**.
