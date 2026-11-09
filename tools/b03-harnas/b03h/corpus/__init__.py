"""Corpusgenerator (B03 2.0 §10.13, B03-016 deel a): recepten met grondwaarheid, seed en sha256-manifest.

Regels: bron altijd alleen-lezen; uitvoer buiten de repo; schrijven via een tijdelijk bestand + sha256 + atomaire
hernoeming; testsets bevroren met een sha256-manifest vóór het afstemmen; on demand maken en na de test opruimen
(BG-38: alleen recept en manifest blijven).
"""

from __future__ import annotations

import os
from pathlib import Path

CORPUS = Path(os.environ.get("B03_CORPUS", "/home/transcode/truenas-v2/.lokaal/media-corpus"))
# Afgeleide testsets: buiten elke repo, naast het corpus (wordt na gebruik opgeruimd).
UITVOER = Path(os.environ.get("B03_UITVOER", "/home/transcode/truenas-v2/.lokaal/jelly-leon-b03-016/testsets"))
