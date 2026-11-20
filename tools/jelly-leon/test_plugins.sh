#!/usr/bin/env bash
# De negatieve opslagtests gebruiken een datamap en een databasebestand van een andere UID.
set -euo pipefail
umask 022
fixture=$(mktemp -d "$RUNNER_TEMP/pluginproef.XXXXXXXX")
trap 'rm -rf -- "$fixture"' EXIT
mkdir -p "$fixture/kern/jelly-leon/core" "$fixture/vreemd" "$fixture/cli" "$fixture/tmp" "$fixture/vstest"
touch "$fixture/kern/jelly-leon/core/core.db"
gebruiker=$(id -u)
groep=$(id -g)
testcommando=()
beheer=()
if [[ $gebruiker = 0 ]]; then
    gebruiker=1000
    groep=1000
    testcommando=(setpriv --reuid "$gebruiker" --regid "$groep" --clear-groups --no-new-privs)
    chown -R "$gebruiker:$groep" plugins "$fixture"
else
    beheer=(sudo -n)
fi
vreemde_uid=65534
if [[ $gebruiker = "$vreemde_uid" ]]; then vreemde_uid=65533; fi
"${beheer[@]}" chown "$vreemde_uid" "$fixture/vreemd" "$fixture/kern/jelly-leon/core/core.db"
chmod 700 "$fixture/kern/jelly-leon/core" "$fixture/tmp"
export JL_VREEMDE_OPSLAG="$fixture/vreemd" JL_VREEMDE_KERN="$fixture/kern"
export TMPDIR="$fixture/tmp" DOTNET_CLI_HOME="$fixture/cli" NUGET_PACKAGES="$fixture/cli/packages"
export VSTEST_ARTIFACTS_DIRECTORY="$fixture/vstest" XDG_RUNTIME_DIR="$fixture/tmp"
"${testcommando[@]}" dotnet build plugins/JellyLeon.Plugins.sln -c Release
"${testcommando[@]}" dotnet test plugins/JellyLeon.Plugins.sln -c Release --no-build --verbosity minimal
