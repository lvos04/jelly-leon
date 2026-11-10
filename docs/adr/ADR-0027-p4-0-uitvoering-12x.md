# ADR-0027 — P4-0 uitgevoerd: herbasis op v12.4, downgradeweigering, register UG-GEM en de gekozen interpretaties

- **Status:** Aanvaard (2026-11-10) — bouwerbesluit binnen B03-014/B03-019 (P4-0); voert ADR-0011 uit en vult ADR-0019
  aan. Geen nieuw gebruikersbesluit nodig: BG-01 (legacy-auth blijft uit) en BG-02 (geen release op 10.11.11) zijn
  gevolgd.
- **Werkpakketten / testen:** B03-014, B03-019; JLT-60, JLT-61 (a, b), JLT-63 (rooktestdeel), JLT-64 (met de bestaande
  plugin), JLT-67; herhaling JLT-70…73 tegen de jelly-leon-image (B03-015).

## Context

ADR-0011 besloot de server vóór P4 naar de nieuwste stabiele Jellyfin 12.x te brengen. Bij uitvoering (2026-11-10)
gaf `upstream_sync.py kies --spoor nieuwste` opnieuw **v12.4** (`83d0d0e7f76e`; geen nieuwere stabiele tag, alleen
rc-tags van 12.0). De herbasis botste zoals voorspeld op één core-patch (JL-0001, `commands.yml`). Daarnaast moesten
een paar plantekstpunten worden ingevuld die het plan open laat.

## Besluiten

1. **Herbasis met handmatig oplossen in de tool, niet ernaast.** `upstream_sync.py` past elke geregistreerde
   core-patch nu los toe en rapporteert per patch `schoon`/`conflict` (B03-019 d, JLT-67). Met `--handmatig-oplossen`
   blijft `sync/<tag>` bij een conflict staan; `voltooi` maakt daarna precies dezelfde herbasis-commit (twee ouders) en
   baseline-update als een schone sync. Zonder die vlag blijft EX48 ongewijzigd: alles terugdraaien, exitcode 2. Zo
   blijft de tool de enige weg (ADR-0006) en is het oplossen herhaalbaar en gedocumenteerd (PATCHES.md, JL-0001).
2. **Nieuwe upstream-workflow met geheimen krijgt de guard.** `openapi-workflow-run.yml` (12.4) plaatst na een
   PR-workflow een commentaar met `JF_BOT_TOKEN`; hij valt nu onder JL-0001 (ADR-0007 bijgewerkt).
3. **Downgradeweigering in het entrypoint** (JLT-61 b). Jellyfin zelf weigert een nieuwere database niet: gemeten start
   stock 10.11.11 "gezond" op een door 12.4 gemigreerde datamap, maar aanmelden geeft HTTP 500. De image legt daarom in
   `<datamap>/jelly-leon/datamap-versie` de hoogste forkversie vast die de datamap startte (als 568, vlak vóór de
   start) en weigert vóór elke schrijfactie een image die ouder is, met een NL-melding. Een snapshot bevat de oude
   waarde, dus *snapshot + vorige image* start gewoon. Het bestand staat in de config-dataset en is een gedocumenteerd
   restant bij de terugkeer naar stock (B03-013); stock Jellyfin negeert het.
   *Grens:* de weigering werkt vanaf de eerste image die hem heeft (12.4.0-jl.0). Een image van vóór die versie (de
   nooit uitgebrachte 10.11.11-jl.0, BG-02) en stock-images kennen hem niet; voor de overgang 10.11.11 → 12.4 blijft
   JLT-61 (b) met de stock-image dus **Sim-mislukt** (zie contract_issues in het eindrapport).
4. **Register `UPSTREAM_GEDRAG.md`: reeks `UG-GEM-<n>` voor gemeenschappelijk gedrag.** Het plan reserveert
   `UG-F2-1…8`, `UG-F3-1…11` en `UG-F5-1…13`; gedrag waarop P4-0 en meerdere functies steunen, kreeg geen reeks. `GEM`
   botst met geen enkele geplande regel. Elke regel heeft een anker (statisch, CI-job *forkregels* en de sync) en waar
   zinvol een runtime-test op `JL_RUNTIME_IMAGE`. In de sync draaien de runtime-tests op de runtime van de nieuwe tag
   (`jellyfin/jellyfin:<versie>` op de gemeten digest); bestaat die image nog niet, dan blokkeert de sync.
5. **12.x-semantiek in de smoketest.** Vanaf 12.x moeten `X-Emby-Authorization` (gemeten HTTP 400), `X-Emby-Token` en
   `?api_key=` (401) geweigerd worden; een 12.x-server waar ze werken, laat de smoketest falen (BG-01).
6. **Testpakketten van de plugin volgen upstream 12.4** (xunit.v3 3.2.2, Microsoft.NET.Test.Sdk 18.11.0,
   xunit.runner.visualstudio 3.1.5); de metadatatest leest `baseline.json` zodat een sync geen testwijziging vraagt.
   De plugin implementeert geen `IMediaSegmentProvider`; de ABI-breuk `CleanupExtractedData` raakt hem niet.
7. **Web-build begrensd.** De web-stage van de Dockerfile neemt `.npmrc` van jelly-leon-web mee (ignore-scripts,
   engine-strict) en draait webpack op `WEB_BUILD_JOBS` (standaard 4) CPU's; de build eist `<title>Jelly Leon</title>`.
   Lokaal is de image gebouwd met een buildx-builder met 8 GiB/8 CPU's (`docker-container`-driver), alleen een
   werkplekkeuze voor de gedeelde machine, geen repo-eis.
8. **Volledige upstream-testsuite in de SDK-container vraagt `libfontconfig1`.** De SDK-image (Ubuntu 24.04) mist die
   bibliotheek; zonder faalden 131 tests (SkiaSharp). Lokaal wordt hij in de wegwerpcontainer geïnstalleerd (als root,
   daarna `dotnet test` als de eigen gebruiker); GitHub-runners hebben hem al. Dat is een omgevingsafwijking, geen
   code-afwijking.

## Gevolgen

- Forkbasis v12.4 / forkversie 12.4.0-jl.0; .NET 10 (SDK 10.0.403 op digest); runtime en `JL_RUNTIME_IMAGE`
  `jellyfin/jellyfin:12.4@sha256:fea863d0…1771`; Node 24.22.2 op digest; web-fork 5ced8a246.
- `docs/openapi/jelly-leon.openapi.json` is de 12.4-export (structureel gelijk aan upstreams gepubliceerde
  `jellyfin-openapi-12.4.json`); het upgraderapport 10.11.11 → 12.4 staat in `test-evidence/p40/`.
- Overnemen in de standaardbranch en een release blijven handmatige R2-stappen (ADR-0006, BG-02).
