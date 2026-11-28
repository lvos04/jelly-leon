#!/usr/bin/env bash
# Dezelfde checkout, webbron, daemon en bouwargumenten voor beide metingen.
set -euo pipefail
image=${1:?image ontbreekt}
rapport=${2:?rapport ontbreekt}
shift 2
basis="jelly-leon:groeimeting-$(cat /proc/sys/kernel/random/uuid)"
trap 'docker image rm "$basis" >/dev/null 2>&1 || true' EXIT
docker buildx build -f deploy/allinone/Dockerfile "$@" --target serverbasis --load -t "$basis" .
docker buildx build -f deploy/allinone/Dockerfile "$@" --load -t "$image" .
python3 tools/analysewerker/meet_groei.py "$(docker image inspect "$basis" --format '{{.Size}}')" \
    "$(docker image inspect "$image" --format '{{.Size}}')" | tee "$rapport"
