# ADR-0001 — Plugin/extensie vóór core-patch; core-patches alleen via patchregister

- **Status:** Aanvaard (P0, 2026-11-09)
- **Context:** B03 §5 ("Begin met een Jellyfin plugin/adapter in plaats van direct eigen protocol. Maak fork pas wanneer
  onderbouwd nodig"), I06 stap 6–7, I24 stap 3, B03-013 ("Patch stack minimal"), contract §1 (technische identiteit blijft
  Jellyfin). Elke wijziging in upstream-bestanden maakt elke upstream-sync duurder en vergroot de kans dat stock
  Jellyfin-clients breken.

## Besluit (pakketregel)

Voor elke nieuwe functie geldt deze volgorde; je mag pas een stap verder als de vorige aantoonbaar niet volstaat:

1. **Configuratie** van upstream Jellyfin (bestaande opties, bv. QSV/VAAPI, parental control, DVR).
2. **Bestaande upstream-plugin** of officiële extensie (bv. de webhook-plugin) — niet zelf herbouwen.
3. **Eigen plugin** in `plugins/<Naam>/` tegen de publieke plugin-ABI (`Jellyfin.Controller`/`Jellyfin.Model`/
   `Jellyfin.Common` van exact dezelfde versie, zie ADR-0002).
4. **Externe dienst/adapter** buiten Jellyfin (bv. in de Hub of `jelly-leon-platform`) via de Jellyfin-API.
5. **Core-patch** in upstream-bestanden — alleen als 1–4 aantoonbaar niet kunnen, en dan uitsluitend via het
   patchregister `docs/platform-v2/PATCHES.md`.

Een core-patch (elk gewijzigd, toegevoegd of verwijderd bestand buiten de fork-eigen paden) moet in het register staan met:
doel, exacte bestanden, waarom stap 1–4 niet volstaan, upstream-PR-kans, test, status. De CI-stap
`tools/jelly-leon/patch_register_check.py` vergelijkt de boom met de upstream-baseline-commit en **faalt** voor elk
bestand buiten de fork-eigen paden dat niet in het register staat.

Fork-eigen paden (geen core-patch; bron: `tools/jelly-leon/fork_paths.txt`): `plugins/`, `deploy/`, `tools/jelly-leon/`,
`docs/platform-v2/`, `docs/adr/`, `docs/openapi/`, `README.jelly-leon.md`, `.env.example`,
`.github/workflows/jelly-leon-ci.yml`, `.github/workflows/upstream-sync.yml`.

## Gevolgen

- In P0 is de servercode identiek aan upstream `v10.11.11` (gemeten: `git diff upstream-v10.11.11 HEAD` raakt alleen
  docs en `README.jelly-leon.md`). Enige geregistreerde patch: repository-guards op upstream-workflows (JL-0001, CI-patch).
- Een patch met redelijke upstream-PR-kans wordt eerst upstream aangeboden; na acceptatie verdwijnt hij bij de volgende sync.
- Plugins die alleen de publieke ABI gebruiken werken ook op stock Jellyfin van dezelfde versie (terugval-pad A17/I24).

## Overwogen alternatieven

- *Direct een volledige eigen server/protocol* — verworpen (I06 §5: "Geen nieuwe universele media-app met volledige eigen
  protocollen from scratch").
- *Alle uitbreidingen als core-patch* — verworpen: sync-kosten en regressierisico voor stock clients.
