#!/usr/bin/env bash
# De proef publiceert uitsluitend SBOM's/licenties die werkelijk uit de geteste image komen.
set -euo pipefail
image=${1:?image ontbreekt}
rapportmap=${2:?rapportmap ontbreekt}
shift 2
map=/opt/jelly-leon
dockeropties=(--rm --network none --user 568:568 --read-only --cap-drop ALL --security-opt no-new-privileges)
mkdir -p "$rapportmap"
docker run "${dockeropties[@]}" --entrypoint "$map/python/bin/python3" "$image" -IB -m jl_werker.rookproef "$@"
bestanden=(werker.cdx.json)
if [[ $# == 0 ]]; then bestanden+=(image.cdx.json licenties.tsv); fi
for naam in "${bestanden[@]}"; do
    docker run "${dockeropties[@]}" --entrypoint /bin/cat "$image" "$map/$naam" > "$rapportmap/$naam"
    test -s "$rapportmap/$naam"
done
