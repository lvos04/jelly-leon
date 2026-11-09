# ADR-0024 — B03: Clientrollen; stock-clients worden nooit geweigerd of aangepast zonder opt-in

- **Status:** Aanvaard (uitvoering later) — het B03 2.0-plan is op 2026-11-09 door de gebruiker goedgekeurd; er is
  nog niets gebouwd. Uitvoering volgens `docs/platform-v2/02_BOUWPLANNEN/B03_FASERING.md`: golf 0 nu, tegen stock
  12.4; modulewerk pas na de P4-0-gate op de 12.x-basis (ADR-0011).
- **Herkomst:** voorstel ADR-B03-12 uit het bouwplan (`docs/platform-v2/02_BOUWPLANNEN/B03_UNIVERSELE_MEDIASERVER.md` §10.2). Jurypunten J-COMPAT F5-B1 (blokkerend), A-2.
- **Werkpakketten:** B03-068, B03-019, B03-005 (uitgebreid); testen JLT-46, JLT-63.

## Context

- Compatibiliteit met bestaande Jellyfin-clients is heilig (besluit gebruiker). F5 v0.1 beschreef een "nette weigering" en
  een CPU-plafond die ook stock-clients zouden raken; de lanewrapper kan alleen het nodepad wijzigen, niet terugschalen.
- De officiële Android- en desktopapp laden jelly-leon-web van de server en geven de server-`profileBuilder` door
  (`nativeshell.js:102-104`); ze heten net als een Jelly Leon-build "Jellyfin for Android" (`Constants.kt:11`).
- De MediaGuard-afspeeltest gebruikt een vast profiel (`TV_PROFILE`, `clients.py:53-69`).

## Besluit

1. Vijf rollen met één definitie: **stock-native**, **stock-web**, **officiële app met serverweb**, **Jelly Leon-webclient**,
   **fork-app** (tabel in §10.2 van het bouwplan). Tests per rol apart.
2. **Nooit weigeren of verlagen** van een afspeelstart van een client die daar niet zelf voor koos; alle GPU's vol → het
   gedrag van standaard Jellyfin + event. Lagere kwaliteit alleen als opt-in voor Jelly Leon-web (BG-28).
3. Stock-native, stock-web en officiële apps zonder opt-in krijgen **exact** de upstream-PlaybackInfo (vaste veldenlijst,
   bij een gelijke `encoding.xml`). Aanpassen alleen met opt-in per apparaat (BG-26), voor stock-native alleen beperkend.
4. De MediaGuard-afspeeltest en aanroepen met een API-sleutel zijn altijd uitgesloten.
5. Voor derden-clients wordt nooit "werkt ongewijzigd" beweerd zonder meting (12.x zet legacy-auth uit).

## Gevolgen

- De leerwinst van F5 komt vooral bij Jelly Leon-web en de fork-apps; officiële apps profiteren pas na opt-in.

## Verificatie

JLT-46 (100 % identieke PlaybackInfo per rol zonder opt-in; 0 geweigerde of verlaagde starts), JLT-63 (compat per rol met
alle modules aan).
