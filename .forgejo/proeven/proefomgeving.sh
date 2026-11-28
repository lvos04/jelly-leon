#!/usr/bin/env bash
# De proef en de testservers draaien bij dezelfde geïsoleerde buildengine. Alleen de
# aansturende proefcontainer krijgt de engine-socket. De checkout gaat via docker cp.
set -euo pipefail
staat="$RUNNER_TEMP/jl-harnas"
# Deze map behoort op de geïsoleerde engine alleen aan de opslagproeven van deze repo.
opslag=/var/lib/jelly-leon-proeven
case "$1" in
    start)
        mkdir "$staat"
        docker buildx build --load --iidfile "$staat/image" --target "$2" -f .forgejo/proeven/Dockerfile .
        volume="jl-proef-$(cat /proc/sys/kernel/random/uuid)"
        if [[ $2 == basis || ${3:-} == dataset ]]; then
            # De standaardvolumes kunnen tmpfs en noexec zijn. Zowel de database als
            # de gepubliceerde server en healthcheck krijgen een eigen uitvoerbare dataset.
            echo "$volume" > "$staat/dataset"
            docker run --rm --network none --read-only -v "$opslag:/opslag" "$(cat "$staat/image")" \
                sh -ec 'mkdir -- "/opslag/$1"; stat -f -c "Bestandssysteem voor de serverproeven: %T" "/opslag/$1"' sh "$volume"
            docker volume create --opt type=none --opt o=bind --opt "device=$opslag/$volume" "$volume" > "$staat/volume"
        else
            docker volume create "$volume" > "$staat/volume"
        fi
        pad=$(docker volume inspect --format '{{.Mountpoint}}' "$volume")
        printf '%s\n' "$pad" > "$staat/pad"
        docker run -d --init --cidfile "$staat/container" --network host --cpus 2 --shm-size 512m \
            --mount "type=volume,source=$volume,target=$pad" \
            --mount type=bind,source=/var/run/docker.sock,target=/var/run/docker.sock \
            --workdir "$pad/bron" -e "JL_PROEFVOLUME=$volume" -e "JL_PROEFMAP=$pad/werk" -e "RUNNER_TEMP=$pad/rapporten" \
            -e "B03_LOCK_DIR=$pad/werk/sloten" -e "B03_WERK=$pad/werk/b03-werk" -e "B03_CORPUS=$pad/werk/b03-corpus" \
            -e "B03_UITVOER=$pad/werk/b03-testsets" -e PYTHONPATH=tools/b03-harnas \
            -e DOTNET_PROCESSOR_COUNT -e JL_RUNTIME_IMAGE -e JL_CI_IMAGE -e STOCK_IMAGE "$(cat "$staat/image")" sleep infinity
        harnas=$(cat "$staat/container")
        docker exec "$harnas" install -d -o 568 -g 568 "$pad/werk" "$pad/rapporten" \
            "$pad/werk/"{sloten,b03-werk,b03-corpus,b03-testsets}
        docker exec "$harnas" stat -c %g /var/run/docker.sock > "$staat/socketgroep"
        git archive HEAD tools docs/openapi deploy/allinone/healthcheck.sh | docker cp - "$harnas:$pad/bron"
        if [[ $2 == browser || $2 == chromium ]]; then
            docker exec "$harnas" ln -s /opt/playwright/node_modules "$pad/bron/tools/b03-harnas/playwright/node_modules"
        fi
        echo 'JL_HARNAS_ACTIEF=1' >> "$GITHUB_ENV"
        ;;
    voorraad)
        harnas=$(cat "$staat/container")
        werk=$(cat "$staat/pad")/werk
        docker exec "$harnas" mkdir -p "$werk/server" "$werk/plugin"
        docker cp "$RUNNER_TEMP/stockbouw/server/." "$harnas:$werk/server"
        docker cp "$RUNNER_TEMP/stockbouw/plugin/." "$harnas:$werk/plugin"
        docker exec "$harnas" chmod 0755 "$werk/server" "$werk/server/jellyfin"
        ;;
    voer)
        # De proefgebruiker maakt normale datasets met 0755 aan. Negatieve fixtures zetten
        # hun afwijkende rechten zelf. Docker exec kan een umask van 000 doorgeven.
        docker exec -i -e WEB_REF -e NIEUWE_RUNTIME "$(cat "$staat/container")" \
            setpriv --reuid=568 --regid=568 --groups="$(cat "$staat/socketgroep")" --no-new-privs \
            bash -c 'umask 022; exec bash -e -o pipefail -s' < "$2"
        ;;
    rapporten)
        mkdir -p "$RUNNER_TEMP/proefrapporten"
        docker cp "$(cat "$staat/container"):$(cat "$staat/pad")/rapporten/." "$RUNNER_TEMP/proefrapporten/"
        ;;
    ruim)
        if [[ -s $staat/container ]]; then docker rm -fv "$(cat "$staat/container")" >/dev/null; fi
        if [[ -s $staat/volume ]]; then
            volume=$(cat "$staat/volume")
            eigen=$(docker ps -aq --filter "label=nl.medialeon.jelly-leon.proef=$volume")
            if [[ -n $eigen ]]; then
                while read -r container; do docker rm -fv "$container" >/dev/null; done <<< "$eigen"
            fi
            docker volume rm "$volume"
        fi
        if [[ -s $staat/dataset ]]; then
            dataset=$(cat "$staat/dataset")
            [[ $dataset =~ ^jl-proef-[0-9a-f-]{36}$ ]]
            docker run --rm --network none --read-only -v "$opslag:/opslag" "$(cat "$staat/image")" \
                rm -rf -- "/opslag/$dataset"
        fi
        ;;
    *) echo "Onbekende proefopdracht: $1" >&2; exit 2 ;;
esac
