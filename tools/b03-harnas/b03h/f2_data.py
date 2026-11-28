"""D-SYN uit het bevroren manifest en de uitsluitend lokale D-ML met één globaal splitmoment."""

from __future__ import annotations

import csv
import io
import json
import shutil
import zipfile
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from xml.etree import ElementTree as ET

from .corpus import manifest
from .corpus.download import download
from .corpus.generator import BEVROREN, REPO
from .corpus.r_f2_dsyn import KEUREN
from .f2_metrieken import Interactie, Item, Profiel
from .guard import MARKERING

ARCHIEF_URL = "https://files.grouplens.org/datasets/movielens/ml-latest-small.zip"
ARCHIEF_SHA = "696d65a3dfceac7c45750ad32df2c259311949efec81f0f144fdfb91ebc9e436"
MIN_GEBRUIKERS = 100
BEVROREN_DSYN = BEVROREN / "f2-dsyn.v1.vol.manifest.json"


def lokaal(pad: Path) -> Path:
    doel = pad.resolve()
    if doel.is_relative_to(REPO) or any((p / ".git/HEAD").exists() or (p / ".git").is_file() for p in (doel, *doel.parents)):
        raise ValueError("beperkte gegevens horen buiten elke Git-werkboom")
    return doel


def haal_archief(map_: Path) -> Path:
    doel = lokaal(map_ / "ml-latest-small.zip")
    download(ARCHIEF_URL, doel, ARCHIEF_SHA)
    return doel


def tijd(iso: str) -> int:
    moment = datetime.fromisoformat(iso)
    if moment.tzinfo is None:
        raise ValueError("tijdstip zonder tijdzone")
    return int(moment.timestamp())


def utc(seconden: int) -> str:
    return datetime.fromtimestamp(seconden, UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass
class Film:
    titel: str
    genres: frozenset[str]
    eerste: int
    aantal: int
    som: float
    tags: set[str] = field(default_factory=set)


@dataclass
class Dataset:
    naam: str
    sha256: str
    catalogus: dict[str, Item]
    profielen: dict[str, Profiel]
    films: dict[str, Film] = field(default_factory=dict)
    globaal_t: int | None = None
    bovengrens_n: int | None = None
    deler_training: dict[str, tuple[Interactie, ...]] = field(default_factory=dict)

    def pop(self, gebruiker: str) -> list[str]:
        if self.globaal_t is not None:
            aantallen = {k: film.aantal for k, film in self.films.items()}
        else:
            # Het bevroren D-SYN-recept heeft een eigen klok per gebruiker.
            t = self.profielen[gebruiker].splitsing
            aantallen = Counter(i.item for p in self.profielen.values() for i in p.training if i.tijd < t)
        return sorted(self.catalogus, key=lambda k: (-aantallen.get(k, 0), k))

    def samenvatting(self) -> dict:
        return {"dataset": self.naam, "dataset_sha256": self.sha256, "catalogus": len(self.catalogus),
                "n": len(self.profielen), "T": utc(self.globaal_t) if self.globaal_t is not None else {
                    u: utc(p.splitsing) for u, p in self.profielen.items()}}


def lees_dsyn(map_: Path) -> Dataset:
    vast = json.loads(BEVROREN_DSYN.read_text())
    fouten = manifest.controleer(map_, vast)
    if fouten:
        raise ValueError("D-SYN wijkt af van het bevroren manifest: " + fouten[0])
    data = json.loads((map_ / "grondwaarheid.json").read_text())
    cat = {i["id"]: Item(i["type"], frozenset(i["genres"])) for i in data["items"]}
    kind = frozenset(i["id"] for i in data["items"] if KEUREN.index(i["keur"]) <= KEUREN.index("9"))
    profielen = {}
    for u, p in data["gebruikers"].items():
        training = tuple(Interactie(i["item"], tijd(i["datePlayed"]), i["favoriet"]) for i in p["training"])
        profielen[u] = Profiel(tijd(p["T_splitsing"]), training, frozenset(p["test"]), kind if p["kind"] else frozenset(cat))
    return Dataset("D-SYN", vast["set_sha256"], cat, profielen)


def _csv(z: zipfile.ZipFile, naam: str) -> Iterator[dict[str, str]]:
    with z.open("ml-latest-small/" + naam + ".csv") as bron, io.TextIOWrapper(bron, encoding="utf-8-sig", newline="") as tekst:
        yield from csv.DictReader(tekst)


def splitmoment(positieven: Iterable[list[int]]) -> tuple[int, int]:
    """Sweep over hele seconden. Een gebruiker telt mee vanaf de vijfde positieve + 1 tot exclusief de voorlaatste."""
    grenzen = Counter()
    for tijden in positieven:
        tijden = sorted(tijden)
        if len(tijden) >= 7 and tijden[4] + 1 < tijden[-2]:
            grenzen[tijden[4] + 1] += 1
            grenzen[tijden[-2]] -= 1
    beste_t, hoogste, aantal = 0, 0, 0
    for t, delta in sorted(grenzen.items()):
        aantal += delta
        if aantal > hoogste:
            beste_t, hoogste = t, aantal
    if hoogste == 0:
        raise ValueError("geen gebruiker met vijf positieven vóór en twee na hetzelfde T")
    return beste_t, hoogste


def lees_dml(archief: Path, *, validatie_voor: int | None = None) -> Dataset:
    if manifest.sha256_bestand(lokaal(archief)) != ARCHIEF_SHA:
        raise ValueError("D-ML-archief wijkt af van de vastgelegde SHA-256")
    with zipfile.ZipFile(archief) as z:
        return splits_dml(z, validatie_voor=validatie_voor)


def splits_dml(z: zipfile.ZipFile, *, validatie_voor: int | None = None) -> Dataset:
    beoordelingen = [(r["userId"], r["movieId"], float(r["rating"]), int(r["timestamp"])) for r in _csv(z, "ratings")
                     if validatie_voor is None or int(r["timestamp"]) < validatie_voor]
    positieven = defaultdict(list)
    for u, _, waarde, ts in beoordelingen:
        if waarde >= 4:
            positieven[u].append(ts)
    if validatie_voor is None:
        t, bovengrens = splitmoment(positieven.values())
    else:
        # Alle gelijktijdige beoordelingen bij de grens zitten samen aan de validatiekant.
        tijden = sorted(ts for _, _, _, ts in beoordelingen)
        if not tijden:
            raise ValueError("lege training vóór het vastgelegde T")
        t, bovengrens = tijden[9 * len(tijden) // 10], None
    titels = {r["movieId"]: r for r in _csv(z, "movies")}
    films, trainingen, holdouts = {}, defaultdict(list), defaultdict(set)
    for u, item, waarde, ts in beoordelingen:
        if ts < t:
            if item not in films:
                rij = titels[item]
                genres = frozenset(rij["genres"].split("|")) - {"(no genres listed)"}
                films[item] = Film(rij["title"], genres, ts, 0, 0.0)
            f = films[item]
            f.eerste = min(f.eerste, ts)
            f.aantal += 1
            f.som += waarde
            trainingen[u].append(Interactie(item, ts, waarde >= 4))
        elif waarde >= 4 and (ts > t or validatie_voor is not None):
            holdouts[u].add(item)
    for r in _csv(z, "tags"):
        if int(r["timestamp"]) < t and r["movieId"] in films:
            films[r["movieId"]].tags.add(r["tag"])
    catalogus = {k: Item("Movie", f.genres) for k, f in films.items()}
    toegang = frozenset(catalogus)
    profielen = {}
    for u, training in trainingen.items():
        holdout = (holdouts[u] & toegang) - {i.item for i in training}
        if sum(i.favoriet for i in training) >= 5 and len(holdout) >= 2:
            profielen[u] = Profiel(t, tuple(sorted(training, key=lambda i: (i.tijd, i.item))), frozenset(holdout), toegang)
    # Ook een deler zonder latere holdout telt mee. Selectie van delers op latere activiteit zou lekken.
    return Dataset("D-ML", ARCHIEF_SHA, catalogus, profielen, films, t, bovengrens,
                   {u: tuple(training) for u, training in trainingen.items()})


def schrijf_dml_stubs(dataset: Dataset, stub: Path, doel: Path) -> None:
    """Schrijf de lokale proefbibliotheek in een nieuwe map. De aanroeper beheert de tijdelijke bovenliggende map."""
    doel = lokaal(doel)
    if dataset.naam != "D-ML" or not dataset.films:
        raise ValueError("geen D-ML-films")
    if shutil.disk_usage(doel.parent).free < len(dataset.films) * (stub.stat().st_size + 16384):
        raise OSError("te weinig vrije ruimte voor de stubbibliotheek")
    doel.mkdir()
    for item, f in dataset.films.items():
        if not item.isascii() or not item.isdecimal():
            raise ValueError("ongeldig filmnummer")
        map_ = doel / item
        map_.mkdir()
        shutil.copyfile(stub, map_ / f"{item}.mkv")
        film = ET.Element("movie")
        film.append(ET.Comment(MARKERING))
        ET.SubElement(film, "uniqueid", type="dml", default="true").text = item
        ET.SubElement(film, "title").text = f.titel
        ET.SubElement(film, "dateadded").text = utc(f.eerste).replace("T", " ").removesuffix("Z")
        ET.SubElement(film, "rating").text = format(2 * f.som / f.aantal, ".4f")
        for groep, waarden in (("genre", f.genres), ("tag", f.tags)):
            for waarde in sorted(waarden):
                ET.SubElement(film, groep).text = waarde
        ET.ElementTree(film).write(map_ / f"{item}.nfo", encoding="utf-8", xml_declaration=True)
