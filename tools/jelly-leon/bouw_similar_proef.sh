#!/usr/bin/env bash
# De normale Release en de testvariant hebben eigen tussenbestanden. Alleen de proef krijgt de waarnemer.
set -euo pipefail
dotnet build plugins/JellyLeon/src/Jellyfin.Plugin.JellyLeon/Jellyfin.Plugin.JellyLeon.csproj -c SimilarProef \
  -p:CustomAfterMicrosoftCommonTargets="$PWD/tools/jelly-leon/e2e/similar_fixture/Proef.targets" -o "${1:?uitvoermap nodig}"
