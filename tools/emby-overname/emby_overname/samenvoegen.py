"""Samenvoegregels per item en per gebruiker (B03-015 A7, JLT-71) — puur en zonder netwerk, dus volledig unit-getest.

E = Emby nu, J = Jelly Leon nu, P = Emby bij de vorige geslaagde overzetting (of None bij de eerste).

- **Gezien:** eens gezien blijft gezien. E gezien en J niet → gezien zetten. Nooit terug naar "niet gezien".
- **Aantal keren gezien:** eerste keer max(E, J); daarna J + (E − P) (alleen de nieuwe keren uit Emby erbij, zodat kijken
  in beide servers samen telt). Een daling in Emby verandert niets.
- **Datum laatst gezien:** de nieuwste van E en J.
- **Hervatpunt (ticks, exact):** volgens het nieuwste moment. Alleen als Emby sinds P veranderde én Emby nieuwer is (of
  Jelly Leon nog niets heeft) wordt het hervatpunt van Emby gezet; is Jelly Leon nieuwer, dan blijft Jelly Leon staan.
- **Favoriet:** E favoriet en J niet → zetten, behalve als het al bij de vorige run favoriet was (dan heeft iemand het in
  Jelly Leon weggehaald). Een in Emby verwijderde favoriet wordt nooit automatisch in Jelly Leon verwijderd.
- **Beoordeling:** zetten als Jelly Leon er geen heeft; anders nooit stil overschrijven.

Containers (serie, seizoen, album, collectie, persoon, …) krijgen alleen favoriet en beoordeling; gezien/aantal zijn daar
afgeleid van de onderliggende items.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from .hulp import ticks_naar_datum
from .model import CONTAINER, Kijkgegevens


def samenvoegen(e: Kijkgegevens, j: Kijkgegevens, p: Kijkgegevens | None, item_type: str
                ) -> tuple[dict[str, Any], Kijkgegevens]:
    """Geeft de UserData-velden om te schrijven (leeg = niets) en de verwachte Jelly Leon-toestand daarna."""
    velden: dict[str, Any] = {}
    doel = j
    if item_type not in CONTAINER:
        if e.gezien and not j.gezien:
            velden["Played"] = True
            doel = replace(doel, gezien=True)
        if p is None:
            aantal = max(e.aantal, j.aantal)
        else:
            aantal = j.aantal + max(0, e.aantal - p.aantal)
        if aantal != j.aantal:
            velden["PlayCount"] = aantal
            doel = replace(doel, aantal=aantal)
        if e.laatst is not None and (j.laatst is None or e.laatst > j.laatst):
            velden["LastPlayedDate"] = ticks_naar_datum(e.laatst)
            doel = replace(doel, laatst=e.laatst)
        if e.positie != j.positie:
            emby_gewijzigd = p is None or e.positie != p.positie or e.laatst != p.laatst
            jl_leeg = j.positie == 0 and not j.gezien and j.aantal == 0 and j.laatst is None
            emby_nieuwer = e.laatst is not None and (j.laatst is None or e.laatst > j.laatst)
            if emby_gewijzigd and (emby_nieuwer or jl_leeg):
                velden["PlaybackPositionTicks"] = e.positie
                doel = replace(doel, positie=e.positie)
    if e.favoriet and not j.favoriet and not (p is not None and p.favoriet):
        velden["IsFavorite"] = True
        doel = replace(doel, favoriet=True)
    if e.beoordeling is not None and j.beoordeling is None:
        velden["Rating"] = e.beoordeling
        doel = replace(doel, beoordeling=e.beoordeling, vind_ik_leuk=e.beoordeling >= 6.5)
    elif e.beoordeling is None and e.vind_ik_leuk is not None and j.vind_ik_leuk is None and j.beoordeling is None:
        velden["Likes"] = e.vind_ik_leuk
        doel = replace(doel, vind_ik_leuk=e.vind_ik_leuk, beoordeling=10.0 if e.vind_ik_leuk else 1.0)
    return velden, doel


# --- verschillen tussen Emby en Jelly Leon (na het schrijven, of voorspeld in de proefrun) --------------------------

ACTIE = "actie"  # er moet iets gebeuren (bijv. alsnog overzetten of handmatig instellen)
BESLISSING = "beslissing"  # de gebruiker kiest
KENNISNAME = "kennisname"  # verklaard verschil; akkoord van de gebruiker volstaat


def verschillen_item(e: Kijkgegevens, j: Kijkgegevens, p: Kijkgegevens | None, item_type: str) -> list[dict[str, str]]:
    """Elk verschil tussen de Emby-kijkgegevens en Jelly Leon voor één gekoppeld item, met soort, reden en uitleg."""
    uit: list[dict[str, str]] = []

    def voeg(soort: str, reden: str, klasse: str, uitleg: str) -> None:
        uit.append({"soort": soort, "reden": reden, "klasse": klasse, "uitleg": uitleg})

    if item_type not in CONTAINER:
        if e.gezien and not j.gezien:
            voeg("gezien", "gezien_niet_overgezet", ACTIE, "In Emby gezien, in Jelly Leon niet.")
        elif not e.gezien and j.gezien:
            if p is not None and p.gezien:
                voeg("gezien", "gezien_teruggezet_in_emby", BESLISSING,
                     "In Emby sinds de vorige overzetting weer op 'niet gezien'; Jelly Leon houdt 'gezien' (eens gezien "
                     "blijft gezien). Beslis of het in Jelly Leon ook terug moet.")
            elif e.positie == 0 and e.aantal == 0:
                voeg("gezien", "gezien_alleen_in_jelly_leon", KENNISNAME, "In Jelly Leon gezien, in Emby (nog) niet.")
        if j.aantal < e.aantal:
            voeg("aantal", "aantal_lager", ACTIE, f"Aantal keren gezien: Emby {e.aantal}, Jelly Leon {j.aantal}.")
        if e.laatst is not None and (j.laatst is None or j.laatst < e.laatst):
            voeg("datum", "datum_ouder", ACTIE,
                 f"Laatst gezien: Emby {ticks_naar_datum(e.laatst)}, Jelly Leon {ticks_naar_datum(j.laatst) or '—'}.")
        if e.positie != j.positie:
            if j.laatst is not None and (e.laatst is None or j.laatst > e.laatst):
                voeg("hervatpunt", "hervatpunt_jelly_leon_nieuwer", KENNISNAME,
                     "Jelly Leon is later bekeken dan Emby; het nieuwste hervatpunt (Jelly Leon) blijft staan.")
            elif p is not None and e.positie == p.positie and e.laatst == p.laatst:
                voeg("hervatpunt", "hervatpunt_in_jelly_leon_gewijzigd", KENNISNAME,
                     "Emby is sinds de vorige overzetting niet veranderd; het hervatpunt in Jelly Leon is daarna gewijzigd.")
            elif e.laatst is not None and j.laatst is not None and e.laatst == j.laatst:
                voeg("hervatpunt", "conflict_hervatpunt", BESLISSING,
                     "Beide servers hebben hetzelfde moment maar een ander hervatpunt; kies welk hervatpunt geldt.")
            else:
                voeg("hervatpunt", "hervatpunt_niet_overgezet", ACTIE, "Het hervatpunt van Emby staat niet in Jelly Leon.")
    if e.favoriet != j.favoriet:
        if e.favoriet and p is not None and p.favoriet:
            voeg("favoriet", "favoriet_in_jelly_leon_verwijderd", KENNISNAME,
                 "Al eerder overgezet en daarna in Jelly Leon als favoriet verwijderd; dat blijft zo.")
        elif e.favoriet:
            voeg("favoriet", "favoriet_niet_overgezet", ACTIE, "Favoriet in Emby, niet in Jelly Leon.")
        elif p is not None and p.favoriet:
            voeg("favoriet", "favoriet_verwijderd_in_emby", BESLISSING,
                 "In Emby sinds de vorige overzetting geen favoriet meer; in Jelly Leon nog wel. Beslis of het in Jelly "
                 "Leon ook weg moet (de tool verwijdert nooit zelf).")
        else:
            voeg("favoriet", "favoriet_alleen_in_jelly_leon", KENNISNAME, "Favoriet in Jelly Leon, niet in Emby.")
    if e.beoordeling is not None and e.beoordeling != j.beoordeling:
        klasse, reden = (ACTIE, "beoordeling_niet_overgezet") if j.beoordeling is None else (BESLISSING, "conflict_beoordeling")
        voeg("beoordeling", reden, klasse, f"Beoordeling: Emby {e.beoordeling}, Jelly Leon {j.beoordeling}.")
    elif e.beoordeling is None and e.vind_ik_leuk is not None and e.vind_ik_leuk != j.vind_ik_leuk:
        voeg("beoordeling", "conflict_beoordeling" if j.vind_ik_leuk is not None else "beoordeling_niet_overgezet",
             BESLISSING if j.vind_ik_leuk is not None else ACTIE,
             f"Vind ik leuk: Emby {e.vind_ik_leuk}, Jelly Leon {j.vind_ik_leuk}.")
    return uit


def volgende_vorige(e: Kijkgegevens, j_na: Kijkgegevens, p: Kijkgegevens | None) -> Kijkgegevens:
    """De nieuwe P na een geslaagde run: de Emby-waarden, behalve een openstaande beslissing (in Emby teruggezet of
    favoriet verwijderd, in Jelly Leon nog aanwezig) — die blijft zichtbaar tot de gebruiker haar oplost."""
    nieuw = e
    if p is not None:
        if p.gezien and not e.gezien and j_na.gezien:
            nieuw = replace(nieuw, gezien=True)
        if p.favoriet and not e.favoriet and j_na.favoriet:
            nieuw = replace(nieuw, favoriet=True)
    return nieuw


def toepassen(j: Kijkgegevens, velden: dict[str, Any]) -> Kijkgegevens:
    """Voorspelt de Jelly Leon-toestand na een UserData-schrijfactie (gebruikt in de proefrun en bij hervatten)."""
    from .hulp import datum_naar_ticks

    nieuw = j
    if "Played" in velden:
        nieuw = replace(nieuw, gezien=bool(velden["Played"]))
    if "PlayCount" in velden:
        nieuw = replace(nieuw, aantal=int(velden["PlayCount"]))
    if "LastPlayedDate" in velden:
        nieuw = replace(nieuw, laatst=datum_naar_ticks(velden["LastPlayedDate"]))
    if "PlaybackPositionTicks" in velden:
        nieuw = replace(nieuw, positie=int(velden["PlaybackPositionTicks"]))
    if "IsFavorite" in velden:
        nieuw = replace(nieuw, favoriet=bool(velden["IsFavorite"]))
    if "Rating" in velden:
        nieuw = replace(nieuw, beoordeling=float(velden["Rating"]), vind_ik_leuk=float(velden["Rating"]) >= 6.5)
    if "Likes" in velden:
        nieuw = replace(nieuw, vind_ik_leuk=bool(velden["Likes"]), beoordeling=10.0 if velden["Likes"] else 1.0)
    return nieuw


def velden_toegepast(j: Kijkgegevens, velden: dict[str, Any]) -> bool:
    """Is elke te schrijven waarde al aanwezig in Jelly Leon? (hervatten zonder dubbele schrijfacties)"""
    return toepassen(j, velden) == j
