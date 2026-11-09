#!/usr/bin/env python3
"""Bepaalt het .NET-SDK-kanaal voor CI uit de upstream-global.json (zonder global.json te wijzigen).

Upstream-Jellyfin zet in `global.json` een ondergrens als `9.0.0` met `rollForward: latestMinor`. Die exacte SDK-versie
bestaat niet als download, dus `actions/setup-dotnet` met `global-json-file` faalt ("Could not find .NET Core SDK with
version = 9.0.0"). Upstream zelf installeert daarom `9.0.x`. Dit hulpmiddel leidt dat kanaal af uit global.json, zodat
er één bron van waarheid blijft en een upstream-sync naar een nieuwe reeks (bv. 12.x met SDK 10.0.0 → `10.0.x`)
vanzelf de juiste SDK krijgt. global.json blijft een ongewijzigd upstream-bestand (geen core-patch nodig).

Uitvoer: het kanaal op stdout (bv. `9.0.x`); met `--github-output` ook `kanaal=<kanaal>` en `major_minor=<x.y>` in
`$GITHUB_OUTPUT`. Exitcodes: 0 = in orde, 3 = global.json ontbreekt of is ongeldig.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from jl_common import DEFAULT_REPO_ROOT, GLOBAL_JSON_REL, ToolError, read_global_json_sdk, sdk_channel, sdk_major_minor  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Leid het .NET-SDK-kanaal (x.y.x) af uit global.json.")
    parser.add_argument("--repo", type=Path, default=DEFAULT_REPO_ROOT)
    parser.add_argument("--github-output", action="store_true", help="schrijf kanaal en major_minor naar $GITHUB_OUTPUT")
    args = parser.parse_args(argv)
    try:
        version = read_global_json_sdk(args.repo.resolve())
        if version is None:
            raise ToolError(f"{GLOBAL_JSON_REL} ontbreekt in {args.repo}", exit_code=3)
        channel, major_minor = sdk_channel(version), sdk_major_minor(version)
    except ToolError as exc:
        print(f"FOUT: {exc}", file=sys.stderr)
        return 3
    if args.github_output:
        output = os.environ.get("GITHUB_OUTPUT")
        if not output:
            print("FOUT: --github-output gevraagd maar GITHUB_OUTPUT is niet gezet", file=sys.stderr)
            return 3
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(f"kanaal={channel}\nmajor_minor={major_minor}\n")
    print(channel)
    print(f"global.json vraagt SDK {version} (rollForward volgens global.json); CI installeert kanaal {channel}.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
