"""Vóór/na-rapport per gebruiker: JSON (met sha256), Markdown en eenvoudig HTML met akkoordveld (B03-015 A8).

Het rapport is voor de gebruiker geschreven: per gebruiker wat er in Emby staat, wat er in Jelly Leon staat of komt, en
een afhandellijst met per regel wat er nodig is. Het HTML-bestand werkt zonder JavaScript (afdrukken en tekenen); met
JavaScript maakt de knop onderaan een `akkoord.json` met precies de aangevinkte verschillen.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from . import TOOL_NAAM, __version__
from .hulp import nu_utc, schrijf_atomisch, schrijf_json_met_sha, sha256_json

SCHEMA = "jelly-leon/emby-overname-rapport/1"
SOORT_TITEL = {
    "proefrun": "Proefrun — er is nog niets geschreven",
    "overzetting": "Vóór/na-rapport na de overzetting",
    "verificatie": "Controle (alleen lezen)",
}
KLASSE_TEKST = {"actie": "Actie nodig", "beslissing": "Uw beslissing", "kennisname": "Ter kennisname"}
SOORT_NAAM = {"gezien": "Gezien (met datum en aantal)", "hervatpunten": "Hervatpunten (ticks exact)",
              "favorieten": "Favorieten", "beoordelingen": "Beoordelingen", "spoorkeuzes": "Onthouden spoorkeuzes"}
STATUS_TEKST = {"aanmaken": "wordt aangemaakt", "aangemaakt_door_tool": "door de overname aangemaakt",
                "bestaand": "bestond al in Jelly Leon (rechten niet aangepast)", "ongeldige_naam": "naam niet toegestaan"}


def bouw_rapport(soort: str, opname: dict[str, Any], doel_info: dict[str, Any], plan_sha: str, plan_acties: int,
                 toestand: dict[str, Any], run: dict[str, Any] | None, bron_extra: dict[str, Any]) -> dict[str, Any]:
    inhoud = sha256_json(toestand)
    rapport = {
        "schema": SCHEMA, "soort": soort, "gemaakt": nu_utc(), "tool": {"naam": TOOL_NAAM, "versie": __version__},
        "bron": {"server_id": opname["bron"].get("server_id"), "server_naam": opname["bron"].get("server_naam"),
                 "versie": opname["bron"].get("versie"), "export_inhoud_sha256": opname.get("inhoud_sha256"), **bron_extra},
        "doel": {"server_id": doel_info.get("Id"), "server_naam": doel_info.get("ServerName"), "versie": doel_info.get("Version"),
                 "product": doel_info.get("ProductName") or "Jellyfin Server"},
        "plan_sha256": plan_sha, "plan_schrijfacties": plan_acties, "run": run, "toestand": toestand,
        "inhoud_sha256": inhoud,
        "akkoord": {
            "vereist_voor": "overzetten" if soort == "proefrun" else "overstap (cutover)",
            "verschillen": toestand["verschillen"], "aantal": len(toestand["verschillen"]),
        },
    }
    return rapport


def schrijf_rapport(rapport: dict[str, Any], map_pad: Path) -> dict[str, str]:
    """Schrijft rapport.json (+ .sha256), rapport.md en rapport.html; geeft de paden en de sha256 terug."""
    som = schrijf_json_met_sha(map_pad / "rapport.json", rapport)
    schrijf_atomisch(map_pad / "rapport.md", markdown(rapport, som))
    schrijf_atomisch(map_pad / "rapport.html", als_html(rapport, som))
    return {"json": str(map_pad / "rapport.json"), "sha256": som, "md": str(map_pad / "rapport.md"),
            "html": str(map_pad / "rapport.html")}


def _pct(gelijk: int, nieuwer: int, gekoppeld: int) -> str:
    if gekoppeld == 0:
        return "—"
    return f"{(gelijk + nieuwer) * 100 / gekoppeld:.1f} %".replace(".", ",")


def _telling_rijen(telling: dict[str, Any]) -> list[list[str]]:
    rijen = []
    for soort in ("gezien", "hervatpunten", "favorieten", "beoordelingen", "spoorkeuzes"):
        t = telling.get(soort, {})
        rijen.append([SOORT_NAAM[soort], str(t.get("emby", 0)), str(t.get("gekoppeld", 0)), str(t.get("gelijk", 0)),
                      str(t.get("jelly_leon_nieuwer", 0)), str(t.get("afhandellijst", 0)),
                      _pct(t.get("gelijk", 0), t.get("jelly_leon_nieuwer", 0), t.get("gekoppeld", 0))])
    return rijen


TELLING_KOP = ["Soort", "In Emby", "Gekoppeld", "Gelijk in Jelly Leon", "Jelly Leon nieuwer", "Afhandellijst",
               "Gelijk of verklaard (van gekoppeld)"]


def _md_tabel(kop: list[str], rijen: list[list[str]]) -> str:
    def cel(t: str) -> str:
        return str(t).replace("|", "\\|").replace("\n", " ")

    regels = ["| " + " | ".join(kop) + " |", "|" + "|".join("---" for _ in kop) + "|"]
    regels += ["| " + " | ".join(cel(c) for c in r) + " |" for r in rijen]
    return "\n".join(regels)


def markdown(r: dict[str, Any], som: str) -> str:
    t = r["toestand"]
    uit = [
        f"# Overname kijkgeschiedenis Emby → Jelly Leon — {SOORT_TITEL.get(r['soort'], r['soort'])}",
        "",
        f"- Gemaakt: {r['gemaakt']} · tool {r['tool']['naam']} {r['tool']['versie']}",
        f"- Bron: Emby {r['bron'].get('versie')} (server {r['bron'].get('server_naam')}); "
        f"exportinhoud sha256 `{r['bron'].get('export_inhoud_sha256')}`"
        + (" — **ingelezen uit het exportarchief**" if r["bron"].get("archief") else ""),
        f"- Doel: {r['doel'].get('product')} {r['doel'].get('versie')} (server {r['doel'].get('server_naam')})",
        f"- Rapport (JSON) sha256: `{som}` · inhoud sha256: `{r['inhoud_sha256']}` · plan sha256: `{r['plan_sha256']}`",
        "",
        "Emby is alleen gelezen (alleen GET). Wachtwoorden zijn niet overgezet. Niets is stil weggelaten: wat niet "
        "automatisch over te zetten is, staat hieronder op de afhandellijst.",
        "",
        "## Samenvatting (alle gebruikers)",
        "",
        _md_tabel(TELLING_KOP, _telling_rijen(t.get("totaal", {}))),
        "",
        f"- Alles verantwoord (overgezet of op de afhandellijst): **{'ja' if t.get('verantwoord') else 'NEE'}**",
    ]
    if r["soort"] == "proefrun":
        uit.append(f"- Geplande schrijfacties in Jelly Leon: {r['plan_schrijfacties']} (er is nog niets geschreven)")
    elif r.get("run"):
        uit.append(f"- Schrijfacties in deze run: {r['run'].get('schrijfacties')} ({json.dumps(r['run'].get('per_soort'), ensure_ascii=False)})")
    if t.get("alleen_in_jelly_leon"):
        uit.append(f"- Gebruikers die alleen in Jelly Leon bestaan (niet aangeraakt): {', '.join(t['alleen_in_jelly_leon'])}")
    bib = t.get("bibliotheken", {})
    if bib.get("gekoppeld"):
        uit.append("- Bibliotheken: " + "; ".join(f"{k} → {v}" for k, v in bib["gekoppeld"].items()))
    if bib.get("niet_gekoppeld"):
        uit.append(f"- Bibliotheken zonder tegenhanger: {', '.join(bib['niet_gekoppeld'])}")
    uit += ["", f"Te beoordelen verschillen: **{r['akkoord']['aantal']}** (elk verschil vraagt uw akkoord).", ""]
    for g in t["gebruikers"]:
        uit += [
            f"## Gebruiker: {g['emby_naam']}",
            "",
            f"- In Jelly Leon: **{g['jelly_leon_naam']}** — {STATUS_TEKST.get(g['status'], g['status'])}"
            + (" · beheerder" if g.get("beheerder") else ""),
            f"- Wachtwoord: {g['wachtwoord']}",
            f"- Kijkgegevens verantwoord: {g['verantwoord']['verantwoord']} van {g['verantwoord']['met_kijkgegevens']} "
            f"items ({'klopt' if g['verantwoord']['klopt'] else 'KLOPT NIET'})",
        ]
        z = g.get("zichtbaarheid") or {}
        if z.get("jelly_leon") is not None:
            uit.append(f"- Zichtbaar: Emby {z['emby']} items, Jelly Leon {z['jelly_leon']}; ruimer dan Emby: **{z['ruimer']}**, "
                       f"smaller: {z['smaller']}, alleen in Jelly Leon: {z['alleen_in_jelly_leon']}")
        else:
            uit.append(f"- Zichtbaar in Emby: {z.get('emby')} items (Jelly Leon wordt na het aanmaken gecontroleerd)")
        uit += ["", _md_tabel(TELLING_KOP, _telling_rijen(g["telling"])), ""]
        rechten = [x for x in g["rechten"] if x["status"] != "gelijk" or x["veld"] in (
            "IsAdministrator", "Bibliotheektoegang", "MaxParentalRating", "Geblokkeerde tags", "EnableRemoteAccess",
            "EnableContentDownloading", "AudioLanguagePreference", "SubtitleLanguagePreference", "SubtitleMode")]
        if rechten:
            uit += ["**Rechten, ouderlijk toezicht en voorkeuren**", "",
                    _md_tabel(["Instelling", "Emby", "Jelly Leon", "Status", "Toelichting"],
                              [[x["veld"], _waarde(x["emby"]), _waarde(x["jelly_leon"]), x["status"], x.get("uitleg") or ""]
                               for x in rechten]), ""]
        if g["afhandellijst"]:
            uit += ["**Afhandellijst en verschillen**", "",
                    _md_tabel(["ID", "Soort", "Wat", "Item", "Kijkgegevens in Emby", "Toelichting"],
                              [[p["id"], p["soort"], KLASSE_TEKST.get(p["klasse"], p["klasse"]),
                                (p["item"] or {}).get("titel", "—"), p.get("kijkgegevens_tekst") or "—",
                                f"{p['reden']}: {p['uitleg']}"] for p in g["afhandellijst"]]), ""]
        else:
            uit += ["Geen verschillen voor deze gebruiker.", ""]
    uit += [
        "## Akkoord",
        "",
        f"Ik heb dit rapport (inhoud sha256 `{r['inhoud_sha256']}`) gelezen en ga akkoord met elk hierboven genoemd verschil "
        f"({r['akkoord']['aantal']} stuks){' en met de geplande overzetting' if r['soort'] == 'proefrun' else ''}.",
        "",
        "Naam: ______________________   Datum: ____________   Handtekening: ______________________",
        "",
        "Digitaal: open `rapport.html`, vink elk verschil aan en kies *Akkoord-bestand maken*; of maak zelf een `akkoord.json` "
        "met `schema`, `soort` (`plan` of `cutover`), `rapport_inhoud_sha256`, `plan_sha256` (bij `plan`), `akkoord_door`, "
        "`datum` en de lijst `verschillen`. Zonder volledig akkoord geen overzetting en geen overstap.",
        "",
    ]
    return "\n".join(uit)


def _waarde(v: Any) -> str:
    if v is None:
        return "—"
    if isinstance(v, bool):
        return "ja" if v else "nee"
    if isinstance(v, list):
        return ", ".join(str(x) for x in v) or "—"
    return str(v)


CSS = """
:root{color-scheme:light dark;--rand:#8888;--accent:#1d4ed8}
body{font:16px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;max-width:72rem;margin:0 auto;padding:1rem}
h1{font-size:1.6rem}h2{font-size:1.3rem;margin-top:2rem;border-top:1px solid var(--rand);padding-top:1rem}
table{border-collapse:collapse;width:100%;margin:.5rem 0 1rem;font-size:.95rem}
th,td{border:1px solid var(--rand);padding:.35rem .5rem;text-align:left;vertical-align:top}
th{background:#8882}.ok{color:#15803d;font-weight:600}.fout{color:#b91c1c;font-weight:600}
.klasse-actie{font-weight:600}.mono{font-family:ui-monospace,monospace;font-size:.85em;word-break:break-all}
label{display:flex;gap:.5rem;align-items:flex-start;min-height:44px}input[type=checkbox]{width:1.4rem;height:1.4rem}
button{font:inherit;padding:.6rem 1rem;min-height:44px;border-radius:.4rem;border:1px solid var(--accent);cursor:pointer}
.akkoord{border:2px solid var(--accent);padding:1rem;border-radius:.5rem;margin-top:2rem}
@media print{button,.alleen-scherm{display:none}}
"""

JS = """
function maakAkkoord(){
  var gekozen=[].slice.call(document.querySelectorAll('input[name=verschil]:checked')).map(function(i){return i.value});
  var alle=document.querySelectorAll('input[name=verschil]').length;
  var naam=document.getElementById('naam').value.trim();
  var uit=document.getElementById('melding');
  if(!naam){uit.textContent='Vul uw naam in.';return}
  if(gekozen.length!==alle){
    uit.textContent='Nog '+(alle-gekozen.length)+' verschil(len) niet aangevinkt: zonder volledig akkoord geen overzetting of overstap.';
  }
  var d=document.body.dataset;
  var akkoord={schema:'jelly-leon/emby-overname-akkoord/1',soort:d.soort==='proefrun'?'plan':'cutover',
    rapport_inhoud_sha256:d.inhoud,plan_sha256:d.plan,akkoord_door:naam,datum:new Date().toISOString(),verschillen:gekozen};
  var blob=new Blob([JSON.stringify(akkoord,null,2)],{type:'application/json'});
  var a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='akkoord.json';a.click();
}
"""


def als_html(r: dict[str, Any], som: str) -> str:
    e = html.escape
    t = r["toestand"]

    def tabel(kop: list[str], rijen: list[list[str]], ruw_kolommen: tuple[int, ...] = ()) -> str:
        kopregel = "".join(f"<th scope='col'>{e(k)}</th>" for k in kop)
        regels = "".join(
            "<tr>" + "".join(f"<td>{c if i in ruw_kolommen else e(str(c))}</td>" for i, c in enumerate(rij)) + "</tr>"
            for rij in rijen
        )
        return f"<table><thead><tr>{kopregel}</tr></thead><tbody>{regels}</tbody></table>"

    delen = [
        "<!doctype html><html lang='nl'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width,initial-scale=1'>",
        f"<title>Overname kijkgeschiedenis — {e(SOORT_TITEL.get(r['soort'], r['soort']))}</title>",
        f"<style>{CSS}</style></head>",
        f"<body data-soort='{e(r['soort'])}' data-inhoud='{e(r['inhoud_sha256'])}' data-plan='{e(r['plan_sha256'])}'>",
        "<main>",
        f"<h1>Overname kijkgeschiedenis Emby → Jelly Leon<br><small>{e(SOORT_TITEL.get(r['soort'], r['soort']))}</small></h1>",
        "<ul>",
        f"<li>Gemaakt: {e(r['gemaakt'])}</li>",
        f"<li>Bron: Emby {e(str(r['bron'].get('versie')))} (server {e(str(r['bron'].get('server_naam')))})"
        + (" — <strong>ingelezen uit het exportarchief</strong>" if r["bron"].get("archief") else "") + "</li>",
        f"<li>Doel: {e(str(r['doel'].get('product')))} {e(str(r['doel'].get('versie')))}</li>",
        f"<li>Rapport (JSON) sha256: <span class='mono'>{e(som)}</span></li>",
        f"<li>Inhoud sha256: <span class='mono'>{e(r['inhoud_sha256'])}</span> · plan sha256: "
        f"<span class='mono'>{e(r['plan_sha256'])}</span></li>",
        "</ul>",
        "<p>Emby is alleen gelezen. Wachtwoorden zijn niet overgezet. Niets is stil weggelaten: wat niet automatisch over te "
        "zetten is, staat op de afhandellijst.</p>",
        "<h2>Samenvatting (alle gebruikers)</h2>",
        tabel(TELLING_KOP, _telling_rijen(t.get("totaal", {}))),
        f"<p>Alles verantwoord (overgezet of op de afhandellijst): "
        f"<span class='{'ok' if t.get('verantwoord') else 'fout'}'>{'ja' if t.get('verantwoord') else 'NEE'}</span></p>",
    ]
    if r["soort"] == "proefrun":
        delen.append(f"<p>Geplande schrijfacties in Jelly Leon: {r['plan_schrijfacties']} — er is nog niets geschreven.</p>")
    elif r.get("run"):
        delen.append(f"<p>Schrijfacties in deze run: {e(str(r['run'].get('schrijfacties')))}.</p>")
    for g in t["gebruikers"]:
        z = g.get("zichtbaarheid") or {}
        delen += [
            f"<h2>Gebruiker: {e(g['emby_naam'])}</h2>",
            "<ul>",
            f"<li>In Jelly Leon: <strong>{e(g['jelly_leon_naam'])}</strong> — {e(STATUS_TEKST.get(g['status'], g['status']))}"
            + (" · beheerder" if g.get("beheerder") else "") + "</li>",
            f"<li>Wachtwoord: {e(g['wachtwoord'])}</li>",
            f"<li>Kijkgegevens verantwoord: {g['verantwoord']['verantwoord']} van {g['verantwoord']['met_kijkgegevens']}</li>",
            (f"<li>Zichtbaar: Emby {z.get('emby')}, Jelly Leon {z.get('jelly_leon')}; ruimer dan Emby: "
             f"<span class='{'ok' if not z.get('ruimer') else 'fout'}'>{z.get('ruimer')}</span>; smaller: {z.get('smaller')}</li>"
             if z.get("jelly_leon") is not None else f"<li>Zichtbaar in Emby: {z.get('emby')} items</li>"),
            "</ul>",
            tabel(TELLING_KOP, _telling_rijen(g["telling"])),
        ]
        rechten = [x for x in g["rechten"] if x["status"] != "gelijk" or x["veld"] in (
            "IsAdministrator", "Bibliotheektoegang", "MaxParentalRating", "Geblokkeerde tags", "EnableRemoteAccess",
            "EnableContentDownloading", "AudioLanguagePreference", "SubtitleLanguagePreference", "SubtitleMode")]
        if rechten:
            delen += ["<h3>Rechten, ouderlijk toezicht en voorkeuren</h3>",
                      tabel(["Instelling", "Emby", "Jelly Leon", "Status", "Toelichting"],
                            [[x["veld"], _waarde(x["emby"]), _waarde(x["jelly_leon"]), x["status"], x.get("uitleg") or ""]
                             for x in rechten])]
        if g["afhandellijst"]:
            rijen = []
            for p in g["afhandellijst"]:
                vak = (f"<label><input type='checkbox' name='verschil' value='{e(p['id'])}'>"
                       f"<span class='mono'>{e(p['id'])}</span></label>")
                wat = f"<span class='klasse-{e(p['klasse'])}'>{e(KLASSE_TEKST.get(p['klasse'], p['klasse']))}</span>"
                rijen.append([vak, e(p["soort"]), wat,
                              e((p["item"] or {}).get("titel", "—")), e(p.get("kijkgegevens_tekst") or "—"),
                              f"<strong>{e(p['reden'])}</strong>: {e(p['uitleg'])}"])
            delen += ["<h3>Afhandellijst en verschillen</h3>",
                      tabel(["Akkoord", "Soort", "Wat", "Item", "Kijkgegevens in Emby", "Toelichting"], rijen, (0, 1, 2, 3, 4, 5))]
        else:
            delen.append("<p>Geen verschillen voor deze gebruiker.</p>")
    delen += [
        "<section class='akkoord' aria-labelledby='akkoord-kop'>",
        "<h2 id='akkoord-kop'>Akkoord</h2>",
        f"<p>Ik heb dit rapport (inhoud sha256 <span class='mono'>{e(r['inhoud_sha256'])}</span>) gelezen en ga akkoord met "
        f"elk aangevinkt verschil ({r['akkoord']['aantal']} in totaal)"
        f"{' en met de geplande overzetting' if r['soort'] == 'proefrun' else ''}. Zonder akkoord op elk verschil geen "
        f"{'overzetting' if r['soort'] == 'proefrun' else 'overstap'}.</p>",
        "<p>Naam: ______________________ &nbsp; Datum: ____________ &nbsp; Handtekening: ______________________</p>",
        "<div class='alleen-scherm'><label for='naam'>Uw naam (voor het akkoord-bestand)</label>",
        "<input id='naam' autocomplete='name' style='font:inherit;min-height:44px;width:100%;max-width:24rem'>",
        "<p><button type='button' onclick='maakAkkoord()'>Akkoord-bestand maken</button></p>",
        "<p id='melding' role='status' aria-live='polite'></p></div>",
        "</section></main>",
        f"<script>{JS}</script></body></html>",
    ]
    return "\n".join(delen) + "\n"
