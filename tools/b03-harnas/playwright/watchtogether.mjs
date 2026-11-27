// Twee afzonderlijke stock-clients, dezelfde groep en één klok op de ontwikkelmachine.
import { chromium, firefox } from 'playwright';
import { openDesktop } from './watchdesktop.mjs';
import fs from 'node:fs';
import { setTimeout as wacht } from 'node:timers/promises';
import { fileURLToPath } from 'node:url';

const browsers = { chromium, firefox };
const klokHtml = fs.readFileSync(fileURLToPath(new URL('./watchklok.html', import.meta.url)), 'utf8');
const nu = () => performance.timeOrigin + performance.now();
const frameMs = 1001 / 24;
function meetfout(fase) {
  return Object.assign(new Error(fase), { fase });
}

async function fase(naam, actie) {
  try { return await actie(); } catch (fout) { throw fout.fase ? fout : meetfout(naam); }
}

function onderbroken(reden, fout) {
  // Alleen een vaste classificatie bewaren. Playwright-foutteksten bevatten soms de URL of formuliervelden.
  const regel = /watchtogether\.mjs:(\d+):/.exec(String(fout.stack));
  const soort = /timeout/i.test(fout.name) ? 'wachttijd verstreken'
    : /interrupted by another navigation|NS_BINDING_ABORTED/i.test(fout.message) ? 'navigatie onderbroken'
    : ['SyntaxError', 'TypeError'].includes(fout.name) ? fout.name : 'clientfout';
  return { status: 'proef onderbroken', reden: fout.fase || reden, foutsoort: soort, ...(regel ? { bronregel: Number(regel[1]) } : {}) };
}

async function wachtOp(actie, reden, limiet = 30000) {
  const einde = nu() + limiet;
  do {
    const waarde = await actie();
    if (waarde) return waarde;
    await wacht(100);
  } while (nu() < einde);
  throw meetfout(reden);
}

function xwdLezer(pad) {
  // Xvfb -fbdir schrijft XWD-versie 7. Lees alleen de rasterrij uit het live framebuffer.
  const fd = fs.openSync(pad, 'r');
  try {
    const kop = Buffer.alloc(100);
    fs.readSync(fd, kop, 0, kop.length, 0);
    const veld = i => kop.readUInt32BE(i * 4);
    if (veld(1) !== 7 || veld(2) !== 2 || veld(11) !== 32 || veld(7) !== 0 || veld(4) !== 1280 || veld(5) !== 720) {
      throw meetfout('onbekende Xvfb-rastergeometrie');
    }
    const begin = veld(0) + veld(19) * 12;
    const rij = Buffer.alloc(veld(12));
    return {
      sluit: () => fs.closeSync(fd),
      lees(y) {
        if (fs.readSync(fd, rij, 0, rij.length, begin + y * rij.length) !== rij.length) throw meetfout('onvolledige Xvfb-opname');
        let frame = 0;
        for (let i = 0; i < 16; i++) if (rij[(i * 80 + 36) * 4 + 1] >= 128) frame += 2 ** i;
        return frame;
      }
    };
  } catch (fout) { fs.closeSync(fd); throw fout; }
}

async function pngFrame(decoder, png) {
  // PNG-decodering na de tijdstempel ná de screenshot.
  return decoder.evaluate(async base64 => {
    const img = new Image();
    img.src = 'data:image/png;base64,' + base64;
    await img.decode();
    const canvas = document.createElement('canvas');
    canvas.width = img.width;
    canvas.height = 1;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(img, 0, Math.floor(img.height / 2), img.width, 1, 0, 0, img.width, 1);
    const pixels = ctx.getImageData(0, 0, img.width, 1).data;
    let frame = 0;
    for (let i = 0; i < 16; i++) if (pixels[Math.floor((i + .45) * img.width / 16) * 4] >= 128) frame += 2 ** i;
    return frame;
  }, png.toString('base64'));
}

async function rasterKlok(page, xwd) {
  const decoder = xwd ? null : await page.context().newPage();
  try {
    // Vervang alleen de actuele documentinhoud. De volgende navigatie herstelt de stock-webclient.
    if (xwd) await page.toonKlok(klokHtml);
    else { await page.setContent(klokHtml); await page.bringToFront(); }
    await wacht(200);
    const opnamen = [];
    for (let i = 0; i < 15; i++) {
      const voor_ms = nu();
      const beeld = xwd ? xwd.lees(360) : await page.screenshot({ type: 'png' });
      const na_ms = nu();
      const frame = xwd ? beeld : await pngFrame(decoder, beeld);
      const cyclus = Math.round(((voor_ms + na_ms) / (2 * frameMs) - frame) / 65536);
      opnamen.push({ voor_ms, na_ms, klok_ms: (frame + cyclus * 65536) * frameMs });
      await wacht(50);
    }
    return opnamen;
  } finally { if (decoder) await decoder.close(); }
}

async function videoStand(page) {
  return page.evaluate(() => {
    const v = document.querySelector('video');
    if (!v || !v.videoWidth || v.error || v.ended) return null;
    return [performance.timeOrigin + performance.now(), v.currentTime * 1000, v.paused || v.readyState < 3 ? 0 : v.playbackRate];
  });
}

async function deelnemer(cfg, soort, url, naam, login, afsluiten) {
  if (soort === 'desktop') {
    const qt = await openDesktop(cfg, afsluiten, wachtOp);
    await qt.login();
    return qt;
  }
  const browser = await browsers[soort].launch({ headless: true });
  afsluiten.push(() => browser.close());
  const ctx = await browser.newContext({ locale: 'nl-NL', viewport: { width: 1280, height: 720 } });
  const page = await ctx.newPage();
  if (cfg.systeem === 'stock-best') {
    await page.addInitScript(kv => {
      if (/^https?:$/.test(location.protocol)) for (const [k, v] of Object.entries(kv)) localStorage.setItem(k, v);
    }, cfg.instellingen);
  }
  let autorisatie;
  const ready = [], segmenten = [];
  page.on('request', req => {
    if (new URL(req.url()).origin !== url) return;
    const auth = req.headers().authorization || req.headers()['x-emby-authorization'];
    if (auth && /Token="[^"]+"/i.test(auth)) autorisatie = auth;
    if (/\/SyncPlay\/Ready$/i.test(new URL(req.url()).pathname) && req.method() === 'POST') {
      const body = req.postDataJSON();
      ready.push({ positie_ms: body.PositionTicks / 10000 });
    }
  });
  page.on('response', res => {
    if (/\.(ts|m4s)$/i.test(new URL(res.url()).pathname)) segmenten.push(res.status());
  });
  await page.addInitScript(() => {
    window.b03Playing = [];
    document.addEventListener('playing', e => {
      if (e.target.tagName === 'VIDEO') window.b03Playing.push(performance.timeOrigin + performance.now());
    }, true);
  });
  await login(page, naam, cfg.wachtwoord, url);
  if (cfg.systeem === 'stock-best' && !await page.evaluate(kv => Object.entries(kv).every(([k, v]) => localStorage.getItem(k) === v),
    cfg.instellingen)) throw meetfout('clientinstellingen wijken af van stock-best');
  await wachtOp(() => autorisatie, 'sessie van de ingelogde client ontbreekt');
  const api = async (methode, pad, data) => {
    const res = await page.request.fetch(url + pad, { method: methode, headers: { Authorization: autorisatie }, data, maxRedirects: 0 });
    if (!res.ok()) throw meetfout('stock weigerde een groepsactie (' + res.status() + ')');
    return res.status() === 204 ? null : res.json();
  };
  return { page, api, ready, segmenten };
}

const menu = 'button[aria-label="SyncPlay"]:visible, .headerSyncButton:visible';

async function sluitAan(b, naam) {
  if (b.sluitAan) return b.sluitAan(naam);
  // Stock bewaart de lijst tot een minuut. Deze deelnemer is ingelogd en heeft nog geen actieve groep.
  await b.page.reload({ waitUntil: 'domcontentloaded' });
  await b.page.locator(menu).first().click();
  const rij = b.page.locator('[role=menu] li:visible').filter({ hasText: naam });
  const klassiek = b.page.locator('.actionSheetMenuItem:visible').filter({ hasText: naam });
  await rij.getByRole('button', { name: /deelnemen|join/i }).or(klassiek).first().click();
}

async function maakGroep(a) {
  await fase('SyncPlay-menu van de eerste deelnemer ontbreekt', () => a.page.locator(menu).first().click());
  const [gemaakt] = await fase('stockclient maakt geen nieuwe groep', () => Promise.all([
    a.page.waitForResponse(r => new URL(r.url()).pathname.endsWith('/SyncPlay/New') && r.request().method() === 'POST'),
    a.page.locator('[role=menuitem]:visible, .actionSheetMenuItem:visible').filter({ hasText: /nieuw|new/i }).first().click()
  ]));
  return gemaakt.json();
}

async function openGroep(a, b) {
  const { GroupId: id, GroupName: naam } = await maakGroep(a);
  await fase('de aangemaakte groep ontbreekt in de tweede stockclient', () => sluitAan(b, naam));
  await wachtOp(async () => (await a.api('GET', '/SyncPlay/' + id)).Participants.length === 2, 'tweede deelnemer ontbreekt');
  return id;
}

async function currentTimeKlok(page) {
  const opnamen = [];
  for (let i = 0; i < 20; i++) {
    const voor = nu();
    const [a, b] = await Promise.all([videoStand(page), videoStand(page)]);
    const na = nu();
    if (!a || !b || a[2] !== 1 || b[2] !== 1) throw meetfout('referentiesessie loopt niet op normale snelheid');
    // Extrapoleer de eerste lezer naar de beide hosttijdstippen. De tweede leest dezelfde bekende mediaklok.
    opnamen.push({ host_voor_ms: voor, host_na_ms: na, voor_ms: a[1] + voor - a[0], na_ms: a[1] + na - a[0], klok_ms: b[1] });
    await wacht(80);
  }
  return opnamen;
}

async function startFilm(a, cfg) {
  await a.page.goto(cfg.url + '/web/#/details?id=' + cfg.item, { waitUntil: 'domcontentloaded' });
  await a.page.locator('.mainDetailButtons .btnPlay:visible, button.btnPlay:visible').first().click();
}

async function afspelen(a, cfg) {
  await startFilm(a, cfg);
  await wachtOp(async () => (await videoStand(a.page))?.[1] > 500, 'eerste deelnemer speelt niet');
}

async function androidGroep(cfg, a) {
  const groep = await maakGroep(a);
  const detail = '/SyncPlay/' + groep.GroupId;
  await afspelen(a, cfg);
  // De telefoon sluit via zijn eigen UI aan op de afspelende webgroep.
  await wachtOp(async () => (await a.api('GET', detail)).Participants.length === 2, 'Android trad niet toe tot de webgroep', 135000);
  await a.api('POST', '/SyncPlay/Unpause');
  const begin = nu(), staten = [];
  const posities = cfg.namen.map(() => []);
  while (nu() - begin < 45000) {
    const groep = await a.api('GET', detail);
    if (groep.Participants.length !== 2) throw meetfout('een client verliet de Android-groep');
    if (staten.at(-1) !== groep.State) staten.push(groep.State);
    const sessies = await actieveSessies(cfg);
    sessies.forEach((s, i) => {
      if (s?.NowPlayingItem?.Id === cfg.item && Number.isFinite(s.PlayState?.PositionTicks)) posities[i].push(s.PlayState.PositionTicks);
    });
    await wacht(750);
  }
  await a.api('POST', '/SyncPlay/Leave');
  return { observatie_ms: nu() - begin, groepsstaten: staten, voortgang_ms: posities.map(p => p.length ? (Math.max(...p) - p[0]) / 10000 : 0) };
}

async function groepsrun(cfg, a, b, xwd) {
  const id = await openGroep(a, b);
  if (cfg.scenario === 'S5') {
    const cdp = await b.page.context().newCDPSession(b.page);
    await cdp.send('Network.enable');
    await cdp.send('Network.emulateNetworkConditions', { offline: false, latency: 0, downloadThroughput: 1500000 / 8,
      uploadThroughput: -1, connectionType: 'cellular3g' });
  }
  await afspelen(a, cfg);
  const posB = xwd ? () => xwd.lees(46) : async () => (await videoStand(b.page))?.[1];
  await wachtOp(async () => (await posB()) > 2, 'tweede deelnemer start niet (#17351)');
  await a.api('POST', '/SyncPlay/Pause');
  await wachtOp(async () => (await videoStand(a.page))?.[2] === 0, 'eerste deelnemer pauzeert niet');
  if (!xwd) await wachtOp(async () => (await videoStand(b.page))?.[2] === 0, 'tweede deelnemer pauzeert niet');
  let vorigeFrame = 0;
  if (xwd) {
    await wachtOp(async () => { vorigeFrame = xwd.lees(46); await wacht(160); return vorigeFrame === xwd.lees(46); }, 'desktop pauzeert niet');
  }
  const hervat_ms = nu();
  await a.api('POST', '/SyncPlay/Unpause');
  const playingEvent = p => wachtOp(() => p.evaluate(t => window.b03Playing.find(x => x >= t), hervat_ms), 'playing-event ontbreekt');
  const playing_ms = await Promise.all([playingEvent(a.page), xwd
    ? (async () => { while (nu() - hervat_ms < 30000) { if (xwd.lees(46) !== vorigeFrame) return nu(); await wacht(50); }
      throw meetfout('desktop hervat niet'); })() : playingEvent(b.page)]);
  // Werkelijk geselecteerde afspeelpaden van de twee eigen clients, terwijl ze in de groep spelen.
  const sessies = await sessiePaden(cfg);
  const begin_ms = nu();
  const paren = [], rasteropnamen = [];
  let frameVorige = xwd ? xwd.lees(46) : 0, cycli = 0, gewijzigd = begin_ms;
  function desktopStand() {
    const voor = nu(), f = xwd.lees(46), na = nu();
    const tijd = (voor + na) / 2;
    rasteropnamen.push([voor, na, f]);
    if (f < 24 && frameVorige > cfg.framePeriodeMs / frameMs - 25) cycli++;
    if (f !== frameVorige) gewijzigd = tijd;
    frameVorige = f;
    return [tijd, f * frameMs + cycli * cfg.framePeriodeMs, tijd - gewijzigd < 130 ? 1 : 0];
  }
  while (nu() - begin_ms < 300000) {
    const t = nu();
    const paar = await Promise.all([videoStand(a.page), xwd ? desktopStand() : videoStand(b.page)]);
    if (paar.some(s => !s)) throw meetfout('onvolledige afspeelpositie');
    paren.push(paar);
    await wacht(Math.max(0, 65 - (nu() - t)));
  }
  const eind_ms = nu();
  const regressies = await seekProef(a, b, xwd);
  await b.api('POST', '/SyncPlay/Leave');
  await a.api('POST', '/SyncPlay/Leave');
  const groepen = await a.api('GET', '/SyncPlay/List');
  regressies.expliciet_verlaten = { groep_opgeruimd: !groepen.some(g => g.GroupId === id) };
  return { begin_ms, eind_ms, hervat_ms, playing_ms, paren, sessies, regressies, ...(xwd ? { rasteropnamen } : {}) };
}

async function sessiePaden(cfg) {
  const res = await fetch(cfg.url + '/Sessions', { headers: { Authorization: cfg.beheer }, redirect: 'error' });
  if (!res.ok) throw meetfout('kan afspeelpaden niet bevestigen');
  const sessies = await res.json();
  return cfg.namen.map(naam => {
    const s = sessies.find(s => s.UserName === naam && s.NowPlayingItem?.Id === cfg.item);
    if (!s?.PlayState?.PlayMethod) throw meetfout('actieve sessie met het gekozen item ontbreekt');
    return { methode: s.PlayState.PlayMethod, video_transcode: s.TranscodingInfo?.IsVideoDirect === false };
  });
}

async function seekProef(a, b, xwd) {
  const voor = b.ready.length, segmentenVoor = b.segmenten.length;
  await a.api('POST', '/SyncPlay/Seek', { PositionTicks: 10 * 10000000 });
  await wacht(4000);
  const meldingen = b.ready.slice(voor);
  const uit = {
    'web-8408': { ready_na_een_seek: meldingen.length },
    'web-8396': { ready_posities_ms: meldingen.map(r => r.positie_ms), doel_ms: 10000 },
    'server-17654': { segmentfouten_na_seek: b.segmenten.slice(segmentenVoor).filter(status => status >= 400), segmenten: b.segmenten.length - segmentenVoor }
  };
  if (xwd) uit['desktop-1290'] = { ready_posities_ms: meldingen.map(r => r.positie_ms), doel_ms: 10000,
    ok: meldingen.length > 0 && meldingen.every(r => Math.abs(r.positie_ms - 10000) <= 1000) };
  return uit;
}

export async function meet(opdracht, cfg, login) {
  const afsluiten = [];
  try {
    const a = await fase('aanmelding eerste testclient', () => deelnemer(cfg, cfg.browser, cfg.url, cfg.namen[0], login, afsluiten));
    if (opdracht === 'watchandroid') return await fase('Android-groep starten en volgen', () => androidGroep(cfg, a));
    if (opdracht === 'watchklok') {
      await afspelen(a, cfg);
      const lezers = await currentTimeKlok(a.page);
      const screenshot = await rasterKlok(a.page);
      const uit = { currentTime: lezers, 'browser-screenshot': screenshot };
      if (cfg.cdp) {
        const page = await openDesktop(cfg, afsluiten, wachtOp);
        const lezer = xwdLezer(cfg.xwd);
        afsluiten.push(() => lezer.sluit());
        uit.Xvfb = await rasterKlok(page, lezer);
      }
      return uit;
    }
    const b = await fase('aanmelding tweede testclient', () => deelnemer(cfg, cfg.tweede, cfg.desktopUrl || cfg.urlB || cfg.url,
      cfg.namen[1], login, afsluiten));
    const xwd = cfg.cdp ? xwdLezer(cfg.xwd) : null;
    if (xwd) afsluiten.push(() => xwd.sluit());
    if (opdracht === 'watchfunctie') {
      const nrs = ['server-17351', 'server-16241', 'server-16964', 'server-18422', 'server-17654', 'server-17352',
        'web-8408', 'web-8396', 'web-8690', 'web-8727'];
      const uit = Object.fromEntries(nrs.map(nr => [nr, { status: 'niet gemeten', reden: 'proef niet bereikt' }]));
      uit['desktop-1290'] = { status: 'niet gemeten', reden: 'de desktop-proef staat in S4' };
      try { await functieproef(cfg, a, b, uit); }
      catch (fout) { uit.groepsproef = onderbroken('groepsbediening', fout); }
      return uit;
    }
    return await fase('groepsmeting', () => groepsrun(cfg, a, b, xwd));
  } finally { for (const sluit of afsluiten.reverse()) await sluit(); }
}

async function actieveSessies(cfg) {
  const res = await fetch(cfg.url + '/Sessions', { headers: { Authorization: cfg.beheer }, redirect: 'error' });
  if (!res.ok) throw meetfout('sessiecontrole mislukt');
  const alle = await res.json();
  return cfg.namen.map(naam => alle.find(s => s.UserName === naam && s.NowPlayingItem));
}

async function versiesEnSporen(cfg, a) {
  const ontbreekt = reden => ({ status: 'niet reproduceerbaar in de simulatie', reden });
  const resultaat = {
    'server-16964': ontbreekt('de versie heeft geen selecteerbare audio- en ondertitelsporen'),
    'server-18422': ontbreekt('de UI bood geen tweede versie aan')
  };
  if (!cfg.versieItem) return resultaat;
  const p = a.page;
  await p.goto(cfg.url + '/web/#/details?id=' + cfg.versieItem, { waitUntil: 'domcontentloaded' });
  const speel = p.locator('.mainDetailButtons .btnPlay:visible, button.btnPlay:visible').first();
  await speel.waitFor();
  const bron = p.locator('.selectSource:visible');
  if (!await bron.count() || await bron.locator('option').count() < 2) return resultaat;
  const bronnen = await bron.locator('option').evaluateAll(opts => opts.map(o => ({ id: o.value, naam: o.text })));
  const standaard = await bron.inputValue();
  const gekozen = bronnen.find(o => o.id !== standaard);
  if (!gekozen) return resultaat;
  await bron.selectOption(gekozen.id);
  const audio = p.locator('.selectAudio:visible'), subs = p.locator('.selectSubtitles:visible');
  let indices;
  if (await audio.count() && await subs.count()) {
    const kiesAndere = async veld => {
      const huidig = await veld.inputValue();
      const opties = await veld.locator('option').evaluateAll(opts => opts.map(o => o.value));
      const index = opties.find(v => v !== huidig && /^\d+$/.test(v));
      if (index === undefined) return null;
      await veld.selectOption(index);
      return Number(index);
    };
    const selectie = [await kiesAndere(audio), await kiesAndere(subs)];
    if (selectie.every(index => index !== null)) indices = selectie;
  }
  await speel.click();
  let s;
  try {
    s = await wachtOp(async () => {
      const [sessie] = await actieveSessies(cfg);
      const id = sessie?.NowPlayingItem?.Id;
      return (id === cfg.versieItem || bronnen.some(o => o.id === id)) && sessie.PlayState?.PositionTicks > 0 && sessie;
    }, 'versie start niet', 18000);
  } catch (fout) { if (fout.fase !== 'versie start niet') throw fout; }
  const tweedeBron = !!s && s.PlayState.MediaSourceId === gekozen.id;
  resultaat['server-18422'] = { ok: tweedeBron, aflevering_gestart: !!s, tweede_bron_gestart: tweedeBron };
  if (indices) resultaat['server-16964'] = {
    ok: tweedeBron && s.PlayState.AudioStreamIndex === indices[0] && s.PlayState.SubtitleStreamIndex === indices[1],
    gekozen: indices, gemeld: s ? [s.PlayState.AudioStreamIndex, s.PlayState.SubtitleStreamIndex] : null
  };
  return resultaat;
}

async function hlsNaCorrectie(cfg, a, b) {
  const ontbreekt = reden => ({ status: 'niet reproduceerbaar in de simulatie', reden });
  if (!cfg.hlsItem) return ontbreekt('de HEVC-testclip ontbreekt');
  await startFilm(a, { ...cfg, item: cfg.hlsItem });
  try {
    await wachtOp(async () => (await actieveSessies(cfg)).every(s => s?.NowPlayingItem?.Id === cfg.hlsItem && s.PlayState?.PositionTicks > 0),
      'de twee deelnemers spelen de HEVC-testclip niet', 25000);
  } catch (fout) {
    if (fout.fase !== 'de twee deelnemers spelen de HEVC-testclip niet') throw fout;
    return ontbreekt(fout.fase);
  }
  const begin = b.segmenten.length;
  for (const sec of [15, 3]) {
    await a.api('POST', '/SyncPlay/Seek', { PositionTicks: sec * 10000000 });
    await wacht(4000);
  }
  const segmenten = b.segmenten.slice(begin), fouten = segmenten.filter(status => status >= 400);
  return segmenten.length ? { ok: fouten.length === 0, segmenten: segmenten.length, segmentfouten_na_seek: fouten }
    : ontbreekt('geen HLS-segment van de HEVC-testclip in de twee correctievensters');
}

async function naVenstersSluiten(cfg, a, b, id) {
  await wachtOp(async () => (await a.api('GET', '/SyncPlay/' + id)).Participants.length === 2, 'sluitproef mist de tweede deelnemer');
  // Beide browserprocessen sluiten met een actieve groep. Een aparte waarnemer leest de resterende leden.
  await Promise.all([a.page.context().browser().close(), b.page.context().browser().close()]);
  const begin = nu();
  let groep;
  do {
    const res = await fetch(cfg.url + '/SyncPlay/List', { headers: { Authorization: cfg.beheer }, redirect: 'error' });
    if (!res.ok) throw meetfout('waarnemer kan na het sluiten de groepslijst niet lezen');
    groep = (await res.json()).find(g => g.GroupId === id);
    if (!groep) break;
    await wacht(1000);
  } while (nu() - begin < 30000);
  return { ok: !groep, observatie_ms: nu() - begin, resterende_deelnemers: groep?.Participants.length ?? 0 };
}

async function functieproef(cfg, a, b, uit) {
  const id = await fase('groep maken en lid worden', () => openGroep(a, b));
  try {
    await fase('groepsfilm starten', () => afspelen(a, cfg));
    await wachtOp(async () => (await videoStand(b.page))?.[1] > 500, 'tweede deelnemer start niet (#17351)');
  } catch (fout) {
    if (!['eerste deelnemer speelt niet', 'tweede deelnemer start niet (#17351)'].includes(fout.fase)) throw fout;
    uit['server-17351'] = { ok: false, reden: fout.fase };
    uit['server-17352'] = await naVenstersSluiten(cfg, a, b, id);
    for (const nr of ['server-16241', 'server-16964', 'server-17654', 'server-18422', 'web-8408', 'web-8396', 'web-8690', 'web-8727']) {
      uit[nr] = { status: 'niet reproduceerbaar in de simulatie', reden: 'de afspeelproef heeft geen twee spelende deelnemers' };
    }
    return;
  }
  uit['server-17351'] = { ok: true, spelende_deelnemers: 2 };
  const seek = await seekProef(a, b);
  const [pa, pb] = await Promise.all([videoStand(a.page), videoStand(b.page)]);
  uit['server-16241'] = { ok: !!pa && !!pb && Math.abs(pa[1] - pb[1]) <= 1000 && pa[1] >= 9000 && pb[1] >= 9000 };
  const meldingen = seek['web-8396'].ready_posities_ms;
  uit['web-8408'] = { ...seek['web-8408'], ok: meldingen.length === 1 };
  uit['web-8396'] = { ...seek['web-8396'], ok: meldingen.length > 0 && meldingen.every(t => Math.abs(t - 10000) <= 1000) };
  try { Object.assign(uit, await versiesEnSporen(cfg, a)); }
  catch (fout) { uit['server-16964'] = uit['server-18422'] = onderbroken('alternatieve aflevering en sporen', fout); }
  try { uit['server-17654'] = await hlsNaCorrectie(cfg, a, b); }
  catch (fout) { uit['server-17654'] = onderbroken('HLS na positiecorrectie', fout); }
  await a.api('POST', '/SyncPlay/SetNewQueue', {
    PlayingQueue: [cfg.item, cfg.volgende], PlayingItemPosition: 0, StartPositionTicks: cfg.duurTicks - 5 * 10000000
  });
  try {
    await wachtOp(async () => (await actieveSessies(cfg)).every(s => s?.NowPlayingItem?.Id === cfg.volgende),
      'wachtrij ging niet naar het volgende item', 25000);
    uit['web-8690'] = { ok: true };
  } catch (fout) {
    if (fout.fase !== 'wachtrij ging niet naar het volgende item') throw fout;
    uit['web-8690'] = { ok: false };
  }
  await b.api('POST', '/SyncPlay/Leave');
  await wachtOp(async () => (await a.api('GET', '/SyncPlay/' + id)).Participants.length === 1, 'deelnemer verliet groep niet');
  const klaarVoor = b.ready.length;
  const soloVoor = await videoStand(b.page);
  await a.api('POST', '/SyncPlay/Seek', { PositionTicks: 3 * 10000000 });
  await wacht(1500);
  const soloNa = await videoStand(b.page);
  const sprong = soloVoor && soloNa ? Math.abs(soloNa[1] - soloVoor[1] - (soloNa[0] - soloVoor[0]) * soloVoor[2]) : null;
  uit['web-8727'] = { ok: b.ready.length === klaarVoor && ((soloVoor === null && soloNa === null) || (sprong !== null && sprong < 1000)),
    ready_van_vertrokken_client: b.ready.length - klaarVoor, onverwachte_positiewijziging_ms: sprong };
  const groep = await a.api('GET', '/SyncPlay/' + id);
  await b.page.goto(cfg.url + '/web/', { waitUntil: 'domcontentloaded' });
  await sluitAan(b, groep.GroupName);
  uit['server-17352'] = await naVenstersSluiten(cfg, a, b, id);
}
