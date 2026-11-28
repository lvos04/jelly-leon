"""Controleer het echte JSON-contract tussen harnas en gebouwde evaluatie-CLI met kleine, handgemaakte testdata."""

from __future__ import annotations

import sys
from pathlib import Path

from b03h.f2_data import Dataset, Film
from b03h.f2_evaluatie import SCENARIOS, opname, samenvatting, uitvoer
from b03h.f2_metrieken import Interactie, Item, Profiel


def main(cli: Path) -> None:
    catalogus = {str(i): Item("Movie", frozenset(["Drama" if i % 2 else "Komedie"])) for i in range(24)}
    films = {k: Film("Testfilm", item.genres, 100, 2, 8) for k, item in catalogus.items()}
    toegang = frozenset(catalogus) - {"23"}
    profielen = {str(n): Profiel(1000, tuple(Interactie(str(n + i), 400 + i, True) for i in range(4)),
                                 frozenset([str(12 + n)]), toegang) for n in range(4)}
    d = Dataset("Test", "test", catalogus, profielen, films, 1000)
    invoer = opname(d, None)
    eerste = uitvoer(cli, "rangschik", invoer)
    if uitvoer(cli, "rangschik", invoer) != eerste:
        raise ValueError("Dezelfde klok gaf een andere ranglijst.")
    cijfers = samenvatting(d, eerste)
    if any(cijfers[s]["min_aantal"] != 10 for s in SCENARIOS):
        raise ValueError("Een testprofiel kreeg minder dan tien zichtbare titels.")
    if any(r["item"] == "23" for rijen in eerste.values() for rij in rijen.values() for r in rij):
        raise ValueError("De afgeschermde titel werd aanbevolen.")
    invoer["profielen"][0]["profiel"]["toestand"][0]["tijd"] = invoer["profielen"][0]["tijd"]
    try:
        uitvoer(cli, "rangschik", invoer)
    except ValueError as fout:
        if "exitcode 1" not in str(fout):
            raise
    else:
        raise ValueError("Training op T werd toegelaten.")
    print("4 testprofielen × 7 scenario’s tweemaal gelijk, 10 zichtbare titels per rij met uitleg, training op T geweigerd.")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
