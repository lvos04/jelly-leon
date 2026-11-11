# ADR-0033 — B03-017: spike `IStartupFilter` — 1 MiB vóór routing en authenticatie uit een plugin

- **Status:** Aanvaard (2026-11-11). Uitkomst van de spike die ADR-0030 en contract 1.3 §2.3 regel 9 openlieten.
- **Werkpakket:** B03-017 (gate golf 1); raakt contract 1.3 §5 (laag vóór routing en authenticatie) en JLT-64.
- **Bewijs:** `tools/jelly-leon/e2e/startupfilter_spike.py` (twee wegwerpcontainers, zonder en met de schakelaar; in CI
  op `JL_RUNTIME_IMAGE` en op de Jelly Leon-image), `plugins/JellyLeon/tests/…/Core/StartupFilterSpikeTests.cs` (xunit)
  en `tools/jelly-leon/tests/test_startupfilter_spike.py`. Sim-getest; geen meting op een echte NAS.

## Context

Contract 1.3 §5 vraagt een bovengrens van 1 MiB in een laag vóór routing en authenticatie. Een plugin draait binnen het
serverproces en bepaalt de volgorde van de middleware niet. Daarom controleert de plugin de grens per route, na de
authenticatie (ADR-0030, contract §2.3 regel 9: "tot de `IStartupFilter`-spike slaagt"). Open vraag uit het bouwplan:
werkt een `IStartupFilter` die een plugin registreert op 12.x, en verandert hij dan niets aan de rest van de server?

## Meting

De plugin registreert in `PluginServiceRegistrator` alleen met `JELLYLEON_SPIKE_STARTUPFILTER=1` een
`IStartupFilter` (`Core/Http/JlStartupFilterSpike.cs`). Die zet één middleware vóór alles wat de server zelf opbouwt:
is `Content-Length` groter dan 1 MiB en begint het pad met `/media/v1` of `/connector/v1`, dan volgt meteen
`413 payload_too_large` in de vaste foutvorm; elk ander verzoek gaat ongewijzigd door.

Het script stuurt dezelfde tien verzoeken zonder aanmelding naar een server zonder en een server met de schakelaar.
Gemeten op stock `jellyfin/jellyfin:12.4` (vaste digest, ontwikkelmachine, 2026-11-11): 21 van 21 uitspraken geslaagd.

| Verzoek (zonder aanmelding) | Zonder schakelaar | Met schakelaar |
|---|---|---|
| `POST /connector/v1/propose`, 1 MiB + 1 byte | 401 `unauthorized` (`not_linked`) | **413 `payload_too_large`** |
| `PUT /media/v1/modules/devices`, 1 MiB + 1 byte (ook met hoofdletters in het pad) | 401 `unauthorized` | **413 `payload_too_large`** |
| pluginroutes met precies 1 MiB, 64 bytes of zonder body | 401 `unauthorized` | gelijk |
| `POST /Users/AuthenticateByName`, 1 MiB + 1 byte en 64 bytes | 401 (van de server) | gelijk |
| `GET /System/Info/Public` | 200 | gelijk |
| foutregels over de plugin of het filter in de serverlog | geen | geen |

De 413 heeft de vier vaste velden, `Content-Type: application/json; charset=utf-8` en `Cache-Control: no-store`.
De meting op de Jelly Leon-image draait in CI (job `image`); de uitkomst daarvan staat in het CI-rapport
`startupfilter-spike-jelly-leon.json`, niet in dit document.

## Besluit

1. **De spike is technisch geslaagd op stock 12.4:** een `IStartupFilter` uit een plugin wordt door de host toegepast
   en draait vóór routing en authenticatie. De plugin-registratie (`IPluginServiceRegistrator`) loopt vóór het
   opbouwen van de container, dus de host ziet het filter bij het starten.
2. **De laag blijft standaard uit.** Aanzetten verandert de volgorde die contract §2.3 regel 9, ADR-0030, de
   OpenAPI-beschrijving en de contracttests nu vastleggen (401 gaat vóór 413). Die volgorde wijzigt pas als het
   contract dat zegt; dat is een besluit buiten deze repo. Tot dan geldt: tests verwachten "413 per route".
3. **De controle per route blijft altijd staan**, ook als de laag later standaard aan gaat. De laag is een extra
   eerdere grens, geen vervanging.
4. De schakelaar is een omgevingsvariabele met precies de waarde `1`. Hij staat niet in het Custom App-formulier en
   niet in `.env.example`: het is een meetmiddel, geen instelling voor de gebruiker.

## Grenzen

- **Alleen `Content-Length`.** Een verzoek zonder `Content-Length` (chunked) gaat door de laag heen; de pipeline telt
  dan bij het lezen en geeft 413 na de authenticatie. Vóór de authenticatie leest de plugin geen body.
- **BaseUrl.** Heeft de server een basis-URL, dan begint het pad daar niet met `/media/v1` of `/connector/v1` en doet de
  laag niets; de controle per route vangt het dan op. Niet gemeten met een basis-URL.
- **Geen meting met andere plugins** die zelf een `IStartupFilter` registreren, en geen meting op een echte NAS.
- **Een fout in een `IStartupFilter` raakt de hele server.** Daarom is de middleware zo klein mogelijk, schrijft ze
  niets weg en raakt ze verzoeken buiten de twee voorvoegsels niet aan. JLT-64 (antwoorden van de server byte-gelijk)
  is gemeten met de laag uit.
- De volledige upstream-testsuite is niet met de laag aan gedraaid.

## Gevolgen

- Contractpunt voor ai-server-manager: §2.3 regel 9 kan van "na authenticatie" naar "vóór authenticatie (met de grens
  per route als tweede laag)". Na dat besluit: schakelaar omkeren naar standaard aan, stap 4 van ADR-0030 verplaatsen,
  de volgordetests en de OpenAPI-toelichting aanpassen, en JLT-64 met de laag aan herhalen.
- Tot dat besluit verandert er voor de gebruiker en voor de Hub niets.

## Alternatieven

- *Meteen standaard aan:* afgewezen; wijzigt een vastgelegde volgorde zonder contractbesluit en zonder JLT-64 met de
  laag aan.
- *Een forkpatch in `Startup.cs`:* afgewezen; werkt niet op stock 12.x en vergroot de patchlast (ADR-0002).
- *`RequestSizeLimit` op de controllers:* is al de grens per route in de pipeline; verplaatst niets naar vóór de
  authenticatie.
