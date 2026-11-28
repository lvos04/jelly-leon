import csv
import io
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from b03h.f2_data import REPO, lokaal, schrijf_dml_stubs, splitmoment, splits_dml
from b03h.guard import beoordeel


def tabel(z, naam, kop, rijen):
    tekst = io.StringIO()
    w = csv.writer(tekst)
    w.writerow(kop)
    w.writerows(rijen)
    z.writestr("ml-latest-small/" + naam + ".csv", tekst.getvalue())


def test_globaal_splitmoment_ook_bij_gelijke_tijden():
    assert splitmoment([[1, 2, 3, 4, 5, 9, 11], [1, 2, 3, 4, 6, 10, 11], [1] * 7]) == (7, 2)
    with pytest.raises(ValueError, match="geen gebruiker"):
        splitmoment([[1] * 6, [2] * 7])


def test_dml_gebruikt_alleen_verleden_en_markeert_afgeleide_nfo(tmp_path):
    ratings = [("a", i, 4, i) for i in range(1, 6)] + [("a", 6, 5, 7), ("a", 7, 4, 8)]
    ratings.extend([("b", 6, 2.5, 2), ("b", 7, 3, 3), ("c", 6, 5, 6), ("c", 8, 5, 9)])
    with zipfile.ZipFile(tmp_path / "bron.zip", "w") as z:
        tabel(z, "movies", ["movieId", "title", "genres"], [(i, f"Film {i}", "Drama") for i in range(1, 9)])
        tabel(z, "ratings", ["userId", "movieId", "rating", "timestamp"], ratings)
        tabel(z, "tags", ["userId", "movieId", "tag", "timestamp"], [("b", 6, "voor", 5), ("c", 6, "op", 6), ("c", 6, "na", 7)])
    with zipfile.ZipFile(tmp_path / "bron.zip") as z:
        d = splits_dml(z)
    assert d.globaal_t == 6 and "8" not in d.catalogus
    assert d.profielen["a"].holdout == {"6", "7"}
    assert [(r.item, r.tijd) for r in d.profielen["a"].training] == [(str(i), i) for i in range(1, 6)]
    assert (d.films["6"].eerste, d.films["6"].aantal, d.films["6"].som) == (2, 1, 2.5)
    assert d.films["6"].tags == {"voor"}
    assert d.pop("a") == list("1234567")
    stub = tmp_path / "stub"
    stub.write_bytes(b"synthetisch")
    schrijf_dml_stubs(d, stub, tmp_path / "Films")
    bron = (tmp_path / "Films/6/6.nfo").read_bytes()
    xml = ET.fromstring(bron)  # noqa: S314 - lokaal gegenereerde synthetische NFO uit deze test
    assert (xml.findtext("dateadded"), xml.findtext("rating"), xml.findtext("tag")) == ("1970-01-01 00:00:02", "5.0000", "voor")
    assert [v.regel for v in beoordeel("hernoemd", bron, {}, media_regel=False)] == ["C"]


def test_weiger_dml_in_git_ook_via_symlink(tmp_path):
    p = tmp_path / "terug"
    p.symlink_to(REPO, target_is_directory=True)
    with pytest.raises(ValueError, match="Git"):
        lokaal(p / "dataset")
    assert lokaal(tmp_path / "extern") == Path(tmp_path / "extern").resolve()


def test_validatie_bevriest_catalogus_tags_en_ratings_voor_de_laatste_tien_procent(tmp_path):
    pad = tmp_path / "validatie.zip"
    # 20 tijdstippen vóór T, dus V is tijdstip 19. De twee validatiefilms bestaan al vóór V.
    ratings = [("u", i, 5, i) for i in range(1, 17)] + [("v", 17, 1, 17), ("v", 18, 2, 18),
                                                        ("u", 17, 5, 19), ("u", 18, 5, 20), ("u", 19, 5, 21)]
    with zipfile.ZipFile(pad, "w") as z:
        tabel(z, "movies", ["movieId", "title", "genres"], [(i, f"Film {i}", "Drama") for i in range(1, 20)])
        tabel(z, "ratings", ["userId", "movieId", "rating", "timestamp"], ratings)
        tabel(z, "tags", ["userId", "movieId", "tag", "timestamp"], [("v", 17, "vroeg", 18), ("v", 17, "laat", 19)])
    with zipfile.ZipFile(pad) as z:
        d = splits_dml(z, validatie_voor=21)
    assert d.globaal_t == 19 and d.profielen["u"].holdout == {"17", "18"}
    assert d.films["17"].tags == {"vroeg"} and (d.films["17"].aantal, d.films["17"].som) == (1, 1)
    assert "19" not in d.catalogus and max(i.tijd for i in d.profielen["u"].training) < 19
