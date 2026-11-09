"""Minimale HTTP-client op de standaardbibliotheek: geen redirects, geen omgevingsproxy's, vaste time-outs.

- Redirects worden nooit gevolgd (een redirect zou de sleutelheader naar een ander adres kunnen sturen).
- Proxy-instellingen uit de omgeving worden genegeerd (de sleutel gaat alleen naar het opgegeven adres).
- Alleen GET wordt bij een tijdelijke fout herhaald; schrijfacties nooit automatisch.
- Het spoor (`spoor`) bevat methode, pad, querysleutels (geen waarden), status en duur — nooit headers of sleutels.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .fouten import VerbindingsFout


class _GeenRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001, ARG002
        raise VerbindingsFout(f"server antwoordde met een redirect ({code}); redirects worden nooit gevolgd", status=code)


def controleer_basis_url(url: str, omschrijving: str) -> str:
    deel = urllib.parse.urlsplit(url)
    if deel.scheme not in ("http", "https") or not deel.hostname:
        raise VerbindingsFout(f"{omschrijving}: ongeldig adres {url!r} (verwacht http(s)://host:poort)")
    if deel.username or deel.password or deel.query or deel.fragment:
        raise VerbindingsFout(f"{omschrijving}: het adres mag geen gebruikersnaam, wachtwoord, query of fragment bevatten")
    return url.rstrip("/")


@dataclass
class Antwoord:
    status: int
    data: Any


class HttpClient:
    def __init__(
        self,
        basis_url: str,
        headers: dict[str, str],
        omschrijving: str,
        timeout: float = 30.0,
        spoor: Callable[[dict[str, Any]], None] | None = None,
        pogingen_get: int = 3,
    ) -> None:
        self.basis_url = controleer_basis_url(basis_url, omschrijving)
        self._headers = dict(headers)
        self.omschrijving = omschrijving
        self.timeout = timeout
        self.spoor = spoor
        self.pogingen_get = max(1, pogingen_get)
        self._opener = urllib.request.build_opener(_GeenRedirect(), urllib.request.ProxyHandler({}))

    def _url(self, pad: str, query: dict[str, Any] | None) -> str:
        url = self.basis_url + pad
        if query:
            schoon = {k: ("true" if v is True else "false" if v is False else v) for k, v in query.items() if v is not None}
            url += "?" + urllib.parse.urlencode(schoon, doseq=True)
        return url

    def verzoek(self, methode: str, pad: str, query: dict[str, Any] | None = None, body: Any = None) -> Antwoord:
        """Voert één verzoek uit (GET met herhaling bij tijdelijke fouten). Fouten → VerbindingsFout met status."""
        pogingen = self.pogingen_get if methode == "GET" else 1
        laatste: VerbindingsFout | None = None
        for poging in range(1, pogingen + 1):
            try:
                return self._een_verzoek(methode, pad, query, body)
            except VerbindingsFout as fout:
                laatste = fout
                tijdelijk = fout.status is None or fout.status >= 500 or fout.status == 429
                if methode != "GET" or not tijdelijk or poging == pogingen:
                    raise
                time.sleep(min(8.0, 0.5 * 2 ** (poging - 1)))
        raise laatste or VerbindingsFout("onbekende fout")

    def _een_verzoek(self, methode: str, pad: str, query: dict[str, Any] | None, body: Any) -> Antwoord:
        url = self._url(pad, query)
        data = None
        headers = {"Accept": "application/json", **self._headers}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        verzoek = urllib.request.Request(url, data=data, method=methode, headers=headers)  # noqa: S310 - schema gecontroleerd
        begin = time.monotonic()
        status: int | None = None
        try:
            with self._opener.open(verzoek, timeout=self.timeout) as antwoord:
                status = antwoord.status
                ruw = antwoord.read()
        except urllib.error.HTTPError as fout:
            status = fout.code
            tekst = fout.read(300).decode("utf-8", "replace").strip().replace("\n", " ")
            self._spoor(methode, pad, query, status, begin)
            raise VerbindingsFout(f"{self.omschrijving}: {methode} {pad} gaf HTTP {status}: {tekst[:200]}", status=status) from None
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as fout:
            self._spoor(methode, pad, query, None, begin)
            reden = getattr(fout, "reason", fout)
            raise VerbindingsFout(f"{self.omschrijving}: {methode} {pad} niet bereikbaar ({reden})") from None
        self._spoor(methode, pad, query, status, begin)
        if not ruw:
            return Antwoord(status or 0, None)
        try:
            return Antwoord(status or 0, json.loads(ruw))
        except json.JSONDecodeError:
            return Antwoord(status or 0, ruw.decode("utf-8", "replace"))

    def _spoor(self, methode: str, pad: str, query: dict[str, Any] | None, status: int | None, begin: float) -> None:
        if self.spoor is None:
            return
        self.spoor(
            {
                "doel": self.omschrijving,
                "methode": methode,
                "pad": pad,
                "query_sleutels": sorted(query) if query else [],
                "status": status,
                "ms": round((time.monotonic() - begin) * 1000),
            }
        )
