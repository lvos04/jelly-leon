"""De differentiële poort wijst een gewijzigde vreemde rij of hervatpositie in een gevulde WAL-database af."""
import shutil
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "e2e"))

from segmenten_proef import PROVIDER, controleer_tabellen, opname  # noqa: E402


@pytest.mark.parametrize(("ingreep", "afwijking"), [
    ("", []),
    ("DELETE FROM MediaSegments WHERE SegmentProviderId='proefbron'", ["MediaSegments"]),
    ("UPDATE UserData SET Hervat=0", ["UserData"]),
    ("UPDATE MediaSegments SET Einde=99 WHERE SegmentProviderId IS NULL", ["MediaSegments"]),
])
def test_alleen_eigen_publicatie_is_toegestaan(tmp_path, ingreep, afwijking):
    stock = tmp_path / "stock.db"
    with closing(sqlite3.connect(stock)) as db:
        db.executescript("""
            CREATE TABLE MediaSegments(Id INTEGER PRIMARY KEY, Einde INTEGER, SegmentProviderId TEXT);
            INSERT INTO MediaSegments VALUES(1,20,'proefbron'),(2,20,NULL);
            CREATE TABLE UserData(Id INTEGER PRIMARY KEY, Hervat INTEGER);
            INSERT INTO UserData VALUES(1,15000000);
        """)
        db.commit()
    kopie = tmp_path / "gevulde-kopie.db"
    shutil.copy2(stock, kopie)
    with closing(sqlite3.connect(kopie)) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("INSERT INTO MediaSegments VALUES(3,20,?)", (PROVIDER,))
        if ingreep:
            db.execute(ingreep)
        db.commit()
        doel = tmp_path / "opname.db"
        assert opname(kopie, doel)[0] == 1
        assert controleer_tabellen(stock, stock, doel) == (afwijking, [])
        assert db.execute("SELECT COUNT(*) FROM MediaSegments WHERE SegmentProviderId=?", (PROVIDER,)).fetchone() == (1,)
