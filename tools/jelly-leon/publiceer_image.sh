#!/usr/bin/env bash
# Lever de aanmelding alleen via stdin/stdout van de Docker-credentialhelper.
set -euo pipefail
: "${REGISTRY_USER:?REGISTRY_USER ontbreekt}" "${REGISTRY_TOKEN:?REGISTRY_TOKEN ontbreekt}"
config=$(mktemp -d "$RUNNER_TEMP/register.XXXXXXXX")
trap 'rm -rf -- "$config"' EXIT
export DOCKER_CONFIG="$config" PATH="$config:$PATH"
printf '%s\n' '{"credHelpers":{"git.medialeon.nl":"jelly-leon"}}' > "$config/config.json"
cat > "$config/docker-credential-jelly-leon" <<'HELPER'
#!/bin/sh
set -eu
test "$1" = get
registry=$(cat)
test "$registry" = git.medialeon.nl
python3 -c 'import json, os; print(json.dumps({"Username": os.environ["REGISTRY_USER"], "Secret": os.environ["REGISTRY_TOKEN"]}))'
HELPER
chmod 700 "$config/docker-credential-jelly-leon"
target="git.medialeon.nl/leon/jelly-leon:sha-${GITHUB_SHA:0:12}"
docker tag "$1" "$target"
trap 'docker image rm "$target" >/dev/null; rm -rf -- "$config"' EXIT
docker push "$target"
