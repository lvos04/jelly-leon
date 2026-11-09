"""Het plan: per Emby-gebruiker de doelgebruiker, rechten, en per item met kijkgegevens de koppeling en de schrijfactie.

Het plan wordt in de proefrun gemaakt en getoond; `overzetten` maakt het opnieuw uit verse gegevens en schrijft alleen als
het identiek is aan het plan waarop de gebruiker akkoord gaf (sha256). Het plan bevat alleen wat de tool zou schrijven en
de basis waarop dat berust; verschillen en de afhandellijst volgen uit `vergelijk.py`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .hulp import normaliseer_naam, sha256_json
from .jellyfin import JellyfinClient
from .koppelen import JellyLeonIndex, Koppelaar, Koppeling, Padvertaling
from .model import BENOEMD, ItemInfo, Kijkgegevens
from .rechten import (
    Bibliotheekkoppeling,
    RechtRegel,
    instellingen_sha,
    koppel_bibliotheken,
    vergelijk_beleid,
    vergelijk_configuratie,
    vertaal_beleid,
    vertaal_configuratie,
)
from .samenvoegen import samenvoegen

PLAN_SCHEMA = "jelly-leon/emby-overname-plan/1"
GELDIGE_NAAM = re.compile(r"^[\w\ \-'._@+]+$")


@dataclass
class Opties:
    paden: list[Padvertaling] = field(default_factory=list)
    gebruikers: dict[str, str] = field(default_factory=dict)  # genormaliseerde Emby-naam → Jelly Leon-naam
    met_spoorkeuzes: bool = True


@dataclass
class Doelopname:
    info: dict[str, Any]
    bibliotheken: list[dict[str, Any]]
    classificaties: list[dict[str, Any]]
    gebruikers: dict[str, dict[str, Any]]  # genormaliseerde naam → gebruiker (met Policy en Configuration)
    index: JellyLeonIndex
    per_gebruiker: dict[str, dict[str, Kijkgegevens]]  # jl_uid → zichtbaar item → kijkgegevens

    def zichtbaar(self, jl_uid: str) -> set[str]:
        return set(self.per_gebruiker.get(jl_uid, {}))


def lees_doel(client: JellyfinClient) -> Doelopname:
    gebruikers = {normaliseer_naam(g["Name"]): client.gebruiker(g["Id"]) for g in client.gebruikers()}
    index = JellyLeonIndex(list(client.alle_items()))
    per_gebruiker = {g["Id"]: lees_gebruiker_items(client, g["Id"]) for g in gebruikers.values()}
    return Doelopname(client.systeeminfo(), client.bibliotheken(), client.leeftijdsclassificaties(), gebruikers, index,
                      per_gebruiker)


def lees_gebruiker_items(client: JellyfinClient, jl_uid: str) -> dict[str, Kijkgegevens]:
    return {str(i["Id"]): Kijkgegevens.uit_userdata(i.get("UserData")) for i in client.alle_items(jl_uid)}


@dataclass
class Actie:
    emby_uid: str
    emby_id: str
    jl_id: str
    velden: dict[str, Any]
    basis: dict[str, Any]
    doel: dict[str, Any]
    emby: dict[str, Any]

    def naar_json(self) -> dict[str, Any]:
        return {"emby_uid": self.emby_uid, "emby_id": self.emby_id, "jl_id": self.jl_id, "velden": self.velden,
                "basis": self.basis, "doel": self.doel, "emby": self.emby}

    @classmethod
    def van_json(cls, d: dict[str, Any]) -> Actie:
        return cls(**d)


@dataclass
class GebruikerPlan:
    emby_uid: str
    emby_naam: str
    jl_naam: str
    jl_uid: str | None
    status: str  # aanmaken | aangemaakt_door_tool | bestaand | ongeldige_naam
    beleid_doel: dict[str, Any]
    config_doel: dict[str, Any]
    beleid_schrijven: bool
    config_schrijven: bool
    rechten: list[RechtRegel]
    acties: list[Actie]
    koppelingen: dict[str, Koppeling]
    basis: dict[str, dict[str, Any]]  # emby_id → J vóór (alleen gekoppelde items)
    niet_zichtbaar: list[str]  # gekoppelde items die de Jelly Leon-gebruiker niet ziet
    vorige: dict[str, dict[str, Any]]  # emby_id → P (alleen als dezelfde koppeling)
    emby_kijk: dict[str, dict[str, Any]]  # emby_id → E (alleen gekoppelde, zichtbare items)
    handmatig_gewijzigd: bool = False  # door de tool aangemaakt, maar rechten daarna in Jelly Leon gewijzigd
    zonder_gegevens: list[str] = field(default_factory=list)  # vorige keer wel kijkgegevens in Emby, nu niet meer

    def plan_json(self) -> dict[str, Any]:
        """Het deel dat de akkoord-sha bepaalt: wie, welk beleid, welke schrijfacties op welke basis."""
        return {
            "emby_uid": self.emby_uid, "jl_naam": self.jl_naam, "status": self.status,
            "beleid": self.beleid_doel if self.beleid_schrijven else None,
            "configuratie": self.config_doel if self.config_schrijven else None,
            "acties": [a.naar_json() for a in sorted(self.acties, key=lambda a: a.emby_id)],
        }


@dataclass
class Plan:
    emby_server_id: str
    jl_server_id: str
    gebruikers: list[GebruikerPlan]
    bibliotheken: Bibliotheekkoppeling
    alleen_in_jl: list[str]

    def naar_json(self) -> dict[str, Any]:
        return {"schema": PLAN_SCHEMA, "emby_server_id": self.emby_server_id, "jl_server_id": self.jl_server_id,
                "gebruikers": [g.plan_json() for g in self.gebruikers]}

    def sha256(self) -> str:
        return sha256_json(self.naar_json())

    def aantal_schrijfacties(self) -> int:
        return sum(len(g.acties) + int(g.status == "aanmaken") + int(g.beleid_schrijven) + int(g.config_schrijven)
                   for g in self.gebruikers)


def maak_plan(opname: dict[str, Any], doel: Doelopname, staat: dict[str, Any], opties: Opties,
              client: JellyfinClient | None = None) -> Plan:
    emby_items = {k: ItemInfo.van_json(v) for k, v in opname["items"].items()}
    koppelaar = Koppelaar(emby_items, doel.index, opties.paden)
    bib = koppel_bibliotheken(opname["bibliotheken"], doel.bibliotheken, opties.paden)
    staat_gebruikers = staat.get("gebruikers", {})
    plannen: list[GebruikerPlan] = []
    for eg in opname["gebruikers"]:
        emby_uid, emby_naam = str(eg["id"]), str(eg["naam"])
        jl_naam = opties.gebruikers.get(normaliseer_naam(emby_naam), emby_naam)
        jl = doel.gebruikers.get(normaliseer_naam(jl_naam))
        st = staat_gebruikers.get(emby_uid, {})
        if jl is None and not GELDIGE_NAAM.match(jl_naam):
            status = "ongeldige_naam"
        elif jl is None:
            status = "aanmaken"
        elif st.get("aangemaakt_door_tool") and st.get("jl_uid") == jl["Id"]:
            status = "aangemaakt_door_tool"
        else:
            status = "bestaand"
        jl_uid = jl["Id"] if jl else None
        beleid_doel, rechten = vertaal_beleid(eg["beleid"], {}, bib, opname["classificaties"], doel.classificaties, jl_uid)
        config_doel, config_regels = vertaal_configuratie(eg["configuratie"], {}, bib)
        beleid_schrijven = config_schrijven = handmatig = False
        if status == "aanmaken":
            beleid_schrijven = config_schrijven = True
            rechten = rechten + config_regels
        elif status in ("aangemaakt_door_tool", "bestaand") and jl is not None:
            huidig_beleid = instellingen_sha(jl.get("Policy") or {}, sorted(beleid_doel))
            huidig_config = instellingen_sha(jl.get("Configuration") or {}, sorted(config_doel))
            ongewijzigd_beleid = huidig_beleid == st.get("beleid_sha")
            ongewijzigd_config = huidig_config == st.get("config_sha")
            if status == "aangemaakt_door_tool" and ongewijzigd_beleid:
                beleid_schrijven = huidig_beleid != instellingen_sha(beleid_doel, sorted(beleid_doel))
            if status == "aangemaakt_door_tool" and ongewijzigd_config:
                config_schrijven = huidig_config != instellingen_sha(config_doel, sorted(config_doel))
            if status == "aangemaakt_door_tool":
                # De tool beheert deze rechten: de vertaling geldt; afwijkingen in Jelly Leon toont vergelijk.py.
                rechten = rechten + config_regels
                if not (ongewijzigd_beleid and ongewijzigd_config):
                    handmatig = True
            else:
                # Bestaande gebruiker (niet door de tool aangemaakt): het werkelijke verschil met Emby telt.
                vergelijking = vergelijk_beleid(beleid_doel, jl.get("Policy") or {}, bib) + \
                    vergelijk_configuratie(config_doel, jl.get("Configuration") or {})
                vertaling = {r.veld: r for r in rechten if r.status != "gelijk"}
                rechten = [r for r in vergelijking if r.status != "gelijk" or r.veld not in vertaling] + list(vertaling.values())
        zichtbaar = doel.zichtbaar(jl_uid) if jl_uid else None
        gegevens_jl = doel.per_gebruiker.get(jl_uid, {}) if jl_uid else {}
        koppelingen: dict[str, Koppeling] = {}
        acties: list[Actie] = []
        basis: dict[str, dict[str, Any]] = {}
        vorige: dict[str, dict[str, Any]] = {}
        niet_zichtbaar: list[str] = []
        emby_kijk: dict[str, dict[str, Any]] = {}
        benoemd = set(eg.get("benoemde_favorieten") or [])
        # Items die bij de vorige overzetting kijkgegevens hadden maar nu in Emby niet meer (favoriet weg, weer "niet
        # gezien"): ook vergelijken, anders zou zo'n wijziging onzichtbaar blijven. Er wordt dan nooit iets gewist.
        bronnen = dict(eg["kijkgegevens"])
        zonder_gegevens = sorted(e for e, st_item in (st.get("items") or {}).items()
                                 if e not in bronnen and e in emby_items and st_item.get("emby"))
        for emby_id in zonder_gegevens:
            bronnen[emby_id] = Kijkgegevens().naar_json()
        for emby_id, ruw in sorted(bronnen.items()):
            item = emby_items[emby_id]
            e = Kijkgegevens.van_json(ruw)
            if emby_id in benoemd and item.type in BENOEMD and client is not None:
                kandidaten = client.benoemde_items(BENOEMD[item.type], item.naam, jl_uid)
                koppeling = koppelaar.koppel_benoemd(item, kandidaten)
                j_benoemd = {str(k["Id"]): Kijkgegevens.uit_userdata(k.get("UserData")) for k in kandidaten}
                j = j_benoemd.get(koppeling.jl_id or "", Kijkgegevens())
                zichtbaar_item = True
            elif emby_id in benoemd and item.type in BENOEMD:
                koppeling = Koppeling(emby_id, None, reden="ontbreekt", uitleg="benoemd item zonder Jelly Leon-verbinding")
                j, zichtbaar_item = Kijkgegevens(), False
            else:
                koppeling = koppelaar.koppel(emby_id)
                j = gegevens_jl.get(koppeling.jl_id or "", Kijkgegevens())
                zichtbaar_item = zichtbaar is None or (koppeling.jl_id in zichtbaar)
            koppelingen[emby_id] = koppeling
            if koppeling.jl_id is None or status == "ongeldige_naam":
                continue
            if not zichtbaar_item:
                niet_zichtbaar.append(emby_id)
                continue
            st_item = (st.get("items") or {}).get(emby_id) or {}
            p = Kijkgegevens.van_json(st_item["emby"]) if st_item.get("jl_id") == koppeling.jl_id and "emby" in st_item else None
            basis[emby_id] = j.naar_json()
            emby_kijk[emby_id] = ruw
            if p is not None:
                vorige[emby_id] = p.naar_json()
            velden, verwacht = samenvoegen(e, j, p, item.type)
            if velden:
                acties.append(Actie(emby_uid, emby_id, koppeling.jl_id, velden, j.naar_json(), verwacht.naar_json(), ruw))
        plannen.append(GebruikerPlan(emby_uid, emby_naam, jl_naam, jl_uid, status, beleid_doel, config_doel,
                                     beleid_schrijven, config_schrijven, rechten, acties, koppelingen, basis,
                                     niet_zichtbaar, vorige, emby_kijk, handmatig, zonder_gegevens))
    emby_namen = {normaliseer_naam(opties.gebruikers.get(normaliseer_naam(g["naam"]), g["naam"])) for g in opname["gebruikers"]}
    alleen_in_jl = sorted(g["Name"] for k, g in doel.gebruikers.items() if k not in emby_namen)
    return Plan(str(opname["bron"].get("server_id")), str(doel.info.get("Id")), plannen, bib, alleen_in_jl)
