// B03-016 desktop-spike: jellyfin-desktop 2.0.0 onder Xvfb besturen via **ruwe CDP** (de Node 22-WebSocket op het
// paginadoel), niet via Playwright connectOverCDP (dat faalt op QtWebEngine: "Browser context management is not supported",
// analyse 5 §4). Stappen: servers-pagina (find-webclient) → serveradres → jellyfin-web-login → item openen → afspelen.
// Uitvoer: één JSON-regel. Alleen voor ontwikkeling; draait nooit op de NAS.
//   node cdp.mjs '{"cdp":"http://127.0.0.1:9333","server":"http://127.0.0.1:8096","gebruiker":"…","wachtwoord":"…","item":"<id>","scherm":"/pad.png"}'
import fs from 'node:fs';

const cfg = JSON.parse(process.argv[2]);
const wacht = (ms) => new Promise((r) => setTimeout(r, ms));
const uit = { stappen: [], fouten: [] };

async function doelen() {
  const r = await fetch(`${cfg.cdp}/json/list`);
  return (await r.json()).filter((d) => d.type === 'page');
}

async function verbind(doel) {
  const ws = new WebSocket(doel.webSocketDebuggerUrl);
  await new Promise((ok, nok) => { ws.onopen = ok; ws.onerror = nok; });
  let id = 0;
  const wachtend = new Map();
  ws.onmessage = (m) => {
    const d = JSON.parse(m.data);
    if (d.id && wachtend.has(d.id)) { wachtend.get(d.id)(d); wachtend.delete(d.id); }
    if (d.method === 'Runtime.exceptionThrown') uit.fouten.push(d.params.exceptionDetails?.exception?.description?.slice(0, 200));
    if (d.method === 'Log.entryAdded' && d.params.entry.level === 'error') uit.fouten.push(d.params.entry.text.slice(0, 200));
  };
  const stuur = (method, params = {}) => new Promise((ok) => { id += 1; wachtend.set(id, ok); ws.send(JSON.stringify({ id, method, params })); });
  await stuur('Runtime.enable');
  await stuur('Log.enable');
  const evalueer = async (expr) => {
    const r = await stuur('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true });
    if (r.result?.exceptionDetails) throw new Error(r.result.exceptionDetails.text);
    return r.result?.result?.value;
  };
  return { ws, stuur, evalueer };
}

async function wachtOp(evalueer, expr, ms) {
  const einde = Date.now() + ms;
  while (Date.now() < einde) {
    try { if (await evalueer(expr)) return true; } catch { /* pagina wisselt */ }
    await wacht(500);
  }
  return false;
}

async function main() {
  let d = (await doelen())[0];
  if (!d) throw new Error('geen paginadoel in /json/list');
  uit.stappen.push(`doel: ${d.url.slice(0, 80)}`);
  let c = await verbind(d);
  if (/find-webclient/.test(d.url) || (await c.evalueer("!!document.getElementById('address')"))) {
    await c.evalueer(`(() => { const a = document.getElementById('address'); a.value = ${JSON.stringify(cfg.server)};
      document.getElementById('connect-button').click(); return true; })()`);
    uit.stappen.push('serveradres ingevuld op find-webclient');
  }
  // Na het verbinden laadt de app de jellyfin-web van de server (eventueel in een nieuw paginadoel).
  for (let i = 0; i < 60; i++) {
    await wacht(1000);
    const lijst = await doelen();
    const web = lijst.find((x) => x.url.startsWith(cfg.server)) || lijst[0];
    if (web && web.url.startsWith(cfg.server)) {
      if (web.id !== d.id) { c.ws.close(); d = web; c = await verbind(d); }
      break;
    }
  }
  uit.stappen.push(`webclient: ${d.url.slice(0, 80)}`);
  const login = await wachtOp(c.evalueer, "!!document.querySelector('#txtManualName, .btnManual')", 60000);
  uit.chunkloaderror = uit.fouten.some((f) => /ChunkLoadError/.test(f || ''));
  if (!login) throw new Error('inlogscherm van jellyfin-web verscheen niet');
  await c.evalueer(`(() => { if (!document.querySelector('#txtManualName')) document.querySelector('.btnManual')?.click(); return true; })()`);
  await wachtOp(c.evalueer, "!!document.querySelector('#txtManualName')", 15000);
  await c.evalueer(`(() => {
    const zet = (sel, v) => { const e = document.querySelector(sel); e.value = v; e.dispatchEvent(new Event('input', { bubbles: true })); e.dispatchEvent(new Event('change', { bubbles: true })); };
    zet('#txtManualName', ${JSON.stringify(cfg.gebruiker)}); zet('#txtManualPassword', ${JSON.stringify(cfg.wachtwoord)});
    document.querySelector('.manualLoginForm button[type=submit]').click(); return true; })()`);
  const ingelogd = await wachtOp(c.evalueer, "(() => { try { return JSON.parse(localStorage.getItem('jellyfin_credentials')||'{}').Servers?.some(s => s.AccessToken); } catch { return false; } })()", 30000);
  if (!ingelogd) throw new Error('inloggen in jellyfin-web lukte niet');
  uit.stappen.push('ingelogd');
  await c.evalueer(`(() => { location.hash = '#/details?id=${cfg.item}'; return true; })()`);
  const knop = await wachtOp(c.evalueer, "[...document.querySelectorAll('.mainDetailButtons .btnPlay, button.btnPlay')].some(b => b.offsetParent)", 30000);
  if (!knop) throw new Error('afspeelknop niet gevonden');
  await c.evalueer("(() => { [...document.querySelectorAll('.mainDetailButtons .btnPlay, button.btnPlay')].find(b => b.offsetParent).click(); return true; })()");
  uit.stappen.push('afspelen aangeklikt');
  uit.nativeshell = await c.evalueer("typeof window.NativeShell === 'object'");
  await wacht(8000);
  const shot = await c.stuur('Page.captureScreenshot', { format: 'png' });
  if (cfg.scherm && shot.result?.data) fs.writeFileSync(cfg.scherm, Buffer.from(shot.result.data, 'base64'));
  c.ws.close();
}

main().then(() => { uit.ok = true; }).catch((e) => { uit.ok = false; uit.fout = String(e).slice(0, 400); })
  .finally(() => { process.stdout.write(JSON.stringify(uit) + '\n'); });
