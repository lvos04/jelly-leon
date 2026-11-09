# ADR-0016 — B03: Eén serverplugin met modules

- **Status:** Aanvaard (uitvoering later) — het B03 2.0-plan is op 2026-11-09 door de gebruiker goedgekeurd; er is
  nog niets gebouwd. Uitvoering volgens `docs/platform-v2/02_BOUWPLANNEN/B03_FASERING.md`: golf 0 nu, tegen stock
  12.4; modulewerk pas na de P4-0-gate op de 12.x-basis (ADR-0011).
- **Herkomst:** voorstel ADR-B03-02 uit het bouwplan (`docs/platform-v2/02_BOUWPLANNEN/B03_UNIVERSELE_MEDIASERVER.md` §10.1). Blokkerend jurypunt (J-COMPAT A-1, J-HAALB A-2).
- **Werkpakket:** B03-017; test JLT-68.

## Context

- 12.x laadt elke plugin in een eigen `PluginLoadContext` (`PluginManager.cs:130-140`) en maakt van elke plugin-DLL een
  MVC-application part (`ApiServiceCollectionExtensions.cs:155-160`).
- De zes functies delen singletons: `/connector/v1/*`, één outbox, idempotency, Hub-pin (JL4), de MediaGuard-viewerclient,
  de planner en de budgetbeslisser. In v1.0 van de plandelen waren F2–F5 losse plugins met een gedeelde bibliotheek.
- Gevolg van losse plugins (afgeleid uit de code, **niet gemeten**): dubbel geregistreerde `/connector/v1`-routes
  (ambiguous match) en typen die tussen plugins niet via DI te delen zijn; vijf outboxen.
- De ladder (ADR-0001) blijft: plugin vóór patch.

## Besluit

1. Eén assembly `Jellyfin.Plugin.JellyLeon` (fork-eigen pad `plugins/`, GPL-2.0, `net10.0`, `Jellyfin.Controller 12.x`) met
   modules **WatchTogether, Recommendations, Subtitles, Quality, Devices, Segments** en **Core** (gedeeld).
2. Elke module heeft een eigen schakelaar, een eigen SQLite onder `/config/data/jelly-leon/<module>/`, een eigen namespace
   en een eigen set routes, events, jobtypes en webdelen. Module uit = die delen zijn weg; de rest blijft ongewijzigd.
3. Core bevat één connector, één outbox, één OpenAPI-bestand, de foutcatalogus (ai-server-manager ADR-0016, voorstel ADR-B03-05), de Hub-koppeling (ai-server-manager ADR-0017, voorstel ADR-B03-06),
   de geheimenmap, `IsKid`, de `UserDeleted`-afhandeling en het register van persoonsgegevens (ADR-0020), de analyzer
   voor verboden API's per namespace en de stabiele spoorsleutel.
4. Een tweede DLL in dezelfde pluginmap is toegestaan (bijv. `JellyLeon.Recommendations.Core`); die laadt in dezelfde
   `PluginLoadContext`.
5. De plugin moet ook op de **stock** 12.x-image laden (dan ontbreekt alleen de F5-lanekeuze).
6. **Eerste gate van golf 1:** een prototype met twee modules. Faalt het, dan valt het plan terug op één kernplugin die als
   enige `/connector/v1` host, met de overige modules achter een procesgrens; de functieplannen blijven gelijk.

## Alternatieven

- *Zes losse plugins + gedeelde bibliotheek:* modulair voor de beheerder, maar dubbele routes en geen gedeelde staat.
  Verworpen.
- *Kernplugin + losse functieplugins via een procesgrens:* werkt, maar meer IPC en meer foutpaden. Terugvaloptie.

## Gevolgen

- Eén versie voor alle modules; een fout in één module mag de andere niet raken (try/catch op de modulegrens, health per
  module).
- De analyzer moet per namespace werken, omdat F3 bewaakte schrijfacties nodig heeft die in F4 verboden zijn.

## Verificatie

JLT-68 (routes precies één keer, foutcatalogus gelijk per module, Hub-gedrag), JLT-64 (module uit = stock), laden op fork en
stock-image in CI.
