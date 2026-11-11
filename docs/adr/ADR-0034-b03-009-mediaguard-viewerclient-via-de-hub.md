# ADR-0034 — B03-009: MediaGuard-viewerclient via de Hub, zonder sleutel in Jelly Leon (BG-04)

- **Status:** Aanvaard (2026-11-11). Vult ADR-0021 aan en vervangt daarvan besluit 2 ("de sleutel wordt in Jelly Leon
  zelf ingevoerd").
- **Werkpakket:** B03-009 (gate golf 1, deel viewerclient) en B03-010 (deel `IsKid`); contract 1.3 §2.3 regels 2–3,
  conformiteitsrij C1.3-JL-08.
- **Bewijs:** `plugins/JellyLeon/tests/…/Core/MediaGuardTests.cs` (xunit, nagebootst vervoer) en de pluginproef
  `tools/jelly-leon/e2e/plugin_proef.py` (health met de nieuwe controle). Unit-getest en Sim-getest; echte Hub en echte
  MediaGuard NIET GEVALIDEERD.

## Context

- Bouwplan §10.5 en §11 (rij B03-009), ADR-0021 en contract 1.3 §2.3 beschrijven een eigen MediaGuard-sleutel met rol
  viewer, ingevoerd in Jelly Leon zelf, "alleen na besluit BG-04".
- De gebruiker heeft BG-04 anders beslist (`B03_BESLUITEN.md`, vastgelegde antwoorden): de sleutel loopt **via de Hub**.
  De Hub beheert de alleen-lezen sleutel in de eigen kluis; Jelly Leon krijgt alleen wat nodig is, bij voorkeur zonder
  sleuteloverdracht (Jelly Leon vraagt de MediaGuard-gegevens via de Hub met een dienst-JWT). Tot dan: `mediaguard: onbekend`.
- Contract 1.3 kent geen route waarmee Jelly Leon MediaGuard-gegevens bij de Hub opvraagt, en Jelly Leon kan zelf geen
  dienst-JWT krijgen: de plugin controleert alleen dienst-JWT's van de Hub (JL4, ADR-0031) en ondertekent eigen antwoorden.
- De standaard van het contract bij een open BG-04 is: geen sleutel in Jelly Leon, MediaGuard-status daar `onbekend`.

Plan, contract en besluit spreken elkaar dus tegen. De veiligste lezing die het besluit van de gebruiker volgt: geen
sleutel in Jelly Leon, en niets raden over een Hub-route die nog niet bestaat.

## Besluit

1. **Geen MediaGuard-sleutel in Jelly Leon.** Er is geen invoerveld, geen instelling en geen bestand in de geheimenmap
   voor een MediaGuard-sleutel. De plugin kent ook geen MediaGuard-adres.
2. **Eén client achter één vervoergrens.** `Core/MediaGuard/MediaGuardClient` is de enige plek die MediaGuard-gegevens
   leest. Hij praat alleen met `IMediaGuardVervoer` ("via de Hub"). De standaardregistratie is `GeenMediaGuardVervoer`:
   geen enkele aanroep, status `onbekend`, reden `geen_route_via_hub`. Er is bewust **geen** HTTP-vervoer gebouwd; dat
   komt pas als het contract de Hub-route en het bewijs (dienst-JWT) vastlegt. Niets wordt nagebootst.
3. **Rolcontrole, fail-closed.** Zodra er vervoer is: `GET /api/v1/auth/me` bij de eerste ronde en daarna elke 60 minuten
   (`LinkCheckMinutes`). Alleen precies `viewer` is goed. Elke andere rol (operator, admin, leeg, andere schrijfwijze)
   geeft status `geweigerd`; tot de volgende rolcontrole volgt geen enkele andere aanroep.
4. **Routewitte lijst** (`MediaGuardWitteLijst`): alleen GET-routes en het niet-muterende `POST /api/v1/audio/inspect`.
   `/api/v1/app/control` en elke andere muterende route staan er niet op en zijn niet aan te roepen: de client neemt
   alleen routes uit de lijst aan.
5. **Veldenwitte lijst per route.** Van een antwoord worden alleen genoemde, enkelvoudige velden overgenomen:
   - `auth/me`: `role`;
   - `mediaserver/status`: `kind`, `url`, `connected`, `hold.active`, `subtitles.source|nl_wanted|nl_auto|missing` —
     nooit `sessions`, `hold.reason`, `actions`, `tests` of `last` (daar staat wie wat kijkt);
   - `app/status`: `encoder.reachable`, `encoder.lanes[].lane|running|slots|paused`.
     Vorm nagelezen in de bron van MediaGuard (`apps/core/mediaguard/mobile.py`, alleen lezen): `lane` is `gpu` of
     `cpu`, `running` is een aantal lopende encodes, `slots` een aantal, `paused` waar/onwaar.
   De overige routes uit het plan (`encoding/resources`, `encoding/capabilities`, `mediaserver/subtitles/missing`,
   `policy/effective`, `recovery/transactions/{id}`, `audio/inspect`) staan op de lijst met een **lege** veldenlijst en
   zijn daardoor nog niet bruikbaar: het plan noemt hun velden niet, en raden is hier een privacyrisico.
6. **Ruwe antwoorden** worden nooit gelogd of bewaard. In het geheugen staat alleen het gefilterde beeld (`MgBeeld`);
   er is geen tabel en geen bestand voor. Antwoorden die geen 200 zijn, leeg zijn, groter dan 1 MiB zijn of geen geldige
   JSON zijn, tellen als `onbereikbaar`.
7. **Eén poller** (`MediaGuardPoller`) in Core: `app/status` elke 20 seconden (`PollSeconds`), `mediaserver/status` samen
   met de rolcontrole. Zonder vervoer stopt de poller na één ronde.
8. **Health.** De connector krijgt de controle `mediaguard`: `ok` → `healthy`, `geweigerd` → `degraded`, anders
   `unknown` als een actieve module batchwerk heeft en `healthy` als geen module MediaGuard nodig heeft. Het detail
   bevat alleen `nodig`, `koppeling` en `reden`.
9. **Batchwerk** (B03-018) mag alleen bij status `ok`. `onbekend`, `geweigerd` en `onbereikbaar` betekenen: geen batch.
10. **`IsKid` (B03-010, deel).** `Core/Privacy/KidPolicy.IsKid` is de ene regel voor kindprofielen: Hub-rol kind, of in
    Jellyfin een leeftijdsgrens, geblokkeerde tags of een toegangsschema. BG-03 is open, dus geldt de breedste regel.
    De pipeline weigert zo'n sessie met 403 `kid_profile` en een Hub-rol kind met 403 `role_kind`, vóór de beheercontrole.
    De rest van B03-010 (register, bewaartermijnen per module, export) hoort bij latere golven.

## Grenzen

- Er is geen weg naar MediaGuard. Op elke installatie staat de koppeling nu op `onbekend`; dat is de afgesproken stand,
  geen storing. De budgetbeslisser start daardoor geen batchwerk.
- De client is alleen getest tegen nagebootst vervoer. Of de echte antwoorden van MediaGuard de genoemde velden zo
  bevatten, is niet gemeten.
- De verzoekroute `POST /media/v1/mediaguard/request` (deeplink `handmatig_in_mediaguard`) is golf 3 en bestaat nog niet.
- `IsKid` is unit-getest; de E2E-proef dekt Hub-rol kind en de beheercontrole, niet een Jellyfin-sessie van een kindprofiel.

## Gevolgen

- **Contractpunt voor ai-server-manager:** leg een leesroute in de Hub vast waarmee Jelly Leon de gefilterde
  MediaGuard-gegevens opvraagt (route, bewijs, velden, tempo), en hoe Jelly Leon aan een dienst-JWT komt; pas §2.3
  regel 2 aan ("eigen sleutel in Jelly Leon") aan het besluit BG-04.
- **Contractpunt:** de veldenwitte lijsten voor de overige MediaGuard-routes ontbreken in plan en contract.
- ADR-0021 besluit 2 vervalt; de overige besluiten van ADR-0021 blijven gelden.

## Alternatieven

- **Sleutel toch in Jelly Leon invoeren** (plan §10.5): afgewezen; strijdig met het besluit van de gebruiker.
- **Nu al een Hub-route aannemen en HTTP-vervoer bouwen:** afgewezen; een geraden route is een contractbreuk en
  onbewezen code op het pad naar een sleutel.
- **Status `healthy` melden zolang er geen koppeling is, ook met batchmodules aan:** afgewezen; dat verbergt dat de
  planner niet mag draaien.
