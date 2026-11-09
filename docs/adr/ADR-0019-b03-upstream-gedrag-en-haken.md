# ADR-0019 — B03: Register van upstream-gedrag, patches en webhaken

- **Status:** Aanvaard (uitvoering later) — het B03 2.0-plan is op 2026-11-09 door de gebruiker goedgekeurd; er is
  nog niets gebouwd. Uitvoering volgens `docs/platform-v2/02_BOUWPLANNEN/B03_FASERING.md`: golf 0 nu, tegen stock
  12.4; modulewerk pas na de P4-0-gate op de 12.x-basis (ADR-0011).
- **Herkomst:** voorstel ADR-B03-07 uit het bouwplan (`docs/platform-v2/02_BOUWPLANNEN/B03_UNIVERSELE_MEDIASERVER.md` §10.11). Jurypunten J-COMPAT (register, haken), J-TEST.
- **Werkpakket:** B03-019 (register en sync-proef), B03-017 (haakmodule); testen JLT-64, JLT-67.

## Context

- Het PATCHES-register van de drie forks bewaakt elke wijziging aan upstream-bestanden (CI faalt bij een ongeregistreerde
  afwijking). Maar de modules steunen ook op upstream-**gedrag** dat geen ABI is: de DI-registratie van
  `ISyncPlayManager`, de volgorde en limietstop van similar-providers, de scan van de interne metadatamap en de
  hernummering van sporen, het ffmpeg-pad en de ffprobe-afleiding, het `-init_hw_device`-token, de EncoderValidator-probes,
  de mtime-cleanup van MediaSegments, `forceOverwrite`, provider-ID = MD5, en webfuncties (`loadSections`,
  `setButtonText`, `DEFAULT_ACTIONS`, `getDeviceProfile`, `config.json`-plugins, de SyncPlay-instance).
- Een 12.y-update kan dat gedrag stil veranderen. `JL_RUNTIME_IMAGE` stond nog op 10.11.11.
- De plandelen noemden rond tien webhaken met losse werknamen; de geplande JLW-0001…0003 verschuiven in 12.x
  (`apps/stable` → `legacy`, `experimental` → `modern`).

## Besluit

1. **`docs/platform-v2/UPSTREAM_GEDRAG.md`** naast `PATCHES.md` in jelly-leon (webdeel in jelly-leon-web). Per regel: het
   gedrag, de bron (bestand:regel in de upstream-tag), de module die erop steunt, en een **sync-blokkerende contracttest**
   op de 12.x-runtime (`JL_RUNTIME_IMAGE`). Nummering `UG-<functie>-<n>` (F3 U<n> = UG-F3-<n>, F5 U<n> = UG-F5-<n>).
2. CI-controle: een verwijzing `UG-…` in code of docs zonder test laat de build falen.
3. De **DI-vervanging** van `ISyncPlayManager` (F1) staat hier als geregistreerde afwijking; faalt de decorator-gate, dan
   eerst een kleine core-patch in PATCHES.
4. **Webhaken:** elke haak is één regel `jlHook('naam', ctx)` naar één fork-eigen module `src/jelly-leon/hooks`
   (dynamische import, try/catch). Eén haak in de legacy-controller `itemDetails/index.js` dekt Modern én Legacy;
   JLW-0002 en de F5-routehaak worden één haak; het F5-label komt via een webplugin op `SHOW_VIDEO_OSD` zonder haak.
   Nummers (`JLW-NNNN`) pas bij de echte patch. Eén generator maakt de `config.json` van de image.
5. **Clientpatches** (jelly-leon-clients) alleen voor de eigen apps, klein en per subtree herbaseerbaar; geen patches in
   Swiftfin in v1.

## Gevolgen

- Een upstream-sync faalt luid als gedrag verandert, in plaats van stil verkeerd te werken.
- Het aantal haken blijft klein en elke haak kan een fout in fork-code niet doorgeven aan de upstream-pagina.

## Verificatie

JLT-67 (sync-proef: elke patch los herbaseerbaar, elke UG-test groen of blokkerend), JLT-64 (alleen additief; module uit =
stock), herbasisproef per webhaak op de volgende 12.x-tag.
