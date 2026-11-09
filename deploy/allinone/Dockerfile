# syntax=docker/dockerfile:1.7
# Jelly Leon — alles-in-één image ghcr.io/lvos04/jelly-leon (ADR-0008). Lokaal volledig gebouwd en getest (incl. de
# echte web-build van jelly-leon-web); publicatie naar GHCR en de release-workflow volgen in P4.
#
# Inhoud: Jellyfin-server uit deze fork (self-contained) + web-client uit lvos04/jelly-leon-web + de Jelly Leon-plugin,
# op de officiële upstream-runtime (jellyfin/jellyfin, met jellyfin-ffmpeg en de Intel QSV/VAAPI-stack) — die runtime
# bouwen we bewust niet zelf na (geen dubbel werk, INVENTARIS.md §6). Database: de ingebouwde SQLite van Jellyfin
# (geen PostgreSQL; ADR-0008). Installatie uitsluitend als standaard TrueNAS Custom App (deploy/truenas/CUSTOM_APP.md).
#
# Bouwen (vanaf de repo-root; de web-client komt als aparte build-context, bij voorkeur een schone export via
# `git archive` van lvos04/jelly-leon-web zodat er geen lokale node_modules of bouwresten meegaan):
#   docker buildx build -f deploy/allinone/Dockerfile \
#     --build-context jelly-leon-web=<map-met-export-van-jelly-leon-web> \
#     --build-arg FORK_VERSION=<forkversie> --build-arg VCS_REF=<commit> --build-arg WEB_REF=<commit-jelly-leon-web> \
#     [--secret id=ca_bundle,src=<ca-bestand>] -t ghcr.io/lvos04/jelly-leon:<forkversie> .
# Het optionele geheim ca_bundle is alleen voor bouwomgevingen achter een TLS-proxy; het komt niet in de image.

ARG SDK_IMAGE=mcr.microsoft.com/dotnet/sdk:9.0.320@sha256:07ed28d9e7279248fcea27334880f6c415b42c631c39b8bc5b3caf13ec6fdaa2
ARG NODE_IMAGE=docker.io/library/node:22.23.4-bookworm-slim@sha256:5ec23b7c622b00547753bc6ffd78085dd868a68aeb41c8e0a1418f033e13d96d
ARG RUNTIME_IMAGE=docker.io/jellyfin/jellyfin:10.11.11@sha256:aefb67e6a7ff1debdd154a78a7bbb780fd0c873d8639210a7f6a2016ad2b35db

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
FROM ${NODE_IMAGE} AS web
WORKDIR /web
COPY --from=jelly-leon-web package.json package-lock.json ./
RUN --mount=type=secret,id=ca_bundle,required=false \
    --mount=type=cache,target=/root/.npm \
    if [ -s /run/secrets/ca_bundle ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/ca_bundle; fi; \
    npm ci --no-audit --no-fund
COPY --from=jelly-leon-web . .
RUN npm run build:production && test -f dist/index.html

# ---------------------------------------------------------------- runtime
FROM ${RUNTIME_IMAGE}
ARG FORK_VERSION=0.0.0-jl.0
ARG VCS_REF=unknown
# Commit van lvos04/jelly-leon-web waaruit de web-client is gebouwd (GPL "bron beschikbaar", ADR-0004).
ARG WEB_REF=unknown
LABEL org.opencontainers.image.title="Jelly Leon" \
      org.opencontainers.image.description="Jelly Leon — mediaserver gebaseerd op Jellyfin (technische identiteit: Jellyfin)" \
      org.opencontainers.image.source="https://github.com/lvos04/jelly-leon" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.version="${FORK_VERSION}" \
      org.opencontainers.image.licenses="GPL-2.0-only AND GPL-2.0-or-later" \
      org.opencontainers.image.base.name="docker.io/jellyfin/jellyfin:10.11.11" \
      io.github.lvos04.jelly-leon.web.source="https://github.com/lvos04/jelly-leon-web" \
      io.github.lvos04.jelly-leon.web.revision="${WEB_REF}"
# Upstream-server en -web uit de basisimage vervangen door de fork-build (ffmpeg en drivers blijven).
RUN rm -rf /jellyfin
COPY --from=server /out/server /jellyfin
COPY --from=web /web/dist /jellyfin/jellyfin-web
COPY --from=server /out/plugin/Jellyfin.Plugin.JellyLeon.dll /usr/share/jelly-leon/plugins/JellyLeon_0.1.0.0/
COPY LICENSE CONTRIBUTORS.md /usr/share/doc/jelly-leon/
COPY deploy/allinone/NOTICE.jelly-leon /usr/share/doc/jelly-leon/NOTICE.jelly-leon
COPY deploy/allinone/entrypoint.sh /usr/local/bin/jelly-leon-entrypoint
RUN set -eu; \
    chmod 0755 /usr/local/bin/jelly-leon-entrypoint; \
    printf '%s\n' "${FORK_VERSION}" > /usr/share/doc/jelly-leon/VERSION; \
    printf 'server %s\nweb %s\n' "${VCS_REF}" "${WEB_REF}" > /usr/share/doc/jelly-leon/SOURCE_REVISIONS; \
    mkdir -p /config /cache; chown 568:568 /config /cache; \
    test -x /jellyfin/jellyfin; test -f /jellyfin/jellyfin-web/index.html; test -x /usr/lib/jellyfin-ffmpeg/ffmpeg
EXPOSE 8096
VOLUME ["/config", "/cache"]
HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
  CMD ["curl", "--noproxy", "localhost", "-fsS", "-o", "/dev/null", "http://localhost:8096/health"]
ENTRYPOINT ["/usr/local/bin/jelly-leon-entrypoint"]
