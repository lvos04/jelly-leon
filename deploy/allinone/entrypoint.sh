#!/bin/sh
# Jelly Leon — start van de alles-in-één container (ADR-0008; contract 1.2 §2.2).
#
#  * Start de container als root (standaard bij een TrueNAS Custom App zonder "Custom User"), dan:
#      - /config en /cache moeten bestaan (opslag uit het formulier); alleen DIE mappen krijgen eigenaar 568:568,
#        en alleen recursief als de bovenste map nog niet van 568 is (eerste start / migratie). Mediamappen worden
#        nooit aangeraakt (die horen read-only gemount te zijn).
#      - een datamap via JELLYFIN_DATA_DIR/JELLYFIN_CACHE_DIR buiten /config of /cache (of een symlink daarheen)
#        wordt als root geweigerd: nooit `chown -R` op systeem- of mediamappen (fail-closed).
#      - voor elk aanwezig /dev/dri/renderD*-apparaat (optionele GPU) wordt de groep ervan als aanvullende groep
#        meegegeven, zodat QSV/VAAPI als 568 werkt zonder privileged-modus;
#      - daarna draait alles als 568:568 zonder capabilities (setpriv): dit script start zichzelf opnieuw als 568 en
#        werkt pas dán de eigen pluginmap bij (geen schrijfacties als root in de datamap behalve chown).
#  * Altijd (ook als niet-root): datamap en instellingenmap moeten op blijvende, lokale opslag uit het formulier
#    staan — geen anoniem Docker-volume, geen tmpfs, niet in de container zelf, geen NFS/SMB-share — en padopties
#    (--datadir, --configdir, …) in het veld Command worden geweigerd. Anders zou de database bij een herstart of
#    update verdwijnen en de startwizard weer anoniem openstaan (fail-closed, review P0-afronding).
#  * Start de container al als niet-root (Custom User), dan wordt niets gewijzigd behalve de eigen pluginmap; zijn
#    /config of /cache niet schrijfbaar, dan een NL-fout; daarna no_new_privs (setpriv) vóór de server start.
#  * De meegeleverde Jelly Leon-plugin wordt in <datamap>/plugins/JellyLeon_<versie> gezet; andere plugins blijven
#    onaangeroerd. Geen geheimen, geen netwerkaanroepen, geen shell voor iets anders dan deze start.
set -eu

APP_UID=568
APP_GID=568
DATA_DIR="${JELLYFIN_DATA_DIR:-/config}"
CACHE_DIR="${JELLYFIN_CACHE_DIR:-/cache}"
BUNDLED_PLUGINS=/usr/share/jelly-leon/plugins
SELF=$(readlink -f -- "$0")

log() { printf '%s jelly-leon: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
fail() { log "FOUT: $*"; exit 1; }

# Map met instellingen (o.a. system.xml: "startwizard afgerond") — zelfde standaard als upstream (StartupHelpers).
CONFIG_DIR="${JELLYFIN_CONFIG_DIR:-$DATA_DIR/config}"

# Padopties op de opdrachtregel (veld Entrypoint/Command in het formulier) zouden de controles hieronder omzeilen.
for arg in "$@"; do
  case "$arg" in
    -d | -d* | --datadir | --datadir=* | -c | -c* | --configdir | --configdir=* | -C | -C* | --cachedir | --cachedir=* | \
    -l | -l* | --logdir | --logdir=* | -w | -w* | --webdir | --webdir=*)
      fail "opdrachtregeloptie '$arg' verplaatst een datamap of de web-client; laat Entrypoint/Command in het Custom App-formulier leeg" ;;
  esac
done

for dir in "$DATA_DIR" "$CACHE_DIR"; do
  [ -d "$dir" ] || fail "$dir bestaat niet: voeg in het Custom App-formulier opslag toe met Mount Path $dir"
done

# Mount waarop een pad ligt (langste mountpoint-voorvoegsel in /proc/self/mountinfo; bij gestapelde mounts de
# bovenste): "<bestandssysteemtype> <root binnen de bron> <mountpoint>".
mount_of() {
  target=$(readlink -f -- "$1") || return 1
  awk -v p="$target" '
    {
      fs = ""
      for (i = 7; i <= NF; i++) if ($i == "-") { fs = $(i + 1); break }
      m = $5
      if (m == p || m == "/" || index(p, m "/") == 1) {
        if (length(m) >= best) { best = length(m); out = fs " " $4 " " m }
      }
    }
    END { if (out != "") print out }' /proc/self/mountinfo
}

# Datamap en instellingen moeten op blijvende, lokale opslag uit het formulier staan; anders verdwijnen database en
# "startwizard afgerond" (bij herstart, update of herinstallatie) en staat de startwizard weer anoniem open
# — de eerste bezoeker wordt dan beheerder. Onduidelijke datamap = no-go (fasering P0) → weigeren (fail-closed).
#  * anoniem Docker-volume (/…/volumes/<64 hex>/_data): de upstream-basisimage declareert VOLUME /config en /cache,
#    dus zonder opslagregel maakt Docker er stilletjes één (verdwijnt bij verwijderen/herinstalleren);
#  * tmpfs/ramfs (opslagtype tmpfs in het formulier): leeg na elke herstart;
#  * de container zelf (geen eigen mount): weg bij elke update of herinstallatie;
#  * netwerkshare (opslagtype NFS/SMB): de SQLite-database van Jellyfin is daar niet betrouwbaar (vergrendeling).
# Voor /cache (opnieuw op te bouwen) geldt alleen de controle op een anoniem volume.
assert_persistent() {
  info=$(mount_of "$1") || fail "$1 kan niet worden opgelost; laat JELLYFIN_*-variabelen leeg in het formulier"
  [ -n "$info" ] || fail "$1: geen mount gevonden in /proc/self/mountinfo"
  fstype=${info%% *}
  rest=${info#* }
  root=${rest%% *}
  mnt=${rest#* }
  if printf '%s\n' "$root" | grep -Eq '/volumes/[0-9a-f]{64}/_data$'; then
    fail "$mnt is een anoniem Docker-volume, geen gekozen dataset: voeg in het Custom App-formulier opslag (Host Path of ixVolume) toe met Mount Path $mnt"
  fi
  [ "$2" = "cache" ] && return 0
  if [ "$mnt" = "/" ]; then
    fail "$1 staat niet op eigen opslag maar in de container zelf (weg bij elke update): laat JELLYFIN_*-variabelen leeg en gebruik de opslagregel met Mount Path /config"
  fi
  case "$fstype" in
    tmpfs | ramfs)
      fail "$1 staat in het werkgeheugen ($fstype): database en instellingen verdwijnen bij elke herstart en de startwizard staat dan weer open. Kies voor Mount Path $mnt het opslagtype Host Path of ixVolume" ;;
    nfs | nfs4 | cifs | smb3 | smbfs)
      fail "$1 staat op een netwerkshare ($fstype): de SQLite-database van Jellyfin is daar niet betrouwbaar. Kies voor Mount Path $mnt een Host Path of ixVolume op de NAS zelf" ;;
  esac
}
assert_persistent "$DATA_DIR" data
assert_persistent "$CONFIG_DIR" data
assert_persistent "$CACHE_DIR" cache

# Alleen /config, /cache en mappen daaronder mogen als root van eigenaar wisselen (na het oplossen van symlinks).
assert_owned_mount() {
  resolved=$(readlink -f -- "$1") || fail "$1 kan niet worden opgelost"
  case "$resolved" in
    /config | /config/* | /cache | /cache/*) ;;
    *) fail "$1 (werkelijk pad $resolved) ligt buiten /config of /cache; als root wordt hier niets aangepast. Laat JELLYFIN_DATA_DIR/JELLYFIN_CACHE_DIR leeg in het formulier." ;;
  esac
}

install_plugins() {
  [ -d "$BUNDLED_PLUGINS" ] || return 0
  if ! mkdir -p "$DATA_DIR/plugins" 2>/dev/null; then
    log "waarschuwing: $DATA_DIR/plugins niet schrijfbaar; Jelly Leon-plugin niet bijgewerkt"
    return 0
  fi
  for src in "$BUNDLED_PLUGINS"/JellyLeon_*; do
    [ -d "$src" ] || continue
    name=$(basename "$src")
    # Alleen eigen pluginmappen (JellyLeon_*) van een andere versie opruimen.
    for old in "$DATA_DIR/plugins"/JellyLeon_*; do
      [ -d "$old" ] || continue
      [ "$(basename "$old")" = "$name" ] && continue
      if rm -rf -- "$old"; then
        log "oude Jelly Leon-plugin $(basename "$old") verwijderd"
      else
        log "waarschuwing: oude Jelly Leon-plugin $(basename "$old") kon niet worden verwijderd"
      fi
    done
    if ! cmp -s "$src/Jellyfin.Plugin.JellyLeon.dll" "$DATA_DIR/plugins/$name/Jellyfin.Plugin.JellyLeon.dll" 2>/dev/null; then
      if mkdir -p "$DATA_DIR/plugins/$name" && cp "$src/Jellyfin.Plugin.JellyLeon.dll" "$DATA_DIR/plugins/$name/"; then
        log "Jelly Leon-plugin $name geïnstalleerd"
      else
        log "waarschuwing: Jelly Leon-plugin $name kon niet worden geïnstalleerd (zie GET /media/v1/version)"
      fi
    fi
  done
}

if [ "$(id -u)" != "0" ]; then
  # JELLY_LEON_ENTRYPOINT_STAGE markeert de tweede fase na setpriv (geen geheim). Alleen geloofwaardig als
  # no_new_privs echt aan staat: een in het formulier gezette variabele kan de stap hieronder niet overslaan.
  nnp=$(awk '/^NoNewPrivs:/ { print $2 }' /proc/self/status)
  if [ "${JELLY_LEON_ENTRYPOINT_STAGE:-}" = "app" ] && [ "$nnp" = "1" ]; then
    log "draait als $(id -u):$(id -g) (groepen $(id -G | tr ' ' ',')), zonder capabilities, no_new_privs"
    unset JELLY_LEON_ENTRYPOINT_STAGE
    install_plugins
    exec /jellyfin/jellyfin "$@"
  fi
  # Custom User in het formulier: geen eigenaarschapsstap, dus de opslag moet al van deze gebruiker zijn. Niet
  # schrijfbaar → NL-melding en stoppen (healthcheck rood), nooit stil doorstarten (contract 1.2 §2.2).
  for dir in "$DATA_DIR" "$CACHE_DIR"; do
    if [ ! -w "$dir" ] || [ ! -x "$dir" ]; then
      fail "$dir is niet schrijfbaar voor gebruiker $(id -u):$(id -g) (Custom User in het formulier): zet Custom User uit (de container maakt dan zelf 568:568 eigenaar van /config en /cache) of maak de dataset eerst van deze gebruiker"
    fi
  done
  log "start als gebruiker $(id -u):$(id -g) (Custom User; geen eigenaarschap aangepast)"
  # Het formulier zet geen no-new-privileges (contract 1.2 §2.2): zelf zetten vóór de eerste execve van de server.
  # (Zonder CAP_SETPCAP kan een niet-root-proces de bounding-set niet legen; met no_new_privs en CapEff 0 kan het
  # ook via setuid-bestanden geen rechten meer krijgen.)
  export JELLY_LEON_ENTRYPOINT_STAGE=app
  exec setpriv --no-new-privs --inh-caps=-all -- "$SELF" "$@"
fi

for dir in "$DATA_DIR" "$CACHE_DIR"; do
  assert_owned_mount "$dir"
done

for dir in "$DATA_DIR" "$CACHE_DIR"; do
  owner=$(stat -c '%u' "$dir")
  if [ "$owner" != "$APP_UID" ]; then
    log "$dir is van uid $owner; eigenaar wordt $APP_UID:$APP_GID (eenmalig, alleen deze map)"
    chown -R "$APP_UID:$APP_GID" "$dir"
  fi
done

groups="$APP_GID"
for node in /dev/dri/renderD* /dev/dri/card*; do
  [ -e "$node" ] || continue
  gid=$(stat -c '%g' "$node")
  if [ "$gid" = "0" ]; then
    log "waarschuwing: $node hoort bij groep 0 (root); die groep wordt niet toegevoegd — GPU mogelijk niet bruikbaar"
    continue
  fi
  case ",$groups," in
    *",$gid,"*) ;;
    *) groups="$groups,$gid" ;;
  esac
done
if [ "$groups" != "$APP_GID" ]; then
  log "GPU-apparaten gevonden; aanvullende groepen: $groups"
else
  log "geen /dev/dri-apparaten: transcoderen alleen via CPU (hardwareversnelling uit)"
fi

# Tweede fase: hetzelfde script als 568 zonder capabilities; dat werkt de pluginmap bij en start Jellyfin.
export JELLY_LEON_ENTRYPOINT_STAGE=app
exec setpriv --reuid="$APP_UID" --regid="$APP_GID" --groups="$groups" --inh-caps=-all --bounding-set=-all \
  --no-new-privs -- "$SELF" "$@"
