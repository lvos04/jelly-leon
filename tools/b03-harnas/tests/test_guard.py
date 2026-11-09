"""CI-guard testdatalicenties — inclusief de negatieve test uit de acceptatie: een commit met een beperkt gelicentieerd
bestand wordt geweigerd."""

from __future__ import annotations

import hashlib
import io
import json
import subprocess
import tarfile
from pathlib import Path

import pytest

from b03h import guard

MOVIELENS_KOP = "userId,movieId,rating,timestamp\n1,1,4.0,964982703\n"


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)
    (repo / "README.md").write_text("schoon\n", encoding="utf-8")
    _commit(repo, "begin")
    return repo


def _commit(repo: Path, bericht: str) -> str:
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", bericht], check=True)
    return subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()


def test_schone_repo_in_orde(tmp_path: Path):
    repo = _repo(tmp_path)
    assert guard.main(["--git", str(repo)]) == 0


@pytest.mark.parametrize(("pad", "inhoud", "regel"), [
    ("data/ratings.csv", MOVIELENS_KOP.encode(), "C"),
    ("data/ml-latest-small/README.txt", b"MovieLens\n", "N"),
    ("subs/Pioneer.One.S01E01.nl.srt", b"1\n00:00:01,000 --> 00:00:02,000\nhoi\n", "N"),
    ("labels/grondwaarheid.json", json.dumps({"markering": guard.MARKERING}).encode(), "C"),
    ("media/clip.mkv", b"\x1aE\xdf\xa3" + b"\0" * 64, "M"),
    ("media/capture.ts", (b"\x47" + b"\0" * 187) * 3, "M"),
])
def test_negatief_commit_met_beperkte_data_geweigerd(tmp_path: Path, pad: str, inhoud: bytes, regel: str):
    repo = _repo(tmp_path)
    doel = repo / pad
    doel.parent.mkdir(parents=True, exist_ok=True)
    doel.write_bytes(inhoud)
    _commit(repo, "beperkte testdata (mag niet)")
    vondsten = guard.controleer(guard.bestanden_git(repo))
    assert any(v.regel == regel and pad in v.pad for v in vondsten), vondsten
    assert guard.main(["--git", str(repo)]) == 1


def test_hernoemd_beperkt_bestand_via_hash(monkeypatch: pytest.MonkeyPatch):
    inhoud = b"pretend this is a restricted subtitle\n"
    monkeypatch.setattr(guard, "beperkte_hashes", lambda: {hashlib.sha256(inhoud).hexdigest(): "testbron"})
    vondsten = guard.controleer([("docs/onschuldige-naam.txt", inhoud)])
    assert [v.regel for v in vondsten] == ["H"]


def test_echte_lijst_beperkte_hashes():
    hashes = guard.beperkte_hashes()
    assert len(hashes) == 16  # 6 afleveringen + 10 fanondertitels (CORPUS.md)
    assert all(len(h) == 64 for h in hashes)


def test_typescript_ts_is_geen_media():
    assert guard.controleer([("web/src/index.ts", b"export const a = 1;\n")]) == []


def test_toestemmingslijst_upstream_testdata():
    assert guard.controleer([("tests/Jellyfin.MediaEncoding.Tests/Test Data/example.srt", b"1\n")]) == []


def test_commitbereik_vangt_ook_later_verwijderd(tmp_path: Path):
    repo = _repo(tmp_path)
    basis = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    (repo / "ratings.csv").write_text(MOVIELENS_KOP, encoding="utf-8")
    _commit(repo, "per ongeluk")
    (repo / "ratings.csv").unlink()
    _commit(repo, "weer weg")
    assert guard.main(["--git", str(repo)]) == 0  # boom is schoon …
    assert guard.main(["--bereik", str(repo), f"{basis}..HEAD"]) == 1  # … maar de geschiedenis niet


def test_image_modus_zonder_media_regel():
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for naam, data in (("jellyfin/jellyfin-web/assets/audio/silence.mp3", b"ID3"), ("data/ratings.csv", MOVIELENS_KOP.encode())):
            info = tarfile.TarInfo(naam)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    buf.seek(0)
    with tarfile.open(fileobj=buf, mode="r") as tar:
        items = [(m.name, tar.extractfile(m).read()) for m in tar if m.isfile()]
    vondsten = guard.controleer(items, media_regel=False)
    assert [v.pad for v in vondsten] == ["data/ratings.csv"]


def test_deze_repo_is_schoon():
    repo = Path(__file__).resolve().parents[3]
    if not (repo / ".git").exists():
        pytest.skip("geen git-checkout")
    vondsten = guard.controleer(guard.bestanden_git(repo))
    assert vondsten == [], [str(v) for v in vondsten]
