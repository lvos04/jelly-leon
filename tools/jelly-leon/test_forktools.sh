#!/usr/bin/env bash
# De healthchecktests meten de rechtenwisseling van een gewone gebruiker.
set -euo pipefail
if [[ $(id -u) != 0 ]]; then
    exec python -m pytest -q tools/jelly-leon/tests
fi
werk=$(mktemp -d "$RUNNER_TEMP/forktests.XXXXXXXX")
trap 'rm -rf -- "$werk"' EXIT
chown 1000:1000 "$werk"
TMPDIR="$werk" PYTHONDONTWRITEBYTECODE=1 setpriv --reuid 1000 --regid 1000 --clear-groups \
    python -m pytest -q -o "cache_dir=$werk/cache" tools/jelly-leon/tests
