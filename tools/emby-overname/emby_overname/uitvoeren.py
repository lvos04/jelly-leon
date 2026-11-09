"""Uitvoeren met write-ahead-journaal en herstel na een afbreking (B03-015 A7, JLT-71).

Volgorde per gebruiker: (aanmaken met een willekeurig, nergens bewaard wachtwoord) → beleid → configuratie →
zichtbaarheid controleren → UserData per item. Elke schrijfactie: eerst `voornemen` in het journaal (fsync), dan het
verzoek, dan `klaar`. Bij het herstarten na een kill wordt elk open voornemen in Jelly Leon gecontroleerd: al toegepast →
als klaar geboekt (niet opnieuw schrijven); nog niet → opnieuw gepland; anders → afhandellijst.
"""

from __future__ import annotations

import os
import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .hulp import nu_utc
from .jellyfin import JellyfinClient
from .model import Kijkgegevens
from .plan import GebruikerPlan, Plan, lees_gebruiker_items
from .rechten import instellingen_sha
from .samenvoegen import velden_toegepast, volgende_vorige
from .staat import Werkmap, open_run, plan_van_run


@dataclass
class Herstel:
    onderbroken_run: str | None = None
    onderbroken_plan: str | None = None
    al_uitgevoerd: list[dict[str, Any]] = field(default_factory=list)
    niet_uitgevoerd: list[dict[str, Any]] = field(default_factory=list)
    onduidelijk: list[dict[str, Any]] = field(default_factory=list)


def _boek(staat: dict[str, Any], record: dict[str, Any]) -> None:
    gebruikers = staat.setdefault("gebruikers", {})
    st = gebruikers.setdefault(record["emby_uid"], {"items": {}})
    soort = record["t"]
    if soort == "gebruiker_aangemaakt":
        st.update({"jl_uid": record["jl_uid"], "naam": record["naam"], "aangemaakt_door_tool": True,
                   "aangemaakt": record.get("tijd")})
    elif soort == "beleid_geschreven":
        st["beleid_sha"] = record["sha"]
    elif soort == "config_geschreven":
        st["config_sha"] = record["sha"]
    elif soort == "klaar":
        st.setdefault("items", {})[record["emby_id"]] = {"jl_id": record["jl_id"], "emby": record["emby"]}
    elif soort == "gebruiker_klaar":
        st["jl_uid"] = record.get("jl_uid") or st.get("jl_uid")
        st.setdefault("naam", record.get("naam"))
        st.setdefault("aangemaakt_door_tool", False)
        st.setdefault("items", {}).update(record.get("items") or {})


def herstel(werkmap: Werkmap, staat: dict[str, Any], client: JellyfinClient | None) -> Herstel:
    """Verwerkt het journaal in de staat; bepaalt bij open voornemens in Jelly Leon zelf of ze al zijn uitgevoerd."""
    regels = werkmap.journaal_regels()
    resultaat = Herstel()
    if not regels:
        return resultaat
    resultaat.onderbroken_run = open_run(regels)
    if resultaat.onderbroken_run:
        resultaat.onderbroken_plan = plan_van_run(regels, resultaat.onderbroken_run)
    open_voornemens: dict[tuple[str, str], dict[str, Any]] = {}
    for r in regels:
        if r.get("t") == "voornemen":
            open_voornemens[(r["emby_uid"], r["emby_id"])] = r
        elif r.get("t") == "klaar":
            open_voornemens.pop((r["emby_uid"], r["emby_id"]), None)
            _boek(staat, r)
        elif r.get("t") in ("gebruiker_aangemaakt", "beleid_geschreven", "config_geschreven", "gebruiker_klaar"):
            _boek(staat, r)
    if open_voornemens and client is None:
        raise RuntimeError("herstel met open voornemens vraagt een verbinding met Jelly Leon")
    per_gebruiker: dict[str, list[dict[str, Any]]] = {}
    for r in open_voornemens.values():
        per_gebruiker.setdefault(r["jl_uid"], []).append(r)
    for jl_uid, lijst in per_gebruiker.items():
        assert client is not None
        ids = sorted({r["jl_id"] for r in lijst})
        nu = {str(i["Id"]): Kijkgegevens.uit_userdata(i.get("UserData"))
              for i in client.alle_items(jl_uid, {"ids": ",".join(ids)})}
        for r in lijst:
            j = nu.get(r["jl_id"], Kijkgegevens())
            samenvatting = {"emby_uid": r["emby_uid"], "emby_id": r["emby_id"], "jl_id": r["jl_id"], "velden": r["velden"]}
            if velden_toegepast(j, r["velden"]):
                resultaat.al_uitgevoerd.append(samenvatting)
                _boek(staat, {**r, "t": "klaar", "emby": r.get("volgende_p", r["emby"])})
            elif j == Kijkgegevens.van_json(r["basis"]):
                resultaat.niet_uitgevoerd.append(samenvatting)
            else:
                resultaat.onduidelijk.append({**samenvatting, "nu": j.naar_json(), "basis": r["basis"]})
    staat["laatste_herstel"] = {
        "tijd": nu_utc(), "onderbroken_run": resultaat.onderbroken_run, "onderbroken_plan": resultaat.onderbroken_plan,
        "al_uitgevoerd": len(resultaat.al_uitgevoerd), "niet_uitgevoerd": len(resultaat.niet_uitgevoerd),
        "onduidelijk": resultaat.onduidelijk,
    }
    if resultaat.onderbroken_plan:
        staat["onderbroken_plan"] = resultaat.onderbroken_plan
    werkmap.schrijf_staat(staat)
    werkmap.wis_journaal()
    return resultaat


@dataclass
class Uitvoering:
    schrijfacties: int = 0
    per_soort: dict[str, int] = field(default_factory=dict)
    niet_bevestigd: list[dict[str, Any]] = field(default_factory=list)
    later_niet_zichtbaar: dict[str, list[str]] = field(default_factory=dict)
    aangemaakt: dict[str, str] = field(default_factory=dict)  # emby_uid → jl_uid

    def tel(self, soort: str) -> None:
        self.schrijfacties += 1
        self.per_soort[soort] = self.per_soort.get(soort, 0) + 1


def voer_uit(plan: Plan, client: JellyfinClient, werkmap: Werkmap, staat: dict[str, Any], run_id: str,
             melden: Callable[[str], None], testhaak_afbreken: int | None = None) -> Uitvoering:
    uitvoering = Uitvoering()
    werkmap.journaal({"t": "run_begin", "run": run_id, "plan_sha256": plan.sha256(), "tijd": nu_utc()})
    userdata_geschreven = 0
    for g in plan.gebruikers:
        if g.status == "ongeldige_naam":
            continue
        jl_uid = _zorg_voor_gebruiker(g, client, werkmap, run_id, uitvoering, melden)
        zichtbaar: set[str] | None = None
        if g.status == "aanmaken":
            zichtbaar = set(lees_gebruiker_items(client, jl_uid))
        for actie in sorted(g.acties, key=lambda a: a.emby_id):
            if zichtbaar is not None and actie.jl_id not in zichtbaar:
                uitvoering.later_niet_zichtbaar.setdefault(g.emby_uid, []).append(actie.emby_id)
                continue
            werkmap.journaal({"t": "voornemen", "run": run_id, "emby_uid": g.emby_uid, "jl_uid": jl_uid,
                              "volgende_p": _vorige_na(g, actie.emby_id),
                              **{k: v for k, v in actie.naar_json().items() if k != "emby_uid"}})
            antwoord = client.zet_userdata(jl_uid, actie.jl_id, actie.velden)
            uitvoering.tel("userdata")
            userdata_geschreven += 1
            if testhaak_afbreken is not None and userdata_geschreven >= testhaak_afbreken:
                # Alleen voor JLT-71: harde afbreking ná het verzoek en vóór "klaar" (het lastigste moment).
                melden(f"TESTHAAK: afbreken na {userdata_geschreven} UserData-schrijfacties")
                os._exit(137)
            if antwoord and not velden_toegepast(Kijkgegevens.uit_userdata(antwoord), actie.velden):
                uitvoering.niet_bevestigd.append({"emby_uid": g.emby_uid, "emby_id": actie.emby_id, "jl_id": actie.jl_id})
            werkmap.journaal({"t": "klaar", "run": run_id, "emby_uid": g.emby_uid, "emby_id": actie.emby_id,
                              "jl_id": actie.jl_id, "emby": _vorige_na(g, actie.emby_id)})
        overgeslagen = set(uitvoering.later_niet_zichtbaar.get(g.emby_uid, [])) | set(g.niet_zichtbaar)
        items = {
            emby_id: {"jl_id": g.koppelingen[emby_id].jl_id, "emby": _vorige_na(g, emby_id)}
            for emby_id in g.basis if emby_id not in overgeslagen
        }
        werkmap.journaal({"t": "gebruiker_klaar", "run": run_id, "emby_uid": g.emby_uid, "jl_uid": jl_uid,
                          "naam": g.jl_naam, "items": items})
    werkmap.journaal({"t": "run_einde", "run": run_id, "tijd": nu_utc()})
    # Journaal verwerken in de staat (compact) en leegmaken.
    for record in werkmap.journaal_regels():
        if record.get("t") in ("gebruiker_aangemaakt", "beleid_geschreven", "config_geschreven", "klaar", "gebruiker_klaar"):
            _boek(staat, record)
    staat.pop("onderbroken_plan", None)
    werkmap.schrijf_staat(staat)
    werkmap.wis_journaal()
    return uitvoering


def _vorige_na(g: GebruikerPlan, emby_id: str) -> dict[str, Any]:
    """P voor de volgende run: Emby nu, met openstaande beslissingen behouden (zie `volgende_vorige`)."""
    e = Kijkgegevens.van_json(g.emby_kijk[emby_id])
    actie = next((a for a in g.acties if a.emby_id == emby_id), None)
    j_na = Kijkgegevens.van_json(actie.doel if actie else g.basis[emby_id])
    p = Kijkgegevens.van_json(g.vorige[emby_id]) if emby_id in g.vorige else None
    return volgende_vorige(e, j_na, p).naar_json()


def _zorg_voor_gebruiker(g: GebruikerPlan, client: JellyfinClient, werkmap: Werkmap, run_id: str,
                         uitvoering: Uitvoering, melden: Callable[[str], None]) -> str:
    jl_uid = g.jl_uid
    if g.status == "aanmaken":
        # Bestaat de gebruiker al (afgebroken run tussen aanmaken en journaal)? Dan overnemen in plaats van dubbel aanmaken.
        bestaand = {g2["Name"].casefold(): g2 for g2 in client.gebruikers()}.get(g.jl_naam.casefold())
        if bestaand is None:
            melden(f"Jelly Leon: gebruiker {g.jl_naam} aanmaken (wachtwoord niet overgezet)")
            wachtwoord = secrets.token_urlsafe(32)  # nergens bewaard: inloggen kan pas na een nieuw wachtwoord of SSO
            nieuw = client.maak_gebruiker(g.jl_naam, wachtwoord)
            del wachtwoord
            uitvoering.tel("gebruiker")
            jl_uid = str(nieuw["Id"])
        else:
            jl_uid = str(bestaand["Id"])
        werkmap.journaal({"t": "gebruiker_aangemaakt", "run": run_id, "emby_uid": g.emby_uid, "jl_uid": jl_uid,
                          "naam": g.jl_naam, "tijd": nu_utc()})
        uitvoering.aangemaakt[g.emby_uid] = jl_uid
        g.jl_uid = jl_uid
    assert jl_uid is not None
    if g.beleid_schrijven:
        huidig = client.gebruiker(jl_uid).get("Policy") or {}
        doel = dict(g.beleid_doel)
        doel["AccessSchedules"] = [{**s, "UserId": jl_uid} for s in doel.get("AccessSchedules") or []]
        client.zet_beleid(jl_uid, {**huidig, **doel})
        uitvoering.tel("beleid")
        terug = client.gebruiker(jl_uid).get("Policy") or {}
        werkmap.journaal({"t": "beleid_geschreven", "run": run_id, "emby_uid": g.emby_uid,
                          "sha": instellingen_sha(terug, sorted(g.beleid_doel))})
    if g.config_schrijven:
        huidig = client.gebruiker(jl_uid).get("Configuration") or {}
        client.zet_configuratie(jl_uid, {**huidig, **g.config_doel})
        uitvoering.tel("configuratie")
        terug = client.gebruiker(jl_uid).get("Configuration") or {}
        werkmap.journaal({"t": "config_geschreven", "run": run_id, "emby_uid": g.emby_uid,
                          "sha": instellingen_sha(terug, sorted(g.config_doel))})
    return jl_uid
