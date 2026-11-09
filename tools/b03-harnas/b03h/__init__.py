"""B03-016 — één harnasraamwerk voor het mediacorpus, de clientmatrix en de baselinemetingen van standaard Jellyfin.

Alleen de standaardbibliotheek. Niets hier draait op de NAS of in de Jelly Leon-image: het is gereedschap voor de
ontwikkelmachine en CI (ADR-0026). Media en afgeleide testsets komen nooit in de repo of een image; alleen recepten,
manifesten (sha256) en meetbewijs.
"""

__all__ = ["VERSIE"]

VERSIE = "0.1.0"
