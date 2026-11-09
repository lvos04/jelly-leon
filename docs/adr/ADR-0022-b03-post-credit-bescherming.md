# ADR-0022 — B03: Post-credit-scènes beschermen met segmentgrenzen, zonder nieuw segmenttype

- **Status:** Aanvaard (uitvoering later) — het B03 2.0-plan is op 2026-11-09 door de gebruiker goedgekeurd; er is
  nog niets gebouwd. Uitvoering volgens `docs/platform-v2/02_BOUWPLANNEN/B03_FASERING.md`: golf 0 nu, tegen stock
  12.4; modulewerk pas na de P4-0-gate op de 12.x-basis (ADR-0011).
- **Herkomst:** voorstel ADR-B03-10 uit het bouwplan (`docs/platform-v2/02_BOUWPLANNEN/B03_UNIVERSELE_MEDIASERVER.md` §17 (F6.3.4)). Uit F6 §3.4; door J-COMPAT het sterkste deel van de plannen genoemd.
- **Werkpakketten:** B03-007 (uitgebreid), B03-071, B03-073, B03-076; testen JLT-51, JLT-55.

## Context

- `MediaSegmentType` kent in 12.x alleen Unknown, Commercial, Preview, Recap, Outro en Intro; er is geen type voor een
  post-credit-scène. De REST-API is alleen `GET`.
- Clients springen bij "overslaan" naar `EndTicks`; zonder `EndTicks` naar het volgende item. Type Unknown voert geen client
  uit. Intro Skipper kan post-credits als Preview markeren, die dan wordt overgeslagen.
- Desktop-issue #1304: een outro tot het bestandseinde kan de speler laten vastlopen.
- De gebruiker eist knoppen "Sla intro over", "Sla samenvatting over", "Sla aftiteling over" zonder post-credit-scènes
  onbedoeld over te slaan.

## Besluit

1. **Geen nieuw enumtype en geen core-patch.** Per aftitelingblok een apart **Outro**-segment; de post-credit- of
   mid-credit-scène valt in **geen enkel** segment.
2. Outro eindigt **2,0 s vóór** de scène (`PostCreditGuardSeconds`); grenzen worden naar binnen afgerond; bij twijfel wordt
   niets overgeslagen; **Unknown** wordt nooit gepubliceerd; EOF-marge 1,0 s.
3. Standaard overal **"vragen"**, nooit automatisch overslaan; in een SyncPlay-groep wordt "Overslaan" "Vragen" (haak van F1).
4. Nieuwe segmenten eerst in **schaduwmodus** tot een QC-steekproef (standaard 3 afleveringen per serie) of menselijke
   bevestiging; publicatie gericht onder de eigen provider-ID (`CreateSegmentAsync`/`DeleteSegmentAsync`), nooit
   `forceOverwrite` of `RunSegmentPluginProviders`.
5. Na "Sla aftiteling over" of bij de "Volgende"-overlay toont de webplugin "Na de aftiteling volgt nog een scène".

## Alternatieven

- *Nieuw type `PostCredit` via een core-patch:* stock-clients kennen het niet en zouden het negeren of verkeerd tonen;
  upstream-kans onzeker. Verworpen.
- *Post-credits als Preview:* wordt overgeslagen. Verworpen.

## Gevolgen

- De bescherming werkt in **elke** client die naar `EndTicks` springt, ook stock-clients.
- Een kijker die de aftiteling niet overslaat, ziet de hint; wie overslaat, landt vóór de scène.

## Verificatie

JLT-51: **0** post-credit-schendingen op de bevroren testset (n ≥ 30 beschermde scènes, Wilson-bovengrens vermeld) en in
elke geteste client; JLT-55 (knoppen en SyncPlay).
