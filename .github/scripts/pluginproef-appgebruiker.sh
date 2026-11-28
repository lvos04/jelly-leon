#!/usr/bin/env bash
# De lokale server en de waardescan delen dezelfde eigenaar van de geheimenmap.
set -euo pipefail
rapport=$1
shift
werk=$(mktemp -d "$RUNNER_TEMP/pluginproef.XXXXXXXX")
trap 'sudo -n rm -rf -- "$werk"' EXIT
sudo -n chown 568:568 "$werk"
socketgroep=$(stat -c %g /var/run/docker.sock)
uitkomst=0
sudo -n setpriv --reuid=568 --regid=568 --groups="$socketgroep" --no-new-privs \
    env HOME="$werk" TMPDIR="$werk" PYTHONDONTWRITEBYTECODE=1 PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-$HOME/.cache/ms-playwright}" \
    python3 tools/jelly-leon/e2e/plugin_proef.py "$@" --werkmap "$werk" --rapport "$werk/rapport.json" || uitkomst=$?
if sudo -n test -f "$werk/rapport.json"; then
    sudo -n install -o "$(id -u)" -g "$(id -g)" -m 0600 "$werk/rapport.json" "$rapport"
fi
exit "$uitkomst"
