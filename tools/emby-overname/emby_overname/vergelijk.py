"""Vóór/na-vergelijking per gebruiker: tellingen per soort, de afhandellijst, rechten, zichtbaarheid en spoorkeuzes.

Alles wat in Emby kijkgegevens heeft, is na afloop **verantwoord**: gekoppeld en gelijk (of verklaard anders), of met reden
op de afhandellijst. Elk verschil krijgt een stabiel ID (`V-…`) waarop de gebruiker akkoord geeft; de inhoud hangt niet af
van het tijdstip, zodat een tweede run zonder wijzigingen een inhoudelijk identiek rapport geeft.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .hulp import leesbare_datum, leesbare_positie, sha256_json
from .koppelen import REDENEN, Koppelaar, vertaal_pad
from .model import CONTAINER, ItemInfo, Kijkgegevens, Spoor, effectieve_spoorkeuze
from .plan import Doelopname, GebruikerPlan, Opties, Plan
from .rechten import Bibliotheekkoppeling, vergelijk_beleid, vergelijk_configuratie
from .samenvoegen import ACTIE, BESLISSING, KENNISNAME, toepassen, verschillen_item

SOORTEN = ("gezien", "hervatpunten", "favorieten", "beoordelingen", "spoorkeuzes")


def verschil_id(emby_uid: str, soort: str, reden: str, sleutel: str) -> str:
    return "V-" + sha256_json([emby_uid, soort, reden, sleutel])[:12]


def _item_json(item: ItemInfo, paden: Any) -> dict[str, Any]:
    return {"emby_id": item.id, "type": item.type, "titel": item.omschrijving(), "provider_ids": item.provider_ids,
            "pad_emby": item.pad, "pad_jelly_leon": vertaal_pad(item.pad, paden), "grootte": item.grootte}


def _kijk_leesbaar(k: dict[str, Any]) -> str:
    e = Kijkgegevens.van_json(k)
    delen = []
    if e.gezien:
        delen.append(f"gezien ({e.aantal}×, laatst {leesbare_datum(e.laatst)})")
    elif e.aantal:
        delen.append(f"{e.aantal}× gespeeld, laatst {leesbare_datum(e.laatst)}")
    if e.positie:
        delen.append(f"hervatten op {leesbare_positie(e.positie)} ({e.positie} ticks)")
    if e.favoriet:
        delen.append("favoriet")
    if e.beoordeling is not None:
        delen.append(f"beoordeling {e.beoordeling}")
    elif e.vind_ik_leuk is not None:
        delen.append("vind ik leuk" if e.vind_ik_leuk else "vind ik niet leuk")
    return ", ".join(delen) or "—"


def vergelijk(opname: dict[str, Any], plan: Plan, na: Doelopname, opties: Opties, voorspelling: bool,
              afspeelinfo_jl: Callable[[str, str], dict[str, Any]] | None,
              later_niet_zichtbaar: dict[str, list[str]] | None = None,
              herstel_onduidelijk: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Maakt de `toestand` van het rapport. `voorspelling`: proefrun (Jelly Leon na = basis + geplande schrijfacties)."""
    emby_items = {k: ItemInfo.van_json(v) for k, v in opname["items"].items()}
    koppelaar = Koppelaar(emby_items, na.index, opties.paden)
    omgekeerd: dict[str, set[str]] = {}
    for emby_id, item in emby_items.items():
        if item.type in CONTAINER and item.type not in ("Series", "Season", "MusicAlbum", "BoxSet"):
            continue
        jl_id = koppelaar.koppel(emby_id).jl_id
        if jl_id:
            omgekeerd.setdefault(jl_id, set()).add(emby_id)
    per_uid = {g["id"]: g for g in opname["gebruikers"]}
    gebruikers_uit: list[dict[str, Any]] = []
    for g in plan.gebruikers:
        eg = per_uid[g.emby_uid]
        gebruikers_uit.append(_gebruiker(eg, g, emby_items, na, opties, voorspelling, afspeelinfo_jl, koppelaar, omgekeerd,
                                         (later_niet_zichtbaar or {}).get(g.emby_uid, []),
                                         [o for o in herstel_onduidelijk or [] if o["emby_uid"] == g.emby_uid],
                                         plan.bibliotheken))
    totaal = {soort: {k: sum(u["telling"][soort][k] for u in gebruikers_uit) for k in gebruikers_uit[0]["telling"][soort]}
              for soort in SOORTEN} if gebruikers_uit else {}
    toestand = {
        "gebruikers": gebruikers_uit,
        "totaal": totaal,
        "alleen_in_jelly_leon": plan.alleen_in_jl,
        "bibliotheken": {
            "gekoppeld": {plan.bibliotheken.namen_emby.get(k, k): plan.bibliotheken.namen_jl.get(v, v)
                          for k, v in sorted(plan.bibliotheken.emby_naar_jl.items())},
            "niet_gekoppeld": plan.bibliotheken.niet_gekoppeld,
        },
        "verantwoord": all(u["verantwoord"]["klopt"] for u in gebruikers_uit),
    }
    toestand["verschillen"] = sorted(v["id"] for u in gebruikers_uit for v in u["afhandellijst"])
    return toestand


def _gebruiker(eg: dict[str, Any], g: GebruikerPlan, emby_items: dict[str, ItemInfo], na: Doelopname, opties: Opties,
               voorspelling: bool, afspeelinfo_jl: Callable[[str, str], dict[str, Any]] | None, koppelaar: Koppelaar,
               omgekeerd: dict[str, set[str]], later_niet_zichtbaar: list[str],
               herstel_onduidelijk: list[dict[str, Any]], bib: Bibliotheekkoppeling) -> dict[str, Any]:
    lijst: list[dict[str, Any]] = []
    jl_uid = g.jl_uid
    bestaat = jl_uid is not None and jl_uid in na.per_gebruiker
    acties = {a.emby_id: a for a in g.acties}

    def punt(soort: str, reden: str, klasse: str, uitleg: str, sleutel: str, item: ItemInfo | None = None,
             kijk: dict[str, Any] | None = None) -> None:
        lijst.append({
            "id": verschil_id(g.emby_uid, soort, reden, sleutel), "soort": soort, "reden": reden, "klasse": klasse,
            "uitleg": uitleg, "item": _item_json(item, opties.paden) if item else None,
            "kijkgegevens": kijk, "kijkgegevens_tekst": _kijk_leesbaar(kijk) if kijk else None,
        })

    if g.status == "ongeldige_naam":
        punt("gebruiker", "ongeldige_naam", ACTIE,
             f"De naam {g.jl_naam!r} is in Jelly Leon niet toegestaan; koppel deze gebruiker met --gebruiker aan een andere naam.",
             "naam")
    if g.status in ("aanmaken", "aangemaakt_door_tool"):
        punt("gebruiker", "wachtwoord_niet_overgezet", ACTIE,
             "Wachtwoorden zijn niet over te zetten (Emby geeft ze niet vrij). Stel in Jelly Leon een nieuw wachtwoord in "
             "(Dashboard → Gebruikers → deze gebruiker → Wachtwoord) of gebruik SSO; tot dan kan niemand als deze gebruiker inloggen.",
             "wachtwoord")
    # Rechten en voorkeuren.
    rechten = list(g.rechten)
    if bestaat and g.status in ("aanmaken", "aangemaakt_door_tool") and not (voorspelling and g.status == "aanmaken"):
        jl = next((u for u in na.gebruikers.values() if u["Id"] == jl_uid), None)
        if jl is not None and not (voorspelling and (g.beleid_schrijven or g.config_schrijven)):
            controle = [r for r in vergelijk_beleid(g.beleid_doel, jl.get("Policy") or {}, bib)
                        + vergelijk_configuratie(g.config_doel, jl.get("Configuration") or {}) if r.status != "gelijk"]
            for r in controle:
                r.uitleg = ("in Jelly Leon handmatig gewijzigd; de tool past deze rechten niet meer aan" if g.handmatig_gewijzigd
                            else "gecontroleerd in Jelly Leon (readback): wijkt af van de vertaling")
            rechten.extend(controle)
    for r in rechten:
        if r.status == "gelijk":
            continue
        klasse = ACTIE if r.status in ("ruimer", "handmatig") else KENNISNAME
        punt("rechten", f"recht_{r.status}", klasse,
             f"{r.veld}: Emby {r.emby!r} → Jelly Leon {r.jelly_leon!r}. {r.uitleg}".strip(), r.veld)
    # Kijkgegevens per item.
    telling = {s: {"emby": 0, "gekoppeld": 0, "gelijk": 0, "jelly_leon_nieuwer": 0, "afhandellijst": 0} for s in SOORTEN}
    verantwoord_items = 0
    met_gegevens = len(eg["kijkgegevens"])
    te_vergelijken = {**{e: Kijkgegevens().naar_json() for e in g.zonder_gegevens}, **eg["kijkgegevens"]}
    for emby_id, ruw in sorted(te_vergelijken.items()):
        item = emby_items[emby_id]
        e = Kijkgegevens.van_json(ruw)
        alleen_vroeger = emby_id in g.zonder_gegevens
        koppeling = g.koppelingen.get(emby_id)
        soorten = _soorten(e, item.type)
        for s in soorten:
            telling[s]["emby"] += 1
        if alleen_vroeger and (koppeling is None or koppeling.jl_id is None or emby_id in g.niet_zichtbaar):
            continue
        if koppeling is None or koppeling.jl_id is None or g.status == "ongeldige_naam":
            reden = koppeling.reden if koppeling else "ontbreekt"
            punt("item", reden or "ontbreekt", BESLISSING,
                 f"{REDENEN.get(reden or '', reden)}. {koppeling.uitleg if koppeling else ''}".strip(),
                 emby_id, item, ruw)
            for s in soorten:
                telling[s]["afhandellijst"] += 1
            verantwoord_items += 1
            continue
        if emby_id in g.niet_zichtbaar or emby_id in later_niet_zichtbaar:
            punt("item", "niet_zichtbaar_in_jelly_leon", BESLISSING,
                 "Gekoppeld, maar deze gebruiker mag het item in Jelly Leon niet zien (rechten strenger dan in Emby); "
                 "de kijkgegevens zijn niet geschreven.", emby_id, item, ruw)
            for s in soorten:
                telling[s]["afhandellijst"] += 1
            verantwoord_items += 1
            continue
        if not alleen_vroeger:
            verantwoord_items += 1
        basis = Kijkgegevens.van_json(g.basis.get(emby_id))
        if voorspelling or not bestaat:
            j = toepassen(basis, acties[emby_id].velden) if emby_id in acties else basis
        else:
            j = na.per_gebruiker[jl_uid].get(koppeling.jl_id, Kijkgegevens())
        p = Kijkgegevens.van_json(g.vorige[emby_id]) if emby_id in g.vorige else None
        for s in soorten:
            telling[s]["gekoppeld"] += 1
            uitkomst = _uitkomst(s, e, j)
            if uitkomst:
                telling[s][uitkomst] += 1
        for v in verschillen_item(e, j, p, item.type):
            punt(v["soort"], v["reden"], v["klasse"], v["uitleg"], emby_id, item, ruw)
    for o in herstel_onduidelijk:
        item = emby_items.get(o["emby_id"])
        punt("herstel", "onduidelijk_na_afbreking", BESLISSING,
             "Na een afgebroken run is deze waarde in Jelly Leon intussen door iets anders gewijzigd; controleer haar.",
             o["emby_id"], item, None)
    # Spoorkeuzes (alleen lezen; Jellyfin 12.4 heeft geen officiële route om ze te zetten).
    spoor_keuzes = eg.get("spoorkeuzes") or {}
    for emby_id, keuze in sorted(spoor_keuzes.items()):
        if not keuze.get("audio") and not keuze.get("ondertitel"):
            continue
        telling["spoorkeuzes"]["emby"] += 1
        koppeling = g.koppelingen.get(emby_id)
        item = emby_items[emby_id]
        if koppeling is None or koppeling.jl_id is None or emby_id in g.niet_zichtbaar or emby_id in later_niet_zichtbaar:
            telling["spoorkeuzes"]["afhandellijst"] += 1
            continue  # het item zelf staat al op de afhandellijst
        telling["spoorkeuzes"]["gekoppeld"] += 1
        if not bestaat or afspeelinfo_jl is None:
            punt("spoorkeuze", "spoorkeuze_na_aanmaken", KENNISNAME,
                 "Wordt na het aanmaken van de gebruiker vergeleken (Emby-keuze: "
                 f"{_spoor_tekst(keuze)}).", emby_id, item, None)
            telling["spoorkeuzes"]["afhandellijst"] += 1
            continue
        jl_keuze = effectieve_spoorkeuze(afspeelinfo_jl(koppeling.jl_id, jl_uid))
        gelijk = all(
            (Spoor.van_json(keuze.get(s)) is None and jl_keuze.get(s) is None)
            or (Spoor.van_json(keuze.get(s)) is not None and Spoor.van_json(keuze.get(s)).gelijk_aan(Spoor.van_json(jl_keuze.get(s))))  # type: ignore[union-attr]
            for s in ("audio", "ondertitel")
        )
        if gelijk:
            telling["spoorkeuzes"]["gelijk"] += 1
            continue
        telling["spoorkeuzes"]["afhandellijst"] += 1
        emby_bestand = keuze.get("bestand") or {}
        jl_bestand = jl_keuze.get("bestand") or {}
        zelfde = (vertaal_pad(emby_bestand.get("pad"), opties.paden) == jl_bestand.get("pad")
                  and emby_bestand.get("grootte") == jl_bestand.get("grootte"))
        if zelfde:
            punt("spoorkeuze", "spoorkeuze_niet_overzetbaar", ACTIE,
                 f"Onthouden spoorkeuze in Emby: {_spoor_tekst(keuze)}; Jelly Leon kiest nu {_spoor_tekst(jl_keuze)}. "
                 "Jellyfin 12.4 heeft geen officiële route om een onthouden spoorkeuze te zetten (capability_unavailable): "
                 "kies het spoor één keer zelf in Jelly Leon, dan onthoudt Jelly Leon het.", emby_id, item, None)
        else:
            punt("spoorkeuze", "ander_bestand", BESLISSING,
                 f"Het bestand verschilt (Emby {emby_bestand.get('grootte')} bytes, Jelly Leon {jl_bestand.get('grootte')} "
                 f"bytes); de spoorkeuze ({_spoor_tekst(keuze)}) wordt daarom niet overgenomen.", emby_id, item, None)
    # Zichtbaarheid: een gebruiker (vooral een kind) ziet in Jelly Leon nooit meer dan in Emby.
    zicht = {"emby": len(eg.get("zichtbaar") or []), "jelly_leon": None, "ruimer": None, "smaller": None, "alleen_in_jelly_leon": None}
    if bestaat and not (voorspelling and g.status == "aanmaken"):
        e_vis = set(eg.get("zichtbaar") or [])
        j_vis = na.zichtbaar(jl_uid)  # type: ignore[arg-type]
        ruimer = sorted(jl for jl in j_vis if jl in omgekeerd and not (omgekeerd[jl] & e_vis))
        smaller = sorted(e for e in e_vis if (k := koppelaar.koppel(e)).jl_id and k.jl_id not in j_vis
                         and emby_items[e].type not in CONTAINER - {"Series", "Season", "MusicAlbum", "BoxSet"})
        zicht.update({"jelly_leon": len(j_vis), "ruimer": len(ruimer), "smaller": len(smaller),
                      "alleen_in_jelly_leon": len([jl for jl in j_vis if jl not in omgekeerd])})
        if ruimer:
            titels = [na.index.items[jl].omschrijving() for jl in ruimer[:20] if jl in na.index.items]
            punt("rechten", "zichtbaar_ruimer_dan_emby", ACTIE,
                 f"{len(ruimer)} item(s) zichtbaar in Jelly Leon die deze gebruiker in Emby niet mocht zien: "
                 f"{'; '.join(titels)}. Pas de rechten in Jelly Leon aan.", "zichtbaarheid_ruimer")
        if smaller:
            titels = [emby_items[e].omschrijving() for e in smaller[:20]]
            punt("rechten", "zichtbaar_smaller_dan_emby", KENNISNAME,
                 f"{len(smaller)} item(s) die deze gebruiker in Emby zag, ziet hij of zij in Jelly Leon niet: "
                 f"{'; '.join(titels)}.", "zichtbaarheid_smaller")
    lijst.sort(key=lambda p: (p["soort"], p["reden"], p["id"]))
    status = "aangemaakt_door_tool" if (g.status == "aanmaken" and not voorspelling) else g.status
    return {
        "emby_naam": g.emby_naam, "emby_id": g.emby_uid, "jelly_leon_naam": g.jl_naam, "jelly_leon_id": jl_uid,
        "status": status, "beheerder": bool(eg["beleid"].get("IsAdministrator")),
        "wachtwoord": "niet overgezet" if g.status in ("aanmaken", "aangemaakt_door_tool") else "eigen Jelly Leon-wachtwoord",
        "telling": telling,
        "verantwoord": {"met_kijkgegevens": met_gegevens, "verantwoord": verantwoord_items,
                        "klopt": verantwoord_items == met_gegevens},
        "rechten": [r.naar_json() for r in rechten],
        "zichtbaarheid": zicht,
        "afhandellijst": lijst,
    }


def _soorten(e: Kijkgegevens, item_type: str) -> list[str]:
    s = []
    if item_type not in CONTAINER:
        if e.gezien or e.aantal:
            s.append("gezien")
        if e.positie:
            s.append("hervatpunten")
    if e.favoriet:
        s.append("favorieten")
    if e.beoordeling is not None or e.vind_ik_leuk is not None:
        s.append("beoordelingen")
    return s


def _uitkomst(soort: str, e: Kijkgegevens, j: Kijkgegevens) -> str | None:
    if soort == "gezien":
        if j.gezien == e.gezien and j.aantal == e.aantal and j.laatst == e.laatst:
            return "gelijk"
        if (j.gezien or not e.gezien) and j.aantal >= e.aantal and (e.laatst is None or (j.laatst or 0) >= e.laatst):
            return "jelly_leon_nieuwer"
        return None
    if soort == "hervatpunten":
        if j.positie == e.positie:
            return "gelijk"
        if j.laatst is not None and (e.laatst is None or j.laatst > e.laatst):
            return "jelly_leon_nieuwer"
        return None
    if soort == "favorieten":
        return "gelijk" if j.favoriet else None
    if soort == "beoordelingen":
        if e.beoordeling is not None:
            return "gelijk" if j.beoordeling == e.beoordeling else None
        return "gelijk" if j.vind_ik_leuk == e.vind_ik_leuk else None
    return None


def _spoor_tekst(keuze: dict[str, Any]) -> str:
    delen = []
    for soort, naam in (("audio", "audio"), ("ondertitel", "ondertitel")):
        s = Spoor.van_json(keuze.get(soort))
        delen.append(f"{naam}: {s.leesbaar() if s else 'uit/standaard'}")
    return "; ".join(delen)
