# syntax=docker/dockerfile:1.7
# Jelly Leon — alles-in-één image ghcr.io/lvos04/jelly-leon (ADR-0008). Lokaal en in GitHub-CI (job `image`) volledig
# gebouwd en getest, incl. de echte web-build van jelly-leon-web op baseline.json `web_fork_commit` (ADR-0013);
# jelly-leon-release.yml publiceert deze build op de vaste forkversie uit VERSION.
#
# Inhoud: Jellyfin-server uit deze fork (self-contained) + web-client uit lvos04/jelly-leon-web + de Jelly Leon-plugin,
# op de officiële upstream-runtime (jellyfin/jellyfin, met jellyfin-ffmpeg en de Intel QSV/VAAPI-stack) — die runtime
# bouwen we bewust niet zelf na (geen dubbel werk, INVENTARIS.md §6). Database: de ingebouwde SQLite van Jellyfin
# (geen PostgreSQL; ADR-0008). Installatie uitsluitend als standaard TrueNAS Custom App (deploy/truenas/CUSTOM_APP.md).
#
# Bouwen (vanaf de repo-root; de web-client komt als aparte build-context: een schone export via `git archive` van
# lvos04/jelly-leon-web op `web_fork_commit` uit tools/jelly-leon/baseline.json, zodat er geen lokale node_modules of
# bouwresten meegaan; tools/jelly-leon/web_bron.py --controleer controleert die checkout):
#   docker buildx build -f deploy/allinone/Dockerfile \
#     --build-context jelly-leon-web=<map-met-export-van-jelly-leon-web> \
#     --build-arg FORK_VERSION=<forkversie> --build-arg VCS_REF=<commit> --build-arg WEB_REF=<commit-jelly-leon-web> \
#     [--secret id=ca_bundle,src=<ca-bestand>] -t ghcr.io/lvos04/jelly-leon:<forkversie> .
# Het optionele geheim ca_bundle is alleen voor bouwomgevingen achter een TLS-proxy; het komt niet in de image.

ARG SDK_IMAGE=mcr.microsoft.com/dotnet/sdk:10.0.403@sha256:212fe4cb74627d5adf9817a4088906ae3edff1bd853bb27565d4b46731efe61e
ARG NODE_IMAGE=docker.io/library/node:24.22.2-bookworm-slim@sha256:01d566e8d94d8c619591d78652babfccd3c6992a3dffa9ed5ab39e11cf6c70e9
ARG RUNTIME_IMAGE=docker.io/jellyfin/jellyfin:12.4@sha256:fea863d0cd9ec445985d9c75fc6ed64e38a1d2766cf0c250a33d553f4fc1b771

ARG PYTHON_IMAGE=docker.io/library/python:3.12.16-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df
ARG SYFT_IMAGE=docker.io/anchore/syft:v1.57.2@sha256:e97e20b6e6d1699c60296b66ab337941724f9bd06ac279d893eda89601fc4b2a

# Eén eigen CPython voor de analysewerker en de overname-assistent (ADR-0017, ADR-0036).
FROM ${PYTHON_IMAGE} AS analysepython
COPY tools/analysewerker/bouw.lock tools/analysewerker/requirements.lock /bouw/
RUN --mount=type=secret,id=ca_bundle,required=false \
    set -eu; p=/opt/jelly-leon/python; mkdir -p "$p/bin" "$p/lib"; \
    cp /usr/local/bin/python3.12 "$p/bin/"; ln -s python3.12 "$p/bin/python3"; ln -s python3 "$p/bin/python"; \
    cp -a /usr/local/lib/libpython3.12.so* /usr/local/lib/python3.12 "$p/lib/"; \
    test "$("$p/bin/python3" -I -c 'import sys; print(sys.prefix)')" = "$p"; \
    if [ -s /run/secrets/ca_bundle ]; then export PIP_CERT=/run/secrets/ca_bundle; fi; \
    "$p/bin/python3" -m pip install --no-cache-dir --no-deps --require-hashes --only-binary=:all: -r /bouw/bouw.lock; \
    "$p/bin/python3" -m pip install --no-cache-dir --no-compile --ignore-installed --no-build-isolation \
        --no-deps --require-hashes --only-binary=:all: --no-binary=srt -r /bouw/requirements.lock; \
    "$p/bin/python3" -m pip uninstall -y setuptools pip; \
    rm -rf "$p/lib/python3.12/ensurepip/_bundled"; \
    find "$p" -name __pycache__ -type d -prune -exec rm -rf {} +
COPY tools/analysewerker/jl_werker/ /opt/jelly-leon/python/lib/python3.12/site-packages/jl_werker/
COPY tools/analysewerker/requirements.lock tools/analysewerker/licenties.json /opt/jelly-leon/

# Zelfde bovenlaag op de vaste of de kandidaat-upstream-runtime. Los bouwbaar voor upstream-sync.
FROM ${RUNTIME_IMAGE} AS werkerproef
COPY --from=analysepython /opt/jelly-leon /opt/jelly-leon
RUN --network=none set -eu; chmod -R a+rX,go-w /opt/jelly-leon; umask 022; \
    /opt/jelly-leon/python/bin/python3 -IB -m jl_werker.inventaris werker

# ---------------------------------------------------------------- server + plugin (.NET)
FROM ${SDK_IMAGE} AS server
# Beperkt MSBuild-parallelisme (gedeelde/kleine bouwomgevingen); in CI desgewenst hoger zetten.
ARG BUILD_JOBS=2
ENV DOTNET_CLI_TELEMETRY_OPTOUT=1 DOTNET_NOLOGO=1
WORKDIR /src
COPY . .
RUN --mount=type=secret,id=ca_bundle,required=false \
    --mount=type=cache,target=/root/.nuget/packages \
    set -eu; \
    if [ -s /run/secrets/ca_bundle ]; then \
      cp /run/secrets/ca_bundle /usr/local/share/ca-certificates/build-proxy-ca.crt && update-ca-certificates >/dev/null; \
    fi; \
    dotnet publish Jellyfin.Server/Jellyfin.Server.csproj -c Release --runtime linux-x64 --self-contained \
      -m:"${BUILD_JOBS}" -p:DebugSymbols=false -p:DebugType=none -o /out/server; \
    dotnet build plugins/JellyLeon/src/Jellyfin.Plugin.JellyLeon/Jellyfin.Plugin.JellyLeon.csproj -c Release \
      -m:"${BUILD_JOBS}" -o /out/plugin; \
    test -x /out/server/jellyfin; test -f /out/plugin/Jellyfin.Plugin.JellyLeon.dll

# ---------------------------------------------------------------- web-client (lvos04/jelly-leon-web)
# jellyfin-web 12.x vraagt Node >= 24 en npm >= 11 (engine-strict); de image staat in jelly-leon-web baseline.json
# toolchain.node_image. Hun .npmrc (o.a. ignore-scripts, engine-strict, min-release-age) gaat mee vóór `npm ci`.
FROM ${NODE_IMAGE} AS web
# Begrenzing van het aantal webpack/terser-werkers (geheugen); 0 = standaard van de bouwtools.
ARG WEB_BUILD_JOBS=4
WORKDIR /web
COPY --from=jelly-leon-web package.json package-lock.json .npmrc ./
RUN --mount=type=secret,id=ca_bundle,required=false \
    --mount=type=cache,target=/root/.npm \
    if [ -s /run/secrets/ca_bundle ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/ca_bundle; fi; \
    npm ci --no-audit --no-fund
COPY --from=jelly-leon-web . .
RUN set -eu; \
    if [ "${WEB_BUILD_JOBS}" != "0" ]; then \
      last=$((WEB_BUILD_JOBS - 1)); taskset -c "0-${last}" npm run build:production; \
    else \
      npm run build:production; \
    fi; \
    test -f dist/index.html; grep -q '<title>Jelly Leon</title>' dist/index.html
# config.json van de webclient: één generator (B03-017, ADR-0019) maakt hem uit de upstream-items plus de eigen webplugins
# van Jelly Leon en controleert daarna dat geen upstream-plugin ontbreekt. Zonder eigen plugins blijft hij byte-gelijk.
COPY deploy/allinone/web-config.mjs deploy/allinone/web-config.jellyleon.json /gen/
RUN set -eu; \
    node /gen/web-config.mjs --upstream src/config.json --eigen /gen/web-config.jellyleon.json \
      --plugins-map src/plugins --uit dist/config.json; \
    node /gen/web-config.mjs --upstream src/config.json --eigen /gen/web-config.jellyleon.json \
      --plugins-map src/plugins --uit dist/config.json --controleer

# ---------------------------------------------------------------- runtime
FROM ${RUNTIME_IMAGE} AS serverbasis
ARG FORK_VERSION=0.0.0-jl.0
ARG VCS_REF=unknown
# Commit van lvos04/jelly-leon-web waaruit de web-client is gebouwd (GPL "bron beschikbaar", ADR-0004).
ARG WEB_REF=unknown
LABEL org.opencontainers.image.title="Jelly Leon" \
      org.opencontainers.image.description="Jelly Leon — mediaserver gebaseerd op Jellyfin (technische identiteit: Jellyfin)" \
      org.opencontainers.image.source="https://git.medialeon.nl/leon/jelly-leon" \
      org.opencontainers.image.url="https://git.medialeon.nl/leon/jelly-leon" \
      org.opencontainers.image.documentation="https://git.medialeon.nl/leon/jelly-leon/src/branch/ccr-c133d7a0-kuz1cv/deploy/truenas/CUSTOM_APP.md" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.version="${FORK_VERSION}" \
      org.opencontainers.image.licenses="GPL-2.0-only AND GPL-2.0-or-later" \
      org.opencontainers.image.base.name="docker.io/jellyfin/jellyfin:12.4" \
      io.github.lvos04.jelly-leon.web.source="https://git.medialeon.nl/leon/jelly-leon-web" \
      io.github.lvos04.jelly-leon.web.revision="${WEB_REF}"
# url/documentation overschrijven die van de basisimage (jellyfin.org): geen schijn van een officiële release (ADR-0004).
# /config en /cache zijn in de basisimage 0777; een tmpfs of nieuw Docker-volume neemt die modus over (de eigenaar niet).
# /config 0755: de start weigert een voor groep of anderen beschrijfbare opslagmap (ADR-0032, "Opslagdreigingen, deel 1c").
# /cache 1777: een tmpfs-/cache (opslagtype tmpfs) is zo ook voor een Custom User schrijfbaar; de start aanvaardt die modus
# alleen bij een tmpfs met /cache als eigen koppelpunt die bij de start leeg is, niet bij een dataset of hostpad, en wijzigt
# een tmpfs nooit (ADR-0032, deel 1f en 1g; een lege gedeelde tmpfs is niet te onderscheiden: CUSTOM_APP.md, Verplicht 3).
# Upstream-server en -web uit de basisimage vervangen door de fork-build (ffmpeg en drivers blijven).
RUN rm -rf /jellyfin
COPY --from=server /out/server /jellyfin
COPY --from=web /web/dist /jellyfin/jellyfin-web
COPY --from=server /out/plugin/Jellyfin.Plugin.JellyLeon.dll /usr/share/jelly-leon/plugins/JellyLeon_0.1.0.0/
COPY LICENSE CONTRIBUTORS.md /usr/share/doc/jelly-leon/
COPY deploy/allinone/NOTICE.jelly-leon /usr/share/doc/jelly-leon/NOTICE.jelly-leon
COPY deploy/allinone/entrypoint.sh /usr/local/bin/jelly-leon-entrypoint
COPY deploy/allinone/healthcheck.sh /usr/local/bin/jelly-leon-healthcheck
RUN set -eu; \
    chmod 0755 /usr/local/bin/jelly-leon-entrypoint /usr/local/bin/jelly-leon-healthcheck; \
    printf '%s\n' "${FORK_VERSION}" > /usr/share/doc/jelly-leon/VERSION; \
    printf 'server %s\nweb %s\n' "${VCS_REF}" "${WEB_REF}" > /usr/share/doc/jelly-leon/SOURCE_REVISIONS; \
    mkdir -p /config /cache; chown 568:568 /config /cache; chmod 0755 /config; chmod 1777 /cache; \
    test -x /jellyfin/jellyfin; test -f /jellyfin/jellyfin-web/index.html; test -x /usr/lib/jellyfin-ffmpeg/ffmpeg
EXPOSE 8096
VOLUME ["/config", "/cache"]
# De healthcheck (exec-vorm, geen sh -c) wisselt als eerste handeling naar 568 zonder capabilities met no_new_privs en
# controleert daarna zijn eigen rechten vóór curl (Docker start hem als de containergebruiker, bij een Custom App zonder
# Custom User dus als root; contract 1.3 §2.2, ADR-0014, ADR-0028). Controlevlag voor de rooktest: --toon-rechten.
HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
  CMD ["/usr/local/bin/jelly-leon-healthcheck"]
ENTRYPOINT ["/usr/local/bin/jelly-leon-entrypoint"]

# De scan leest de samengevoegde runtime inclusief server, web en werker. Syft blijft in de bouwfase.
FROM serverbasis AS inhoud
COPY --from=werkerproef /opt/jelly-leon /opt/jelly-leon

FROM ${SYFT_IMAGE} AS catalogus
USER 0
ENV SYFT_CHECK_FOR_APP_UPDATE=false SYFT_PARALLELISM=2
RUN --network=none --mount=type=bind,from=inhoud,source=/,target=/rootfs,ro \
    ["/syft", "scan", "dir:/rootfs", "--quiet", "--source-name", "jelly-leon", "-o", "cyclonedx-json=/image.cdx.json"]

FROM inhoud
RUN --network=none --mount=type=bind,from=catalogus,source=/image.cdx.json,target=/inventaris.json,ro \
    /opt/jelly-leon/python/bin/python3 -IB -m jl_werker.inventaris image /inventaris.json
