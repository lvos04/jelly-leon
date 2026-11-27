"""Vergelijk de elf clientrollen van de JLT-63-rooktest op stock en de eindimage."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from . import legacy
from .android import AVDS
from .stock import STOCK_IMAGE
from .web import UA

ROLLEN = ("web-chromium", "web-firefox", "web-webkit", *(f"ua-{naam}" for naam in UA), "webdir", "legacy", *AVDS)


def afspelen(rij: dict) -> bool | None:
    """None betekent dat het harnas geen afspeeluitkomst kon meten."""
    if not rij:
        return None
    if rij["id"] == "legacy":
        statussen = rij.get("status_per_vorm")
        routes = ("system_info", "gebruiker_items", "stream_statisch")
        if not statussen or any(type(statussen.get(v, {}).get(r)) is not int for v in legacy.VORMEN for r in routes):
            return None
        return not legacy.afwijkingen(statussen)
    if rij["id"] in AVDS:
        pogingen = rij.get("pogingen", [])
        speelt = pogingen[-1].get("ok") if pogingen else None
    else:
        speelt = rij.get("orakel_ok")
    return speelt if isinstance(speelt, bool) else None


def vergelijk(stock: dict, fork: dict) -> tuple[int, dict]:
    if stock.get("server") != STOCK_IMAGE or fork.get("server") in (None, "", STOCK_IMAGE):
        raise ValueError("Stockreferentie of eindimage ontbreekt of wijkt af.")
    if not stock.get("testitem") or stock["testitem"] != fork.get("testitem"):
        raise ValueError("De twee matrices vereisen hetzelfde testitem.")
    dagen = {datetime.fromisoformat(s["begin"]).astimezone(UTC).date() for rapport in (stock, fork)
             for s in [rapport, *rapport.get("eerdere_sessies", [])]}
    if len(dagen) != 1:
        raise ValueError("De stockreferentie en alle eindimagemetingen moeten op dezelfde UTC-dag beginnen.")
    metingen = fork.get("actieve_modules", {})
    modules = metingen.get("ingebouwde_webclient")
    if not fork.get("alle_modules") or not modules or modules != metingen.get("stock_webdir"):
        raise ValueError("De modulemeting ontbreekt of verschilt tussen de twee proefservers.")
    kanten = []
    for rapport in (stock, fork):
        rijen = {r["id"]: r for r in rapport["clients"]}
        if len(rijen) != len(rapport["clients"]):
            raise ValueError("Een clientrol komt meermaals voor in hetzelfde rapport.")
        kanten.append(rijen)
    uitkomsten = {}
    regressies, onbeslist = [], []
    for rol in ROLLEN:
        referentie, eindimage = (afspelen(kant.get(rol, {})) for kant in kanten)
        uitkomsten[rol] = {"stock": referentie, "eindimage": eindimage}
        if referentie is True and eindimage is False:
            regressies.append(rol)
        if referentie is None or eindimage is None:
            onbeslist.append(rol)
    if not any(r["stock"] is True for r in uitkomsten.values()):
        raise ValueError("Geen enkele spelende stockrol als referentie.")
    code = 1 if regressies else 2 if onbeslist else 0
    return code, {"meetdag_utc": dagen.pop().isoformat(), "actieve_modules": modules, "clients": uitkomsten,
                  "regressies": regressies, "onbeslist": onbeslist}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stock", type=Path)
    parser.add_argument("eindimage", type=Path)
    parser.add_argument("--uit", type=Path)
    args = parser.parse_args(argv)
    try:
        code, rapport = vergelijk(*(json.loads(p.read_text(encoding="utf-8")) for p in (args.stock, args.eindimage)))
    except (OSError, KeyError, TypeError, ValueError) as fout:
        parser.exit(2, f"Onbruikbare clientmatrix: {fout}\n")
    if args.uit:
        args.uit.write_text(json.dumps(rapport, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(rapport['regressies'])} regressies ({', '.join(rapport['regressies']) or 'geen'}), "
          f"{len(rapport['onbeslist'])} onbeslist van {len(ROLLEN)} clientrollen")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
