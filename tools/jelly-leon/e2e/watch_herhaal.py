"""WT-1d. Herhaal op één lokale wegwerpserver de interne LeaveGroup, het sessie-einde en een echte herstart."""
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import tempfile
import time
import uuid
from contextlib import closing
from pathlib import Path

from plugin_proef import BEHEER, PLUGIN_DLL, TOESTEL_BEHEER, Server, Sessie, eerste_beheerder
from watch_contract import schakel


def lees(db: Path, sql: str, *waarden: str) -> list[tuple]:
    with closing(sqlite3.connect(db.as_uri() + "?mode=ro", uri=True)) as verbinding:
        return verbinding.execute(sql, waarden).fetchall()


def controleer(data: Path, einde: str, actief: set[str], reden: str) -> None:
    meta = data / "watch" / "watch.db"
    laatste = time.monotonic() + 40
    while time.monotonic() < laatste:
        open_ids = {r[0] for r in lees(meta, "SELECT group_id FROM wt_group_meta WHERE ended_at IS NULL")}
        rij = lees(meta, "SELECT event_id FROM wt_group_meta WHERE group_id=? AND ended_at IS NOT NULL AND detected_by=? AND reported=1",
                   uuid.UUID(einde).hex, reden)
        if open_ids == {uuid.UUID(g).hex for g in actief} and len(rij) == 1:
            events = lees(data / "core" / "core.db", "SELECT json FROM outbox WHERE event_id=? AND module='watch'", str(uuid.UUID(rij[0][0])))
            if len(events) == 1:
                event = json.loads(events[0][0])
                if event["event_type"] == "media.watchgroup.ended" and event["payload"]["detected_by"] == reden:
                    return
        time.sleep(0.2)
    raise RuntimeError(f"{reden}: groepsmetadata of bijbehorend outbox-event komt niet overeen")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--plugin-map", type=Path, help="plugin-DLL voor de stock-runtime")
    parser.add_argument("--werkmap", required=True, type=Path)
    parser.add_argument("--rapport", required=True, type=Path)
    parser.add_argument("--herhalingen", type=int, default=50)
    args = parser.parse_args()
    if args.herhalingen < 50:
        parser.error("WT-1d vereist minstens 50 herhalingen")
    werk = Path(tempfile.mkdtemp(prefix="jl-wt1-", dir=args.werkmap)).resolve()
    server = Server(werk.name, args.image, werk / "server", werk / "media")
    teller = dict.fromkeys(("reconcile", "session_ended", "startup"), 0)
    resultaat = {"rondes": 0, "gevraagd": args.herhalingen, "bevestigde_events": teller, "volledig": False}
    fase = "opstarten"
    try:
        server.media.mkdir()
        if args.plugin_map:
            doel = server.config / "plugins" / "JellyLeon_0.1.0.0"
            doel.mkdir(parents=True)
            shutil.copy2(args.plugin_map / PLUGIN_DLL, doel)
        server.start()
        wachtwoord = uuid.uuid4().hex
        beheer = eerste_beheerder(server, wachtwoord)

        def aanmelden() -> Sessie:
            return Sessie(server, BEHEER, wachtwoord, TOESTEL_BEHEER, "jl-proef-beheer")

        def maak(sessie: Sessie) -> str:
            return sessie.http.doe("POST", "/SyncPlay/New", body={"GroupName": "Herhaalproef"})["GroupId"]

        fase = "schakelaar"
        schakel(beheer.http, True)
        data = server.config / "data" / "jelly-leon"
        for ronde in range(args.herhalingen):
            fase = "decorator"
            if beheer.http.doe("GET", "/media/v1/watch/capabilities")["decorator_active"] is not True:
                raise RuntimeError("de decorator is inactief")
            fase = "tweede NewGroup"
            eerste, tweede = maak(beheer), maak(beheer)
            controleer(data, eerste, {tweede}, "reconcile")
            teller["reconcile"] += 1
            fase = "sessie-einde"
            beheer.http.doe("POST", "/Sessions/Logout")
            controleer(data, tweede, set(), "session_ended")
            teller["session_ended"] += 1
            fase = "herstart"
            derde = maak(aanmelden())
            server.stop()
            server.start()
            beheer = aanmelden()
            controleer(data, derde, set(), "startup")
            teller["startup"] += 1
            resultaat["rondes"] = ronde + 1
            print(f"WT-1d ronde {ronde + 1}: drie beëindigingen bevestigd", flush=True)
        resultaat["volledig"] = True
    except Exception as fout:  # noqa: BLE001 - geef uitsluitend de proefstand en het fouttype door
        resultaat.update({"fase": fase, "fouttype": type(fout).__name__})
        print(f"WT-1d: {fase} onderbroken ({type(fout).__name__})", flush=True)
    finally:
        server.ruim_op()
        shutil.rmtree(werk)
        args.rapport.write_text(json.dumps(resultaat, indent=2) + "\n")
    print(f"WT-1d: {resultaat['rondes']}/{args.herhalingen} volledige rondes")
    return 0 if resultaat["volledig"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
