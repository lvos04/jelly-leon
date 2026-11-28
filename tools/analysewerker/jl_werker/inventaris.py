"""Koppel de geïnstalleerde werker aan de vastgezette distributies en de image-inventaris."""

import csv
import json
import platform
import re
import subprocess
import sys
from importlib import metadata
from pathlib import Path

from .opdrachten import FFMPEG_MAP, versies

MAP = Path("/opt/jelly-leon")
VERBODEN = {"auditok", "ctranslate2", "torch", "transformers"}


def naam(waarde: str) -> str:
    return re.sub(r"[-_.]+", "-", waarde.lower())


def controleer_componenten(componenten: list[dict]) -> None:
    for item in componenten:
        if naam(item["name"]) in VERBODEN:
            raise ValueError(f"verboden component in de SBOM: {item['name']}")
        controleer_componenten(item.get("components", []))


def lees_lock(pad: Path) -> dict[str, tuple[str, str]]:
    pakketten = {}
    for regel in pad.read_text().splitlines():
        if not regel.strip() or regel.startswith("#"):
            continue
        match = re.fullmatch(r"([\w.-]+)==([\w.+-]+) --hash=sha256:([a-f0-9]{64})", regel)
        if not match or naam(match[1]) in pakketten:
            raise ValueError("ongeldige of dubbele pakketregel in requirements.lock")
        pakketten[naam(match[1])] = (match[2], match[3])
    return pakketten


def ffmpeg_licentie(tool: str) -> str:
    tekst = subprocess.check_output([str(FFMPEG_MAP / tool), "-L"], stderr=subprocess.DEVNULL, text=True, timeout=10)
    match = re.search(r"either version (\d+(?:\.\d+)?) of the License", tekst)
    if not match or "any later version" not in tekst:
        raise ValueError(f"licentietekst van {tool} vereist beoordeling")
    versie = match[1] if "." in match[1] else match[1] + ".0"
    familie = "LGPL" if "Lesser General Public License" in tekst else "GPL"
    return f"{familie}-{versie}-or-later"


def werker_sbom() -> dict:
    lock = lees_lock(MAP / "requirements.lock")
    licenties = json.loads((MAP / "licenties.json").read_text())
    geinstalleerd = {naam(d.metadata["Name"]): d.version for d in metadata.distributions()}
    if geinstalleerd != {k: v for k, (v, _) in lock.items()} or licenties.keys() != lock.keys():
        raise ValueError("geïnstalleerde pakketten, vastgezette versies en licentie-inventaris verschillen")
    componenten = []
    for pakket, (versie, digest) in lock.items():
        purl = f"pkg:pypi/{pakket}@{versie}"
        componenten.append({
            "type": "library", "bom-ref": purl, "purl": purl, "name": pakket, "version": versie,
            "licenses": [{"expression": licenties[pakket]}],
            "externalReferences": [{"type": "distribution", "url": f"https://pypi.org/project/{pakket}/{versie}/",
                                    "hashes": [{"alg": "SHA-256", "content": digest}]}],
        })
    gemeten = versies()
    if gemeten["ffsubsync"] != geinstalleerd["ffsubsync"] or gemeten["python"] != platform.python_version():
        raise ValueError("gereedschapsversie verschilt van de geïnstalleerde distributie")
    for tool, licentie in (("python", "Python-2.0"), ("ffmpeg", ffmpeg_licentie("ffmpeg")), ("ffprobe", ffmpeg_licentie("ffprobe"))):
        componenten.append({"type": "application", "bom-ref": f"jl-gereedschap:{tool}", "name": tool,
                            "version": gemeten[tool], "licenses": [{"expression": licentie}]})
    controleer_componenten(componenten)
    return {"bomFormat": "CycloneDX", "specVersion": "1.6", "version": 1, "components": componenten}


def vergelijk_versies(sbom: dict, actueel: dict) -> None:
    componenten = sbom["components"]
    controleer_componenten(componenten)
    for tool in ("python", "ffsubsync", "ffmpeg", "ffprobe"):
        referentie = f"pkg:pypi/ffsubsync@{actueel[tool]}" if tool == "ffsubsync" else f"jl-gereedschap:{tool}"
        sleutel = "purl" if tool == "ffsubsync" else "bom-ref"
        if not any(c.get(sleutel) == referentie and c["version"] == actueel[tool] for c in componenten):
            raise ValueError(f"versie van {tool} verschilt van de SBOM")


def schrijf_image(bron: Path) -> None:
    sbom = json.loads(bron.read_text())
    werker = json.loads((MAP / "werker.cdx.json").read_text())
    # Syft levert de imagecomponenten. Voeg de geverifieerde distributiehashes en gereedschapsversies toe.
    for item in werker["components"]:
        bestaand = next((c for c in sbom["components"] if item.get("purl") and c.get("purl") == item["purl"]), None)
        if bestaand is None:
            sbom["components"].append(item)
        else:
            # Houd Syfts bom-ref aan: de afhankelijkheidsgraaf verwijst ernaar.
            bestaand.update({k: v for k, v in item.items() if k not in {"bom-ref", "purl"}})
    controleer_componenten(sbom["components"])
    (MAP / "image.cdx.json").write_text(json.dumps(sbom) + "\n")
    with (MAP / "licenties.tsv").open("w", newline="") as bestand:
        tabel = csv.writer(bestand, delimiter="\t", lineterminator="\n")
        tabel.writerow(["Component", "Versie", "Licentie"])
        for c in sorted(sbom["components"], key=lambda c: (c["name"], c.get("version", ""))):
            waarden = [v.get("expression") or v.get("license", {}).get("id") or v.get("license", {}).get("name")
                       for v in c.get("licenses", [])]
            tabel.writerow([c["name"], c.get("version", ""), ", ".join(filter(None, waarden)) or "onbekend"])


if __name__ == "__main__":
    if sys.argv[1:] == ["werker"]:
        (MAP / "werker.cdx.json").write_text(json.dumps(werker_sbom(), indent=2) + "\n")
    elif len(sys.argv) == 3 and sys.argv[1] == "image":
        schrijf_image(Path(sys.argv[2]))
    else:
        sys.exit("Verwacht werker of image <Syft-inventaris>.")
