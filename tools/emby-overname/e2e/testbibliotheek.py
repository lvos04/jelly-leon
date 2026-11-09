"""Recept van de testbibliotheek voor de proefrun (JLT-70…72) — met opzettelijke gaten — en het opbouwen ervan.

Twee bomen, één per server: `emby/` (gekoppeld als `/mnt/emby/media`) en `jl/` (als `/data/media`), zodat ook de
padvertaling (mountroot) beproefd wordt. Modus `corpus`: harde links naar het lokale mediacorpus (B03-016; niets
gekopieerd, de bron blijft ongewijzigd; alleen lokaal, BG-37). Modus `synthetisch`: kleine, zelfgemaakte clips met
ffmpeg (CI; geen auteursrechtelijk materiaal). In beide modi komen de provider-ID's uit NFO-bestanden en staan de
internet-metadatabronnen uit, zodat de proef reproduceerbaar is. Na de proef wordt de testset weggegooid (BG-38); alleen
dit recept en het manifest in het bewijs blijven.

Verwachte uitkomst per item (`verwacht`): `gekoppeld` (met het verwachte Jelly Leon-pad) of een set toegestane redenen
voor de afhandellijst. `onzeker`: gekoppeld aan precies het juiste bestand óf op de afhandellijst — nooit iets anders.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

FILMS = "Films"
SERIES = "Series"


@dataclass
class Media:
    corpus: str | None  # pad binnen het mediacorpus
    duur: int  # seconden (synthetisch)
    audio: tuple[str, ...] = ("eng",)
    ondertitels: tuple[str, ...] = ()
    toon: int = 440


@dataclass
class Plek:
    pad: str  # relatief binnen de boom
    media: Media
    nfo: dict[str, Any] | None = None


@dataclass
class Item:
    sleutel: str
    soort: str  # film | aflevering
    emby: Plek | None
    jl: list[Plek] = field(default_factory=list)
    verwacht: str = "gekoppeld"  # gekoppeld | afhandellijst | onzeker
    redenen: tuple[str, ...] = ()
    jl_doel: str | None = None  # verwacht Jelly Leon-pad bij gekoppeld/onzeker


def _film(titel: str, jaar: int, ext: str) -> str:
    return f"{FILMS}/{titel} ({jaar})/{titel} ({jaar}).{ext}"


SINTEL = Media("bron/blender/sintel/Sintel.2010.1080p.mkv", 90, ("eng",), ("ger", "eng", "dut"), 440)
BBB = Media("bron/blender/bbb/uitgepakt/bbb_sunflower_1080p_30fps_normal.mp4", 60, ("eng", "eng"), (), 470)
ED = Media("bron/blender/ed/elephantsdream-720-h264-st-aac.mov", 70, ("eng",), (), 500)
TOS = Media("bron/blender/tos/uitgepakt/tears_of_steel_1080p.mov", 65, ("eng",), (), 530)
TOS_MULTI = Media("afgeleid/formaten/tos-multiaudio-5.1-me-subs.mkv", 66, ("eng", "eng", "zxx"), ("nld", "eng"), 560)
COSMOS = Media("bron/blender/cosmos/Cosmos_Laundromat_First_Cycle_2k.mp4", 80, ("eng",), (), 590)
LLAMA = Media("bron/blender/caminandes/01_llama_drama_1080p.mp4", 45, ("eng",), (), 620)
HERO = Media("bron/blender/hero/hero.mp4", 50, ("eng",), (), 650)
SPRING = Media("bron/blender/spring/Spring-Blender-Open-Movie.mkv", 55, ("eng",), (), 680)
KORT_EMBY = Media("afgeleid/kwaliteit/sintel-60s-referentie.mkv", 60, ("eng",), ("nld", "eng"), 710)
KORT_JL = Media("afgeleid/kwaliteit/sintel-60s-afgekapt-70pct.mkv", 42, ("eng",), ("nld", "eng"), 710)


def recept() -> list[Item]:
    items: list[Item] = [
        Item("sintel", "film", Plek(_film("Sintel", 2010, "mkv"), SINTEL,
                                    {"imdb": "tt1727587", "tmdb": "45745", "mpaa": "PG-13", "titel": "Sintel", "jaar": 2010}),
             [Plek(_film("Sintel", 2010, "mkv"), SINTEL,
                   {"imdb": "tt1727587", "tmdb": "45745", "mpaa": "PG-13", "titel": "Sintel", "jaar": 2010})]),
        # Provider-ID gaat vóór het pad: in Jelly Leon staat dezelfde film in een andere map.
        Item("bbb", "film", Plek(_film("Big Buck Bunny", 2008, "mp4"), BBB,
                                 {"imdb": "tt1254207", "tmdb": "10378", "mpaa": "G", "titel": "Big Buck Bunny", "jaar": 2008}),
             [Plek(f"{FILMS}/Big Buck Bunny/Big Buck Bunny (2008).mp4", BBB,
                   {"imdb": "tt1254207", "tmdb": "10378", "mpaa": "G", "titel": "Big Buck Bunny", "jaar": 2008})],
             jl_doel=f"{FILMS}/Big Buck Bunny/Big Buck Bunny (2008).mp4"),
        Item("ed", "film", Plek(_film("Elephants Dream", 2006, "mov"), ED,
                                {"imdb": "tt0807840", "tmdb": "9761", "mpaa": "PG", "tag": "Horror", "titel": "Elephants Dream",
                                 "jaar": 2006}),
             [Plek(_film("Elephants Dream", 2006, "mov"), ED,
                   {"imdb": "tt0807840", "tmdb": "9761", "mpaa": "PG", "tag": "Horror", "titel": "Elephants Dream", "jaar": 2006})]),
        # Twee items met dezelfde IMDb-ID (versies): het pad wijst er precies één aan.
        Item("tos", "film", Plek(_film("Tears of Steel", 2012, "mov"), TOS,
                                 {"imdb": "tt2285752", "mpaa": "PG-13", "titel": "Tears of Steel", "jaar": 2012}),
             [Plek(_film("Tears of Steel", 2012, "mov"), TOS,
                   {"imdb": "tt2285752", "mpaa": "PG-13", "titel": "Tears of Steel", "jaar": 2012})]),
        Item("tos_multi", "film", Plek(_film("Tears of Steel Multiaudio", 2012, "mkv"), TOS_MULTI,
                                       {"imdb": "tt2285752", "mpaa": "PG-13", "titel": "Tears of Steel Multiaudio", "jaar": 2012}),
             [Plek(_film("Tears of Steel Multiaudio", 2012, "mkv"), TOS_MULTI,
                   {"imdb": "tt2285752", "mpaa": "PG-13", "titel": "Tears of Steel Multiaudio", "jaar": 2012})]),
        # Ontbreekt in Jelly Leon.
        Item("cosmos", "film", Plek(_film("Cosmos Laundromat", 2015, "mp4"), COSMOS,
                                    {"imdb": "tt4957236", "tmdb": "358332", "mpaa": "PG-13", "titel": "Cosmos Laundromat", "jaar": 2015}),
             [], verwacht="afhandellijst", redenen=("ontbreekt",)),
        # Geen provider-ID's: koppelen op het (vertaalde) pad.
        Item("llama", "film", Plek(_film("Caminandes Llama Drama", 2013, "mp4"), LLAMA),
             [Plek(_film("Caminandes Llama Drama", 2013, "mp4"), LLAMA)]),
        # Geen provider-ID's en in Jelly Leon onder een andere naam: niet te koppelen.
        Item("hero", "film", Plek(_film("Hero", 2018, "mp4"), HERO),
             [Plek(_film("Hero Blender Studio", 2018, "mp4"), HERO)], verwacht="afhandellijst", redenen=("geen_id",)),
        # Dezelfde IMDb-ID op twee Jelly Leon-items en geen passend pad: dubbel.
        Item("spring", "film", Plek(_film("Spring", 2019, "mkv"), SPRING, {"imdb": "tt10200208", "titel": "Spring", "jaar": 2019}),
             [Plek(_film("Spring A", 2019, "mkv"), SPRING, {"imdb": "tt10200208", "titel": "Spring A", "jaar": 2019}),
              Plek(_film("Spring B", 2019, "mkv"), SPRING, {"imdb": "tt10200208", "titel": "Spring B", "jaar": 2019})],
             verwacht="afhandellijst", redenen=("dubbel",)),
        # Zelfde pad en ID, ander bestand (andere grootte): kijkgegevens wel, spoorkeuze niet (ander_bestand).
        Item("kort", "film", Plek(_film("Sintel Kort", 2010, "mkv"), KORT_EMBY,
                                  {"imdb": "tt9900100", "titel": "Sintel Kort", "jaar": 2010}),
             [Plek(_film("Sintel Kort", 2010, "mkv"), KORT_JL, {"imdb": "tt9900100", "titel": "Sintel Kort", "jaar": 2010})]),
    ]
    # Serie met seizoenen: afleveringen zonder eigen ID → serie-ID + seizoen + aflevering.
    for seizoen, aflevering in ((1, 1), (1, 2), (1, 3), (2, 1), (2, 2)):
        rel = f"{SERIES}/B03 Testserie/Season {seizoen:02d}/B03 Testserie S{seizoen:02d}E{aflevering:02d}.mkv"
        media = Media(f"afgeleid/series/B03 Testserie/Season {seizoen:02d}/B03 Testserie S{seizoen:02d}E{aflevering:02d}.mkv",
                      30 + seizoen * 5 + aflevering, ("eng",), (), 300 + 10 * aflevering)
        items.append(Item(f"testserie_s{seizoen}e{aflevering}", "aflevering", Plek(rel, media), [Plek(rel, media)]))
    # Anime met absolute nummering in Emby en seizoenen in Jelly Leon.
    anime = {n: Media(f"afgeleid/series/B03 Anime/Season 01/B03 Anime S01E{n:02d}.mkv", 25 + n, ("jpn",), ("eng",), 800 + 20 * n)
             for n in (1, 2, 3)}
    for n, jl_rel in ((1, f"{SERIES}/B03 Anime/Season 01/B03 Anime S01E01.mkv"), (2, f"{SERIES}/B03 Anime/Season 01/B03 Anime S01E02.mkv"),
                      (3, f"{SERIES}/B03 Anime/Season 02/B03 Anime S02E01.mkv")):
        items.append(Item(f"anime_{n}", "aflevering", Plek(f"{SERIES}/B03 Anime/B03 Anime - {n:02d}.mkv", anime[n]), [Plek(jl_rel, anime[n])],
                          verwacht="onzeker" if n < 3 else "afhandellijst", redenen=("ontbreekt", "geen_id", "dubbel"), jl_doel=jl_rel))
    # Echte serie (Pioneer One; CC BY-NC-SA, alleen lokaal — in CI synthetisch).
    for n in range(1, 7):
        rel = f"{SERIES}/Pioneer One/Season 01/Pioneer One S01E{n:02d}.mp4"
        media = Media(f"bron/pioneer-one/Pioneer.One.S01E{n:02d}.720p.x264-VODO.mp4", 40 + n, ("eng",), (), 900 + 15 * n)
        items.append(Item(f"pioneer_e{n}", "aflevering", Plek(rel, media), [Plek(rel, media)]))
    return items


SERIE_NFO = {
    "B03 Testserie": {"tvdb": "990001", "mpaa": "TV-PG"},
    "B03 Anime": {"tvdb": "990002"},
    "Pioneer One": {"tvdb": "990003", "mpaa": "TV-14"},
}


def _nfo_film(n: dict[str, Any]) -> str:
    regels = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>', "<movie>", f"  <title>{n['titel']}</title>",
              f"  <year>{n['jaar']}</year>"]
    if n.get("mpaa"):
        regels.append(f"  <mpaa>{n['mpaa']}</mpaa>")
    for soort in ("imdb", "tmdb"):
        if n.get(soort):
            regels.append(f'  <uniqueid type="{soort}"{" default=\"true\"" if soort == "imdb" else ""}>{n[soort]}</uniqueid>')
            regels.append(f"  <{soort}id>{n[soort]}</{soort}id>")
    if n.get("tag"):
        regels.append(f"  <tag>{n['tag']}</tag>")
    regels.append("</movie>")
    return "\n".join(regels) + "\n"


def _nfo_serie(titel: str, n: dict[str, Any]) -> str:
    regels = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>', "<tvshow>", f"  <title>{titel}</title>",
              f'  <uniqueid type="tvdb" default="true">{n["tvdb"]}</uniqueid>', f"  <tvdbid>{n['tvdb']}</tvdbid>"]
    if n.get("mpaa"):
        regels.append(f"  <mpaa>{n['mpaa']}</mpaa>")
    regels.append("</tvshow>")
    return "\n".join(regels) + "\n"


def _srt(taal: str) -> str:
    return f"1\n00:00:01,000 --> 00:00:04,000\nOndertitel ({taal})\n\n2\n00:00:05,000 --> 00:00:08,000\nTweede regel ({taal})\n"


def maak_synthetisch(media: Media, doel: Path, ffmpeg: list[str], werk: Path, koppelpunt: Path) -> None:
    """Kleine clip met testbeeld, één of meer sinustonen (met taaltag) en ingebedde ondertitels; deterministisch."""
    doel.parent.mkdir(parents=True, exist_ok=True)
    werk.mkdir(parents=True, exist_ok=True)
    args = ["-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
            f"testsrc2=size=320x180:rate=10:duration={media.duur}"]
    for i, _ in enumerate(media.audio):
        args += ["-f", "lavfi", "-i", f"sine=frequency={media.toon + 37 * i}:duration={media.duur}:sample_rate=22050"]
    srt_bestanden = []
    for taal in media.ondertitels:
        srt = werk / f"{taal}.srt"
        srt.write_text(_srt(taal), encoding="utf-8")
        srt_bestanden.append(srt)
        args += ["-i", str(srt) if ffmpeg[0] != "docker" else f"/w/{srt.relative_to(koppelpunt).as_posix()}"]
    args += ["-map", "0:v"]
    for i in range(len(media.audio)):
        args += ["-map", f"{i + 1}:a"]
    for i in range(len(media.ondertitels)):
        args += ["-map", f"{len(media.audio) + 1 + i}:s"]
    ext = doel.suffix.lower()
    args += ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "38", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "32k",
             "-threads", "1", "-fflags", "+bitexact", "-flags:v", "+bitexact", "-flags:a", "+bitexact"]
    if media.ondertitels:
        args += ["-c:s", "srt" if ext == ".mkv" else "mov_text"]
    for i, taal in enumerate(media.audio):
        args += [f"-metadata:s:a:{i}", f"language={taal}"]
    for i, taal in enumerate(media.ondertitels):
        args += [f"-metadata:s:s:{i}", f"language={taal}"]
    if ffmpeg[0] == "docker":
        uitvoer = f"/w/{doel.relative_to(koppelpunt).as_posix()}"  # koppelpunt = de map die als /w is gekoppeld
    else:
        uitvoer = str(doel)
    subprocess.run([*ffmpeg, *args, uitvoer], check=True, capture_output=True, timeout=300)


def _sha256(pad: Path) -> str:
    h = hashlib.sha256()
    with pad.open("rb") as f:
        for blok in iter(lambda: f.read(1 << 20), b""):
            h.update(blok)
    return h.hexdigest()


def bouw(modus: str, basis: Path, corpus: Path | None, ffmpeg: list[str] | None) -> dict[str, Any]:
    """Bouwt `basis/emby` en `basis/jl`; geeft een manifest terug (per bestand: boom, pad, bron, grootte, sha256)."""
    if basis.exists():
        shutil.rmtree(basis)
    (basis / "emby").mkdir(parents=True)
    (basis / "jl").mkdir(parents=True)
    gemaakt: dict[str, Path] = {}
    manifest: list[dict[str, Any]] = []
    corpus_sha: dict[str, str] = {}
    if modus == "corpus":
        assert corpus is not None
        for lijst in ("SHA256SUMS.bron.txt", "SHA256SUMS.afgeleid.txt"):
            for regel in (corpus / lijst).read_text(encoding="utf-8").splitlines():
                if regel.strip():
                    som, naam = regel.split(None, 1)
                    prefix = "bron/" if "bron" in lijst else "afgeleid/"
                    corpus_sha[prefix + naam.lstrip("*").removeprefix("./")] = som

    def plaats(boom: str, plek: Plek) -> None:
        doel = basis / boom / plek.pad
        doel.parent.mkdir(parents=True, exist_ok=True)
        if modus == "corpus":
            bron = corpus / plek.media.corpus  # type: ignore[operator]
            if os.stat(bron).st_dev != os.stat(doel.parent).st_dev:
                raise RuntimeError("harde links vragen hetzelfde bestandssysteem als het corpus")
            os.link(bron, doel)
            herkomst = plek.media.corpus
        else:
            sleutel = f"{plek.media.corpus}|{plek.media.duur}"
            if sleutel not in gemaakt:
                maak_synthetisch(plek.media, doel, ffmpeg or [], basis / "_werk" / f"{len(gemaakt)}", basis)
                gemaakt[sleutel] = doel
            else:
                os.link(gemaakt[sleutel], doel)
            herkomst = f"synthetisch ({plek.media.duur} s, audio {','.join(plek.media.audio)}, ondertitels {','.join(plek.media.ondertitels)})"
        if plek.nfo:
            doel.with_suffix(".nfo").write_text(_nfo_film(plek.nfo), encoding="utf-8")
        manifest.append({"boom": boom, "pad": plek.pad, "bron": herkomst, "grootte": doel.stat().st_size})

    items = recept()
    for item in items:
        if item.emby:
            plaats("emby", item.emby)
        for plek in item.jl:
            plaats("jl", plek)
    for boom in ("emby", "jl"):
        for titel, nfo in SERIE_NFO.items():
            map_pad = basis / boom / SERIES / titel
            if map_pad.is_dir():
                (map_pad / "tvshow.nfo").write_text(_nfo_serie(titel, nfo), encoding="utf-8")
    if (basis / "_werk").exists():
        shutil.rmtree(basis / "_werk")
    controle = []
    if modus == "corpus":
        for bron in sorted({i.emby.media.corpus for i in items if i.emby} | {p.media.corpus for i in items for p in i.jl}):
            verwacht = corpus_sha.get(bron)  # type: ignore[arg-type]
            gemeten = _sha256(corpus / bron)  # type: ignore[operator]
            controle.append({"bron": bron, "sha256": gemeten, "manifest": verwacht, "klopt": verwacht == gemeten})
    return {"modus": modus, "bestanden": manifest, "corpuscontrole": controle}
