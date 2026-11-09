"""python -m b03h <onderdeel> … — ingang van het B03-016-harnas."""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    hulp = ("gebruik: python -m b03h {corpus|guard|baseline|diffrun|legacy|clientmatrix|desktop|rapport} …\n"
            "  corpus        corpusgenerator (recepten F1–F6, manifest, bevriezen, opruimen)\n"
            "  guard         CI-guard testdatalicenties (repo, commitbereik, image, map)\n"
            "  baseline      baselinemetingen tegen stock jellyfin/jellyfin (stock-standaard en stock-best)\n"
            "  diffrun       differentiële controle-run (twee kopieën van dezelfde datamap)\n"
            "  legacy        derden-client met legacy-headers (wat doet 12.x?)\n"
            "  clientmatrix  rooktest van de clientmatrix (web, UA-simulatie, legacy, Android-emulator)\n"
            "  desktop       gezamenlijke desktop-spike (jellyfin-desktop 2.0.0 onder Xvfb, ruwe CDP)\n"
            "  rapport       baselinebewijs als Markdown-tabel")
    if not argv or argv[0] in ("-h", "--help"):
        print(hulp)
        return 0
    onderdeel, rest = argv[0], argv[1:]
    if onderdeel == "corpus":
        from .corpus.generator import main as m
    elif onderdeel == "guard":
        from .guard import main as m
    elif onderdeel == "baseline":
        from .baseline import main as m
    elif onderdeel == "diffrun":
        from .diffrun import main as m
    elif onderdeel == "legacy":
        from .legacy import main as m
    elif onderdeel == "clientmatrix":
        from .clientmatrix import main as m
    elif onderdeel == "desktop":
        from .desktop import main as m
    elif onderdeel == "rapport":
        from .rapport import main as m
    else:
        print(hulp, file=sys.stderr)
        return 2
    return m(rest)


if __name__ == "__main__":
    sys.exit(main())
