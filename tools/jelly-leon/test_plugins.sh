#!/usr/bin/env bash
# De opslagproeven draaien als de app. Alleen de eigenaarfixture wordt vooraf met beheerdersrechten ingericht.
set -euo pipefail
umask 022
sdk=$(command -v dotnet)
"$sdk" build plugins/JellyLeon.Plugins.sln -c Release

beheer=()
if [[ $(id -u) != 0 ]]; then beheer=(sudo -n); fi
fixture=$(mktemp -d "${TMPDIR:-/tmp}/pluginproef.XXXXXXXX")
trap '"${beheer[@]}" rm -rf -- "$fixture"' EXIT
mkdir -p "$fixture"/{kern/jelly-leon/core,geheim/jelly-leon/secrets,vreemd,cli,tmp,vstest}
touch "$fixture/kern/jelly-leon/core/core.db" "$fixture/geheim/jelly-leon/secrets/vreemd.salt"
chmod 600 "$fixture/geheim/jelly-leon/secrets/vreemd.salt"
chmod 700 "$fixture/kern/jelly-leon/core" "$fixture/geheim/jelly-leon/secrets" "$fixture/tmp"
"${beheer[@]}" chown -R 568:568 "$fixture"
"${beheer[@]}" chown 65534 "$fixture/vreemd" "$fixture/kern/jelly-leon/core/core.db" "$fixture/geheim/jelly-leon/secrets/vreemd.salt"

app=()
if [[ $(id -u) != 568 ]]; then
    app=("${beheer[@]}" setpriv --reuid=568 --regid=568 --clear-groups --no-new-privs)
fi
# De gebouwde testassembly bevat al haar afhankelijkheden. De testgebruiker hoeft niet te schrijven in de checkout.
assemblies=(plugins/JellyLeon/tests/*/bin/Release/net*/Jellyfin.Plugin.JellyLeon.Tests.dll)
"${app[@]}" env PATH="$PATH" DOTNET_ROOT="$(dirname "$(readlink -f "$sdk")")" HOME="$fixture/cli" DOTNET_CLI_HOME="$fixture/cli" \
    TMPDIR="$fixture/tmp" XDG_RUNTIME_DIR="$fixture/tmp" \
    VSTEST_ARTIFACTS_DIRECTORY="$fixture/vstest" JL_VREEMDE_OPSLAG="$fixture/vreemd" JL_VREEMDE_KERN="$fixture/kern" \
    JL_VREEMD_GEHEIM="$fixture/geheim" "$sdk" test "${assemblies[@]}" --verbosity minimal
