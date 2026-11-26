#!/usr/bin/env bash
# Een fout bij aanmelden, een onbekend antwoord of een bestaande tag stopt de publicatie.
set -euo pipefail
repository=lvos04/jelly-leon
bearer=$(curl -fsS --user "$GITHUB_ACTOR:$GH_TOKEN" --get --data-urlencode 'service=ghcr.io' \
    --data-urlencode "scope=repository:$repository:pull,push" https://ghcr.io/token |
    jq -er '.token | strings | select(length > 0)')
antwoord=$(mktemp "${RUNNER_TEMP:?}/imagetag.XXXXXXXX")
trap 'rm -f -- "$antwoord"' EXIT
status=$(curl -sS -o "$antwoord" -w '%{http_code}' -H "Authorization: Bearer $bearer" \
    -H 'Accept: application/vnd.oci.image.index.v1+json, application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.list.v2+json, application/vnd.docker.distribution.manifest.v2+json' \
    "https://ghcr.io/v2/$repository/manifests/${1:?versie ontbreekt}")
if [[ $status != 404 ]] || ! jq -e '
    (.errors | type == "array" and length > 0) and
    all(.errors[]; .code == "MANIFEST_UNKNOWN" or .code == "NAME_UNKNOWN")
' "$antwoord" >/dev/null; then
    echo "GHCR bevestigt geen vrije imagetag (HTTP $status). Publicatie gestopt." >&2
    exit 1
fi
echo 'GHCR bevestigt dat de versietag vrij is.'
