"""Differentiële controle-run (B03 2.0 §10.15; gedeeld gereedschap voor JLT-65 en de gegevensbescherming).

Twee systemen (standaard: stock tegen stock; later stock tegen Jelly Leon) krijgen exact hetzelfde scenario op **kopieën
van dezelfde datamap**. Daarna worden de echte 12.x-tabellen (``BaseItems``, ``UserData``, ``Users``, … — een tabel
``Items`` bestaat in 12.x niet) rij voor rij vergeleken. Alleen de vaste uitzonderingen (tijdstempels van activiteit,
tokens) en de toegestane wijzigingslijst per module mogen verschillen. Waarden van geheime kolommen komen nooit in het
rapport.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import meetslot
from .jfapi import CLIENT, Http
from .stock import GEBRUIKER, STOCK_IMAGE, WACHTWOORD, WERK, StockServer

REPO = Path(__file__).resolve().parents[3]
# Vaste uitzonderingen (plan: "Users.LastActivityDate en BaseItems.DateLastSaved e.d. veranderen altijd").
VASTE_UITZONDERINGEN: dict[str, set[str]] = {
    "Users": {"LastActivityDate", "LastLoginDate", "RowVersion", "InvalidLoginAttemptCount"},
    "BaseItems": {"DateLastSaved", "DateLastRefreshed", "DateLastMediaAdded"},
    "Devices": {"AccessToken", "DateLastActivity", "DateModified", "DateCreated", "Id"},
    "DeviceOptions": {"Id"},
    "ActivityLogs": {"DateCreated", "Id", "ShortOverview", "Overview", "RowVersion"},
    "UserData": {"LastPlayedDate"},
    "__EFMigrationsHistory": set(),
}
GEHEIM = {("Devices", "AccessToken"), ("ApiKeys", "AccessToken"), ("Users", "Password"), ("Users", "EasyPassword")}
VASTE_DATUM = "2026-01-02T03:04:05.0000000Z"


def _rijen(db: Path) -> dict[str, tuple[list[str], list[tuple]]]:
    with tempfile.TemporaryDirectory() as tmp:
        for f in db.parent.glob(db.name + "*"):
            shutil.copy2(f, Path(tmp) / f.name)
        con = sqlite3.connect(Path(tmp) / db.name)
        try:
            tabellen = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
            uit = {}
            for t in tabellen:
                cur = con.execute(f'SELECT * FROM "{t}"')  # noqa: S608 - tabelnaam uit sqlite_master
                kolommen = [c[0] for c in cur.description]
                uit[t] = (kolommen, [tuple(r) for r in cur.fetchall()])
            return uit
        finally:
            con.close()


def vergelijk(db_a: Path, db_b: Path, toegestaan: dict[str, set[str]] | None = None) -> dict[str, Any]:
    """Vergelijkt twee datamappen-databases. Rijen worden gematcht op alle kolommen behalve de uitzonderingen."""
    uitz = {t: set(k) for t, k in VASTE_UITZONDERINGEN.items()}
    for t, k in (toegestaan or {}).items():
        uitz.setdefault(t, set()).update(k)
    a, b = _rijen(db_a), _rijen(db_b)
    rapport: dict[str, Any] = {"tabellen": {}, "verschillen_buiten_uitzonderingen": 0, "uitzonderingen_geraakt": {}}
    for t in sorted(set(a) | set(b)):
        if t not in a or t not in b:
            rapport["tabellen"][t] = {"fout": "tabel ontbreekt in " + ("a" if t not in a else "b")}
            rapport["verschillen_buiten_uitzonderingen"] += 1
            continue
        ka, ra = a[t]
        kb, rb = b[t]
        if ka != kb:
            rapport["tabellen"][t] = {"fout": "kolommen verschillen"}
            rapport["verschillen_buiten_uitzonderingen"] += 1
            continue
        genegeerd = [i for i, k in enumerate(ka) if k in uitz.get(t, set())]
        vergeleken = [i for i in range(len(ka)) if i not in genegeerd]

        def sleutel(rij: tuple, vergeleken: list[int] = vergeleken) -> tuple:
            return tuple(rij[i] for i in vergeleken)

        sa = sorted(map(sleutel, ra), key=repr)
        sb = sorted(map(sleutel, rb), key=repr)
        alleen_a = [r for r in sa if r not in sb]
        alleen_b = [r for r in sb if r not in sa]
        geraakt = []
        if genegeerd and len(ra) == len(rb):
            for i in genegeerd:
                if sorted(map(repr, (r[i] for r in ra))) != sorted(map(repr, (r[i] for r in rb))):
                    geraakt.append(ka[i])
        if geraakt:
            rapport["uitzonderingen_geraakt"][t] = geraakt
        info: dict[str, Any] = {"rijen_a": len(ra), "rijen_b": len(rb), "genegeerde_kolommen": [ka[i] for i in genegeerd]}
        if alleen_a or alleen_b:
            verborgen = {i for i, k in enumerate([ka[j] for j in vergeleken]) if (t, k) in GEHEIM}
            info["alleen_in_a"] = [_toon(r, verborgen) for r in alleen_a[:5]]
            info["alleen_in_b"] = [_toon(r, verborgen) for r in alleen_b[:5]]
            info["verschil_rijen"] = len(alleen_a) + len(alleen_b)
            rapport["verschillen_buiten_uitzonderingen"] += len(alleen_a) + len(alleen_b)
        rapport["tabellen"][t] = info
    return rapport


def _toon(rij: tuple, verborgen: set[int]) -> list[Any]:
    return ["<geheim>" if i in verborgen else (v if not isinstance(v, bytes) else f"<{len(v)} bytes>") for i, v in enumerate(rij)]


# --- scenario ---------------------------------------------------------------------------------------------------

def scenario(server: StockServer, extra: bool = False) -> dict[str, Any]:
    """Zelfde handelingen op elk systeem: gezien (vaste datum), favoriet, beoordeling, hervatpunt met spoorkeuze.

    ``extra`` (alleen voor de negatieve proef) voegt op één systeem één favoriet toe: de vergelijking moet dat vinden."""
    jf = server.jf
    assert jf
    jf.login(GEBRUIKER, WACHTWOORD)
    uid = jf.admin_id
    items = sorted(jf.items(), key=lambda i: i["Path"])
    log = []
    for i, it in enumerate(items):
        iid = it["Id"]
        if i % 3 == 0:
            jf.a.doe("POST", f"/UserPlayedItems/{iid}", {"userId": uid, "datePlayed": VASTE_DATUM})
            log.append(("gezien", it["Path"]))
        if i % 4 == 1:
            jf.a.doe("POST", f"/UserFavoriteItems/{iid}", {"userId": uid})
            log.append(("favoriet", it["Path"]))
        if i % 5 == 2:
            jf.a.doe("POST", f"/UserItems/{iid}/Rating", {"userId": uid, "likes": "true"})
            log.append(("vind-ik-leuk", it["Path"]))
    if extra and items:
        jf.a.doe("POST", f"/UserFavoriteItems/{items[0]['Id']}", {"userId": uid})
        log.append(("EXTRA favoriet (negatieve proef)", items[0]["Path"]))
    if items:
        it = items[-1]
        sessie = Http(server.url, {"Authorization": CLIENT + f', Token="{jf.token}"'})
        body = {"ItemId": it["Id"], "PositionTicks": 0, "PlaySessionId": "b03016-diff", "AudioStreamIndex": 1,
                "SubtitleStreamIndex": -1, "PlayMethod": "DirectPlay", "CanSeek": True}
        sessie.doe("POST", "/Sessions/Playing", body=body)
        sessie.doe("POST", "/Sessions/Playing/Progress", body={**body, "PositionTicks": 123_450_000})
        sessie.doe("POST", "/Sessions/Playing/Stopped", body={**body, "PositionTicks": 123_450_000})
        log.append(("hervatpunt 12,345 s", it["Path"]))
    time.sleep(3)
    return {"handelingen": len(log), "items": len(items)}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="b03h diffrun")
    p.add_argument("--image-a", default=STOCK_IMAGE)
    p.add_argument("--image-b", default=STOCK_IMAGE)
    p.add_argument("--toegestaan", type=Path, help="JSON {tabel: [kolommen]} met de toegestane wijzigingen van een module")
    p.add_argument("--uit", type=Path, default=REPO / "docs/platform-v2/test-evidence/b03-016-diffrun-stock-stock.json")
    p.add_argument("--negatieve-proef", action="store_true", help="systeem b doet één extra handeling; verwacht: verschil gevonden")
    a = p.parse_args(argv)
    toegestaan = {t: set(k) for t, k in json.loads(a.toegestaan.read_text(encoding="utf-8")).items()} if a.toegestaan else None
    koppelingen = {"/media/movies/blender/hero": "bron/blender/hero", "/media/movies/kwaliteit": "afgeleid/kwaliteit",
                   "/media/series": "afgeleid/series"}
    bibliotheken = [("Films", "movies", ["/media/movies"]), ("Series", "tvshows", ["/media/series"])]
    begin = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    with meetslot.exclusief_slot() as wacht:
        basis = StockServer("diff-basis", image=a.image_a, gpu=False, koppelingen=koppelingen).start()
        try:
            basis.inrichten(bibliotheken)
            basis.stop()
            uitkomst = {}
            for kant, image in (("a", a.image_a), ("b", a.image_b)):
                srv = StockServer(f"diff-{kant}", image=image, gpu=False, koppelingen=koppelingen)
                shutil.rmtree(srv.map, ignore_errors=True)
                srv.map.mkdir(parents=True)
                shutil.copytree(basis.map / "config", srv.map / "config", symlinks=True)
                (srv.map / "cache").mkdir()
                srv.start(schoon=False)
                uitkomst[kant] = scenario(srv, extra=a.negatieve_proef and kant == "b")
                srv.stop()
            rapport = vergelijk(WERK / "servers/diff-a/config/data/jellyfin.db", WERK / "servers/diff-b/config/data/jellyfin.db",
                                toegestaan)
        finally:
            for naam in ("diff-basis", "diff-a", "diff-b"):
                StockServer(naam).verwijder()
    document = {"schema": "jelly-leon/b03-016-diffrun/1", "begin": begin, "negatieve_proef": a.negatieve_proef,
                "meetslot_wacht_s": round(wacht, 1),
                "images": {"a": a.image_a, "b": a.image_b}, "scenario": uitkomst,
                "vaste_uitzonderingen": {t: sorted(k) for t, k in VASTE_UITZONDERINGEN.items()},
                "toegestaan_module": {t: sorted(k) for t, k in (toegestaan or {}).items()}, "rapport": rapport,
                "uitkomst": "0 verschillen buiten de vaste uitzonderingen" if rapport["verschillen_buiten_uitzonderingen"] == 0
                else f"{rapport['verschillen_buiten_uitzonderingen']} verschillen buiten de uitzonderingen",
                "validatie": "Sim-getest (echte stock-containers op de ontwikkelmachine)"}
    a.uit.parent.mkdir(parents=True, exist_ok=True)
    a.uit.write_text(json.dumps(document, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    print(document["uitkomst"])
    return 0 if rapport["verschillen_buiten_uitzonderingen"] == 0 else 1
