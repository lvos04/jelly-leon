# Compatibiliteitsmatrix server ↔ clients (B03-001)

Server: Jelly Leon `12.4.0-jl.0` (technische identiteit Jellyfin Server 12.4.0) sinds P4-0 (2026-11-10); §1–§2 zijn de
P0-peiling op 10.11.11, §3 de voormeting tegen stock 12.4, §4 de rooktest tegen de jelly-leon-image 12.4.

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
| Hub-adapter v1 (contract 1.2 §2.3, ADR-0012): eigen **niet-admin**-gebruiker leest `/media/v1/version`, krijgt 403 op `/Auth/Keys`; Hub-JWT (`Bearer` of als token) → 401 | Hub (nagebootst) | Sim-getest ✔ (reviewer-QA contract 1.2; echte Hub NIET GEVALIDEERD) |
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

**Upgrade 12.x (besluit gebruiker, ADR-0011):** vóór P4 gaat de server naar de nieuwste stabiele Jellyfin 12.x. Deze
matrix wordt dan volledig opnieuw doorlopen. Swiftfin blijft op **1.6.1**; of 1.6.1, Jellyfin Android en Android TV
met een 12.x-server werken is nog niet gemeten → **unknown** tot de upgradefase (Android/Android TV-controle in
`jelly-leon-clients`; Swiftfin NIET GEVALIDEERD (Mac/Xcode)).

**Regel:** een client gaat pas op "getest" na een echte sessie (inloggen, afspelen, ondertitel, hervatten) op het
apparaat dat in huis gebruikt wordt, met app-versie, datum en bewijs. Geen aanname dat elk tv-platform werkt (B03 §5).

## 3. Clientmatrix-rooktest tegen stock 12.4 (B03-016, golf 0, Sim-getest)

Gemeten op 2026-11-10 tegen stock `jellyfin/jellyfin:12.4` op digest (emulators en browsers, geen echte apparaten):
Chromium 153, Firefox 155 en WebKit 26.6 (Playwright 1.63), webOS/Tizen via UA-simulatie, stock-web via `--webdir`, een
gesimuleerde derden-client met legacy-headers, jellyfin-android 2.7.3 op een telefoon- en tablet-AVD (API 35) en
jellyfin-androidtv 0.19.10 op Android TV API 34 (x86) en API 36 (x86_64) spelen `hero.mp4` af (**Sim-getest**). Met 12.4
geven `X-Emby-Token`, `X-MediaBrowser-Token`, `X-Emby-Authorization` en `?api_key=` een 401 op API-routes (alleen
`Authorization: MediaBrowser Token=…` en `?ApiKey=` werken); dat raakt derden-apps zoals Kodi-add-ons → besluit BG-01.
Details en bewijs: `BOUWVERIFICATIE_B03-016.md` §2 en `test-evidence/b03-016-clientmatrix-rooktest.json`. De apps op echte
apparaten blijven **NIET GEVALIDEERD (hardware)**; Swiftfin **NIET GEVALIDEERD (Mac/Xcode)**.

## 4. Rooktest tegen de jelly-leon-image 12.4 (P4-0, B03-019, JLT-63 rooktestdeel; Sim-getest)

Gemeten op 2026-11-10 tegen de lokaal gebouwde jelly-leon-image `12.4.0-jl.0` (image-ID `sha256:53a03a44…50ed`, commit
`7dc66d364`, echte jelly-leon-web-build `5ced8a246`; alleen de bestaande plugin, nog geen modules) met
`python -m b03h clientmatrix --onderdelen web,ua,legacy,webdir --image jelly-leon:p40`
(`test-evidence/p40/clientmatrix-rooktest-jelly-leon-12.4.json`):

| Client / rol | Uitkomst |
|---|---|
| Jelly Leon-webclient (ingebouwd) in Chromium 153, Firefox 155, WebKit 26.6 (Playwright 1.63, headless) | hero.mp4 speelt (orakel geslaagd; eerste frame 0,5–0,9 s) — Sim-getest |
| webOS en Tizen via UA-simulatie (profielcode van de Jelly Leon-webclient) | speelt — Sim-getest (geen echte decoder) |
| Stock-web uit de stock-image tegen de Jelly Leon-server (over `/jellyfin/jellyfin-web` gekoppeld; de image weigert `--webdir`) | speelt — Sim-getest |
| Derden-client met legacy-headers (gesimuleerd) | gemeten: `X-Emby-Token`, `X-MediaBrowser-Token`, `X-Emby-Authorization`, `api_key` geweigerd op API-routes; statische stream speelt (UG-GEM-1/2) — besluit BG-01 |
| PlaybackInfo (3 apparaatprofielen) | byte-gelijk aan stock 12.4 op dezelfde datamap, Direct Play én transcode (`test-evidence/p40/compat-api.json`) |

Niet in deze ronde tegen de jelly-leon-image: de Android-/Android TV-emulators (tegen stock 12.4 wel, §3), de desktopapp
(spike Geblokkeerd), SyncPlay, skipknoppen, downloaden en de MediaGuard-afspeeltest. Echte apparaten: NIET GEVALIDEERD
(hardware); Swiftfin/Safari: NIET GEVALIDEERD (Mac/Xcode).
