# ADR-0017 — B03: Eén analysewerker, één Python-omgeving, één bestandspas

- **Status:** Aanvaard (uitvoering later) — het B03 2.0-plan is op 2026-11-09 door de gebruiker goedgekeurd; er is
  nog niets gebouwd. Uitvoering volgens `docs/platform-v2/02_BOUWPLANNEN/B03_FASERING.md`: golf 0 nu, tegen stock
  12.4; modulewerk pas na de P4-0-gate op de 12.x-basis (ADR-0011).
- **Herkomst:** voorstel ADR-B03-03 uit het bouwplan (`docs/platform-v2/02_BOUWPLANNEN/B03_UNIVERSELE_MEDIASERVER.md` §10.6). Jurypunten J-COMPAT (werkervorm), J-HAALB A-4, A-6, A-7.
- **Werkpakket:** B03-018; testen JLT-66, JLT-28, JLT-36, JLT-58.

## Context

- F3 (ondertitels), F4 (kwaliteit) en F6 (segmenten) analyseren mediabestanden. F3 dacht aan een daemon met socket, F4 aan
  een kindproces per job, F6 was neutraal. Elk bestand werd zo meerdere keren volledig gelezen; op remuxes van 30–80 GB is
  dat I/O-gebonden.
- De officiële 12.4-image heeft geen python3 (gemeten). ffsubsync heeft een harde afhankelijkheid op `auditok` (GPL-3.0);
  met `--vad webrtc` werkt de sync ook zonder (gemeten, F3).
- `ffsubsync --serialize-speech` schrijft een `.npz` naast de video (gelezen in de bron) — een schrijfactie in de mediamap.
- Contract §2.2: na de eigenaarschapsstap draait geen enkel proces als root; PID 1 blijft het dienstproces of een bewaker.

## Besluit

1. **Vorm:** één langlevende Python-werker als kindproces van de Jellyfin-server, gestart en bewaakt door module Core
   (herstart met backoff, health-ping, `PR_SET_CHILD_SUBREAPER`). Berichten in JSON ≤ 1 MiB over een unix-socket onder
   `/run/jelly-leon/` (eigenaar 568, 0700, `SO_PEERCRED`).
2. **Tools als kindproces per taak:** ffmpeg, ffprobe en ffsubsync met een argumentenlijst (nooit een shell), elk in een
   eigen procesgroep; stoppen = hele groep (SIGTERM, na 5 s SIGKILL); geen wees-processen.
3. **Omgeving:** vastgezette interpreter onder `/opt/jelly-leon/python`; `pip install --no-deps --require-hashes`; SBOM,
   licentie-inventaris en `pip-audit` in CI; tool-smoketest in `upstream-sync.yml`; de groei van de image is een gate
   (grens vastgelegd bij de eerste meting). Niet in de jelly-leon-image: torch, transformers, ctranslate2, auditok.
4. **Eén bestandspas per bestand** die de audiokenmerken voor F3, F4 en F6 maakt (chromaprint, spraakkaart met VAD,
   silencedetect/astats/ebur128, cue-extractie) en, als F4 niveau 2 gepland is, in dezelfde decode de beeldsignalen.
   Resultaat in een weggooibare featurecache onder `/cache/jelly-leon/` op een bestandsvingerafdruk.
5. `--serialize-speech` en elk uitvoerpad in een bibliotheekmap zijn verboden (opdrachtbouwer weigert ze).
6. Metriek in elke prestatietest: gelezen bytes per item per functie.

## Alternatieven

- *Kindproces per job zonder daemon:* eenvoudiger, maar elke job laadt Python en bibliotheken opnieuw. Verworpen voor de
  Python-tools; wel gebruikt voor ffmpeg.
- *Analyse in C# in het serverproces:* geen Python nodig, maar ffsubsync/py3langid zouden opnieuw gebouwd moeten worden.
  Verworpen voor v1.
- *Een aparte werker-container:* past niet bij "één alles-in-één image per repo" (contract §1).

## Gevolgen

- De image groeit met een Python-runtime; dat is gemeten en begrensd.
- Eén plek voor procesbewaking en opruimen; makkelijker te testen zonder netwerk (`--network none`).

## Verificatie

Smoketest in de image, kill-test (0 wees-processen en 0 zombies na 100 herhalingen), SBOM-controle, gelezen bytes
≤ 1,1 × bestandsgrootte voor F3/F4/F6 samen (B03-018-acceptatie).
