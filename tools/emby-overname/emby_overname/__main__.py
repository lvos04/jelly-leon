"""Opdrachtregel van de overnametool. Alle meldingen zijn Nederlands; exitcodes staan in `fouten.py`.

    python -m emby_overname inventaris  --emby-url URL --emby-sleutel-bestand PAD --werkmap MAP
    python -m emby_overname export      --emby-url URL --emby-sleutel-bestand PAD --uitvoer BESTAND.json
    python -m emby_overname proefrun    (--emby-url … --emby-sleutel-bestand … | --bron-archief BESTAND.json)
                                        --jl-url URL --jl-sleutel-bestand PAD --werkmap MAP [--pad EMBY=JL]… [--gebruiker E=J]…
    python -m emby_overname overzetten  (zelfde opties) --akkoord akkoord.json
    python -m emby_overname akkoord-controle --rapport rapport.json --akkoord akkoord.json
    python -m emby_overname vergelijk-export A.json B.json
    python -m emby_overname testhaak-schrijfpoging --emby-url URL --emby-sleutel-bestand PAD   (alleen voor JLT-73)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from . import TOOL_NAAM, __version__
from .akkoord import controleer_cutover, controleer_verschillen, lees_akkoord
from .emby import EmbyLezer
from .fouten import EXIT_CONTROLE, EXIT_GEBRUIK, EXIT_OK, AkkoordFout, AlleenLezenFout, OvernameFout, PlanGewijzigd
from .hulp import lees_geheim, map_stempel, nu_utc, schrijf_atomisch, schrijf_json_met_sha
from .jellyfin import JellyfinClient
from .koppelen import Padvertaling
from .momentopname import laad_archief, maak_momentopname, schrijf_archief, vergelijk_opnames
from .plan import Opties, lees_doel, maak_plan
from .rapport import bouw_rapport, schrijf_rapport
from .staat import Werkmap
from .uitvoeren import herstel, voer_uit
from .vergelijk import vergelijk


def melden(tekst: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {tekst}", file=sys.stderr, flush=True)


class Spoorlog:
    """Schrijft elk HTTP-verzoek (methode, pad, querysleutels, status, duur) naar log.jsonl — nooit headers of sleutels."""

    def __init__(self) -> None:
        self.regels: list[dict[str, Any]] = []

    def __call__(self, record: dict[str, Any]) -> None:
        self.regels.append({"tijd": nu_utc(), **record})

    def schrijf(self, pad: Path) -> None:
        schrijf_atomisch(pad, "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in self.regels))


def _emby(args: argparse.Namespace, spoor: Spoorlog) -> EmbyLezer:
    if not args.emby_url or not args.emby_sleutel_bestand:
        raise OvernameFout("geef --emby-url en --emby-sleutel-bestand (of --bron-archief)", EXIT_GEBRUIK)
    return EmbyLezer(args.emby_url, lees_geheim(Path(args.emby_sleutel_bestand), "Emby-API-sleutel"), spoor=spoor)


def _jl(args: argparse.Namespace, spoor: Spoorlog) -> JellyfinClient:
    return JellyfinClient(args.jl_url, lees_geheim(Path(args.jl_sleutel_bestand), "Jelly Leon-API-sleutel"), spoor=spoor)


def _opties(args: argparse.Namespace) -> Opties:
    try:
        paden = [Padvertaling.uit_tekst(t) for t in args.pad or []]
    except ValueError as fout:
        raise OvernameFout(str(fout), EXIT_GEBRUIK) from fout
    gebruikers: dict[str, str] = {}
    for tekst in args.gebruiker or []:
        if "=" not in tekst:
            raise OvernameFout(f"--gebruiker {tekst!r}: verwacht <emby-naam>=<jelly-leon-naam>", EXIT_GEBRUIK)
        links, rechts = tekst.split("=", 1)
        from .hulp import normaliseer_naam

        gebruikers[normaliseer_naam(links)] = rechts.strip()
    return Opties(paden=paden, gebruikers=gebruikers, met_spoorkeuzes=not args.zonder_spoorkeuzes)


def _bron(args: argparse.Namespace, spoor: Spoorlog, run_map: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    if args.bron_archief:
        opname = laad_archief(Path(args.bron_archief))
        melden(f"Bron: exportarchief {args.bron_archief} (Emby wordt niet benaderd)")
        return opname, {"archief": True, "export_bestand": Path(args.bron_archief).name}
    lezer = _emby(args, spoor)
    melden("Emby lezen (alleen GET) …")
    opname = maak_momentopname(lezer, met_spoorkeuzes=not args.zonder_spoorkeuzes, voortgang=melden)
    som = schrijf_archief(opname, run_map / "emby-export.json")
    return opname, {"archief": False, "export_bestand": "emby-export.json", "export_sha256": som}


def cmd_inventaris(args: argparse.Namespace) -> int:
    spoor = Spoorlog()
    werkmap = Werkmap(Path(args.werkmap))
    run_map = werkmap.runs / f"{map_stempel()}-inventaris"
    run_map.mkdir(parents=True)
    lezer = _emby(args, spoor)
    info = lezer.systeeminfo()
    inventaris = {
        "schema": "jelly-leon/emby-inventaris/1", "gemaakt": nu_utc(), "tool": {"naam": TOOL_NAAM, "versie": __version__},
        "emby": {"server_id": info.get("Id"), "server_naam": info.get("ServerName"), "versie": info.get("Version"),
                 "besturingssysteem": info.get("OperatingSystem")},
        "gebruikers": [{"naam": g.get("Name"), "beheerder": bool((g.get("Policy") or {}).get("IsAdministrator")),
                        "uitgeschakeld": bool((g.get("Policy") or {}).get("IsDisabled"))} for g in lezer.gebruikers()],
        "bibliotheken": [{"naam": b.get("Name"), "type": b.get("CollectionType"), "locaties": b.get("Locations")}
                         for b in lezer.bibliotheken()],
        "plugins": [{"naam": p.get("Name"), "versie": p.get("Version")} for p in lezer.plugins()],
    }
    som = schrijf_json_met_sha(run_map / "inventaris.json", inventaris)
    spoor.schrijf(run_map / "log.jsonl")
    print(json.dumps({"inventaris": str(run_map / "inventaris.json"), "sha256": som,
                      "gebruikers": len(inventaris["gebruikers"]), "bibliotheken": len(inventaris["bibliotheken"])},
                     ensure_ascii=False))
    return EXIT_OK


def cmd_export(args: argparse.Namespace) -> int:
    spoor = Spoorlog()
    lezer = _emby(args, spoor)
    opname = maak_momentopname(lezer, met_spoorkeuzes=not args.zonder_spoorkeuzes, voortgang=melden)
    uitvoer = Path(args.uitvoer)
    som = schrijf_archief(opname, uitvoer)
    spoor.schrijf(uitvoer.with_name(uitvoer.stem + ".log.jsonl"))
    laad_archief(uitvoer)  # leest terug en controleert beide sha256's
    print(json.dumps({"archief": str(uitvoer), "sha256": som, "inhoud_sha256": opname["inhoud_sha256"],
                      "gebruikers": len(opname["gebruikers"]),
                      "items_met_kijkgegevens": sum(len(g["kijkgegevens"]) for g in opname["gebruikers"])},
                     ensure_ascii=False))
    return EXIT_OK


def _voorbereiden(args: argparse.Namespace, soort: str) -> tuple[Any, ...]:
    spoor = Spoorlog()
    werkmap = Werkmap(Path(args.werkmap))
    run_id = f"{map_stempel()}-{soort}"
    run_map = werkmap.runs / run_id
    run_map.mkdir(parents=True)
    client = _jl(args, spoor)
    staat = werkmap.lees_staat()
    hersteld = herstel(werkmap, staat, client)
    if hersteld.onderbroken_run:
        melden(f"Afgebroken run {hersteld.onderbroken_run} hersteld: {len(hersteld.al_uitgevoerd)} schrijfactie(s) waren al "
               f"uitgevoerd (niet opnieuw), {len(hersteld.niet_uitgevoerd)} nog niet, {len(hersteld.onduidelijk)} onduidelijk")
    opties = _opties(args)
    opname, bron_extra = _bron(args, spoor, run_map)
    melden("Jelly Leon lezen …")
    doel = lees_doel(client)
    plan = maak_plan(opname, doel, staat, opties, client)
    return spoor, werkmap, run_id, run_map, client, staat, hersteld, opties, opname, bron_extra, doel, plan


def cmd_proefrun(args: argparse.Namespace) -> int:
    spoor, werkmap, run_id, run_map, client, staat, hersteld, opties, opname, bron_extra, doel, plan = _voorbereiden(args, "proefrun")
    toestand = vergelijk(opname, plan, doel, opties, voorspelling=True,
                         afspeelinfo_jl=client.afspeelinfo if opties.met_spoorkeuzes else None,
                         herstel_onduidelijk=hersteld.onduidelijk)
    rapport = bouw_rapport("proefrun", opname, doel.info, plan.sha256(), plan.aantal_schrijfacties(), toestand, None, bron_extra)
    uit = schrijf_rapport(rapport, run_map)
    schrijf_json_met_sha(werkmap.plannen / f"{plan.sha256()}.json", {
        "plan": plan.naar_json(), "verschillen": toestand["verschillen"], "rapport_inhoud_sha256": rapport["inhoud_sha256"],
        "run": run_id, "gemaakt": nu_utc(),
    })
    spoor.schrijf(run_map / "log.jsonl")
    _samenvatting(rapport, uit, run_map)
    return EXIT_OK


def _plan_akkoord(args: argparse.Namespace, werkmap: Werkmap, staat: dict[str, Any], plan: Any) -> dict[str, Any]:
    akkoord = lees_akkoord(Path(args.akkoord))
    if akkoord.get("soort") != "plan":
        raise AkkoordFout(f"voor 'overzetten' is een akkoord van soort 'plan' nodig (gekregen: {akkoord.get('soort')!r})")
    goedgekeurd = str(akkoord.get("plan_sha256") or "")
    plan_bestand = werkmap.plannen / f"{goedgekeurd}.json"
    if not plan_bestand.is_file():
        raise AkkoordFout(f"het goedgekeurde plan {goedgekeurd[:12]}… staat niet in de werkmap; maak eerst een proefrun")
    goedgekeurd_plan = json.loads(plan_bestand.read_text(encoding="utf-8"))
    if akkoord.get("rapport_inhoud_sha256") != goedgekeurd_plan.get("rapport_inhoud_sha256"):
        raise AkkoordFout("het akkoord hoort bij een ander proefrunrapport (inhoud-sha256 verschilt)")
    ontbrekend = controleer_verschillen(akkoord, goedgekeurd_plan.get("verschillen") or [])
    if ontbrekend:
        raise AkkoordFout(f"geen akkoord op {len(ontbrekend)} verschil(len) uit de proefrun: {', '.join(ontbrekend[:20])}")
    if plan.sha256() == goedgekeurd:
        return akkoord
    if staat.get("onderbroken_plan") == goedgekeurd:
        # Hervatten na een afbreking: wat nu nog moet, moet een deel zijn van het goedgekeurde plan (niets nieuws).
        oud = {(g["emby_uid"], a["emby_id"], json.dumps(a["velden"], sort_keys=True))
               for g in goedgekeurd_plan["plan"]["gebruikers"] for a in g["acties"]}
        nieuw = {(g.emby_uid, a.emby_id, json.dumps(a.velden, sort_keys=True)) for g in plan.gebruikers for a in g.acties}
        oud_gebruikers = {(g["emby_uid"], g["status"]) for g in goedgekeurd_plan["plan"]["gebruikers"]}
        nieuwe_aanmaak = {(g.emby_uid, g.status) for g in plan.gebruikers if g.status == "aanmaken"} - oud_gebruikers
        if nieuw <= oud and not nieuwe_aanmaak:
            melden(f"Hervatten van het goedgekeurde plan: nog {len(nieuw)} van {len(oud)} schrijfacties")
            return akkoord
    raise PlanGewijzigd(
        "het plan is sinds de proefrun veranderd (Emby of Jelly Leon is gewijzigd); maak een nieuwe proefrun en geef "
        f"opnieuw akkoord (goedgekeurd {goedgekeurd[:12]}…, nu {plan.sha256()[:12]}…)"
    )


def cmd_overzetten(args: argparse.Namespace) -> int:
    spoor, werkmap, run_id, run_map, client, staat, hersteld, opties, opname, bron_extra, doel, plan = _voorbereiden(args, "overzetting")
    akkoord = _plan_akkoord(args, werkmap, staat, plan)
    melden(f"Akkoord van {akkoord.get('akkoord_door')} op plan {plan.sha256()[:12]}…; schrijven in Jelly Leon …")
    begin = time.monotonic()
    uitvoering = voer_uit(plan, client, werkmap, staat, run_id, melden, testhaak_afbreken=args.testhaak_afbreken)
    melden(f"{uitvoering.schrijfacties} schrijfactie(s) uitgevoerd; Jelly Leon opnieuw lezen voor het vóór/na-rapport …")
    na = lees_doel(client)
    toestand = vergelijk(opname, plan, na, opties, voorspelling=False,
                         afspeelinfo_jl=client.afspeelinfo if opties.met_spoorkeuzes else None,
                         later_niet_zichtbaar=uitvoering.later_niet_zichtbaar, herstel_onduidelijk=hersteld.onduidelijk)
    run = {"id": run_id, "schrijfacties": uitvoering.schrijfacties, "per_soort": uitvoering.per_soort,
           "niet_bevestigd": uitvoering.niet_bevestigd, "duur_s": round(time.monotonic() - begin, 1),
           "akkoord_door": akkoord.get("akkoord_door"),
           "herstel": {"onderbroken_run": hersteld.onderbroken_run, "al_uitgevoerd": len(hersteld.al_uitgevoerd),
                       "niet_uitgevoerd": len(hersteld.niet_uitgevoerd), "onduidelijk": len(hersteld.onduidelijk)}}
    rapport = bouw_rapport("overzetting", opname, na.info, plan.sha256(), plan.aantal_schrijfacties(), toestand, run, bron_extra)
    uit = schrijf_rapport(rapport, run_map)
    staat.setdefault("runs", []).append({"id": run_id, "tijd": nu_utc(), "plan_sha256": plan.sha256(),
                                         "rapport_sha256": uit["sha256"], "schrijfacties": uitvoering.schrijfacties})
    werkmap.schrijf_staat(staat)
    spoor.schrijf(run_map / "log.jsonl")
    _samenvatting(rapport, uit, run_map)
    return EXIT_OK if not uitvoering.niet_bevestigd else EXIT_CONTROLE


def _samenvatting(rapport: dict[str, Any], uit: dict[str, str], run_map: Path) -> None:
    t = rapport["toestand"]
    print(json.dumps({
        "soort": rapport["soort"], "map": str(run_map), "rapport": uit["json"], "rapport_sha256": uit["sha256"],
        "inhoud_sha256": rapport["inhoud_sha256"], "plan_sha256": rapport["plan_sha256"],
        "plan_schrijfacties": rapport["plan_schrijfacties"],
        "schrijfacties": (rapport.get("run") or {}).get("schrijfacties", 0),
        "verantwoord": t["verantwoord"], "verschillen": len(t["verschillen"]), "totaal": t["totaal"],
    }, ensure_ascii=False))


def cmd_akkoord_controle(args: argparse.Namespace) -> int:
    rapport = json.loads(Path(args.rapport).read_text(encoding="utf-8"))
    problemen = controleer_cutover(rapport, lees_akkoord(Path(args.akkoord)))
    print(json.dumps({"overstap_toegestaan": not problemen, "problemen": problemen}, ensure_ascii=False))
    return EXIT_OK if not problemen else EXIT_CONTROLE


def cmd_vergelijk_export(args: argparse.Namespace) -> int:
    verschillen = vergelijk_opnames(laad_archief(Path(args.a)), laad_archief(Path(args.b)))
    print(json.dumps({"identiek": not verschillen, "verschillen": verschillen}, ensure_ascii=False))
    return EXIT_OK if not verschillen else EXIT_CONTROLE


def cmd_testhaak_schrijfpoging(args: argparse.Namespace) -> int:
    """JLT-73: een opzettelijke POST en DELETE vanuit de tool; de client moet ze vóór het netwerk weigeren."""
    spoor = Spoorlog()
    lezer = _emby(args, spoor)
    uitkomst = []
    for methode, pad in (("POST", "/Users/0/PlayedItems/0"), ("DELETE", "/Users/0/PlayedItems/0"),
                         ("POST", "/Library/Refresh"), ("GET", "/Users/0/Items/Latest")):
        try:
            lezer.testhaak_schrijfpoging(methode, pad)
            uitkomst.append({"methode": methode, "pad": pad, "geweigerd": False})
        except AlleenLezenFout as fout:
            uitkomst.append({"methode": methode, "pad": pad, "geweigerd": True, "melding": str(fout)})
    print(json.dumps({"pogingen": uitkomst, "netwerkverzoeken": len(spoor.regels)}, ensure_ascii=False))
    return EXIT_OK if all(u["geweigerd"] for u in uitkomst) and not spoor.regels else EXIT_CONTROLE


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="emby_overname", description="Overname kijkgeschiedenis Emby → Jelly Leon (B03-015).")
    p.add_argument("--versie", action="version", version=f"{TOOL_NAAM} {__version__}")
    sub = p.add_subparsers(dest="opdracht", required=True)

    def emby_opties(q: argparse.ArgumentParser) -> None:
        q.add_argument("--emby-url", help="adres van Emby, bijv. http://emby:8096 (alleen lezen)")
        q.add_argument("--emby-sleutel-bestand", help="bestand (0600) met de Emby-API-sleutel uit de geheimenmap")
        q.add_argument("--zonder-spoorkeuzes", action="store_true", help="onthouden spoorkeuzes niet lezen")

    q = sub.add_parser("inventaris", help="D07: versie, gebruikers, bibliotheken en plugins van Emby (alleen lezen)")
    emby_opties(q)
    q.add_argument("--werkmap", required=True)
    q.set_defaults(fn=cmd_inventaris)

    q = sub.add_parser("export", help="blijvend JSON-exportarchief van alle Emby-kijkgegevens (+ .sha256)")
    emby_opties(q)
    q.add_argument("--uitvoer", required=True)
    q.set_defaults(fn=cmd_export)

    for naam, fn, hulp in (("proefrun", cmd_proefrun, "droog: alleen rapport en plan, schrijft niets in Jelly Leon"),
                           ("overzetten", cmd_overzetten, "schrijft het goedgekeurde plan via de officiële Jelly Leon-API")):
        q = sub.add_parser(naam, help=hulp)
        emby_opties(q)
        q.add_argument("--bron-archief", help="exportarchief als bron in plaats van Emby (herimport)")
        q.add_argument("--jl-url", required=True, help="adres van Jelly Leon / Jellyfin 12.x")
        q.add_argument("--jl-sleutel-bestand", required=True, help="bestand (0600) met de Jelly Leon-API-sleutel")
        q.add_argument("--werkmap", required=True,
                       help="staat, journaal, plannen en rapporten (op de NAS onder /config/data/jelly-leon/overname)")
        q.add_argument("--pad", action="append", help="mountroot-vertaling <emby-pad>=<jelly-leon-pad> (meerdere toegestaan)")
        q.add_argument("--gebruiker", action="append", help="gebruikerskoppeling <emby-naam>=<jelly-leon-naam>")
        if naam == "overzetten":
            q.add_argument("--akkoord", required=True, help="akkoord.json op het plan van de proefrun")
            q.add_argument("--testhaak-afbreken", type=int, default=None, help=argparse.SUPPRESS)
        q.set_defaults(fn=fn)

    q = sub.add_parser("akkoord-controle", help="mag de overstap? (vóór/na-rapport + akkoord op elk verschil)")
    q.add_argument("--rapport", required=True)
    q.add_argument("--akkoord", required=True)
    q.set_defaults(fn=cmd_akkoord_controle)

    q = sub.add_parser("vergelijk-export", help="zijn twee exportarchieven inhoudelijk gelijk? (Emby vóór en na)")
    q.add_argument("a")
    q.add_argument("b")
    q.set_defaults(fn=cmd_vergelijk_export)

    q = sub.add_parser("testhaak-schrijfpoging", help=argparse.SUPPRESS)
    emby_opties(q)
    q.set_defaults(fn=cmd_testhaak_schrijfpoging)
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return int(args.fn(args))
    except OvernameFout as fout:
        melden(f"FOUT: {fout}")
        return fout.exit_code


if __name__ == "__main__":
    sys.exit(main())
