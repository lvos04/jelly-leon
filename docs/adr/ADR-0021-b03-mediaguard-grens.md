# ADR-0021 — B03: MediaGuard met één viewerclient en geen mutaties tot een contractwijziging

- **Status:** Aanvaard (uitvoering later) — het B03 2.0-plan is op 2026-11-09 door de gebruiker goedgekeurd; er is
  nog niets gebouwd. Uitvoering volgens `docs/platform-v2/02_BOUWPLANNEN/B03_FASERING.md`: golf 0 nu, tegen stock
  12.4; modulewerk pas na de P4-0-gate op de 12.x-basis (ADR-0011).
- **Herkomst:** voorstel ADR-B03-09 uit het bouwplan (`docs/platform-v2/02_BOUWPLANNEN/B03_UNIVERSELE_MEDIASERVER.md` §10.5). Jurypunten J-BESCH A3/A4, F3-I2, F4-B1, F4-I1, F1-I4, F5-I2.
- **Werkpakket:** B03-009 (uitgebreid); testen JLT-23, JLT-37, JLT-45.

## Context

- MediaGuard is eigenaar van bestand, kwaliteit, import, AV1, quarantaine en het zoeken naar NL-ondertitels
  (02_DATA_EIGENAARSCHAP.md:5); P4-no-go: "media mutatie buiten MediaGuard".
- Contract 1.2 §2.3 regels 2–3: de Hub mag bij MediaGuard alleen "noodstop aan"; operatorrechten pas na sleutelscopes (P3-02).
- `GET /api/v1/mediaserver/status` geeft ook wie wat kijkt (`sessions.watching`, `hold.reason` met titel).
- Een operator-sleutel kan de noodstop van MediaGuard uitzetten; wie Jelly Leon overneemt, zou die kunnen misbruiken.

## Besluit

1. **Eén viewerclient** voor alle modules: rol viewer, gecontroleerd met `GET /api/v1/auth/me` bij elke start en elk uur;
   een andere rol is fail-closed (niet opslaan, niet gebruiken). Routewitte lijst (GET + het niet-muterende
   `POST /api/v1/audio/inspect`); veldenwitte lijst per route; ruwe antwoorden nooit loggen of bewaren; één poller per route.
2. De sleutel wordt in Jelly Leon zelf ingevoerd (BG-04) en staat alleen in de geheimenmap.
   *Vervallen op 2026-11-11:* de gebruiker besliste BG-04 anders (via de Hub, bij voorkeur zonder sleuteloverdracht);
   zie ADR-0034. Er komt geen MediaGuard-sleutel in Jelly Leon.
3. **Geen MediaGuard-mutaties vanuit B03.** Alle wensen (F3 `subtitles.search`, F4 `wanted.search`,
   `quarantine.release_check`, `file.reacquire`, `quality.report`) zijn gebundeld in **Δ-CONTRACT-MG** en staan op
   `Geblokkeerd (contract)`; `quarantine.restore` wordt R3 en wordt nooit door AI voorgesteld.
4. Tot dan: één verzoekroute `POST /media/v1/mediaguard/request` met `kind`; antwoord `handmatig_in_mediaguard` met een
   deeplink — nooit gesimuleerd succes. Na een vervanging door MediaGuard controleert Jelly Leon het nieuwe bestand
   (readback) en koppelt het eigen gegevens opnieuw.
5. **Geen dubbel werk:** Jelly Leon zoekt geen ondertitels, downloadt geen media, bouwt geen eigen audio-/taalbeleid (leest
   `policy/effective` en `audio/inspect`), schrijft geen `.nl.srt` in de bibliotheek en roept MSO nooit aan.
6. Wat MediaGuard mist, staat als deltaverzoek in hoofdstuk 18 (Δ-MG-AUTH, Δ-MG-1…8, Δ-MG-DV).

## Gevolgen

- In v1 kan Jelly Leon problemen vinden, bewijzen en doorverwijzen, maar niet zelf laten herstellen.

## Verificatie

JLT-37 (0 muterende MediaGuard-aanroepen via een loggende proxy; operator-sleutel geweigerd), JLT-45 (budget alleen lezen,
witte lijst), JLT-23 (voorrang menselijke NL; `has_nl()` onaangeroerd).

## Aanvulling 2026-11-09 — MediaGuard volgt Emby én Jelly Leon

7. **Δ-MG-AUTH per server en Δ-MG-DUAL.** MediaGuard spreekt Jelly Leon 12.x aan met `Authorization: MediaBrowser
   Token=…` en houdt voor Emby `X-Emby-Token`. Zolang Emby draait, volgt MediaGuard **beide** servers tegelijk: kijkpauze
   als iemand op één van beide kijkt, afspeeltest en NL-ondertitels per server. De bestaande Emby-koppeling mag op geen
   enkel moment onderbreken. Pas na de controlelijst "Emby verwijderen" (bouwplan §10.9.2) laat MediaGuard Emby netjes los.
8. **MediaGuard-voortgang (HARDE EIS).** Jelly Leon raakt de database van MediaGuard nooit. Elke MediaGuard-release, ook de
   eerste uit de nieuwe publieke repo, bewijst een upgrade op een gevulde database van de vorige versie zonder
   gegevensverlies (eis aan media-guard-ultimate).

Verificatie aanvullend: JLT-73 (MediaGuard-simulator volgt beide servers; kijkpauze bij een sessie op elk van beide).
