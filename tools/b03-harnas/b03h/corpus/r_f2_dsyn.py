"""F2 — D-SYN (B03 2.0 F2.9.3): stub-bibliotheek met NFO-metadata en drie huishoudens met een verborgen voorkeur.

300 stub-items (1 s ``testsrc2`` + ``anullsrc``, ~10 KB per mkv) met genres, tags, personen en type (anime via genre);
drie huishoudens (gezin met kind, stel, single anime-fan) met een gescripte voorkeur in kenmerken die stock én F2 zien,
plus tijdstempels. De grondwaarheid bevat de trainingsgeschiedenis (te zaaien via ``POST /UserPlayedItems/{id}?datePlayed=``)
en per gebruiker de achtergehouden testitems. Alles synthetisch: geen beperkte licentie.
"""

from __future__ import annotations

import math
import shutil
from datetime import UTC, datetime, timedelta
from xml.sax.saxutils import escape

from .basis import Context
from .ffmpeg import BITEXACT

GENRES = ["Animatie", "Familie", "Avontuur", "Drama", "Thriller", "Misdaad", "Komedie", "Sciencefiction", "Fantasy",
          "Documentaire", "Horror", "Romantiek", "Anime"]
TAGS = ["mecha", "slice of life", "roadmovie", "rechtbank", "ruimte", "draken", "tijdreizen", "kerst", "sport",
        "muziek", "dieren", "heist", "school", "zee", "bergen"]
VOORNAMEN = ["Anna", "Bram", "Cor", "Daan", "Eva", "Femke", "Gijs", "Hanna", "Isa", "Joris", "Kees", "Lotte", "Mila",
             "Noor", "Olaf", "Pim", "Roos", "Sem", "Tess", "Vince"]
ACHTERNAMEN = ["de Vries", "Jansen", "Bakker", "Visser", "Smit", "Meijer", "Mulder", "de Boer", "Bos", "Peters"]
KEUREN = ["AL", "6", "9", "12", "14", "16"]
T0 = datetime(2026, 5, 1, tzinfo=UTC)

HUISHOUDENS = {
    "gezin_met_kind": {
        "ouder1": {"genres": {"Familie": 2.0, "Avontuur": 1.2, "Drama": 0.8}, "tags": {"dieren": 1.0}},
        "ouder2": {"genres": {"Komedie": 1.6, "Familie": 1.4, "Romantiek": 0.8}, "tags": {"kerst": 1.0}},
        "kind": {"genres": {"Animatie": 2.5, "Familie": 1.5}, "tags": {"draken": 1.2, "dieren": 1.0}, "max_keur": "9"},
    },
    "stel": {
        "partner1": {"genres": {"Thriller": 2.0, "Misdaad": 1.6}, "tags": {"heist": 1.2, "rechtbank": 0.8}},
        "partner2": {"genres": {"Drama": 2.0, "Romantiek": 1.2}, "tags": {"roadmovie": 1.0}},
    },
    "anime_fan": {
        "fan": {"genres": {"Anime": 3.0, "Sciencefiction": 1.0}, "tags": {"mecha": 1.5, "slice of life": 1.0}},
    },
}


def _persoon(rng) -> str:
    return f"{rng.choice(VOORNAMEN)} {rng.choice(ACHTERNAMEN)}"


def maak(ctx: Context) -> None:
    ctx.synthetisch()
    rng = ctx.rng
    aantal = int(ctx.parameters.get("items", 300 if ctx.vol else 12))
    stub_tmp = ctx.uit / ".stub.mkv"
    ctx.ff.ffmpeg(["-f", "lavfi", "-i", "testsrc2=s=320x180:r=24:d=1", "-f", "lavfi", "-i",
                   "anullsrc=r=48000:cl=stereo:d=1", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "35",
                   "-c:a", "aac", "-b:a", "32k", "-shortest", *BITEXACT, str(stub_tmp)])
    regisseurs = [_persoon(rng) for _ in range(25)]
    acteurs = [_persoon(rng) for _ in range(80)]
    items = []
    n_series = max(1, aantal // 15)
    afleveringen = 3
    n_films = aantal - n_series * afleveringen
    for i in range(n_films + n_series):
        is_serie = i >= n_films
        genres = rng.sample(GENRES, k=rng.choice([1, 2, 2, 3]))
        if "Anime" in genres and "Animatie" not in genres:
            genres.append("Animatie")
        item = {"id": f"dsyn-{i:04d}", "type": "Series" if is_serie else "Movie",
                "titel": f"{'Serie' if is_serie else 'Film'} {i:04d} {rng.choice(TAGS).title()}",
                "jaar": rng.randint(1985, 2025), "genres": sorted(set(genres)), "tags": sorted(rng.sample(TAGS, k=2)),
                "regisseur": rng.choice(regisseurs), "acteurs": rng.sample(acteurs, k=3),
                "keur": "AL" if "Animatie" in genres and rng.random() < 0.7 else rng.choice(KEUREN),
                "toegevoegd": (T0 - timedelta(days=rng.randint(0, 400))).strftime("%Y-%m-%dT%H:%M:%SZ")}
        items.append(item)
        if is_serie:
            map_ = f"Series/{item['titel']}"
            ctx.tekst(f"{map_}/tvshow.nfo", _nfo("tvshow", item))
            for e in range(1, afleveringen + 1):
                rel = f"{map_}/Season 01/{item['titel']} S01E{e:02d}.mkv"
                shutil.copyfile(stub_tmp, ctx.pad(rel))
                ep = {**item, "titel": f"{item['titel']} aflevering {e}"}
                ctx.tekst(rel.removesuffix(".mkv") + ".nfo", _nfo("episodedetails", ep, seizoen=1, aflevering=e))
                ctx.tel("stub-aflevering")
        else:
            naam = f"{item['titel']} ({item['jaar']})"
            shutil.copyfile(stub_tmp, ctx.pad(f"Films/{naam}/{naam}.mkv"))
            ctx.tekst(f"Films/{naam}/{naam}.nfo", _nfo("movie", item))
            ctx.tel("stub-film")
    stub_tmp.unlink()

    keur_rang = {k: i for i, k in enumerate(KEUREN)}
    gebruikers = {}
    for huishouden, leden in HUISHOUDENS.items():
        for naam, voorkeur in leden.items():
            toegestaan = [it for it in items if keur_rang[it["keur"]] <= keur_rang[voorkeur.get("max_keur", "16")]]

            def score(it, vk=voorkeur):
                return (sum(vk["genres"].get(g, 0.0) for g in it["genres"]) + sum(vk["tags"].get(t, 0.0) for t in it["tags"]))

            gewichten = [math.exp(score(it)) for it in toegestaan]
            gekozen: list[dict] = []
            pool = list(zip(toegestaan, gewichten, strict=True))
            for _ in range(min(int(ctx.parameters.get("interacties", 30 if ctx.vol else 6)), len(pool))):
                totaal = sum(w for _, w in pool)
                r, acc = rng.random() * totaal, 0.0
                for j, (it, w) in enumerate(pool):
                    acc += w
                    if acc >= r:
                        gekozen.append(it)
                        pool.pop(j)
                        break
            moment = T0
            geschiedenis = []
            for it in gekozen:
                moment += timedelta(hours=rng.randint(6, 96))
                geschiedenis.append({"item": it["id"], "datePlayed": moment.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                     "favoriet": score(it) >= 3.0 and rng.random() < 0.4})
            k_test = max(1, len(geschiedenis) // 6)
            gebruikers[naam] = {"huishouden": huishouden, "kind": naam == "kind",
                                "verborgen_voorkeur": voorkeur, "training": geschiedenis[:-k_test],
                                "test": [g["item"] for g in geschiedenis[-k_test:]],
                                "T_splitsing": geschiedenis[-k_test]["datePlayed"]}
            ctx.tel("gebruiker")
    ctx.json("grondwaarheid.json", {
        "recept": "f2-dsyn", "items": items, "gebruikers": gebruikers,
        "regels": {"splitsing": "per gebruiker de laatste ~1/6 interacties als test (leave-last-out); zaaien alleen "
                                "training via POST /UserPlayedItems/{id}?datePlayed=",
                   "kind": "kind krijgt alleen items met keur ≤ 9; aanbevelingen voor kind nooit buiten die grens",
                   "spike_vooraf": "hoe Jellyfin met stubs van 1 s omgaat (scannen, Played, MaxResumePct) wordt in B03-030 "
                                   "gemeten en in EVIDENCE gezet; niet aangenomen"},
    })


def _nfo(soort: str, it: dict, seizoen: int | None = None, aflevering: int | None = None) -> str:
    regels = ["<?xml version=\"1.0\" encoding=\"utf-8\"?>", f"<{soort}>", f"  <title>{escape(it['titel'])}</title>",
              f"  <year>{it['jaar']}</year>", f"  <mpaa>NL-{it['keur']}</mpaa>",
              f"  <uniqueid type=\"dsyn\" default=\"true\">{it['id']}</uniqueid>",
              f"  <dateadded>{it['toegevoegd'].replace('T', ' ').removesuffix('Z')}</dateadded>"]
    regels += [f"  <genre>{escape(g)}</genre>" for g in it["genres"]]
    regels += [f"  <tag>{escape(t)}</tag>" for t in it["tags"]]
    regels.append(f"  <director>{escape(it['regisseur'])}</director>")
    regels += [f"  <actor><name>{escape(a)}</name><type>Actor</type></actor>" for a in it["acteurs"]]
    if seizoen is not None:
        regels += [f"  <season>{seizoen}</season>", f"  <episode>{aflevering}</episode>"]
    regels.append(f"</{soort}>")
    return "\n".join(regels) + "\n"
