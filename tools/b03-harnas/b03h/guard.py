"""CI-guard testdatalicenties (B03 2.0 §10.13, jury HB §5): weigert beperkt gelicentieerde testdata in commits en images.

Beperkt (BG-37): MovieLens (onderzoekslicentie), Pioneer One (CC BY-NC-SA), afgeleide labels daarvan en
fanondertitels. Daarnaast hoort geen enkel mediabestand of corpusbestand in de repo (contract: geen media in repo of image).

Regels per bestand:
  N  naam/pad wijst op beperkte data of op het lokale corpus;
  H  sha256 staat op de lijst van beperkte bronbestanden (``beperkt_sha256.txt``), ook als het bestand hernoemd is;
  C  inhoud: MovieLens-CSV-kop of de markering die de corpusgenerator in elke beperkte afgeleide set zet;
  M  media-/ondertitelbestand in de repo (behalve de kleine upstream-testbestanden op de toestemmingslijst).
In de image-modus gelden N, H en C (een image mag web-geluidjes e.d. bevatten; M is daar te grof).
"""

from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
import tarfile
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

HIER = Path(__file__).resolve().parent
# De markering wordt uit delen opgebouwd, zodat deze bron zelf geen treffer is.
MARKERING = "B03-" + "BEPERKTE-" + "TESTDATA"
NAAM_PATRONEN = [
    (re.compile(r"pioneer[ ._-]?one", re.I), "Pioneer One (CC BY-NC-SA, alleen lokaal)"),
    (re.compile(r"ml-(latest|25m|20m|1m|100k)", re.I), "MovieLens-dataset (onderzoekslicentie, alleen lokaal)"),
    (re.compile(r"movielens", re.I), "MovieLens (onderzoekslicentie, alleen lokaal)"),
    (re.compile(r"addic7ed", re.I), "fanondertitels (licentie onduidelijk)"),
    (re.compile(r"(^|/)media-corpus(/|$)"), "lokaal mediacorpus hoort niet in de repo"),
    (re.compile(r"(^|/)\.lokaal(/|$)"), "lokale werkmap hoort niet in de repo"),
]
CSV_KOPPEN = ["userId,movieId,rating,timestamp", "userId,movieId,tag,timestamp", "movieId,imdbId,tmdbId", "movieId,title,genres",
              "movieId,tagId,relevance"]
MEDIA_EXT = {".mkv", ".mp4", ".m4v", ".mov", ".avi", ".webm", ".wmv", ".flv", ".mpg", ".mpeg", ".m2ts", ".mts", ".vob",
             ".mp3", ".flac", ".aac", ".ac3", ".eac3", ".dts", ".wav", ".ogg", ".opus", ".m4a", ".aif", ".aiff", ".mka",
             ".h264", ".h265", ".hevc", ".y4m"}
ONDERTITEL_EXT = {".srt", ".ass", ".ssa", ".vtt", ".sub", ".idx", ".sup", ".smi"}
TOESTEMMING = {  # kleine upstream-testbestanden (Jellyfin, GPL-2.0) — geen corpusmateriaal
    "tests/Jellyfin.MediaEncoding.Tests/Test Data/example.ass",
    "tests/Jellyfin.MediaEncoding.Tests/Test Data/example.ssa",
    "tests/Jellyfin.MediaEncoding.Tests/Test Data/example.srt",
    "tests/Jellyfin.MediaEncoding.Tests/Test Data/example2.srt",
}
MAX_LEES = 64 << 20


@dataclass(frozen=True)
class Vondst:
    pad: str
    regel: str
    reden: str

    def __str__(self) -> str:
        return f"[{self.regel}] {self.pad}: {self.reden}"


def beperkte_hashes(pad: Path = HIER / "beperkt_sha256.txt") -> dict[str, str]:
    uit = {}
    for regel in pad.read_text(encoding="utf-8").splitlines():
        if regel and not regel.startswith("#"):
            h, _, omschrijving = regel.partition("  ")
            uit[h.strip()] = omschrijving.strip()
    return uit


def _is_mpeg_ts(kop: bytes) -> bool:
    return len(kop) >= 377 and kop[0] == 0x47 and kop[188] == 0x47 and kop[376] == 0x47


def beoordeel(pad: str, inhoud: bytes | None, hashes: dict[str, str], *, media_regel: bool = True) -> list[Vondst]:
    vondsten: list[Vondst] = []
    for patroon, reden in NAAM_PATRONEN:
        if patroon.search(pad):
            vondsten.append(Vondst(pad, "N", reden))
            break
    if inhoud is None:
        return vondsten
    h = hashlib.sha256(inhoud).hexdigest()
    if h in hashes:
        vondsten.append(Vondst(pad, "H", f"inhoud = beperkt bronbestand ({hashes[h]})"))
    kop = inhoud[:4096]
    tekst = kop.decode("utf-8", "replace").lstrip("﻿")
    eerste = tekst.splitlines()[0].strip() if tekst else ""
    if eerste in CSV_KOPPEN:
        vondsten.append(Vondst(pad, "C", f"MovieLens-CSV-kop '{eerste}'"))
    if MARKERING.encode() in inhoud:
        vondsten.append(Vondst(pad, "C", "afgeleide data van een beperkte bron (markering van de corpusgenerator)"))
    if media_regel and pad not in TOESTEMMING:
        ext = Path(pad).suffix.lower()
        if ext in MEDIA_EXT or (ext == ".ts" and _is_mpeg_ts(kop)):
            vondsten.append(Vondst(pad, "M", "mediabestand hoort niet in de repo (corpus blijft lokaal)"))
        elif ext in ONDERTITEL_EXT:
            vondsten.append(Vondst(pad, "M", "ondertitelbestand hoort niet in de repo (corpus blijft lokaal)"))
    return vondsten


def _git(repo: Path, *args: str) -> bytes:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=True).stdout


def bestanden_git(repo: Path) -> Iterator[tuple[str, bytes | None]]:
    """Alle getrackte bestanden in de werkboom (zoals ze gecommit/gestaged zijn)."""
    for rel in _git(repo, "ls-files", "-z").decode().split("\0"):
        if not rel:
            continue
        pad = repo / rel
        if pad.is_file() and not pad.is_symlink():
            yield rel, pad.read_bytes() if pad.stat().st_size <= MAX_LEES else None
        else:
            yield rel, None


def bestanden_bereik(repo: Path, bereik: str) -> Iterator[tuple[str, bytes | None]]:
    """Elk bestand dat in een commit van het bereik is toegevoegd of gewijzigd (ook als een latere commit het weer weghaalt)."""
    for commit in _git(repo, "rev-list", bereik).decode().split():
        namen = _git(repo, "diff-tree", "-r", "--root", "--no-commit-id", "--diff-filter=AMR", "--name-only", "-z", commit)
        for rel in namen.decode().split("\0"):
            if not rel:
                continue
            grootte = int(_git(repo, "cat-file", "-s", f"{commit}:{rel}").decode().strip() or 0)
            inhoud = _git(repo, "cat-file", "blob", f"{commit}:{rel}") if grootte <= MAX_LEES else None
            yield f"{rel} (commit {commit[:9]})", inhoud


def bestanden_map(map_: Path) -> Iterator[tuple[str, bytes | None]]:
    for pad in sorted(p for p in map_.rglob("*") if p.is_file()):
        yield pad.relative_to(map_).as_posix(), pad.read_bytes() if pad.stat().st_size <= MAX_LEES else None


def bestanden_image(ref: str) -> Iterator[tuple[str, bytes | None]]:
    """Leest het bestandssysteem van een image (docker create + export, gestreamd); inhoud alleen voor kandidaten."""
    cid = subprocess.run(["docker", "create", ref], capture_output=True, text=True, check=True).stdout.strip()
    try:
        proc = subprocess.Popen(["docker", "export", cid], stdout=subprocess.PIPE)
        assert proc.stdout is not None
        with tarfile.open(fileobj=proc.stdout, mode="r|") as tar:
            for lid in tar:
                if not lid.isfile():
                    continue
                naam = lid.name
                ext = Path(naam).suffix.lower()
                kandidaat = ext in MEDIA_EXT | ONDERTITEL_EXT | {".csv", ".json", ".ts"} or lid.size >= (1 << 20)
                inhoud = None
                if kandidaat and lid.size <= MAX_LEES:
                    f = tar.extractfile(lid)
                    inhoud = f.read() if f else None
                yield naam, inhoud
        proc.wait()
    finally:
        subprocess.run(["docker", "rm", "-f", cid], capture_output=True, check=False)


def controleer(bron: Iterable[tuple[str, bytes | None]], *, media_regel: bool = True) -> list[Vondst]:
    hashes = beperkte_hashes()
    vondsten: list[Vondst] = []
    for pad, inhoud in bron:
        vondsten.extend(beoordeel(pad, inhoud, hashes, media_regel=media_regel))
    return vondsten


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="b03h guard", description="CI-guard: geen beperkt gelicentieerde testdata in commits/images")
    groep = p.add_mutually_exclusive_group(required=True)
    groep.add_argument("--git", type=Path, metavar="REPO", help="alle getrackte bestanden van de repo")
    groep.add_argument("--bereik", nargs=2, metavar=("REPO", "A..B"), help="elk bestand dat in het commitbereik is toegevoegd")
    groep.add_argument("--image", metavar="REF", help="bestandssysteem van een image")
    groep.add_argument("--map", type=Path, help="een map (bv. een build-context)")
    a = p.parse_args(argv)
    if a.git:
        vondsten = controleer(bestanden_git(a.git))
        wat = f"repo {a.git}"
    elif a.bereik:
        vondsten = controleer(bestanden_bereik(Path(a.bereik[0]), a.bereik[1]))
        wat = f"commits {a.bereik[1]}"
    elif a.image:
        vondsten = controleer(bestanden_image(a.image), media_regel=False)
        wat = f"image {a.image}"
    else:
        vondsten = controleer(bestanden_map(a.map))
        wat = f"map {a.map}"
    if vondsten:
        print(f"GEWEIGERD — beperkt gelicentieerde of lokale testdata in {wat} ({len(vondsten)} vondsten):", file=sys.stderr)
        for v in vondsten[:200]:
            print(f"  {v}", file=sys.stderr)
        print("Testdata met een beperkende licentie blijft lokaal (BG-37); media en afgeleide sets nooit in repo of image.",
              file=sys.stderr)
        return 1
    print(f"in orde: geen beperkt gelicentieerde testdata in {wat}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

