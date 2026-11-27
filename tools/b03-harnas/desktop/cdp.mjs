// Besturing van de echte QtWebEngine-pagina en meting op de wegwerptestserver.
// Alleen de desktop en de CDP-besturing delen deze netwerkruimte.
import fs from 'node:fs';
import { doelen, verbind } from './pagina.mjs';

const cfg = JSON.parse(fs.readFileSync(0, 'utf8'));
const server = 'http://testserver:8096';
const cdp = 'http://localhost:9222';
const uit = { webclient_geladen: false, ingelogd: false, consolelog: [], chunkloaderror: null,
  afspelen: [], hervatten: [], voortgang_hervatten_s: [] };
const wacht = (ms) => new Promise((klaar) => setTimeout(klaar, ms));
let fase = 'start';

// Bewaar de foutmelding of herkenbare consolegebeurtenis, zonder vrije argumenten,
// stacktraces, URL's of gegevens uit de aanmelding in het bewijs over te nemen.
function logregel(bron, niveau, tekst) {
  const herkenbaar = tekst.match(/ChunkLoadError|net::ERR_[A-Z_]+|Loading chunk \d+ failed|Failed to fetch|Failed to load resource|Uncaught (?:TypeError|ReferenceError|SyntaxError)|jmpCheckServerConnectivity|ConnectionManager|AppHost|NativeShell|WebSocket|playbackManager|PlaySession|Jellyfin Desktop/gi);
  if (/ChunkLoadError/i.test(tekst)) uit.chunkloaderror = true;
  const melding = herkenbaar ? [...new Set(herkenbaar)].join(', ') : 'overige melding';
  const regel = uit.consolelog.find((r) => r.bron === bron && r.niveau === niveau && r.melding === melding && r.fase === fase);
  if (regel) regel.aantal++;
  else uit.consolelog.push({ fase, bron, niveau, melding, aantal: 1 });
}

function gebeurtenis(method, p) {
  if (method === 'Runtime.consoleAPICalled') {
    logregel(method, p.type, p.args.map((a) => String(a.value ?? a.description ?? '')).join(' '));
  } else if (method === 'Runtime.exceptionThrown') {
    logregel(method, 'error', p.exceptionDetails.exception?.description ?? p.exceptionDetails.text);
  } else if (method === 'Log.entryAdded') {
    logregel(method, p.entry.level, p.entry.text);
  } else if (method === 'Network.requestWillBeSent' && fase === 'hervatten') {
    const r = p.request;
    const url = new URL(r.url);
    if (r.method !== 'POST' || url.origin !== server || !/\/Sessions\/Playing\/Progress\/?$/i.test(url.pathname)) return;
    if (!r.postData) return;
    let body;
    try { body = JSON.parse(r.postData); } catch { return; }
    if (body?.ItemId === cfg.item && Number.isFinite(body.PositionTicks)) uit.voortgang_hervatten_s.push(body.PositionTicks / 1e7);
  }
}

async function wachtTot(meting, reden, ms = 30000) {
  const einde = Date.now() + ms;
  do {
    const waarde = await meting();
    if (waarde) return waarde;
    await wacht(400);
  } while (Date.now() < einde);
  throw new Error(reden);
}

async function klik(pagina, selector, bijKlik = fase) {
  const plek = await wachtTot(() => pagina.evalueer(`(() => {
    const knop = [...document.querySelectorAll(${JSON.stringify(selector)})].find((b) => b.offsetParent);
    if (!knop) return null;
    knop.scrollIntoView({ block: 'center' });
    const r = knop.getBoundingClientRect();
    return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
  })()`), 'knop ontbreekt: ' + fase);
  fase = bijKlik;
  const begin = performance.now();
  for (const type of ['mousePressed', 'mouseReleased']) {
    await pagina.stuur('Input.dispatchMouseEvent', { type, ...plek, button: 'left', clickCount: 1 });
  }
  return begin;
}

async function api(pad, method = 'GET') {
  const r = await fetch(server + pad, { method, headers: { Authorization: cfg.autorisatie }, redirect: 'error',
    signal: AbortSignal.timeout(5000) });
  if (!r.ok) throw new Error('testserver gaf HTTP ' + r.status + ' bij ' + fase);
  if (method === 'GET') return r.json();
}

async function speelstand() {
  const sessies = await api('/Sessions');
  return sessies.find((s) => s.Client === 'Jellyfin Desktop' && s.UserId === cfg.uid && s.NowPlayingItem?.Id === cfg.item);
}

async function bewaard() {
  const data = await api('/UserItems/' + cfg.item + '/UserData?userId=' + cfg.uid);
  return Number.isFinite(data.PlaybackPositionTicks) ? data.PlaybackPositionTicks / 1e7 : null;
}

async function speel(pagina, naam, minimum) {
  fase = 'detailpagina';
  // Na de stop haalt een nieuwe detailpagina de zojuist opgeslagen UserData op.
  await pagina.evalueer(`location.hash = '#/details?id=${cfg.item}'`);
  const knop = '.mainDetailButtons .btnPlay';
  const begin = await klik(pagina, naam === 'hervatten' ? knop + '[title="Resume"], ' + knop + '[title="Hervatten"]' : knop, naam);
  const rij = uit[naam];
  const sessie = await wachtTot(async () => {
    const s = await speelstand();
    if (!s || s.PlayState?.IsPaused || !Number.isFinite(s.PlayState?.PositionTicks)) return false;
    const pos = s.PlayState.PositionTicks / 1e7;
    if (!rij.length || rij.at(-1)[1] !== pos) rij.push([Math.round(performance.now() - begin) / 1000, pos]);
    // Ook een sprong vanaf nul blijft in de meetreeks voor de eindbeoordeling.
    const voortgangGemeld = naam === 'afspelen' || uit.voortgang_hervatten_s.length > 0;
    return voortgangGemeld && rij.length >= 2 && pos >= minimum && pos - rij[0][1] >= 2 && s;
  }, 'geen oplopende positie van de desktopsessie bij ' + naam, 55000);
  uit.sessie = { client: sessie.Client, versie: sessie.ApplicationVersion, methode: sessie.PlayState.PlayMethod };
  if (naam === 'hervatten') {
    const beeld = await pagina.stuur('Page.captureScreenshot', { format: 'png' });
    if (beeld.data) fs.writeFileSync('/bewijs/desktop-spike.png', Buffer.from(beeld.data, 'base64'));
  }
  fase = 'stop na ' + naam;
  await api('/Sessions/' + sessie.Id + '/Playing/Stop', 'POST');
  await wachtTot(async () => !(await speelstand()), 'desktop stopte niet');
  // Wacht op de schrijfactie van de server, ook als de sessie al verdwenen is.
  return wachtTot(async () => {
    const punt = await bewaard();
    return punt > (uit.hervatpunt_s || 0) && Math.abs(punt - rij.at(-1)[1]) <= 5 && punt;
  }, 'hervatpunt na stoppen niet bewaard');
}

async function main() {
  const eerste = await wachtTot(async () => (await doelen(cdp))[0], 'geen CDP-paginadoel onder Xvfb', 60000);
  let pagina = await verbind(cdp, eerste, gebeurtenis);
  try {
    if (eerste.url.startsWith('qrc:')) {
      await wachtTot(() => pagina.evalueer("!!document.getElementById('address')"), 'serverkeuze ontbreekt');
      await pagina.evalueer(`(() => { const a = document.getElementById('address'); a.value = ${JSON.stringify(server)};
        a.dispatchEvent(new Event('input', { bubbles: true })); document.getElementById('connect-form').requestSubmit(); })()`);
    }
    const web = await wachtTot(async () => (await doelen(cdp)).find((d) => d.url?.startsWith(server + '/')),
      'webclient van de testserver niet geladen', 60000);
    if (web.id !== eerste.id) { pagina.sluit(); pagina = await verbind(cdp, web, gebeurtenis); }
    await wachtTot(() => pagina.evalueer("!!document.querySelector('#txtManualName, .btnManual')"), 'inlogscherm niet geladen');
    uit.webclient_geladen = true;
    fase = 'inloggen';
    await pagina.evalueer("if (!document.querySelector('#txtManualName')?.offsetParent) document.querySelector('.btnManual')?.click()");
    await wachtTot(() => pagina.evalueer("!!document.querySelector('#txtManualName')?.offsetParent"), 'aanmeldformulier ontbreekt');
    await pagina.evalueer(`(() => {
      if (location.origin !== ${JSON.stringify(server)}) return;
      for (const [sel, v] of Object.entries(${JSON.stringify({ '#txtManualName': cfg.gebruiker, '#txtManualPassword': cfg.wachtwoord })})) {
        const e = document.querySelector(sel); e.value = v;
        for (const type of ['input', 'change']) e.dispatchEvent(new Event(type, { bubbles: true }));
      }
    })()`);
    await klik(pagina, '.manualLoginForm button[type=submit]');
    await wachtTot(() => pagina.evalueer(`Object.values(JSON.parse(localStorage.getItem('jellyfin_credentials') || '{}').Servers || {})
      .some((s) => s.AccessToken && s.UserId === ${JSON.stringify(cfg.uid)})`), 'aanmelding testgebruiker mislukt');
    uit.ingelogd = true;
    uit.beginpunt_s = await bewaard();
    uit.hervatpunt_s = await speel(pagina, 'afspelen', 17);
    uit.eindpunt_s = await speel(pagina, 'hervatten', uit.hervatpunt_s + 2);
    if (uit.chunkloaderror === null) uit.chunkloaderror = false;
  } finally { pagina.sluit(); }
}

main().catch((fout) => { uit.fout = fout.message; }).finally(() => {
  process.stdout.write(JSON.stringify(uit) + '\n');
});
