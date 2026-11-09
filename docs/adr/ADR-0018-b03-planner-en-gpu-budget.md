# ADR-0018 — B03: Globale batchplanner en GPU-budget A310 / UHD 770

- **Status:** Aanvaard (uitvoering later) — het B03 2.0-plan is op 2026-11-09 door de gebruiker goedgekeurd; er is
  nog niets gebouwd. Uitvoering volgens `docs/platform-v2/02_BOUWPLANNEN/B03_FASERING.md`: golf 0 nu, tegen stock
  12.4; modulewerk pas na de P4-0-gate op de 12.x-basis (ADR-0011).
- **Herkomst:** voorstel ADR-B03-04 uit het bouwplan (`docs/platform-v2/02_BOUWPLANNEN/B03_UNIVERSELE_MEDIASERVER.md` §10.7 en §10.8). Blokkerend jurypunt J-HAALB A-1; verder A-3, A-5, F5-1…4.
- **Werkpakketten:** B03-018 (planner, budgetbeslisser), B03-004/062/063/064 (F5 live-lanes); testen JLT-36, JLT-44,
  JLT-45, JLT-66.

## Context

- Het manifest geeft jelly-leon 4 CPU's en 4096 MiB (`jelly-leon.manifest.yaml:41-43`). Opgeteld vroegen de functies meer
  (± 4,4–5,5 GB; 7 threads), en de OOM-killer zou dan Jellyfin zelf raken.
- Upstream kent één GPU-apparaat. MediaGuard encodeert AV1 op de kaart met AV1-encode (A310) en slaat de UHD 770 over; zijn
  kijkpauze laat lopende GPU-encodes doorgaan en vervalt na ± 60 s stilte.
- GPU-cijfers komen van de Meteor Lake-iGPU; volgens specificaties heeft de UHD 770 ≈ 1/6 en de A310 ≈ 2/3 daarvan (niet
  gemeten). D08 is onbekend; de iGPU kan in het BIOS uit staan.
- HW-decode verbergt beschadiging (gemeten, F4).

## Besluit

1. **Eén globale batchplanner** voor alle modules: hooguit één zware taak tegelijk; batch samen ≤ 2 threads en ≤ 1 GiB;
   `nice 19`, `ionice idle`; pauze ≤ 5 s na elke `PlaybackStart` (niet uit te zetten; enige uitzondering een expliciet
   beheerdersverzoek met ≥ 1024 MiB cgroup-marge en zonder CPU-transcode); één vensterbeleid afgestemd op het
   MediaGuard-nachtvenster; stilstand bij software-transcode, noodstop, leesfouten, schrijfbare mount en (op de NAS) zonder
   Δ-MG-AUTH. Modules leveren alleen jobtypes, kostenklasse per codec en prioriteit.
2. **Eén budgetbeslisser** als enige bron van waarheid over GPU/CPU-bezetting: live-transcodes (via `ITranscodeManager` +
   `/proc`, aangeleverd door module Devices), MediaGuard-lanes (één poller via de viewerclient, elke 20 s, witte lijst),
   batchvraag; lane-reservering per sessiesleutel (seek, hervatten, groepspauze op dezelfde node).
3. **Regels G1–G10:** live > MediaGuard-AV1 > B03-batch; rollen "UHD 770 live, A310 AV1/overloop" zijn hypotheses en de
   routering volgt **gemeten** capaciteit per werkklasse; AV1-encode nooit op een node zonder AV1-encode; VPP-tonemapping
   nooit voor DV-profiel 5; B03-batch nooit op de A310 terwijl MediaGuard daar encodeert; F4 decodeert altijd op de CPU;
   F6-beelddecode alleen op de UHD 770 na D08; model-apps nooit op de A310; **nooit** `/api/v1/app/control`; alle nodes
   vol → upstreamgedrag + event, nooit weigeren (ADR-0024).
4. **Topologieën** `two_gpu`, `a310_only`, `uhd770_only`, `single_other`, `none` zijn expliciete standen.
5. **Live-lanekeuze** zelf is van F5: een NativeAOT-lanewrapper die alleen het nodepad herschrijft en met `execv` dezelfde
   PID houdt; faalt de spike, dan een klein C-programma, pas daarna een geregistreerde core-patch.
6. **Meten** zonder MediaGuard te bedienen: de beheerder pauzeert MediaGuard zelf via een deeplink, of de meting krijgt het
   label "met MediaGuard-last".
7. Een **gecombineerde belastingtest** (alle modules, 4 live streams, MediaGuard-simulator) levert de invoer voor het besluit
   over de manifestresources (BG-07); geen NAS-waarde wordt ingevuld zonder meting.

## Alternatieven

- *Budget per module:* eenvoudiger per functie, maar opgeteld niet beheersbaar. Verworpen.
- *Jelly Leon pauzeert MediaGuard via `/app/control`:* buiten de contractgrens en eigenaarschap. Verworpen.
- *Weigeren of terugschalen bij volle GPU's:* breekt stock-clients en kan door de wrapper niet worden afgedwongen. Verworpen.

## Gevolgen

- Batchwerk loopt langzamer (achterstandsschatting zichtbaar), maar live kijken heeft altijd voorrang.
- De echte rolverdeling op de NAS is pas na D08 en een meting per werkklasse bekend (NIET GEVALIDEERD (hardware)).

## Verificatie

JLT-66 (belasting), JLT-36 (pauze ≤ 5 s), JLT-44 (lanekeuze, sessiesleutel, terugval), JLT-45 (MediaGuard-budget alleen
lezen), JLT-49/JLT-69 (NAS, *Geblokkeerd*).
