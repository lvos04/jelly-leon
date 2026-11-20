#!/usr/bin/env bash
# Publiceer het geteste Linux-image in delen die door het Forgejo-register passen.
set -euo pipefail
: "${REGISTRY_USER:?REGISTRY_USER ontbreekt}" "${REGISTRY_TOKEN:?REGISTRY_TOKEN ontbreekt}"
config=$(mktemp -d "$RUNNER_TEMP/register.XXXXXXXX")
trap 'rm -rf -- "$config"' EXIT
export DOCKER_CONFIG="$config" REGCTL_CONFIG="$config/regctl.json" PATH="$config:$PATH"
curl --proto '=https' --fail --silent --show-error --location --retry 3 --output "$config/regctl" \
    https://github.com/regclient/regclient/releases/download/v0.11.7/regctl-linux-amd64
printf '%s  %s\n' 3737fbbdd791e04e7a831640b681f3397a376498e80e2ad9b1b2d27296f239bc "$config/regctl" | sha256sum --check --status
chmod 700 "$config/regctl"
cat > "$config/docker-credential-jelly-leon" <<'HELPER'
#!/bin/sh
set -eu
test "$1" = get
case "$(cat)" in git.medialeon.nl|https://git.medialeon.nl|https://git.medialeon.nl/) ;; *) exit 1 ;; esac
python3 -c 'import json, os; print(json.dumps({"Username": os.environ["REGISTRY_USER"], "Secret": os.environ["REGISTRY_TOKEN"]}))'
HELPER
chmod 700 "$config/docker-credential-jelly-leon"
target="git.medialeon.nl/leon/jelly-leon:sha-${GITHUB_SHA:0:12}"
regctl registry set git.medialeon.nl --cred-helper docker-credential-jelly-leon \
    --blob-max 8388608 --blob-chunk 8388608 --req-concurrent 2
archief="$config/getest.tar"
docker image save --platform linux/amd64 -o "$archief" "$1"
getest=$(python3 - "$archief" <<'PY'
import hashlib
import json
import sys
import tarfile

with tarfile.open(sys.argv[1]) as archief:
    [image] = json.load(archief.extractfile("manifest.json"))
    print("sha256:" + hashlib.sha256(archief.extractfile(image["Config"]).read()).hexdigest())
PY
)
regctl image import "$target" "$archief"
digest=$(regctl image digest "$target")
gepubliceerd=$(regctl manifest get --platform linux/amd64 --format raw-body "${target%:*}@$digest" \
    | python3 -c 'import json, sys; print(json.load(sys.stdin)["config"]["digest"])')
if [[ $gepubliceerd != "$getest" ]]; then
    echo "De gepubliceerde imageconfiguratie $gepubliceerd wijkt af van de geteste $getest." >&2
    exit 1
fi
printf 'Gepubliceerd en teruggelezen: %s %s (imageconfiguratie %s)\n' "$target" "$digest" "$getest"
