#!/usr/bin/env bash
# De Forgejo-runner kan het installatiescript in de actioncache niet rechtstreeks uitvoeren.
set -euo pipefail
kanaal=${1%.x}
[[ "$kanaal" =~ ^[0-9]+\.[0-9]+$ ]] || { echo "Ongeldig SDK-kanaal: $kanaal" >&2; exit 1; }
sdk="$RUNNER_TEMP/dotnet"
installatie="$RUNNER_TEMP/jl-dotnet-install.sh"
curl --fail --silent --show-error --location --retry 3 \
    'https://raw.githubusercontent.com/actions/setup-dotnet/67a3573c9a986a3f9c594539f4ab511d57bb3ce9/externals/install-dotnet.sh' -o "$installatie"
printf '%s  %s\n' 19b0a7890c371201b944bf0f8cdbb6460d053d63ddbea18cfed3e4199769ce17 "$installatie" | sha256sum --check
bash "$installatie" --channel "$kanaal" --quality GA --install-dir "$sdk" --no-path
printf 'DOTNET_ROOT=%s\n' "$sdk" >> "$GITHUB_ENV"
printf '%s\n' "$sdk" >> "$GITHUB_PATH"
"$sdk/dotnet" --version
