"""Maak/beoordeel synthetische opslagregressies; een open restgrens geeft exitcode 1."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROEVEN = {
    "hardlink-tijdelijk", "hardlink-database", "padwissel-bestand", "padwissel-database",
    "botsing-willekeurig-tijdelijk",
}


def maak(doel: Path) -> None:
    doel.mkdir(parents=True, exist_ok=False)
    bron = ROOT / "plugins/JellyLeon/src/Jellyfin.Plugin.JellyLeon/Core/Storage"
    for naam in ("JlPaths.cs", "InternalWriteScope.cs", "JlDatabase.cs"):
        tekst = (bron / naam).read_text()
        if naam == "InternalWriteScope.cs":
            if "new FileStream(" not in tekst:
                raise ValueError("Het controle/openvenster ontbreekt.")
            tekst = tekst.replace("new FileStream(", "GrensHaak.OpenBestand(")
        if naam == "JlDatabase.cs":
            if tekst.count("new SqliteConnection(_connectionString)") != 1:
                raise ValueError("Het databasecontrole/openvenster ontbreekt of is dubbel.")
            tekst = tekst.replace("new SqliteConnection(_connectionString)", "GrensHaak.NieuweVerbinding(_connectionString)")
        (doel / naam).write_text(tekst)
    versies = (ROOT / "plugins/Directory.Packages.props").read_text()
    versie, = re.findall(r'<PackageVersion Include="Microsoft.Data.Sqlite" Version="([0-9.]+)"', versies)
    (doel / "OpslagGrensproef.csproj").write_text(
        '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><TargetFramework>net10.0</TargetFramework>'
        '<OutputType>Exe</OutputType><Nullable>enable</Nullable><ImplicitUsings>enable</ImplicitUsings>'
        '</PropertyGroup><ItemGroup><PackageReference Include="Microsoft.Data.Sqlite" Version="'
        + versie + '" /></ItemGroup></Project>\n'
    )
    (doel / "Program.cs").write_text((ROOT / "plugins/JellyLeon/proeven/OpslagGrensproef.cs").read_text())
    print("Opslagproef aangemaakt met kopieën van de huidige opslagbron; alleen controle/openhaken toegevoegd.")


def beoordeel(log: Path) -> int:
    regels = [r.removeprefix("OPSLAGPROEVEN=") for r in log.read_text().splitlines() if r.startswith("OPSLAGPROEVEN=")]
    if len(regels) != 1:
        print("Opslagproef onvolledig: precies één resultaat vereist.")
        return 2
    rijen = json.loads(regels[0])
    if len(rijen) != len(PROEVEN) or {r["proef"] for r in rijen} != PROEVEN:
        print("Opslagproef onvolledig: niet elke verplichte proef is uitgevoerd.")
        return 2
    for rij in rijen:
        print(f'{rij["proef"]}: buitenbestand bytegelijk={rij["bytegelijk"]}; buitenmap gelijk={rij["mapgelijk"]}; weigering={rij["weigering"]}')
    dicht = all(r["bytegelijk"] is True and r["mapgelijk"] is True for r in rijen)
    print("Opslaggrenzen dicht in alle synthetische proeven." if dicht else "NIET KLAAR: ten minste één synthetische opslaggrens blijft rood.")
    return 0 if dicht else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    groep = parser.add_mutually_exclusive_group(required=True)
    groep.add_argument("--maak", type=Path)
    groep.add_argument("--beoordeel", type=Path)
    args = parser.parse_args()
    if args.maak:
        maak(args.maak)
        return 0
    return beoordeel(args.beoordeel)


if __name__ == "__main__":
    raise SystemExit(main())
