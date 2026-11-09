# Jelly Leon installeren als standaard TrueNAS Custom App (SCHETS P0)

> **Status: SCHETS — NIET GEVALIDEERD (echte NAS).** Er is nog **geen** gepubliceerde image `ghcr.io/lvos04/jelly-leon`:
> forkversie `10.11.11-jl.0` wordt nooit uitgebracht (ADR-0005); de eerste release (`-jl.1`) volgt in P4. Het
> formulier hieronder is niet op een echte TrueNAS doorlopen; veldnamen volgen TrueNAS SCALE 24.10/25.04 en kunnen per
> versie iets afwijken. De installatie gebeurt normaal **door het platform** (Hub → executor → TrueNAS-API
> `app.create` met precies deze formulierwaarden); dit document beschrijft dezelfde velden voor controle en noodgevallen.

**Nooit** via *Install via YAML*, `custom_compose_config` of docker compose. Geen terminal, geen script.

## Vooraf (verplicht, zie I24/I06)

1. **De bestaande Jellyfin blijft draaien en wordt niet aangeraakt** (I24 §5). Jelly Leon krijgt een eigen poort en eigen
   datasets; de media worden alleen-lezen gedeeld.
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

## Formulier: Apps → Discover Apps → Custom App

| Sectie | Veld | Waarde |
|---|---|---|
| Application Name | | `jelly-leon` |
| Image Configuration | Repository | `ghcr.io/lvos04/jelly-leon` |
| | Tag | de vaste forkversie uit de release (vorm `<upstream>-jl.<N>`, ADR-0005; nooit `latest`; nog niet gepubliceerd) |
| | Pull Policy | *Pull the image if it is not already present on host* |
| Container Configuration | Entrypoint / Command | leeg laten |
| | Timezone | tijdzone van de NAS (uit de wizard) |
| | Environment Variables | **leeg laten** (geen geheimen in het formulier; geen `JELLYFIN_*`-paden: datamappen buiten `/config`/`/cache` worden geweigerd) |
| | Restart Policy | *Unless Stopped* |
| Security Context | Privileged | **uit** |
| | Capabilities | geen toevoegen |
| | Custom User | **uit** (de container regelt zelf 568:568) |
| Network Configuration | Host Network | **uit** |
| | Ports → Add | Container Port `8096`, Host Port `30460` (voorstel; de Hub controleert conflicten), Protocol TCP |
| Storage Configuration | Add → Host Path | Mount Path `/config` → Host Path: jouw config-dataset |
| | Add → Host Path | Mount Path `/cache` → Host Path: jouw cache-dataset |
| | Add → Host Path | Mount Path `/media` → Host Path: jouw mediadataset, **Read Only aan** |
| Resources Configuration | CPUs / Memory | voorstel 4 CPU / 4096 MiB (transcoderen deelt de NAS met MediaGuard) |
| GPU Configuration | Intel-GPU doorgeven | **standaard uit.** Pas aanzetten (*Passthrough available (non-NVIDIA) GPUs*) nadat de wizard de rendernodes van A310/UHD 770 heeft gemeten (D08). Dan geen privileged-modus: de container voegt zelf de groep van `/dev/dri/renderD*` toe. |

**Install.** De eerste start duurt kort (database aanmaken). Daarna *Running* en na de healthcheck (`/health`)
*Healthy*.

## Openen en koppelen

- Open `http://<NAS-adres>:<hostpoort>` (adres uit de wizard, D03). De Jellyfin-startwizard verschijnt (technische
  identiteit blijft Jellyfin: bestaande Jellyfin-apps herkennen de server gewoon).
- Bestaande Jellyfin-apps (web, Android, Android TV, iOS/Swiftfin, Kodi, …) verbinden met hetzelfde adres en dezelfde
  poort. Welke apps getest zijn: `docs/platform-v2/CLIENT_COMPAT_MATRIX.md` (nu alles **NIET GEVALIDEERD** op echte apparaten).
- De Hub-pagina *Versie en clientcompatibiliteit* leest `GET /media/v1/version` (Jelly Leon-plugin, met
  Jellyfin-API-sleutel).

## Updaten en terugdraaien

- **Updaten**: via de platform-UI (executor `app.update`, R2 met goedkeuring) of hier *Edit → Tag* naar de nieuwe
  forkversie. Jellyfin migreert de database bij de start; maak vooraf een snapshot van de config-dataset.
- **Terugdraaien**: oude tag **én** de config-snapshot van vóór de update samen terugzetten (database + binary, B03-013,
  I06 stap 8). Alleen de tag terugzetten is niet veilig na een databasemigratie.

## Problemen

| Melding in de app-log | Oplossing |
|---|---|
| `FOUT: /config is een anoniem Docker-volume, geen gekozen dataset` (of `/cache`) | Storage-regel ontbreekt of Mount Path is niet exact `/config` / `/cache`. Voeg de opslagregel toe en start opnieuw. |
| `FOUT: … ligt buiten /config of /cache` | Er staat een `JELLYFIN_DATA_DIR`/`JELLYFIN_CACHE_DIR` in Environment Variables: verwijderen. |
| `geen /dev/dri-apparaten: transcoderen alleen via CPU` | Geen fout. Zet GPU pas aan na meting (D08). |
| Poort bezet bij opslaan | Andere Host Port kiezen; Container Port blijft `8096`. |
| Image kan niet worden opgehaald | Er is nog geen release, of het GHCR-pakket is privé (gebruikersbesluit, ADR-0004). |
