"""De Hub-simulator: Ed25519 volgens RFC 8032 (testvectoren), vingerafdruk en JWT-opbouw."""
from __future__ import annotations

import base64
import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "e2e"))

import hub_sim  # noqa: E402

# RFC 8032 §7.1, TEST 1–3: (geheime sleutel, publieke sleutel, bericht, handtekening).
VECTOREN = [
    ("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60",
     "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a", "",
     "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"),
    ("4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb",
     "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c", "72",
     "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00"),
    ("c5aa8df43f9f837bedb7442f31dcb7b166d38535076f094b85ce3a2e0b4458f7",
     "fc51cd8e6218a1a38da47ed00230f0580816ed13ba3303ac5deb911548908025", "af82",
     "6291d657deec24024827e69c3abe01a30ce548a284743a445e3680d7db5ac3ac18ff9b538d16f290ae67f760984dc6594a7c15e9716ed28dc027beceea1ec40a"),
]


@pytest.mark.parametrize(("geheim", "publiek", "bericht", "handtekening"), VECTOREN)
def test_ed25519_volgt_rfc8032(geheim: str, publiek: str, bericht: str, handtekening: str) -> None:
    zaad = bytes.fromhex(geheim)
    assert hub_sim.publieke_sleutel(zaad).hex() == publiek
    assert hub_sim.teken(zaad, bytes.fromhex(bericht)).hex() == handtekening


def test_vingerafdruk_heeft_vier_groepen_en_hangt_niet_van_de_volgorde_af() -> None:
    a, b, p = hub_sim.Sleutel("a").x, hub_sim.Sleutel("b").x, hub_sim.Sleutel("p").x
    afdruk = hub_sim.vingerafdruk([a, b], [p])
    assert re.fullmatch(r"[0-9A-HJKMNP-TV-Z]{4}(-[0-9A-HJKMNP-TV-Z]{4}){3}", afdruk)
    assert hub_sim.vingerafdruk([b, a], [p]) == afdruk
    assert hub_sim.vingerafdruk([a], [p]) != afdruk
    assert hub_sim.vingerafdruk([a, b], [a]) != afdruk


def test_vingerafdruk_contractvectoren() -> None:
    # Dezelfde vectoren als de C#-test HubSleutelTests.Vingerafdruk_ContractVectoren (contract 1.3 §4.5).
    jwt1 = "11qYAYKxCrfVS_7TyWQHOg7hcvPapiMlrwIaaPcHURo"
    policy1 = "A6EHv_POEL4dcN0Y50vAmWfk1jCbpQ1fHdyGZBJVMbg"
    sleutel2 = "Kay64UG8yvCyLhqU000LxzYeUm0L_hLIl5S8kyKWbdc"
    assert hub_sim.Sleutel("j", bytes.fromhex(VECTOREN[0][0])).x == jwt1
    assert hub_sim.duimafdruk(jwt1) == "kPrK_qmxVWaYVA9wwBF6Iuo3vVzz7TxHCTwXBygrS4k"
    assert hub_sim.vingerafdruk([jwt1], [policy1]) == "MEGG-8GFG-2E4Y-K2RQ"
    assert hub_sim.vingerafdruk([jwt1, sleutel2], [policy1]) == "CYRC-JS8C-14AN-JR17"
    assert hub_sim.vingerafdruk([jwt1], [policy1, sleutel2]) == "HN69-2PHK-XV2D-X85W"


def _deel(token: str, index: int) -> dict:
    tekst = token.split(".")[index]
    return json.loads(base64.urlsafe_b64decode(tekst + "=" * (-len(tekst) % 4)))


def test_token_voor_gebruiker_en_dienst() -> None:
    hub = hub_sim.HubSim()
    gebruiker = hub.token(rollen=["viewer"])
    assert _deel(gebruiker, 0) == {"alg": "EdDSA", "typ": "JWT", "kid": "hub-sim-jwt-1"}
    claims = _deel(gebruiker, 1)
    assert claims["iss"] == "hub" and claims["aud"] == "jelly-leon" and claims["token_use"] == "user"
    assert claims["roles"] == ["viewer"] and claims["exp"] - claims["iat"] == 60 and len(claims["jti"]) == 36
    dienst = _deel(hub.token(gebruik="hub_service"), 1)
    assert dienst["sub"] == "hub" and dienst["roles"] == ["service"] and dienst["service_id"] == hub.service_id


def test_token_varianten_voor_weigeringen() -> None:
    hub = hub_sim.HubSim()
    assert "jti" not in _deel(hub.token(weglaten=("jti",)), 1)
    assert _deel(hub.token(wijzig={"aud": "anders"}), 1)["aud"] == "anders"
    vast = {"jti": "x", "sub": "y"}
    goed, vals = hub.token(nu=1000, wijzig=vast), hub.token(nu=1000, wijzig=vast, vervals=True)
    assert goed.rsplit(".", 1)[0] == vals.rsplit(".", 1)[0] and goed != vals
    assert set(hub.sleutelset()) == {"jwks", "policy_public_key"}
