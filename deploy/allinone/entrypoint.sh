#!/bin/sh
# Jelly Leon — start van de alles-in-één container (SCHETS P0, ADR-0008).
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
#  * Start de container al als niet-root (Custom User), dan wordt niets gewijzigd behalve de eigen pluginmap.
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

for dir in "$DATA_DIR" "$CACHE_DIR"; do
  [ -d "$dir" ] || fail "$dir bestaat niet: voeg in het Custom App-formulier opslag toe met Mount Path $dir"
done

# De upstream-basisimage declareert VOLUME /config en /cache: zonder opslagregel in het formulier maakt Docker
# stilletjes een anoniem volume (/…/volumes/<64 hex>/_data) en staat de database NIET op de gekozen dataset
# (verdwijnt bij verwijderen/herinstalleren). Onduidelijke datamap = no-go (fasering P0) → weigeren.
is_anonymous_volume() {
  mp=$(readlink -f -- "$1") || return 1
  awk -v mp="$mp" '$5 == mp { print $4 }' /proc/self/mountinfo | grep -Eq '/volumes/[0-9a-f]{64}/_data$'
}
for dir in "$DATA_DIR" "$CACHE_DIR"; do
  if is_anonymous_volume "$dir"; then
    fail "$dir is een anoniem Docker-volume, geen gekozen dataset: voeg in het Custom App-formulier opslag (Host Path of ixVolume) toe met Mount Path $dir"
  fi
done

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
  # JELLY_LEON_ENTRYPOINT_STAGE markeert de tweede fase na setpriv (geen geheim; alleen voor de logregel).
  if [ "${JELLY_LEON_ENTRYPOINT_STAGE:-}" = "app" ]; then
    log "draait als $(id -u):$(id -g) (groepen $(id -G | tr ' ' ',')), zonder capabilities"
  else
    log "start als gebruiker $(id -u):$(id -g) (geen eigenaarschap aangepast)"
  fi
  unset JELLY_LEON_ENTRYPOINT_STAGE
  install_plugins
  exec /jellyfin/jellyfin "$@"
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
