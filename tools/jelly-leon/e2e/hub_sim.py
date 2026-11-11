#!/usr/bin/env python3
"""Hub-simulator voor de plugintests van Jelly Leon (B03-017, JLT-68): sleutelset, vingerafdruk en JWT's.

Dit is een **simulator**: hij doet zich voor als de Hub van het TrueNAS Home Platform (contract 1.3 §4) en bewijst
niets over de echte Hub. De Ed25519-handtekening is hier in zuiver Python gemaakt (RFC 8032) zodat de test geen extra
pakket vraagt; de plugin controleert haar met zijn eigen implementatie in C#. Niet bedoeld voor productie: de
berekening is niet constant in tijd en de sleutels zijn wegwerpsleutels.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import time
import uuid
from typing import Any

P = 2**255 - 19
L = 2**252 + 27742317777372353535851937790883648493
D = -121665 * pow(121666, P - 2, P) % P
_I = pow(2, (P - 1) // 4, P)
ALFABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
Punt = tuple[int, int, int, int]


def _inv(x: int) -> int:
    return pow(x, P - 2, P)


def _x_van(y: int) -> int:
    xx = (y * y - 1) * _inv(D * y * y + 1)
    x = pow(xx, (P + 3) // 8, P)
    if (x * x - xx) % P != 0:
        x = x * _I % P
    return P - x if x % 2 else x


_BY = 4 * _inv(5) % P
_BX = _x_van(_BY)
_B: Punt = (_BX, _BY, 1, _BX * _BY % P)


def _plus(p: Punt, q: Punt) -> Punt:
    x1, y1, z1, t1 = p
    x2, y2, z2, t2 = q
    a = (y1 - x1) * (y2 - x2) % P
    b = (y1 + x1) * (y2 + x2) % P
    c = t1 * 2 * D * t2 % P
    d = z1 * 2 * z2 % P
    e, f, g, h = b - a, d - c, d + c, b + a
    return (e * f % P, g * h % P, f * g % P, e * h % P)


def _maal(s: int, p: Punt) -> Punt:
    q: Punt = (0, 1, 1, 0)
    while s > 0:
        if s & 1:
            q = _plus(q, p)
        p = _plus(p, p)
        s >>= 1
    return q


def _bytes(p: Punt) -> bytes:
    x, y, z, _ = p
    zi = _inv(z)
    x, y = x * zi % P, y * zi % P
    return (y | ((x & 1) << 255)).to_bytes(32, "little")


def _uitgebreid(zaad: bytes) -> tuple[int, bytes]:
    h = hashlib.sha512(zaad).digest()
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:]


def publieke_sleutel(zaad: bytes) -> bytes:
    return _bytes(_maal(_uitgebreid(zaad)[0], _B))


def teken(zaad: bytes, bericht: bytes) -> bytes:
    a, voorvoegsel = _uitgebreid(zaad)
    publiek = _bytes(_maal(a, _B))
    r = int.from_bytes(hashlib.sha512(voorvoegsel + bericht).digest(), "little") % L
    grote_r = _bytes(_maal(r, _B))
    h = int.from_bytes(hashlib.sha512(grote_r + publiek + bericht).digest(), "little") % L
    return grote_r + ((r + h * a) % L).to_bytes(32, "little")


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def duimafdruk(x: str) -> str:
    """RFC 7638-duimafdruk van een Ed25519-JWK."""
    return b64url(hashlib.sha256(('{"crv":"Ed25519","kty":"OKP","x":"' + x + '"}').encode()).digest())


def vingerafdruk(jwt_x: list[str], policy_x: list[str]) -> str:
    """De vingerafdruk die de beheerder overtikt (ADR-0031): 16 tekens in vier groepen, eerste 80 bits van de hash."""
    tekst = ("jl-hub-keyset-v1\njwt:" + ",".join(sorted(duimafdruk(x) for x in jwt_x))
             + "\npolicy:" + ",".join(sorted(duimafdruk(x) for x in policy_x)))
    h = hashlib.sha256(tekst.encode()).digest()
    tekens = []
    for i in range(16):
        bit = i * 5
        waarde = (((h[bit // 8] << 8) | h[bit // 8 + 1]) >> (11 - bit % 8)) & 0x1F
        if i and i % 4 == 0:
            tekens.append("-")
        tekens.append(ALFABET[waarde])
    return "".join(tekens)


class Sleutel:
    def __init__(self, kid: str, zaad: bytes | None = None) -> None:
        self.kid = kid
        self.zaad = zaad if zaad is not None else os.urandom(32)
        self.x = b64url(publieke_sleutel(self.zaad))

    def jwk(self) -> dict[str, str]:
        return {"kty": "OKP", "crv": "Ed25519", "x": self.x, "kid": self.kid}


class HubSim:
    """Eén gesimuleerde Hub: een JWT-sleutel, een policy-sleutel en een service_id voor deze koppeling."""

    def __init__(self, audience: str = "jelly-leon") -> None:
        self.audience = audience
        self.jwt = Sleutel("hub-sim-jwt-1")
        self.policy = Sleutel("hub-sim-policy-1")
        self.service_id = str(uuid.uuid4())

    def sleutelset(self) -> dict[str, Any]:
        """De sleutelset zoals de beheerder hem in Jelly Leon plakt (JL4)."""
        return {"jwks": {"keys": [self.jwt.jwk()]}, "policy_public_key": self.policy.jwk()}

    def vingerafdruk(self) -> str:
        return vingerafdruk([self.jwt.x], [self.policy.x])

    def token(self, *, rollen: list[str] | None = None, gebruik: str = "user", sub: str | None = None,
              sleutel: Sleutel | None = None, nu: float | None = None, levensduur: int = 60,
              wijzig: dict[str, Any] | None = None, weglaten: tuple[str, ...] = (), vervals: bool = False,
              kop: dict[str, Any] | None = None) -> str:
        """Maakt een JWT. `wijzig` overschrijft claims, `weglaten` haalt ze weg, `vervals` breekt de handtekening,
        `kop` overschrijft velden van de header (bijvoorbeeld een ander `alg`)."""
        sleutel = sleutel or self.jwt
        iat = int(nu if nu is not None else time.time())
        claims: dict[str, Any] = {
            "iss": "hub", "aud": self.audience, "iat": iat, "nbf": iat, "exp": iat + levensduur,
            "jti": str(uuid.uuid4()), "token_use": gebruik,
        }
        if gebruik == "hub_service":
            claims.update({"sub": "hub", "roles": ["service"], "service_id": self.service_id})
        else:
            claims.update({"sub": sub or str(uuid.uuid4()), "roles": rollen or ["admin"]})
        claims.update(wijzig or {})
        for naam in weglaten:
            claims.pop(naam, None)
        header = {"alg": "EdDSA", "typ": "JWT", "kid": sleutel.kid, **(kop or {})}
        tekst = b64url(json.dumps(header, separators=(",", ":")).encode()) + "." + b64url(json.dumps(claims, separators=(",", ":")).encode())
        handtekening = bytearray(teken(sleutel.zaad, tekst.encode()))
        if vervals:
            handtekening[5] ^= 0x01
        return tekst + "." + b64url(bytes(handtekening))
