"""Fouttypen met een Nederlandse melding en een vaste exitcode."""

from __future__ import annotations

EXIT_OK = 0
EXIT_GEBRUIK = 2
EXIT_AKKOORD = 3
EXIT_PLAN_GEWIJZIGD = 4
EXIT_VERBINDING = 5
EXIT_CONTROLE = 6
EXIT_GEHEIM = 7
EXIT_ALLEEN_LEZEN = 8
EXIT_DOEL = 9


class OvernameFout(Exception):
    """Fout die de CLI als nette Nederlandse melding met exitcode toont."""

    exit_code = 1

    def __init__(self, bericht: str, exit_code: int | None = None) -> None:
        super().__init__(bericht)
        if exit_code is not None:
            self.exit_code = exit_code


class AlleenLezenFout(OvernameFout):
    """Een verzoek naar Emby dat geen GET is of buiten de witte lijst valt; geweigerd vóór het netwerk."""

    exit_code = EXIT_ALLEEN_LEZEN


class NietToegestaneRoute(OvernameFout):
    """Een verzoek naar Jelly Leon buiten de witte lijst van officiële routes; geweigerd vóór het netwerk."""

    exit_code = EXIT_ALLEEN_LEZEN


class DoelFout(OvernameFout):
    """Het doel van de overname is niet aantoonbaar Jellyfin/Jelly Leon (bijv. per vergissing Emby, of dezelfde server als
    de bron); elke schrijfactie wordt dan vóór het netwerk geweigerd (HARDE EIS: nooit schrijven in Emby)."""

    exit_code = EXIT_DOEL


class VerbindingsFout(OvernameFout):
    exit_code = EXIT_VERBINDING

    def __init__(self, bericht: str, status: int | None = None) -> None:
        super().__init__(bericht)
        self.status = status


class GeheimFout(OvernameFout):
    exit_code = EXIT_GEHEIM


class AkkoordFout(OvernameFout):
    exit_code = EXIT_AKKOORD


class PlanGewijzigd(OvernameFout):
    exit_code = EXIT_PLAN_GEWIJZIGD


class ControleFout(OvernameFout):
    exit_code = EXIT_CONTROLE
