#!/bin/sh
# Jelly Leon — start van de alles-in-één container (SCHETS P0, ADR-0008).
#
#  * Start de container als root (standaard bij een TrueNAS Custom App zonder "Custom User"), dan:
#      - /config en /cache moeten bestaan (opslag uit het formulier); alleen DIE mappen krijgen eigenaar 568:568,
#        en alleen recursief als de bovenste map nog niet van 568 is (eerste start / migratie). Mediamappen worden
#        nooit aangeraakt (die horen read-only gemount te zijn).
#      - voor elk aanwezig /dev/dri/renderD*-apparaat (optionele GPU) wordt de groep ervan als aanvullende groep
#        meegegeven, zodat QSV/VAAPI als 568 werkt zonder privileged-modus;
#      - daarna draait alles als 568:568 zonder capabilities (setpriv).
#  * Start de container al als niet-root (Custom User), dan wordt niets gewijzigd behalve de eigen pluginmap.
#  * De meegeleverde Jelly Leon-plugin wordt in <datamap>/plugins/JellyLeon_<versie> gezet; andere plugins blijven
#    onaangeroerd. Geen geheimen, geen netwerkaanroepen, geen shell voor iets anders dan deze start.
set -eu

APP_UID=568
APP_GID=568
DATA_DIR="${JELLYFIN_DATA_DIR:-/config}"
CACHE_DIR="${JELLYFIN_CACHE_DIR:-/cache}"
BUNDLED_PLUGINS=/usr/share/jelly-leon/plugins

log() { printf '%s jelly-leon: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
fail() { log "FOUT: $*"; exit 1; }

for dir in "$DATA_DIR" "$CACHE_DIR"; do
  [ -d "$dir" ] || fail "$dir bestaat niet: voeg in het Custom App-formulier opslag toe met Mount Path $dir"
done

install_plugins() {
  [ -d "$BUNDLED_PLUGINS" ] || return 0
  mkdir -p "$DATA_DIR/plugins" 2>/dev/null || { log "waarschuwing: $DATA_DIR/plugins niet schrijfbaar; plugin niet bijgewerkt"; return 0; }
  for src in "$BUNDLED_PLUGINS"/JellyLeon_*; do
    [ -d "$src" ] || continue
    name=$(basename "$src")
    # Alleen eigen pluginmappen (JellyLeon_*) van een andere versie opruimen.
    for old in "$DATA_DIR/plugins"/JellyLeon_*; do
      [ -d "$old" ] || continue
      [ "$(basename "$old")" = "$name" ] || { rm -rf "$old"; log "oude Jelly Leon-plugin $(basename "$old") verwijderd"; }
    done
    if ! cmp -s "$src/Jellyfin.Plugin.JellyLeon.dll" "$DATA_DIR/plugins/$name/Jellyfin.Plugin.JellyLeon.dll" 2>/dev/null; then
      mkdir -p "$DATA_DIR/plugins/$name"
      cp "$src/Jellyfin.Plugin.JellyLeon.dll" "$DATA_DIR/plugins/$name/"
      log "Jelly Leon-plugin $name geïnstalleerd"
    fi
  done
}

if [ "$(id -u)" != "0" ]; then
  log "start als gebruiker $(id -u):$(id -g) (geen eigenaarschap aangepast)"
  install_plugins
  exec /jellyfin/jellyfin "$@"
fi

for dir in "$DATA_DIR" "$CACHE_DIR"; do
  owner=$(stat -c '%u' "$dir")
  if [ "$owner" != "$APP_UID" ]; then
    log "$dir is van uid $owner; eigenaar wordt $APP_UID:$APP_GID (eenmalig, alleen deze map)"
    chown -R "$APP_UID:$APP_GID" "$dir"
  fi
done

install_plugins
chown -R "$APP_UID:$APP_GID" "$DATA_DIR/plugins" 2>/dev/null || true

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

exec setpriv --reuid="$APP_UID" --regid="$APP_GID" --groups="$groups" --inh-caps=-all --bounding-set=-all \
  --no-new-privs -- /jellyfin/jellyfin "$@"
