"""S-P6-32: de gekozen Emby-digest en een onafhankelijke bewaking van het bronverkeer."""

import http.client
import json
import secrets
from contextlib import closing
from subprocess import CompletedProcess
from urllib.parse import urlsplit

import pytest
from e2e import proefrun


@pytest.mark.parametrize("waarde", ["emby/embyserver:latest", "@sha256:" + "a" * 64, "emby@sha256:1234",
                                   "emby@sha256:" + "g" * 64, "emby@sha256:" + "a" * 65])
def test_emby_image_zonder_geldige_digest_stopt_voor_docker(tmp_path, monkeypatch, capsys, waarde):
    monkeypatch.setattr(proefrun, "docker", lambda *a, **k: pytest.fail("Docker gestart vóór validatie"))
    uitvoer = tmp_path / "proef"
    with pytest.raises(SystemExit) as fout:
        proefrun.main(["--emby-image", waarde, "--uitvoer", str(uitvoer)])
    assert fout.value.code == 2
    assert "vaste digest" in capsys.readouterr().err
    assert not uitvoer.exists()


@pytest.mark.parametrize("optie", [[], ["--emby-image", "emby/embyserver:4.9.0.0@sha256:" + "b" * 64]])
def test_docker_en_bewijs_gebruiken_dezelfde_emby_image(tmp_path, monkeypatch, optie):
    verwacht = optie[-1] if optie else proefrun.EMBY_IMAGE
    opdrachten = []

    def docker(*args, **kwargs):
        opdrachten.append(args)
        if args == ("image", "inspect", verwacht):
            return CompletedProcess(args, 1)
        if args[0] == "run":
            raise RuntimeError("test stopt vóór containerstart")
        return CompletedProcess(args, 0)

    monkeypatch.setattr(proefrun, "docker", docker)
    monkeypatch.setattr(proefrun, "bouw", lambda *a: {})
    monkeypatch.setattr(proefrun.subprocess, "run", lambda *a, **k: None)
    assert proefrun.main(["--uitvoer", str(tmp_path), *optie]) == 1
    assert ("image", "inspect", verwacht) in opdrachten
    assert ("pull", verwacht) in opdrachten
    assert next(args for args in opdrachten if args[0] == "run")[-1] == verwacht
    assert json.loads((tmp_path / "bewijs.json").read_text())["images"]["emby"] == verwacht


def test_emby_versie_vergelijkt_de_gekozen_tag():
    digest = proefrun.EMBY_IMAGE.partition("@")[2]
    assert proefrun.emby_versie_klopt(f"emby:4.9.0.0@{digest}", "4.9.0.0")
    assert not proefrun.emby_versie_klopt(f"emby:4.9.0.0@{digest}", "4.10.2.0")
    assert proefrun.emby_versie_klopt(f"emby@{digest}", "4.9.0.0")
    assert not proefrun.emby_versie_klopt(f"emby@{digest}", None)


@pytest.mark.parametrize("methode", ["POST", "DELETE", "PROPPATCH"])
def test_bronproxy_weigert_schrijfpoging_en_keurt_proef_af(emby, jl, tmp_path, methode):
    bron = proefrun.LoggendeProxy("localhost", urlsplit(emby.url).port, "emby", alleen_get=True)
    doel = proefrun.LoggendeProxy("localhost", urlsplit(jl.url).port, "jelly-leon")
    pad = "/System/Info/Public"
    try:
        with closing(http.client.HTTPConnection("localhost", bron.poort)) as client:
            client.request("GET", pad)
            antwoord = client.getresponse()
            assert antwoord.status == 200
            antwoord.read()
            client.request(methode, pad)
            antwoord = client.getresponse()
            assert antwoord.status == 405
            assert antwoord.getheader("Allow") == "GET"
            antwoord.read()
        assert emby.verzoeken == [("GET", pad)]
        assert [(r["methode"], r["status"]) for r in bron.regels] == [("GET", 200), (methode, 405)]
        bewijs = proefrun.Bewijs("synthetisch")
        proefrun.controleer_proxyverkeer(bewijs, bron, doel)
        bewijs.schrijf(tmp_path / "bewijs.json")
        assert bewijs.data["samenvatting"]["mislukt"] == 1
        assert bewijs.data["per_test"]["JLT-73"].startswith("Sim-mislukt")
    finally:
        bron.stop()
        doel.stop()


def test_eindscan_ziet_sleutel_in_herimportrapport_zonder_waarde_te_loggen(tmp_path):
    waarde = secrets.token_hex(16)
    rapportmap = tmp_path / "werkmap-herimport" / "runs"
    rapportmap.mkdir(parents=True)
    (rapportmap / "rapport.json").write_text(json.dumps({"tekst": waarde}))
    bewijs = proefrun.Bewijs("synthetisch")
    proefrun.controleer_sleutels(bewijs, tmp_path, {"jl": waarde})
    assert bewijs.data["controles"][-1]["ok"] is False
    assert bewijs.data["controles"][-1]["detail"] == ["rapport.json:jl"]
    assert waarde not in json.dumps(bewijs.data)
