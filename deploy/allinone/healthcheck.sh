#!/bin/sh
# Jelly Leon — Docker-healthcheck van de alles-in-één image (contract 1.2 §2.2: na de eigenaarschapsstap draait geen
# proces meer als root).
#
# Docker start de healthcheck als de containergebruiker: bij een Custom App zonder "Custom User" is dat root, mét de
# standaard-capabilities en zonder no_new_privs (het formulier zet die niet). Daarom wisselt dit script vóór de
# HTTP-aanvraag naar 568:568 zonder capabilities en met no_new_privs; curl (dat het antwoord van de server leest)
# draait dus nooit als root. Draait de container al als niet-root (Custom User), dan alleen no_new_privs.
# Geen geheimen, geen netwerkaanroep buiten de container, geen andere opdrachten.
#
#   jelly-leon-healthcheck                → GET http://localhost:8096/health (exitcode 0 = gezond)
#   jelly-leon-healthcheck --toon-rechten → toont /proc/self/status met precies dezelfde rechtenwissel als curl
#                                           (alleen voor de rooktest, tools/jelly-leon/e2e/image_lifecycle.py)
set -eu

APP_UID=568
APP_GID=568

drop_and_exec() {
  if [ "$(id -u)" = "0" ]; then
    exec setpriv --reuid="$APP_UID" --regid="$APP_GID" --clear-groups --inh-caps=-all --bounding-set=-all \
      --no-new-privs -- "$@"
  fi
  exec setpriv --no-new-privs --inh-caps=-all -- "$@"
}

case "${1:-}" in
  "")
    drop_and_exec curl --noproxy localhost -fsS --max-time 8 -o /dev/null http://localhost:8096/health ;;
  --toon-rechten)
    drop_and_exec cat /proc/self/status ;;
  *)
    printf 'jelly-leon-healthcheck: onbekende optie %s\n' "$1" >&2
    exit 2 ;;
esac
