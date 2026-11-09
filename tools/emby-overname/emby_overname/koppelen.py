"""Items koppelen: eerst provider-ID's, daarna het pad (na vertaling van de mountroot); anders afhandellijst.

Regels (bouwplan §10.9.1 stap 4, JLT-72) — bij twijfel nooit een gok:
1. Provider-ID's (IMDb, TMDb, TVDb, en overige zoals MusicBrainz) van hetzelfde itemtype. Een kandidaat telt alleen als
   minstens één ID gelijk is en geen enkele gedeelde soort ID verschilt (zelfde IMDb maar andere TMDb = geen kandidaat).
   Eén kandidaat → gekoppeld (`provider_id`). Meerdere → het pad moet precies één ervan aanwijzen (`pad_bij_dubbel_id`),
   anders reden `dubbel`.
2. Afleveringen zonder eigen ID: de serie (via haar provider-ID's of pad) plus het seizoen- en afleveringnummer zoals Emby
   ze zelf geeft (`serie_seizoen_aflevering`); ontbreekt het seizoennummer, dan wordt niets aangenomen.
3. Pad, na vertaling van de mountroot (`pad`). Meerdere items op hetzelfde pad → `dubbel`.
4. Anders: `geen_id` (het item had geen provider-ID's) of `ontbreekt` (wel ID's, maar geen tegenhanger).
Benoemde items (personen, artiesten, genres, studio's) koppelen op provider-ID of exacte naam (`naam`).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from .hulp import normaliseer_naam, normaliseer_pad
from .model import ONDERSTEUND, ItemInfo

REDENEN = {
    "geen_id": "geen provider-ID's en geen item op hetzelfde pad in Jelly Leon",
    "dubbel": "niet eenduidig: meerdere Jelly Leon-items passen",
    "ontbreekt": "geen tegenhanger in Jelly Leon (ID's en pad gezocht)",
    "ander_bestand": "zelfde item, maar een ander bestand (pad of grootte verschilt)",
    "type_niet_ondersteund": "dit soort item kan de tool niet koppelen",
}


@dataclass(frozen=True)
class Padvertaling:
    emby: str
    jelly_leon: str

    @classmethod
    def uit_tekst(cls, tekst: str) -> Padvertaling:
        if "=" not in tekst:
            raise ValueError(f"padvertaling {tekst!r}: verwacht <emby-pad>=<jelly-leon-pad>")
        links, rechts = tekst.split("=", 1)
        links, rechts = normaliseer_pad(links.strip()), normaliseer_pad(rechts.strip())
        if not links or not rechts or not links.startswith("/") or not rechts.startswith("/"):
            raise ValueError(f"padvertaling {tekst!r}: beide kanten moeten absolute paden zijn")
        return cls(links, rechts)


def vertaal_pad(pad: str | None, regels: list[Padvertaling]) -> str | None:
    pad = normaliseer_pad(pad)
    if not pad:
        return None
    for regel in sorted(regels, key=lambda r: len(r.emby), reverse=True):
        if pad == regel.emby or pad.startswith(regel.emby + "/"):
            return regel.jelly_leon + pad[len(regel.emby):]
    return pad


@dataclass
class Koppeling:
    emby_id: str
    jl_id: str | None
    methode: str | None = None  # provider_id | pad_bij_dubbel_id | serie_seizoen_aflevering | pad | naam
    reden: str | None = None  # bij geen koppeling: geen_id | dubbel | ontbreekt | type_niet_ondersteund
    kandidaten: list[str] = field(default_factory=list)
    uitleg: str = ""

    def naar_json(self) -> dict[str, Any]:
        return {"emby_id": self.emby_id, "jl_id": self.jl_id, "methode": self.methode, "reden": self.reden,
                "kandidaten": self.kandidaten, "uitleg": self.uitleg}


class JellyLeonIndex:
    """Index van alle Jelly Leon-items (als beheerder gelezen) op type + provider-ID, pad en serie/seizoen/aflevering."""

    def __init__(self, items: list[dict[str, Any]]) -> None:
        self.items: dict[str, ItemInfo] = {}
        self.paden_per_item: dict[str, set[str]] = {}
        self._op_id: dict[tuple[str, str, str], set[str]] = defaultdict(set)
        self._op_pad: dict[str, set[str]] = defaultdict(set)
        self._afleveringen: dict[tuple[str, int, int], set[str]] = defaultdict(set)
        for ruw in items:
            info = ItemInfo.uit_api(ruw)
            self.items[info.id] = info
            for soort, waarde in info.provider_ids.items():
                self._op_id[(info.type, soort, waarde.casefold())].add(info.id)
            paden = {p for p in [info.pad, *(normaliseer_pad(b.get("Path")) for b in ruw.get("MediaSources") or [])] if p}
            self.paden_per_item[info.id] = paden
            for pad in paden:
                self._op_pad[pad].add(info.id)
            if info.type == "Episode" and info.serie_id and info.seizoen is not None and info.aflevering is not None:
                self._afleveringen[(str(info.serie_id), int(info.seizoen), int(info.aflevering))].add(info.id)

    def op_provider(self, item: ItemInfo) -> set[str]:
        kandidaten: set[str] = set()
        for soort, waarde in item.provider_ids.items():
            kandidaten |= self._op_id.get((item.type, soort, waarde.casefold()), set())
        # Een kandidaat met een tegenstrijdige ID van dezelfde soort valt af (bijv. zelfde IMDb, andere TMDb).
        return {k for k in kandidaten if not _tegenstrijdig(item.provider_ids, self.items[k].provider_ids)}

    def op_pad(self, pad: str | None, item_type: str) -> set[str]:
        if not pad:
            return set()
        return {k for k in self._op_pad.get(pad, set()) if self.items[k].type == item_type}

    def aflevering(self, serie_jl_id: str, seizoen: int, aflevering: int) -> set[str]:
        return set(self._afleveringen.get((serie_jl_id, seizoen, aflevering), set()))


def _tegenstrijdig(a: dict[str, str], b: dict[str, str]) -> bool:
    return any(soort in b and a[soort].casefold() != b[soort].casefold() for soort in a)


class Koppelaar:
    def __init__(self, emby_items: dict[str, ItemInfo], index: JellyLeonIndex, paden: list[Padvertaling]) -> None:
        self.emby_items = emby_items
        self.index = index
        self.paden = paden
        self._cache: dict[str, Koppeling] = {}

    def koppel(self, emby_id: str) -> Koppeling:
        if emby_id not in self._cache:
            self._cache[emby_id] = self._koppel(self.emby_items[emby_id])
        return self._cache[emby_id]

    def _koppel(self, item: ItemInfo) -> Koppeling:
        if item.type not in ONDERSTEUND:
            return Koppeling(item.id, None, reden="type_niet_ondersteund", uitleg=f"type {item.type}")
        jl_pad = vertaal_pad(item.pad, self.paden)
        kandidaten = self.index.op_provider(item) if item.provider_ids else set()
        if len(kandidaten) == 1:
            return Koppeling(item.id, next(iter(kandidaten)), methode="provider_id", kandidaten=sorted(kandidaten),
                             uitleg=_ids_tekst(item))
        if len(kandidaten) > 1:
            op_pad = {k for k in kandidaten if jl_pad and jl_pad in self.index.paden_per_item.get(k, set())}
            if len(op_pad) == 1:
                return Koppeling(item.id, next(iter(op_pad)), methode="pad_bij_dubbel_id", kandidaten=sorted(kandidaten),
                                 uitleg=f"{len(kandidaten)} items met {_ids_tekst(item)}; het pad wijst er precies één aan")
            return Koppeling(item.id, None, reden="dubbel", kandidaten=sorted(kandidaten),
                             uitleg=f"{len(kandidaten)} Jelly Leon-items met {_ids_tekst(item)} en geen eenduidig pad")
        if item.type == "Episode":
            koppeling = self._koppel_aflevering(item)
            if koppeling is not None:
                return koppeling
        if item.type == "Season":
            koppeling = self._koppel_seizoen(item)
            if koppeling is not None:
                return koppeling
        op_pad = self.index.op_pad(jl_pad, item.type)
        if len(op_pad) == 1:
            return Koppeling(item.id, next(iter(op_pad)), methode="pad", kandidaten=sorted(op_pad),
                             uitleg=f"pad {jl_pad}")
        if len(op_pad) > 1:
            return Koppeling(item.id, None, reden="dubbel", kandidaten=sorted(op_pad),
                             uitleg=f"{len(op_pad)} Jelly Leon-items op pad {jl_pad}")
        if item.provider_ids or (item.type == "Episode" and self._serie_heeft_ids(item)):
            return Koppeling(item.id, None, reden="ontbreekt",
                             uitleg=f"{_ids_tekst(item) or 'serie-ID'} en pad {jl_pad or '—'} niet gevonden")
        return Koppeling(item.id, None, reden="geen_id", uitleg=f"pad {jl_pad or '—'} niet gevonden")

    def _serie_heeft_ids(self, item: ItemInfo) -> bool:
        serie = self.emby_items.get(str(item.serie_id)) if item.serie_id else None
        return bool(serie and serie.provider_ids)

    def _serie_koppeling(self, item: ItemInfo) -> str | None:
        if not item.serie_id or str(item.serie_id) not in self.emby_items:
            return None
        serie = self.koppel(str(item.serie_id))
        return serie.jl_id

    def _koppel_aflevering(self, item: ItemInfo) -> Koppeling | None:
        serie_jl = self._serie_koppeling(item)
        if serie_jl is None or item.seizoen is None or item.aflevering is None:
            return None  # geen seizoennummer → niets aannemen (absolute nummering e.d.)
        kandidaten = self.index.aflevering(serie_jl, int(item.seizoen), int(item.aflevering))
        if len(kandidaten) == 1:
            return Koppeling(item.id, next(iter(kandidaten)), methode="serie_seizoen_aflevering",
                             kandidaten=sorted(kandidaten), uitleg=f"serie + S{item.seizoen:02d}E{item.aflevering:02d}")
        if len(kandidaten) > 1:
            jl_pad = vertaal_pad(item.pad, self.paden)
            op_pad = {k for k in kandidaten if jl_pad and jl_pad in self.index.paden_per_item.get(k, set())}
            if len(op_pad) == 1:
                return Koppeling(item.id, next(iter(op_pad)), methode="pad_bij_dubbel_id", kandidaten=sorted(kandidaten),
                                 uitleg=f"{len(kandidaten)} afleveringen S{item.seizoen:02d}E{item.aflevering:02d}; pad wijst er één aan")
            return Koppeling(item.id, None, reden="dubbel", kandidaten=sorted(kandidaten),
                             uitleg=f"{len(kandidaten)} afleveringen S{item.seizoen:02d}E{item.aflevering:02d} in de serie")
        return None

    def _koppel_seizoen(self, item: ItemInfo) -> Koppeling | None:
        serie_jl = self._serie_koppeling(item)
        if serie_jl is None or item.aflevering is None:  # bij een seizoen staat het nummer in IndexNumber
            return None
        kandidaten = {
            k for k, info in self.index.items.items()
            if info.type == "Season" and str(info.serie_id) == serie_jl and info.aflevering == item.aflevering
        }
        if len(kandidaten) == 1:
            return Koppeling(item.id, next(iter(kandidaten)), methode="serie_seizoen_aflevering",
                             kandidaten=sorted(kandidaten), uitleg=f"serie + seizoen {item.aflevering}")
        return None

    def koppel_benoemd(self, item: ItemInfo, kandidaten_jl: list[dict[str, Any]]) -> Koppeling:
        """Personen, artiesten, genres, studio's: provider-ID (indien aanwezig), anders exacte naam; uniek of afhandellijst."""
        infos = [ItemInfo.uit_api(k) for k in kandidaten_jl if k.get("Type") == item.type]
        if item.provider_ids:
            met_id = [i for i in infos if any(i.provider_ids.get(s, "").casefold() == w.casefold()
                                              for s, w in item.provider_ids.items())]
            if len(met_id) == 1:
                return Koppeling(item.id, met_id[0].id, methode="provider_id", kandidaten=[met_id[0].id])
        exact = [i for i in infos if normaliseer_naam(i.naam) == normaliseer_naam(item.naam)]
        if len(exact) == 1:
            return Koppeling(item.id, exact[0].id, methode="naam", kandidaten=[exact[0].id], uitleg=f"naam {item.naam!r}")
        if len(exact) > 1:
            return Koppeling(item.id, None, reden="dubbel", kandidaten=sorted(i.id for i in exact),
                             uitleg=f"{len(exact)} items met de naam {item.naam!r}")
        return Koppeling(item.id, None, reden="ontbreekt" if item.provider_ids else "geen_id",
                         uitleg=f"naam {item.naam!r} niet gevonden")


def _ids_tekst(item: ItemInfo) -> str:
    return ", ".join(f"{k}={v}" for k, v in sorted(item.provider_ids.items()))
