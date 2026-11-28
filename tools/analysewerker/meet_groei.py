"""Vergelijk twee imagegroottes in bytes, gemeten met dezelfde Docker-daemon."""

import json
import sys

GRENS = 192 * 1024**2  # Voorstel S-G1-30, ADR-0017.


def main(basis: int, met_werker: int) -> int:
    if min(basis, met_werker) <= 0:
        raise ValueError("ongeldige imagegrootte")
    groei = met_werker - basis
    print(json.dumps({"basis_bytes": basis, "image_bytes": met_werker, "groei_bytes": groei, "grens_bytes": GRENS}))
    return int(groei > GRENS)


if __name__ == "__main__":
    sys.exit(main(int(sys.argv[1]), int(sys.argv[2])))
