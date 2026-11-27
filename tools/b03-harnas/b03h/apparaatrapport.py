"""Rapportage B03-060. Herhalingen, afzonderlijke starts en de A5-noemer blijven herkenbaar."""

from __future__ import annotations

import json
from pathlib import Path

from . import statistiek

OMSCHRIJVING = {
    "K1": "onterechte Direct Play", "K2": "tijd tot spelend beeld na mislukte Direct Play",
    "K3": "effectieve Direct Play-ratio", "K4": "dekking van het bevestigde Direct Play-potentieel",
    "K5": "onnodige transcodes", "K6": "hardware en CPU per videotranscode", "K7": "onnodige inbrandingen",
    "K8": "stock-compatibiliteit bij gelijke encoding.xml", "K9": "routering tussen nodes en terugval",
}
VERWACHT = {"chromium": 16, "firefox": 17, "webkit": 21}
GEEN_HERSTEL = "> 60 s (geen automatisch herstel)"
EXTERN = {
    "telefoon": {"bron": "jelly-leon-clients/docs/platform-v2/test-evidence/p4-0-jc3-android-emulator.json",
                 "uitkomst": "Android-telefoon: afspelen aangetoond in het clientharnas."},
    "tablet": {"bron": "jelly-leon-clients/docs/platform-v2/EVIDENCE.json#B03-016",
               "uitkomst": "Tablet: binnen 4 GiB drie OOM-kills; bij 5 GiB één van drie herhalingen positief. Vervolg S-P40-70."},
    "tv": {"bron": "jelly-leon-clients/docs/platform-v2/test-evidence/p4-0-jc3-android-emulator.json",
           "uitkomst": "Android TV: afspelen aangetoond in het clientharnas."},
    "desktop": {"bron": "docs/platform-v2/test-evidence/b03-016-desktop-spike.json",
                "uitkomst": "Desktop 2.0.0: hero.mp4 afgespeeld en hervat in S-P40-90."},
}


def proportie(k: int, n: int) -> dict:
    return {"k": k, "n": n, "wilson95": statistiek.wilson(k, n).als_dict() if n else None, "gate": statistiek.gate_label(n, 20)}


def metrieken(rijen: list[dict]) -> dict:
    dp = [r for r in rijen if r["besluit"] == "DirectPlay"]
    mislukt = [r for r in dp if not r["orakel_ok"]]
    potentieel = [r for r in rijen if r["geforceerd_ok"] and r["hdr_toegestaan"]]
    transcodes = [r for r in rijen if r["besluit"] == "Transcode"]
    video = [r for r in rijen if r["transcoding_info"] and r["transcoding_info"]["video_direct"] is False]
    bekend = [r for r in video if r["transcoding_info"]["hardware"] is not None]
    subs = [r for r in rijen if r["ondertitel"] is not None]
    return {
        "K1": {**proportie(len(mislukt), len(rijen)), "gevallen": [r["id"] for r in mislukt]},
        "K2": {r["id"]: r["herstel_ms"] if r["herstel_ms"] is not None else GEEN_HERSTEL for r in mislukt},
        "K3": proportie(len(dp) - len(mislukt), len(rijen)),
        "K4": {**proportie(sum(r["besluit"] == "DirectPlay" and r["orakel_ok"] for r in potentieel), len(potentieel)),
               "geforceerd_speelt_zonder_hdr_bevestiging": sum(r["geforceerd_ok"] and not r["hdr_toegestaan"] for r in rijen)},
        "K5": {"aantal": sum(r["geforceerd_ok"] for r in transcodes), "transcodes": len(transcodes)},
        "K6": {"videotranscodes": len(video), "hardware": proportie(sum(r["transcoding_info"]["hardware"].lower() != "none"
                                                                        for r in bekend), len(bekend)),
               "hardware_onbekend": len(video) - len(bekend),
               "hls_zonder_sessieinfo": sum(r["hls"] and not r["transcoding_info"] for r in rijen),
               "frames_per_s": {r["id"]: r["transcoding_info"].get("frames_per_s") for r in video},
               "cpu_kernen_per_transcode": {r["id"]: r["cpu_kernen"] for r in video}},
        "K7": {"actieve_sporen": len(subs), "ingebrand": sum(r["ingebrand"] for r in rijen),
               "onnodig": sum(r["ingebrand"] and r["extern_mogelijk"] for r in subs)},
        "K8": "afzonderlijke vergelijking onder gelijke encoding.xml in JLT-46",
        "K9": "n.v.t. bij één rendernode; routering en uitval in JLT-44/45",
    }


def herhaalbaarheid(runs: list[dict]) -> dict:
    """Vergelijk per geval én start, ook als een ander item precies de omgekeerde afwijking heeft."""
    if len(runs) < 3 or not all(run["last"]["geldig"] for run in runs):
        raise ValueError("minstens drie geldige runs vereist")

    def per_start(run):
        index = {(r["groep"], r["id"], r["start"]): r for r in run["rijen"]}
        if not index or len(index) != len(run["rijen"]) or any((*k[:2], 3 - k[2]) not in index or k[2] not in (1, 2) for k in index):
            raise ValueError("lege, dubbele of ontbrekende start")
        return index

    eerste = per_start(runs[0])
    verschillen = []
    for run in runs[1:]:
        nieuw = per_start(run)
        if nieuw.keys() != eerste.keys():
            raise ValueError("verschillende gevallen in de herhalingen")
        for sleutel, r in eerste.items():
            nr = nieuw[sleutel]
            for veld in ("besluit", "orakel_ok", "geforceerd_ok", "ingebrand", "eerste_frame_ms", "tijd_tot_2s_ms", "herstel_ms"):
                a, b = r[veld], nr[veld]
                gelijk = a == b
                if veld.endswith("_ms") and a is not None and b is not None:
                    gelijk = abs(b - a) <= a * 0.10
                if not gelijk:
                    verschillen.append({"run": run["last"]["run"], "geval": sleutel, "veld": veld, "eerste": a, "herhaling": b})
    return {"geldig": not verschillen, "aantal_runs": len(runs), "verschillen": verschillen}


def vergelijking(rijen: list[dict], client: str, historisch: dict) -> dict:
    eerste = {r["id"]: r for r in rijen if r["groep"] == "a5" and r["start"] == 1}
    if len(eerste) != 25:
        raise ValueError("de A5-vergelijking vereist 25 verschillende eerste starts")
    verschillen = []
    for naam, r in eerste.items():
        oud = historisch[naam].split(" (")[0]
        oud_speelt_dp = oud == "DirectPlay" and not (client == "webkit" and naam == "Sintel.2010.1080p.mkv")
        if oud != r["besluit"] or oud_speelt_dp != (r["besluit"] == "DirectPlay" and r["orakel_ok"]):
            verschillen.append({"item": naam, "historisch": oud, "historisch_dp_speelt": oud_speelt_dp, "nu": r["besluit"],
                                "orakel_ok": r["orakel_ok"], "serverreden": r["redenen"], "mediafouten": r["foutcodes"]})
    return {"verwacht_dp": VERWACHT[client], "gekozen_dp": sum(r["besluit"] == "DirectPlay" for r in eerste.values()),
            "effectief_dp": sum(r["besluit"] == "DirectPlay" and r["orakel_ok"] for r in eerste.values()),
            "n": 25, "verschillen_ter_beoordeling": verschillen}


def schrijf(pad: Path, d: dict) -> None:
    pad.parent.mkdir(parents=True, exist_ok=True)
    md = ["# B03-060 — apparaatprofielen en afspeelfouten", "", d["status"] + ".", "",
          f"Loadavg vóór de meetpoging (1, 5 en 15 min) {d['loadavg']}. Grens voor 1 min {d['grens']}.",
          "Audio niet stil is niet gemeten. De browser meet beeld, voortgang en fout-events.", ""]
    md.extend(d["redenen"])
    md.extend(["", f"Meetpoging {d['begin']} (UTC). Basisbestand `{d['basis']}`.", ""])
    leeg = not any(c["runs"] for clients in d["systemen"].values() for c in clients.values())
    if leeg:
        md.extend(["| Stockprofiel | Client | Geldige runs | K1 t/m K9 |", "|---|---|---:|---|"])
    for systeem, clients in d["systemen"].items():
        for client, data in clients.items():
            if leeg:
                md.append(f"| {systeem} | {client} | 0 | {d['status']} |")
                continue
            md.extend(["", f"## {systeem} · {client}", "", f"Rol {data['rol']}. Geldige runs {len(data['runs'])}.", ""])
            if not data["runs"]:
                md.append(d["status"])
                continue
            for run in data["runs"]:
                n = run["last"]["run"] + 1
                md.extend([f"### Run {n}", "", "| Set | Start | Metriek | Waarde |", "|---|---:|---|---|"])
                for groep, starts in run["metingen"].items():
                    for start, waarden in starts.items():
                        for k, v in waarden.items():
                            tekst = json.dumps(v, ensure_ascii=False).replace("|", "\\|")
                            md.append(f"| {groep} | {start} | {k} {OMSCHRIJVING[k]} | {tekst} |")
                md.append("")
            if "herhaalbaarheid" in data:
                h = data["herhaalbaarheid"]
                md.append(f"Herhaalbaarheid over {h['aantal_runs']} runs: {len(h['verschillen'])} verschillen.")
            if "a5" in data:
                a = data["a5"]
                md.append(f"A5 eerste start: {a['gekozen_dp']}/25 gekozen, {a['effectief_dp']}/25 effectief, "
                          f"historisch {a['verwacht_dp']}/25 gekozen.")
                for verschil in a["verschillen_ter_beoordeling"]:
                    md.append("- " + json.dumps(verschil, ensure_ascii=False))
    md.extend(["", "## Overgenomen clientproeven", ""])
    for client, proef in d["overgenomen_clientproeven"].items():
        md.append(f"- {client.capitalize()}. {proef['uitkomst']} Bron `{proef['bron']}`.")
    for doel, tekst in ((pad, json.dumps(d, ensure_ascii=False, indent=2)), (pad.with_suffix(".md"), "\n".join(md))):
        tijdelijk = doel.with_suffix(doel.suffix + ".tmp")
        tijdelijk.write_text(tekst + "\n", encoding="utf-8")
        tijdelijk.replace(doel)
