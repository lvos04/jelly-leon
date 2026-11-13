# Jelly Leon installeren als standaard TrueNAS Custom App (contract 1.3)

> **Status: NIET GEVALIDEERD (echte NAS).** De volledige image (server + echte web-build + plugin) is lokaal én in
> GitHub-CI (job *image*) gebouwd en met dezelfde formulierwaarden in Docker getest (Sim-getest, zie
> `docs/platform-v2/BOUWVERIFICATIE_P0.md` §11–§14 en `BOUWVERIFICATIE_P4-0.md`). Sinds P4-0 (B03-014) staat de basis op
> **Jellyfin 12.4** (forkversie `12.4.0-jl.0`, .NET 10, webclient jelly-leon-web 12.4). Er is nog **geen** gepubliceerde
> image `ghcr.io/lvos04/jelly-leon`: een `-jl.0`-forkversie wordt nooit uitgebracht (ADR-0005) en de eerste release op
> 12.x is een aparte R2-stap (BG-02). Anoniem ophalen gaf op 2026-11-09 `DENIED` (er bestaat nog geen pakket).
> Het formulier hieronder is niet op een echte TrueNAS doorlopen; veldnamen volgen TrueNAS SCALE 24.10/25.04 en kunnen
> per versie iets afwijken (welke versie op jouw NAS staat, meet de wizard: D01). De installatie gebeurt normaal **door
> het platform** (Hub → executor → TrueNAS-API `app.create` met precies deze formulierwaarden, vertaald uit
> `deploy/manifest/jelly-leon.manifest.yaml`); dit document beschrijft dezelfde velden voor controle en noodgevallen.

**Nooit** via *Install via YAML*, `custom_compose_config` of docker compose. Geen terminal, geen script.

## Vooraf (verplicht, zie I24/I06)

1. **Een eventuele bestaande (stock-)Jellyfin blijft draaien en wordt niet aangeraakt** (I24 §5, contract §2.3). Of er
   een is en op welke poort, meet de wizard via de TrueNAS-API (D07); neem dat nooit aan. Jelly Leon krijgt een eigen
   poort, eigen datasets en een eigen appnaam; de media worden alleen-lezen gedeeld.
2. Back-upgate groen (OneDrive-herstel bewezen, D04/D05) en ZFS-snapshot van de mediadataset.
3. Waarden komen uit de onboarding-wizard en de datasetkiezer van de Hub (D01 TrueNAS-versie, D02 datasets,
   D03 NAS-adres, D08 GPU-rendernodes). Vul **geen voorbeeldwaarden** in.

## Datasets

Maak (of laat de Hub maken) twee eigen datasets met preset **Apps**:

| Doel | Dataset (jouw keuze) | Mount in de container | Back-up |
|---|---|---|---|
| Configuratie + database (`jellyfin.db`), metadata, plugins | `<pool>/<pad>/jelly-leon/config` | `/config` | ja (snapshot + Jellyfin-back-up-API) |
| Cache en transcodes | `<pool>/<pad>/jelly-leon/cache` | `/cache` | nee (opnieuw op te bouwen) |
| Media (bestaand, alleen lezen) | jouw bestaande mediadataset | `/media` (of meerdere submappen) | via eigenaar (MediaGuard/MSO) |

Rechten hoef je niet aan te passen: bij de eerste start maakt de container gebruiker `568` (apps) eigenaar van
**alleen** `/config` en `/cache`. Mediamappen worden nooit gewijzigd.

Ontbreekt de opslagregel voor `/config` of `/cache`, dan zou Docker stilletjes een anoniem volume aanmaken (de database
staat dan niet op je dataset en verdwijnt bij verwijderen). De container **weigert dan te starten** en meldt welke
opslagregel ontbreekt.

Kies voor `/config` het opslagtype **Host Path** of **ixVolume**. De container weigert ook te starten als `/config`
het opslagtype **tmpfs** heeft (database en instellingen zouden na elke herstart weg zijn en de startwizard zou weer
voor iedereen openstaan) of een **NFS/SMB-share** is (de SQLite-database van Jellyfin is daar niet betrouwbaar). Voor
`/cache` mag tmpfs wel (alles daarin is opnieuw op te bouwen; het kost werkgeheugen).

## Formulier: Apps → Discover Apps → Custom App

| Sectie | Veld | Waarde |
|---|---|---|
| Application Name | | `jelly-leon` |
| Image Configuration | Repository | `ghcr.io/lvos04/jelly-leon` |
| | Tag | **`<forkversie>@sha256:<64 hex>`** — de vaste forkversie (vorm `<upstream>-jl.<N>`, ADR-0005) mét de digest uit de release (zie *Tag met digest* hieronder). Nooit `latest`. Nog niet gepubliceerd. |
| | Pull Policy | *Pull the image if it is not already present on host* |
| Container Configuration | Entrypoint / Command | leeg laten |
| | Timezone | tijdzone van de NAS (uit de wizard) |
| | Environment Variables | **leeg laten** (geen geheimen in het formulier; geen `JELLYFIN_*`-paden: datamappen buiten `/config`/`/cache` worden geweigerd) |
| | Restart Policy | *Unless Stopped* |
| | Disable Builtin Healthcheck | **uit** laten (de healthcheck van de image op `/health` wisselt als eerste handeling naar 568 zonder capabilities, ADR-0014; *Healthy* hieronder en de bewaking steunen erop) |
| Security Context | Privileged | **uit** |
| | Capabilities | geen toevoegen |
| | Custom User | **uit** (aanbevolen: de container maakt zelf 568:568 eigenaar van `/config` en `/cache` en draait daarna als 568). Aan met User/Group `568` mag ook, maar alleen als beide datasets al van 568 zijn; anders stopt de container met een melding (zie *Problemen*). |
| Network Configuration | Host Network | **uit** |
| | Ports → Add | Container Port `8096`, Host Port `30460` (voorstel uit contract §2; de Hub controleert conflicten via de TrueNAS-API). Draait er al een stock-Jellyfin (D07), dan houdt die zijn eigen poort; kies nooit diens poort. Protocol TCP |
| Portal Configuration | Add | Name `Jelly Leon`, Protocol *HTTP*, Use Node IP aan, Port gelijk aan de Host Port hierboven, Path `/` (uit `custom_app.portal` van het manifest) |
| Storage Configuration | Add → Host Path | Mount Path `/config` → Host Path: jouw config-dataset |
| | Add → Host Path | Mount Path `/cache` → Host Path: jouw cache-dataset |
| | Add → Host Path | Mount Path `/media` → Host Path: jouw mediadataset, **Read Only aan** |
| Resources Configuration | CPUs / Memory | voorstel 4 CPU / 4096 MiB (transcoderen deelt de NAS met MediaGuard) |
| GPU Configuration | Intel-GPU doorgeven | **standaard uit** (manifestparameter `gpu`: `none`). Alleen aanzetten (*Passthrough available (non-NVIDIA) GPUs*) als de wizard via de TrueNAS-API een Intel-render-node heeft gemeten (D08) en jij `intel_render` kiest. Het formulier kan niet per GPU kiezen: de app krijgt dan **elke** niet-NVIDIA-render-GPU van de NAS (NIET GEVALIDEERD op een echte NAS). Geen privileged-modus: de container voegt zelf alleen de groepen toe van de doorgegeven `/dev/dri/renderD*`- en `/dev/dri/card*`-apparaten, en alleen als die in de container bestaan (nooit groep 0). |

**Install.** De eerste start duurt kort (database aanmaken). Daarna *Running* en na de healthcheck (`/health`)
*Healthy*.

### Tag met digest

Het formulier kent alleen *Repository* + *Tag*; TrueNAS maakt daar `<repository>:<tag>` van. Daarom vul je de tag in als
`<forkversie>@sha256:<digest>` (geldige Docker-syntax; trekt precies die image, ook als iemand de tag later verplaatst).
De digest staat bij de release van `lvos04/jelly-leon` (de release-CI publiceert hem, P4). Of het formulier het `@`-teken
accepteert en of TrueNAS met zo'n tag updates herkent, is **NIET GEVALIDEERD (echte NAS)**. Weigert het formulier de tag
met digest, vul dan alleen de exacte forkversie in; de controle is dan de digest-readback: na elke installatie of update
leest de executor de digest terug (TrueNAS-API `app.image.query`, `repo_digests`) en stopt met een incident als die
afwijkt (contract §2.2). Bij een handmatige installatie zonder Hub ontbreekt die controle; vergelijk dan zelf de digest
die TrueNAS na het ophalen toont met die van de release.

### Publieke image, registry-login alleen als terugvaloptie

De repository's van Jelly Leon zijn publiek (gebruikersbesluit 3) en de image wordt bij de eerste release als **publiek**
GHCR-pakket uitgebracht. Installeren gebruikt dan **geen** registry-login. Alleen als het pakket (tijdelijk) privé
blijkt — TrueNAS meldt dan dat de image niet kan worden opgehaald — is een registry-login de terugvaloptie: in TrueNAS
onder *Apps → Configuration → Manage Container Image Registries* (naam kan per versie verschillen) een registry
`ghcr.io` met een GitHub-token dat **alleen pakketten mag lezen**. Gedrag met GHCR-tokens: NIET GEVALIDEERD. Zo'n token
is een geheim van jou in TrueNAS: nooit in dit formulier (Environment Variables), het manifest, een repo of een log.

### Beveiliging zonder formuliervelden

Het standaardformulier (ix-app-template, versie 1.4.8 in de gelezen catalogus) zet **geen** `no-new-privileges` en laat
de standaard-capabilities van Docker staan (contract §2.2; gelezen in de bronnen, NIET GEVALIDEERD op een echte NAS).
De image regelt dat zelf: na de eigenaarschapsstap draait de server als 568:568 zonder capabilities en met
`no_new_privs` (`setpriv` in de entrypoint), ook als *Custom User* aan staat. Ook de healthcheck van de image wisselt
vóór de controle van `/health` naar 568 zonder capabilities (ADR-0014). Je hoeft hiervoor niets in te vullen.

## Openen en koppelen

- Open `http://<NAS-adres>:<hostpoort>` (adres uit de wizard, D03). De Jellyfin-startwizard verschijnt (technische
  identiteit blijft Jellyfin: bestaande Jellyfin-apps herkennen de server gewoon).
- **Rond de startwizard direct af** en maak daarin het beheerdersaccount met een eigen wachtwoord. Zolang de
  startwizard openstaat, kan iedereen op het netwerk die de pagina opent beheerder worden. In het manifest staat dit
  als controle na installatie (`post_install_checks`: `startwizard_afronden`, contract 1.3 §9): volgens het contract
  toont de Hub hem als taak en telt de app pas als gezond nadat de beheerder hem bevestigt (met de echte Hub NIET
  GEVALIDEERD). De kijkgeschiedenis uit Emby overnemen kan daarna en is een eigen keuze; Emby blijft ongewijzigd
  draaien.
- **Bewaking (monitorplan, contract 1.3 §9):** het manifest noemt `GET /health` met verwachte status 200 (timeout
  10 s, elke 60 s). De Hub maakt daar alleen een plan van en past Uptime Kuma niet zelf aan: je neemt de monitor zelf
  over in de Uptime Kuma-UI en bevestigt hem daar ("handmatig bevestigd"). Zonder die bevestiging is de bewaking niet
  gevalideerd.
- Bestaande Jellyfin-apps (web, Android, Android TV, iOS/Swiftfin, Kodi, …) verbinden met hetzelfde adres en dezelfde
  poort. Welke apps getest zijn: `docs/platform-v2/CLIENT_COMPAT_MATRIX.md` (nu alles **NIET GEVALIDEERD** op echte apparaten).
- **Koppelen met de Hub (v1, contract §2.3, ADR-0012):** geen enrollment en geen `HUB_URL`/`HUB_ENROLLMENT_TOKEN` in het
  formulier. De Hub-adapter leeft in de Hub en leest alleen openbare routes (`/System/Info/Public`, `/health`) en wat
  een eigen **niet-admin** Jellyfin-gebruiker mag zien (die maak je zelf in het Jellyfin-dashboard en voer je in de
  Hub-UI in). Een admin-API-sleutel wordt niet gebruikt; Jelly Leon accepteert (nog) geen Hub-JWT's. De Hub-pagina
  *Versie en clientcompatibiliteit* leest `GET /media/v1/version` (Jelly Leon-plugin; vraagt een aangemelde
  Jellyfin-gebruiker, geen beheerder). Met een nagebootste Hub-adapter getest: zo'n niet-admin-gebruiker kan die route
  lezen maar ziet geen API-sleutels, en een Hub-JWT wordt geweigerd (Sim-getest; met de echte Hub NIET GEVALIDEERD).

## Updaten en terugdraaien

- **Updaten**: via de platform-UI (executor `app.update`, R2 met goedkeuring) of hier *Edit → Tag* naar de nieuwe
  `<forkversie>@sha256:<digest>`. Jellyfin migreert de database bij de start; maak vooraf een snapshot van de
  config-dataset. Noteer vóór het wijzigen de huidige tag (met digest): dat is je terugzetrecept.
- **Terugdraaien**: TrueNAS *Roll Back* (`app.rollback`) werkt alleen voor catalogusversies, **niet** voor een
  gewijzigde image-tag van een Custom App (contract §2.2). Terugzetten = *Edit → Tag* terug naar de vorige
  `<forkversie>@sha256:<digest>` **én** de config-snapshot van vóór de update terugzetten (database + binary samen,
  B03-013, I06 stap 8). Alleen de tag terugzetten is niet veilig na een databasemigratie. Via de platform-UI doet de
  Hub/lifecycle dit met de vóór de update bewaarde formulierwaarden.
- **Downgradeweigering (sinds 12.4.0-jl.0, JLT-61 b):** de image onthoudt in `<config>/jelly-leon/datamap-versie` de
  hoogste Jelly Leon-versie die deze datamap heeft gestart. Kies je alléén een oudere tag (zonder de snapshot), dan
  start de app niet en staat in de log `FOUT: deze datamap is al gestart door Jelly Leon <x>, nieuwer dan deze image`;
  er is dan niets gewijzigd. Zet de snapshot mee terug (die bevat ook de oude datamap-versie) of kies weer de nieuwere
  tag. Gemeten (Sim): een **stock** Jellyfin 10.11.11 op een door 12.4 gemigreerde datamap start wél "gezond", maar
  aanmelden geeft HTTP 500 — die image kent deze weigering niet; daarom nooit alleen de image terugzetten.
- **Aanmelden van apps (12.x, BG-01):** de oude aanmeldmethode (`X-Emby-Token`, `?api_key=`, `X-Emby-Authorization`)
  staat in 12.x uit en blijft uit. De officiële Jellyfin-apps gebruiken de nieuwe methode; een oudere derden-app die
  dat niet doet, kan niet meer aanmelden (zie `CLIENT_COMPAT_MATRIX.md`).

## Problemen

| Melding in de app-log | Oplossing |
|---|---|
| `FOUT: /config is een anoniem Docker-volume, geen gekozen dataset` (of `/cache`) | Storage-regel ontbreekt of Mount Path is niet exact `/config` / `/cache`. Voeg de opslagregel toe en start opnieuw. |
| `FOUT: … ligt buiten /config of /cache` | Er staat een `JELLYFIN_DATA_DIR`/`JELLYFIN_CACHE_DIR` in Environment Variables: verwijderen. |
| `FOUT: /config staat in het werkgeheugen (tmpfs)` | Opslagtype van `/config` is tmpfs: wijzig het in Host Path of ixVolume (jouw config-dataset). |
| `FOUT: … staat op een netwerkshare (nfs/cifs)` | `/config` is een NFS/SMB-share: kies een Host Path of ixVolume op de NAS zelf. |
| `FOUT: … staat niet op eigen opslag maar in de container zelf` | Er staat een `JELLYFIN_CONFIG_DIR` (of ander `JELLYFIN_*`-pad) in Environment Variables: verwijderen. |
| `FOUT: opdrachtregeloptie '--datadir' …` (of `--configdir`, `--cachedir`, `--logdir`, `--webdir`) | Veld Entrypoint/Command leegmaken. |
| `geen /dev/dri-apparaten: transcoderen alleen via CPU` | Geen fout. Zet GPU pas aan na meting (D08). |
| `FOUT: deze datamap is al gestart door Jelly Leon <x>, nieuwer dan deze image (<y>)` | Je zette alleen de image terug na een update. Zet de config-snapshot van vóór die update mee terug, of kies weer de nieuwere tag (zie *Updaten en terugdraaien*). Er is niets gewijzigd. |
| `FOUT: … datamap-versie is onleesbaar` | Het bestand `jelly-leon/datamap-versie` in de config-dataset is beschadigd: zet de snapshot van de config-dataset terug. |
| Poort bezet bij opslaan | Andere Host Port kiezen; Container Port blijft `8096`. |
| `FOUT: /config is niet schrijfbaar voor gebruiker 568:568 (Custom User in het formulier)` | Custom User staat aan maar de dataset is (nog) niet van 568: zet Custom User uit (de container regelt het eigenaarschap zelf) of maak de dataset eerst van 568. |
| Image kan niet worden opgehaald | Er is nog geen release, of het GHCR-pakket is (nog) privé: dan de registry-login hierboven als terugvaloptie. Tag met digest geweigerd: alleen de exacte forkversie invullen (zie *Tag met digest*). |
