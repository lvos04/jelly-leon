"""Controleert de drie bronankers van het gedeelde startscherm op de vastgezette jelly-leon-web-bron."""

import re
import sys
from pathlib import Path

ANKERS = {
    "src/components/homesections/homesections.js": r"export function loadSections\(elem, apiClient, user, userSettings\)",
    "src/apps/legacy/controllers/hometab.js": (
        r"homeSections\.loadSections\(view\.querySelector\('\.sections'\), apiClient, user, userSettings\)"),
    "src/apps/modern/routes/home.tsx": r"depends = 'hometab';[\s\S]+apps/legacy/controllers/\$\{depends\}",
}


def controleer(bron):
    for pad, anker in ANKERS.items():
        bestand = bron / pad
        if not bestand.is_file() or not re.search(anker, bestand.read_text(encoding="utf-8")):
            return f"UG-F2-6: webanker gewijzigd in {pad}"
    return None


if __name__ == "__main__":
    fout = controleer(Path(sys.argv[1]))
    print(fout or "UG-F2-6: de drie webankers zijn aanwezig")
    sys.exit(int(bool(fout)))
