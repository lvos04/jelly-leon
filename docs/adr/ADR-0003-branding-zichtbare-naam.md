# ADR-0003 — Branding: alleen zichtbare naam "Jelly Leon", technische identiteit blijft "Jellyfin"

- **Status:** Aanvaard (P0, 2026-11-09)
- **Context:** Vaste keuze gebruiker (contract §1): "technische identiteit/API blijft 'Jellyfin' (clientcompatibiliteit);
  alleen de zichtbare naam is 'Jelly Leon'". Stock clients (Jellyfin Web/Android/Android TV/Swiftfin/Desktop,
  Kodi-add-ons, Infuse, Findroid …) herkennen de server via `GET /System/Info/Public` (`ProductName`
  = `"Jellyfin Server"`, `Version` = `10.11.11`, `Id`), via de `Authorization: MediaBrowser …`-header,
  `X-Emby-*`/`X-MediaBrowser-*`-headers, de UDP-discovery op poort 7359 en via plugin-`targetAbi`.

## Besluit

**Blijft ongewijzigd (technische identiteit):** assemblynamen en namespaces, `AssemblyProduct("Jellyfin Server")`
(levert `ProductName`), `AssemblyVersion`/`SharedVersion.cs` (`10.11.11`), routes en JSON-velden, authenticatieschema
`MediaBrowser`/`Emby`-headers, discovery-antwoord, pluginrepository-formaat en `targetAbi`, NuGet-pakketnamen,
databasenamen (`jellyfin.db`), mapnamen en omgevingsvariabelen (`JELLYFIN_*`), executable `jellyfin`, User-Agent.

**Mag later zichtbaar "Jelly Leon" heten (P1+, niet in P0):** titel/logo/teksten in de web-client
(`jelly-leon-web`), naam van de Custom App en de image (`jelly-leon`), naam en beschrijving van eigen plugins, teksten
in de Hub-UI. Eerst via configuratie (`BrandingOptions`: `LoginDisclaimer`, `CustomCss`, splashscreen) — pas als dat niet
volstaat via een geregistreerde patch (ADR-0001) in `jelly-leon-web`, nooit in serveridentiteit.

**In P0 is niets aan branding gewijzigd.** De E2E-smoketest `tools/jelly-leon/e2e/stock_client_smoke.py` controleert
expliciet dat `ProductName == "Jellyfin Server"` en `Version == <baseline>`; een brandingwijziging die de technische
identiteit raakt laat die test falen. Ook `GET /media/v1/version` van de plugin meldt dan `status: afwijkend`,
`reason_code: technical_identity_changed`.

## Gevolgen

- Volledige compatibiliteit met stock clients en bestaande plugins blijft het uitgangspunt (B03-001-acceptatie).
- Zoekmachines/gebruikers zien in technische schermen (Dashboard → Over) nog "Jellyfin"; dat is bewust.
- GPL-credits en "gebaseerd op Jellyfin" blijven altijd zichtbaar (ADR-0004).
