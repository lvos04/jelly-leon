# ADR-0030 — B03-017: één foutcatalogus, één verzoekpipeline en 1 MiB per route

- **Status:** Aanvaard (2026-11-11). Uitvoering van voorstel ADR-B03-05 (ai-server-manager ADR-0016) in deze repo.
- **Werkpakket:** B03-017; test JLT-68. Contract 1.3 §2.3 regel 9, §4.7 en §5.

## Context

Zes modules in één plugin mogen voor dezelfde situatie nooit een verschillende foutcode geven (gate golf 1). De server
zelf antwoordt op zijn eigen routes met `ProblemDetails`; de pluginroutes volgen het platformcontract
(`{"code","message","details","trace_id"}`). Een plugin kan vóór de authenticatie van de server geen middleware
plaatsen zonder een `IStartupFilter`; of dat op 12.x betrouwbaar werkt is een aparte spike.

## Besluit

1. **Eén catalogus** (`Core/Errors/Fouten.cs`): elke foutcode staat daar één keer met status en Nederlandse melding.
   Modules gooien `JlException` via de fabrieksmethoden; geen module schrijft zelf een foutantwoord. De codes staan als
   `enum` in het OpenAPI-document.
2. **Eén pipeline** (`Core/Http/JlPipeline.cs`) achter één filter `[JlRoute("<id>")]`, in vaste volgorde:
   authenticatie (koppelstatus → soort token → sleutel → claims → `token_use` → `jti`) → rol (403) → module aan (404)
   → omvang (413) → `Idempotency-Key` (400) → body (422) → `If-Match` (428) → idempotentielaag (409/422/herhaling met
   `Idempotent-Replay: true`). Zonder geldige authenticatie is het antwoord altijd 401, ook voor een onbekende of
   uitgeschakelde module: wie niet is aangemeld leert niet welke modules aan staan.
3. **Twee soorten bewijs, nooit door elkaar.** `/connector/v1/**` accepteert alleen een JWT van de gepinde Hub
   (rol `kind` → 403 `role_kind`). De beheerroutes onder `/media/v1/**` accepteren alleen een serversessie van een
   beheerder (kinderprofiel → 403 `kid_profile`, geen beheerder → 403 `admin_required`). Een Hub-token is geen
   beheerdersbewijs en omgekeerd.
4. **1 MiB per route**: `Content-Length` boven 1 048 576 → 413 `payload_too_large` vóór het lezen; zonder
   `Content-Length` leest de pipeline hoogstens 1 MiB + 1 byte. Dit gebeurt ná de authenticatie — de afwijking die
   contract §2.3 regel 9 toestaat tot de `IStartupFilter`-spike slaagt. De limiet van de server zelf blijft daarvóór
   gelden.
5. **Idempotentie**: bereik = aanvrager + methode + pad; vingerafdruk = SHA-256 over body en `If-Match`. Antwoorden
   onder 500 worden 24 uur bewaard en letterlijk herhaald; een 5xx geeft de sleutel vrij. Andere body met dezelfde
   sleutel → 422 `idempotency_key_reused`; dezelfde sleutel terwijl het eerste verzoek loopt → 409
   `idempotency_in_progress`. Vrijgesteld zijn alleen `…/verify` en de connectorroutes die 501 geven (contract §5);
   de vrijstelling staat per route in de routetabel en in het OpenAPI-document.
6. **`jti`**: opslag in de kerndatabase tot `exp` + 30 s. Een herhaald `jti` mag voor `GET`; een mutatie met een al
   gezien `jti` → 401 `token_replayed`, behalve de letterlijke herhaling (zelfde methode, pad en `Idempotency-Key`).
   Is de opslag onbereikbaar, dan faalt de controle dicht: 503 `replay_check_unavailable` met `Retry-After`.
7. **Opslagfouten** worden 503 `storage_unavailable` met `Retry-After`, nooit een 500 met een stack of een pad.
8. **Inhoudsbewaker** (`Core/Outbox/InhoudsBewaker.cs`): geen event en geen connector-item verlaat de plugin met een
   titel, een gebruikers- of apparaatnaam, een pad, een IP-adres of een ruwe ID, als waarde of als veldnaam. ID's naar
   buiten zijn ondoorzichtig (`o_` + 32 hex, HMAC-SHA-256 met een zout per installatie in de geheimenmap).

## Alternatieven

- *`[ApiController]` met de foutvorm van de server:* geeft `ProblemDetails` en een 400 uit de modelbinding vóór de
  eigen volgorde. Verworpen.
- *Een foutfilter per module:* precies het risico dat de gate uitsluit. Verworpen.
- *Nu al een `IStartupFilter`:* niet gedaan zonder meting; zie de spike in B03-017 en de aantekening hieronder.

## Gevolgen

- Een nieuwe route bestaat pas als ze in de routetabel staat; de drifttest en de contracttest lopen dan vanzelf mee.
- De 413 komt bij de pluginroutes na de 401. Slaagt de spike, dan verhuist alleen stap 4 naar vóór de authenticatie;
  codes en volgorde van de overige stappen blijven gelijk.

## Verificatie

xunit-contracttests per route en per module (zelfde code voor zelfde situatie), JLT-68 tegen een draaiende server met
een Hub-simulator. Niet op de echte NAS gevalideerd.
