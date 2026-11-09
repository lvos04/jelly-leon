# ADR-0023 — B03: Licentiebeleid voor code, modellen en testdata

- **Status:** Aanvaard (uitvoering later) — het B03 2.0-plan is op 2026-11-09 door de gebruiker goedgekeurd; er is
  nog niets gebouwd. Uitvoering volgens `docs/platform-v2/02_BOUWPLANNEN/B03_FASERING.md`: golf 0 nu, tegen stock
  12.4; modulewerk pas na de P4-0-gate op de 12.x-basis (ADR-0011).
- **Herkomst:** voorstel ADR-B03-11 uit het bouwplan (`docs/platform-v2/02_BOUWPLANNEN/B03_UNIVERSELE_MEDIASERVER.md` §10.16). Uit analyse 3 en de plandelen; geen juridisch advies.
- **Werkpakketten:** alle; in het bijzonder B03-016 (CI-guard), B03-018 (SBOM), B03-044 (modellen).

## Context

- De fork is **GPL-2.0-only** (ADR-0004). Volgens de lijst van de FSF (https://www.gnu.org/licenses/license-list.html,
  geraadpleegd 2026-11-09 via analyse 3) zijn Apache-2.0, GPL-3.0 en AGPL niet verenigbaar met GPLv2-only.
- Bijna alle Jellyfin-plugins (o.a. Intro Skipper) zijn GPL-3.0; ffsubsync trekt `auditok` (GPL-3.0) mee.
- Modellen: OPUS-MT (Hugging Face-tag apache-2.0, OPUS-MT-documentatie CC-BY 4.0 — de strengste lezing geldt);
  multilingual-e5-small MIT; NLLB, CometKiwi/XCOMET, Tower, Aya, GEITje, fastText lid218e NC; LibreTranslate, Lingarr AGPL.
- Testdata: MovieLens (onderzoekslicentie), Pioneer One (CC BY-NC-SA), fanondertitels (onduidelijk), Blender (CC BY).

## Besluit

1. **Code in de image:** alleen GPL-2.0-verenigbare bibliotheken in het serverproces; GPL-3.0-code alleen als **apart proces**
   of als ongewijzigde, los geïnstalleerde plugin in een **testcontainer** (Intro Skipper als vergelijkingsbasis, BG-32).
   `auditok` niet in de image (ffsubsync met `--vad webrtc`). Geen AGPL-componenten (ook niet ua-parser-js v2).
2. **Modellen:** alleen MIT/Apache-2.0/CC-BY (met naamsvermelding in NOTICE); NC-modellen nooit; gated modellen (Gemma, Llama)
   alleen na een expliciet besluit (BG-18). Modellen nooit in de jelly-leon-image.
3. **Testdata:** alleen lokaal in `.lokaal/`; nooit in een repo of image; een **CI-guard** weigert beperkt gelicentieerde
   bestanden (MovieLens, Pioneer One, afgeleide labels, fanondertitels) in commits en images.
4. **SBOM en licentie-inventaris** van de image (inclusief de Python-werker) in CI; bij de publieke image een aanbod van de
   broncode waar de licentie dat vraagt.

## Gevolgen

- Sommige bruikbare plugins en modellen vallen af; de functies worden eigen code (GPL-2.0) of gebruiken een apart proces.

## Verificatie

CI-guard (negatieve test), SBOM-controle in B03-018, licentie-inventaris bij elke release.
