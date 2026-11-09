"""Loggende HTTP-proxy voor de verkeersmeting (JLT-73): staat tussen de overnametool en Emby (en, voor het tellen van
schrijfacties, tussen de tool en Jelly Leon).

Logt per verzoek alleen tijd, methode, pad, de namen van de queryparameters, de status en de grootte — nooit headers
(dus nooit een API-sleutel). Staat er toch een sleutel in de URL (`api_key`, `X-Emby-Token`, `ApiKey`), dan wordt dat als
`sleutel_in_url: true` gemarkeerd en wordt de waarde niet gelogd. De proxy stuurt alles ongewijzigd door: het is een
meetinstrument, geen filter (de weigering zit in de tool zelf).
"""

from __future__ import annotations

import http.client
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlsplit

SLEUTEL_PARAMETERS = {"api_key", "x-emby-token", "apikey", "token"}
DOORGEEF_HEADERS_WEG = {"connection", "keep-alive", "proxy-connection", "transfer-encoding", "upgrade", "host"}


class LoggendeProxy:
    def __init__(self, doel_host: str, doel_poort: int, naam: str) -> None:
        self.doel = (doel_host, doel_poort)
        self.naam = naam
        self.regels: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        eigenaar = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args: Any) -> None:
                pass

            def _stuur(self) -> None:
                deel = urlsplit(self.path)
                query_namen = sorted(parse_qs(deel.query, keep_blank_values=True))
                lengte = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(lengte) if lengte else None
                headers = {k: v for k, v in self.headers.items() if k.lower() not in DOORGEEF_HEADERS_WEG}
                begin = time.monotonic()
                status, inhoud, antwoord_headers = 502, b"", {}
                try:
                    verbinding = http.client.HTTPConnection(*eigenaar.doel, timeout=300)
                    verbinding.request(self.command, self.path, body=body, headers=headers)
                    antwoord = verbinding.getresponse()
                    status = antwoord.status
                    inhoud = antwoord.read()
                    antwoord_headers = {k: v for k, v in antwoord.getheaders() if k.lower() not in DOORGEEF_HEADERS_WEG
                                        and k.lower() != "content-length"}
                    verbinding.close()
                except OSError as fout:
                    inhoud = json.dumps({"proxyfout": str(fout)}).encode()
                with eigenaar._lock:
                    eigenaar.regels.append({
                        "tijd": time.time(), "proxy": eigenaar.naam, "methode": self.command, "pad": deel.path,
                        "query_sleutels": query_namen, "status": status, "bytes": len(inhoud),
                        "sleutel_in_url": any(q.casefold() in SLEUTEL_PARAMETERS for q in query_namen),
                        "query": {k: v[-1] for k, v in parse_qs(deel.query).items()
                                  if k.casefold() in ("userid", "ids") and k.casefold() not in SLEUTEL_PARAMETERS},
                        "ms": round((time.monotonic() - begin) * 1000),
                    })
                self.send_response(status)
                for k, v in antwoord_headers.items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(inhoud)))
                self.end_headers()
                self.wfile.write(inhoud)

            do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = do_OPTIONS = _stuur  # noqa: N815

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.poort = self.httpd.server_address[1]
        self.url = f"http://127.0.0.1:{self.poort}"
        self._thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self._thread.start()

    def markeer(self) -> int:
        with self._lock:
            return len(self.regels)

    def sinds(self, merk: int) -> list[dict[str, Any]]:
        with self._lock:
            return list(self.regels[merk:])

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()

    def schrijf(self, pad: str) -> None:
        with self._lock, open(pad, "w", encoding="utf-8") as f:
            for r in self.regels:
                f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
