"""Geïsoleerde negatieve browserproef met het bevroren MPEG-2-geval en een kleine lokale spelersimulator."""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
import threading
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from b03h import apparaatrapport, apparaatset, apparaten
from b03h.corpus import CORPUS, UITVOER
from b03h.corpus.manifest import sha256_bestand
from b03h.stock import GEBRUIKER, WACHTWOORD
from b03h.web import harnas

ITEM = "a" * 32
CONTROLE = "b" * 32
PAGINA = """<!doctype html><form class="manualLoginForm">
<input id="txtManualName"><input id="txtManualPassword" type="password"><button type="submit">Aanmelden</button></form>
<button class="btnPlay">Afspelen</button><video muted></video>
<script>
document.querySelector('form').onsubmit = (e) => {
  e.preventDefault();
  localStorage.setItem('jellyfin_credentials', JSON.stringify({Servers:[{AccessToken: crypto.randomUUID()}]}));
};
document.querySelector('.btnPlay').onclick = async () => {
  const v = document.querySelector('video');
  const id = location.hash.split('id=')[1];
  const type = id.startsWith('a') ? 'video/mp2t' : 'video/webm';
  const kan = !!v.canPlayType(type);
  const pi = await fetch('/Items/'+id+'/PlaybackInfo', {method:'POST',
    body:JSON.stringify({DeviceProfile:{DirectPlayProfiles: kan ? [{Container:type}] : []}})}).then(r => r.json());
  if (!pi.MediaSources[0].SupportsDirectPlay) return;
  // Een automatische terugval geeft echt bewegend beeld nadat de browser het foutbestand heeft geweigerd.
  v.addEventListener('error', () => { v.src = '/herstel.webm'; v.play().catch(() => {}); }, {once:true});
  v.src = '/Videos/'+id+'/stream?static=true';
  v.play().catch(() => {});
};
</script>"""


class Speler(BaseHTTPRequestHandler):
    def __init__(self, *args, media: Path, herstel: Path, **kwargs):
        self.media, self.herstel = media, herstel
        super().__init__(*args, **kwargs)

    def log_message(self, *_):
        pass

    def stuur(self, inhoud: bytes, soort: str):
        self.send_response(200)
        self.send_header("Content-Type", soort)
        self.send_header("Content-Length", str(len(inhoud)))
        self.end_headers()
        try:
            self.wfile.write(inhoud)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):  # noqa: N802 - http.server
        pad = urlsplit(self.path).path
        if pad == "/web/":
            self.stuur(PAGINA.encode(), "text/html; charset=utf-8")
        elif pad == f"/Videos/{ITEM}/stream":
            self.stuur(self.media.read_bytes(), "video/mp2t")
        elif pad in ("/herstel.webm", f"/Videos/{CONTROLE}/stream"):
            self.stuur(self.herstel.read_bytes(), "video/webm")
        else:
            self.send_error(404)

    def do_POST(self):  # noqa: N802 - http.server
        if self.path not in (f"/Items/{ITEM}/PlaybackInfo", f"/Items/{CONTROLE}/PlaybackInfo"):
            self.send_error(404)
            return
        profiel = json.loads(self.rfile.read(int(self.headers["Content-Length"])))["DeviceProfile"]
        bron = {"SupportsDirectPlay": bool(profiel["DirectPlayProfiles"]), "SupportsTranscoding": True,
                "MediaStreams": [{"Type": "Video", "VideoRangeType": "SDR"}]}
        self.stuur(json.dumps({"MediaSources": [bron]}).encode(), "application/json")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--sets", type=Path, default=UITVOER)
    p.add_argument("--uit", required=True, type=Path)
    a = p.parse_args()
    bevroren = json.loads(apparaatset.BEWIJS.read_text())
    geval = next(c for c in bevroren["groepen"]["testset"]["gevallen"] if c["id"] == "test-chromium-mpeg2-ts")
    script = apparaatset.setmap(a.sets, "f5-fouten") / geval["middel"]
    media = apparaatset.media_pad(geval["pad"], CORPUS)
    if sha256_bestand(script) != geval["middel_sha256"] or sha256_bestand(media) != geval["media_sha256"]:
        raise ValueError("de proef vereist het bevroren foutbestand en bijbehorend init-script")
    with tempfile.TemporaryDirectory() as tmp:
        herstel = Path(tmp) / "herstel.webm"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=s=96x64:r=12", "-t", "4",
                        "-threads", "1", "-c:v", "libvpx", str(herstel)], check=True)
        with ThreadingHTTPServer(("localhost", 0), partial(Speler, media=media, herstel=herstel)) as server:
            draad = threading.Thread(target=server.serve_forever)
            draad.start()
            try:
                web = harnas("apparaten", {"browser": "chromium", "url": f"http://localhost:{server.server_port}",
                                          "gebruiker": GEBRUIKER, "wachtwoord": WACHTWOORD, "initScript": str(script),
                                          "items": [{"id": ITEM, "naam": geval["id"]}, {"id": CONTROLE, "naam": "controle"}]})
            finally:
                server.shutdown()
                draad.join()
    rijen = [apparaten.lees_start(geval if i["id"] == ITEM else {"id": "controle"}, "testset", i) for i in web["items"]]
    bewijs = {"soort": "lokale spelersimulator", "browser": web["versie"], "testset_sha256": bevroren["groepen"]["testset"]["sha256"],
              "rijen": rijen, "eerste_start": apparaatrapport.metrieken([r for r in rijen if r["start"] == 1])}
    a.uit.parent.mkdir(parents=True, exist_ok=True)
    a.uit.write_text(json.dumps(bewijs, indent=2, ensure_ascii=False) + "\n")
    goed = len(rijen) == 4 and all((r["classificatie"] == "onterechte Direct Play" and bool(r["foutcodes"])
                                  and r["herstel_ms"] is not None and not r["geforceerd_ok"])
                                 if r["id"] == geval["id"] else (r["orakel_ok"] and r["geforceerd_ok"]) for r in rijen)
    print("2/2 onterechte Direct Plays met herstel, 2/2 controles speelbaar" if goed else "De browserproef wijkt af; zie het rapport")
    return 0 if goed else 1


if __name__ == "__main__":
    raise SystemExit(main())
