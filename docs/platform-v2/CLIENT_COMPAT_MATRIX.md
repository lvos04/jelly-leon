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
| Derden-client met legacy-headers (gesimuleerd) | `X-Emby-Token`, `X-MediaBrowser-Token`, `X-Emby-Authorization` en `api_key` geweigerd op de beproefde API-routes. Statische stream speelt (UG-GEM-1/2, BG-01) |
| PlaybackInfo (3 apparaatprofielen) | byte-gelijk aan stock 12.4 op dezelfde datamap, Direct Play én transcode (`test-evidence/p40/compat-api.json`) |

### Serverrooktests op 2026-11-18

De bewaarde Jelly Leon-image van bronrevisie `48293b48a` en de gepinde stock-image van 12.4 gaven dezelfde uitkomst
bij acht runtimetests. De API-proef vergeleek 18 antwoorden met 0 verschillen. OpenAPI bevatte alleen nieuwe paden
onder `/media/v1` en `/connector/v1` en bijbehorende schema's. [Runtimerapporten en API-proef](test-evidence/2026-11-18-s-p40-40/)

Het synthetische browsercorpus gaf op beide servers dezelfde uitkomst. Firefox, WebKit en de webOS- en Tizen-UA's
doorstonden de rooktest. Chromium toonde op beide servers beeld zonder gemeten audiodecodering, ook met stock-web.
De gesimuleerde derden-client kreeg in beide runs HTTP 401 met de oude koppen en `?api_key=`, HTTP 200 met moderne
authenticatie en met `?ApiKey=`, en HTTP 206 bij een statische stream zonder token. [Stockbrowserproef](test-evidence/2026-11-18-s-p40-40/clientmatrix-synthetisch-stock.json) · [Jelly Leon-browserproef](test-evidence/2026-11-18-s-p40-40/clientmatrix-synthetisch-jelly-leon.json)

### Desktoprooktest in het serverharnas op 27 november 2026

**Sim-getest.** Desktop 2.0.0 uit S-P40-72 laadde onder Xvfb de webclient van de Jelly Leon-image van bronrevisie
`48293b48a`. De testkijker logde in en speelde `hero.mp4` via Direct Play. Na **Hervatten** kwamen de eerste
sessiepositie en de voortgangsmelding overeen met het opgeslagen punt van 17,934 s. Er kwam geen nulmelding.
Na stoppen stond 20,645 s opgeslagen. Tijdens deze proef registreerde CDP geen `ChunkLoadError`.
[Desktopbewijs van het serverharnas](test-evidence/b03-016-desktop-spike.json)

### Clientmetingen uit jelly-leon-clients

De clients-repo mat server 12.4 uit jelly-leon `e294f84` en jelly-leon-web `5ced8a2` met stock 12.4 op digest als
controlegroep voor de vergelijkingen hieronder. Herkomst: [EVIDENCE.json, B03-003][clientbewijs] en
[BOUWVERIFICATIE_P4-0.md, §2–§4, §8 en §9.1][clientverslag].

| Datum | Client / rol | Uitkomst uit de clients-repo |
|---|---|---|
| 2026-11-10 | Android-telefoon API 35, officiële app en fork-app | Sim-getest tegen beide servers. Inloggen, bladeren, hervatten rond 300 s, bewaard hervatpunt, Direct Play, transcode en NL-ondertitels gemeten. Ondertitels op afstand wisselen mislukte in het native pad op beide servers. [Fork-app][android] · [officiële app][officieel] |
| 2026-11-10 | Android TV API 34 en 36 | Fork-app op beide emulators Sim-getest op Jelly Leon. Vergelijking op API 34 met stock gaf dezelfde uitkomsten voor de fork-app. Bij de officiële app op API 34 sprong het beeld één keer kort naar het begin op Jelly Leon. De expliciete hervatproef kwam daarna op beide servers op 6/6. [Fork-app][android] · [officiële app en hervatproef][clientverslag] |
| 2026-11-10 | Android-tablet API 35, fork-app | Sim-mislukt. Bij 4 GiB traden OOM-kills op. Bij 5 GiB verliep één van drie pogingen volledig. [Tabletproeven][clientverslag] |
| 2026-11-10 | Desktop 2.0.0 onder Xvfb | Sim-getest. Inloggen, bladeren, hervatten rond 300 s, Direct Play, transcode en ondertitels leverden dezelfde uitkomsten op beide servers. [Desktopbewijs][desktop] |
| 2026-11-10 | Swiftfin 1.6.1, serverprotocol | Moderne MediaBrowser-kop, WebSocket, statische stream en transcode-URL gaven dezelfde uitkomsten op beide servers. De client blijft **NIET GEVALIDEERD (Mac/Xcode)**. [Protocolbewijs][swiftfin] |
| 2026-11-17 | Fork-telefoon en desktop onder Xvfb, afgeschermd testnetwerk | Rooktests herhaald op dezelfde serverbron. De gemeten speluitkomsten kwamen per client overeen met stock. [Telefoonbewijs][telefoon-herhaling] · [desktopbewijs][desktop-herhaling] |

SyncPlay, skipknoppen, downloaden, de MediaGuard-afspeeltest en de combinatie met alle modules aan blijven open voor
JLT-63. NIET GEVALIDEERD (hardware): echte tv's, telefoons en tablets. Safari op Mac blijft buiten het Linux-WebKit-bewijs.

[clientbewijs]: https://github.com/lvos04/jelly-leon-clients/blob/91f9d41cd10542edfb4a4976dffa9d71609e821f/docs/platform-v2/EVIDENCE.json
[clientverslag]: https://github.com/lvos04/jelly-leon-clients/blob/91f9d41cd10542edfb4a4976dffa9d71609e821f/docs/platform-v2/BOUWVERIFICATIE_P4-0.md
[android]: https://github.com/lvos04/jelly-leon-clients/blob/91f9d41cd10542edfb4a4976dffa9d71609e821f/docs/platform-v2/test-evidence/p4-0-jc3-android-emulator.json
[officieel]: https://github.com/lvos04/jelly-leon-clients/blob/91f9d41cd10542edfb4a4976dffa9d71609e821f/docs/platform-v2/test-evidence/p4-0-jc3-android-officieel.json
[desktop]: https://github.com/lvos04/jelly-leon-clients/blob/91f9d41cd10542edfb4a4976dffa9d71609e821f/docs/platform-v2/test-evidence/p4-0-jc3-desktop.json
[swiftfin]: https://github.com/lvos04/jelly-leon-clients/blob/91f9d41cd10542edfb4a4976dffa9d71609e821f/docs/platform-v2/test-evidence/p4-0-jc3-swiftfin-protocol.json
[telefoon-herhaling]: https://github.com/lvos04/jelly-leon-clients/blob/91f9d41cd10542edfb4a4976dffa9d71609e821f/docs/platform-v2/test-evidence/p4-0-s-p40-72-herstel-android-telefoon.json
[desktop-herhaling]: https://github.com/lvos04/jelly-leon-clients/blob/91f9d41cd10542edfb4a4976dffa9d71609e821f/docs/platform-v2/test-evidence/p4-0-s-p40-72-herstel-desktop.json

## 5. Eindimage van S-P6-30 en stock 12.4 (S-P6-31, JLT-63)

Proef van 28 november 2026. De eindimage `jelly-leon:p6` bevat servercommit `5d8784c635ea` en webcommit `5ced8a24601e`. De stockreferentie is gepind op `sha256:fea863d0cd9e…`. Het meetbestand bevat de volledige imageverwijzingen en de begin- en eindtijd van elke afgeronde matrixrun.

| Client en proefvorm | Stock 12.4 (pogingen) | Eindimage (pogingen) |
|---|---|---|
| Chromium, echte headless browser | Niet gemeten | Niet gemeten |
| Firefox, echte headless browser | Niet gemeten | Niet gemeten |
| WebKit, echte headless Linux-browser | Niet gemeten | Niet gemeten |
| webOS, nagebootst profiel in Chromium | Niet gemeten | Niet gemeten |
| Tizen, nagebootst profiel in Chromium | Niet gemeten | Niet gemeten |
| Stock-web uit de stock-image, echte Chromium-browser | Niet gemeten | Niet gemeten |
| Derden-client, nagebootste HTTP-verzoeken | Niet gemeten | Niet gemeten |
| Officiële Android-app, telefoonemulator | Niet gemeten | Niet gemeten |
| Officiële Android-app, tabletemulator | Niet gemeten | Niet gemeten |
| Officiële Android TV-app, emulator API 34 | Niet gemeten | Niet gemeten |
| Officiële Android TV-app, emulator API 36 | Niet gemeten | Niet gemeten |

Een volledige vergelijking op één UTC-meetdag ontbreekt. Voor de vier Android-rollen ontbreekt `/dev/kvm` in de testomgeving. Een cel met “Niet gemeten” heeft geen afgeronde meting in deze proef.

Bij de twee tv-profielen meet het harnas Chromium met een andere user-agent. De legacy-rij toetst zeven aanmeldvormen op drie routes. De afzonderlijke MediaGuard-proef met `TV_PROFILE` uit S-P6-33 staat open.

NIET GEVALIDEERD (hardware) voor echte tv’s, telefoons, tablets en streamingboxen (N-P6-09). NIET GEVALIDEERD (Mac/Xcode) voor Swiftfin en Safari. Desktop, SyncPlay, skipknoppen en downloaden hebben geen nieuwe eindimagemeting in deze rooktest. [Meetbestand van S-P6-31](test-evidence/s-p6-31-compatibiliteit.json)
