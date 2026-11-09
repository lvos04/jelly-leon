# ADR-0004 — GPL-2.0-verplichtingen

- **Status:** Aanvaard (P0, 2026-11-09)
- **Context:** Jellyfin is gelicenseerd onder GPL-2.0 (`LICENSE` in de root, onveranderd). Jelly Leon is een
  afgeleid werk en wordt als container-image (`ghcr.io/lvos04/jelly-leon`) verspreid — ook al is het alleen voor eigen
  gebruik, we behandelen elke gepubliceerde image als distributie. Contract §10: "geen licentie toevoegen zonder vraag aan
  de gebruiker".

## Besluit

1. **Licentie blijft GPL-2.0.** `LICENSE` wordt niet gewijzigd of vervangen; er komt geen extra licentiebestand. Eigen
   bestanden in deze repo vallen onder dezelfde licentie (geen afwijkende headers zonder vraag aan de gebruiker).
2. **Bron beschikbaar:** elke image-tag `X-jl.N` komt van git-tag `vX-jl.N` in de openbaar te maken repo
   `lvos04/jelly-leon` (server + plugins) en `lvos04/jelly-leon-web` (web-client, ref vastgelegd in
   `tools/jelly-leon/baseline.json`). De image draagt de labels `org.opencontainers.image.source`,
   `org.opencontainers.image.revision` en `org.opencontainers.image.licenses="GPL-2.0-only AND GPL-2.0-or-later"`
   (server: GPL-2.0 zoals upstream `LICENSE`; web-client: upstream `package.json` meldt GPL-2.0-or-later). Zolang de repos privé zijn,
   publiceren we geen image publiek (zie followup in EVIDENCE/eindrapport) — de gebruiker beslist over zichtbaarheid.
3. **Credits:** `CONTRIBUTORS.md` en upstream-copyrightregels blijven onaangeroerd; `README.jelly-leon.md` en de
   statusinformatie noemen "gebaseerd op Jellyfin (jellyfin.org), GPL-2.0". In de image staan `LICENSE`,
   `CONTRIBUTORS.md` en een `NOTICE.jelly-leon` onder `/usr/share/doc/jelly-leon/`.
4. **Wijzigingen herkenbaar:** GPL-2.0 §2a — elke core-patch staat met datum en doel in `docs/platform-v2/PATCHES.md`;
   commits vermelden de wijziging.
5. **Derde componenten in de image:** de runtime-laag komt (schets P0) uit de officiële image `jellyfin/jellyfin`
   (bron: `jellyfin/jellyfin-packaging`, `jellyfin/jellyfin-ffmpeg` — GPL/LGPL). Die bronverwijzingen staan in
   `NOTICE.jelly-leon`. Bij een eigen runtime-stage (P4) geldt hetzelfde voor elk toegevoegd pakket.
6. **Geen naamsmisbruik:** "Jellyfin" blijft de technische naam (ADR-0003); we doen ons niet voor als officiële
   Jellyfin-release: geen upstream-logo als eigen merk, image-titel is "Jelly Leon".

## Gevolgen

- CI controleert dat `LICENSE` byte-gelijk is aan de baseline (`patch_register_check.py` behandelt `LICENSE` als
  verboden wijziging).
- Followup voor de gebruiker: besluit over zichtbaarheid (publiek/privé) van `jelly-leon`, `jelly-leon-web` en het
  GHCR-pakket vóór de eerste image-release.
