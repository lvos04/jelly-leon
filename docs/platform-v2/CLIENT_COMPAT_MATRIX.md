# Compatibiliteitsmatrix server ↔ clients (B03-001)

Server: Jelly Leon `10.11.11-jl.0` (technische identiteit Jellyfin Server 10.11.11) · peildatum 2026-11-09.

**Legenda validatie:** `Sim-getest` = protocol nagebootst door `tools/jelly-leon/e2e/stock_client_smoke.py` tegen een
echte server-build (geen echt apparaat) · `NIET GEVALIDEERD (hardware)` = nog niet op een echt apparaat getest ·
`unknown` = nog niet bekend welk apparaat/welke versie in huis gebruikt wordt (D15).

## 1. Protocol (Sim-getest, lokaal 2026-11-09)

Dezelfde 17 stappen zijn geslaagd tegen (a) de fork-build op de officiële runtime, (b) de **stock** image
`jellyfin/jellyfin:10.11.11` en (c) de fork-build via de Jelly Leon-entrypoint als 568 zonder capabilities
(`test-evidence/p0-stock-client-smoke-{fork,stock,entrypoint}.json`). Geen verschil tussen fork en stock.

| Clientgedrag | Nagebootst als | Resultaat |
|---|---|---|
| Server herkennen (`/System/Info/Public`: ProductName, Version) | alle clients | Sim-getest ✔ (`Jellyfin Server`, `10.11.11`) |
| Eerste-startwizard | Jellyfin Web | Sim-getest ✔ |
| Inloggen met `Authorization: MediaBrowser Client=…, Device=…, DeviceId=…, Version=…` | Jellyfin Web, Jellyfin Android | Sim-getest ✔ |
| Inloggen met oude `X-Emby-Authorization` + `X-Emby-Token` | Kodi-achtige clients | Sim-getest ✔ |
| Fout wachtwoord / geen token → 401 | alle | Sim-getest ✔ |
| Bibliotheek scannen, item vinden | Jellyfin Web | Sim-getest ✔ (muziek, zelfgemaakte WAV) |
| Statisch streamen (byte-gelijk) en seek via `Range` → 206 | Jellyfin Android | Sim-getest ✔ |
| Sessies/apparaten zichtbaar | Jellyfin Web | Sim-getest ✔ |
| Jelly Leon-route `/media/v1/version` (met/zonder token) | Hub | Sim-getest ✔ (`compatibel` / 401) |
| Waarneming: streamen zonder token | — | HTTP 200 = upstream-gedrag, risico (ADR-0009) |

Niet in de simulatie: transcoderen/HLS (geen echte video, geen GPU), ondertitels, live-tv, SyncPlay, casten, offline
downloads, DV/HDR. Die volgen in B03-003/004/005/011/012.

## 2. Clients (echte apparaten)

| Client (upstream-app) | Platform | Verwachte compatibiliteit (zelfde protocol als stock 10.11.11) | Validatie |
|---|---|---|---|
| Jellyfin Web (`jelly-leon-web`, fork van jellyfin-web 10.11.11) | browser desktop/mobiel | volledig | NIET GEVALIDEERD (hardware) |
| Jellyfin Android | Android-telefoon | volledig | NIET GEVALIDEERD (hardware) |
| Jellyfin Android TV | Android TV / Google TV | volledig | NIET GEVALIDEERD (hardware) |
| Swiftfin (`jelly-leon-clients/swiftfin`) | iOS / tvOS | volledig | NIET GEVALIDEERD (Mac/Xcode) |
| Jellyfin Desktop (`jelly-leon-clients/desktop`) | Windows/macOS/Linux | volledig | NIET GEVALIDEERD (hardware) |
| Kodi + Jellyfin-add-on | Kodi | volledig (oude headers Sim-getest) | NIET GEVALIDEERD (hardware) |
| Smart-tv-app (Samsung/LG) / tv-browser | tv | afhankelijk van het model | unknown (D15) |
| Chromecast / AirPlay | cast | afhankelijk van de client | unknown (D15) |

**Regel:** een client gaat pas op "getest" na een echte sessie (inloggen, afspelen, ondertitel, hervatten) op het
apparaat dat in huis gebruikt wordt, met app-versie, datum en bewijs. Geen aanname dat elk tv-platform werkt (B03 §5).
