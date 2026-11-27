// Twee afzonderlijke stock-clients, dezelfde groep en één klok op de ontwikkelmachine.
import { chromium, firefox, webkit } from 'playwright';
import fs from 'node:fs';
import { setTimeout as wacht } from 'node:timers/promises';
import { fileURLToPath } from 'node:url';

const browsers = { chromium, firefox, webkit };
const klokHtml = fs.readFileSync(fileURLToPath(new URL('./watchklok.html', import.meta.url)), 'utf8');
const nu = () => performance.timeOrigin + performance.now();
const frameMs = 1001 / 24;
function meetfout(fase) {
  return Object.assign(new Error(fase), { fase });
}

async function fase(naam, actie) {
  try { return await actie(); } catch (fout) { throw fout.fase ? fout : meetfout(naam); }
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
    await page.setContent(klokHtml);
    await page.bringToFront();
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

async function openDesktop(cfg, afsluiten) {
  await wachtOp(async () => {
    try { return (await fetch(cfg.cdp + '/json/list', { signal: AbortSignal.timeout(1000) })).ok; }
    catch { return false; }
  }, 'desktop-CDP niet beschikbaar', 60000);
  const browser = await chromium.connectOverCDP(cfg.cdp);
  afsluiten.push(() => browser.close());
  const ctx = browser.contexts()[0];
  let page = ctx.pages()[0];
  if (page.url().startsWith('qrc:')) {
    await page.locator('#address').fill(cfg.desktopUrl);
    await page.locator('#connect-form').evaluate(form => form.requestSubmit());
    page = await wachtOp(() => ctx.pages().find(p => p.url().startsWith(cfg.desktopUrl + '/')), 'desktop opent de testserver niet');
  }
  return page;
}

async function deelnemer(cfg, soort, url, naam, login, afsluiten) {
  const desktop = soort === 'desktop';
  let page;
  if (desktop) {
    page = await openDesktop(cfg, afsluiten);
  } else {
    const browser = await browsers[soort].launch({ headless: true });
    afsluiten.push(() => browser.close());
    const ctx = await browser.newContext({ locale: 'nl-NL', viewport: { width: 1280, height: 720 } });
    page = await ctx.newPage();
  }
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

async function openGroep(a, b) {
  const menu = 'button[aria-label="SyncPlay"]:visible, .headerSyncButton:visible';
  await a.page.locator(menu).first().click();
  const gemaakt = a.page.waitForResponse(r => new URL(r.url()).pathname.endsWith('/SyncPlay/New') && r.request().method() === 'POST');
  await a.page.locator('[role=menuitem]:visible, .actionSheetMenuItem:visible').filter({ hasText: /nieuw|new/i }).first().click();
  const id = (await (await gemaakt).json()).GroupId;
  await b.page.locator(menu).first().click();
  await b.page.getByRole('button', { name: /deelnemen|join/i }).first().click();
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

async function afspelen(a, cfg) {
  await a.page.goto(cfg.url + '/web/#/details?id=' + cfg.item, { waitUntil: 'domcontentloaded' });
  await a.page.locator('.mainDetailButtons .btnPlay:visible, button.btnPlay:visible').first().click();
  await wachtOp(async () => (await videoStand(a.page))?.[1] > 500, 'eerste deelnemer speelt niet');
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
  const paren = [];
  let frameVorige = xwd ? xwd.lees(46) : 0, cycli = 0, gewijzigd = begin_ms;
  function desktopStand() {
    const f = xwd.lees(46), tijd = nu();
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
  regressies['server-17352'] = { groep_opgeruimd: !groepen.some(g => g.GroupId === id) };
  return { begin_ms, eind_ms, hervat_ms, playing_ms, paren, sessies, regressies };
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
    if (opdracht === 'watchklok') {
      await afspelen(a, cfg);
      const lezers = await currentTimeKlok(a.page);
      const screenshot = await rasterKlok(a.page);
      const uit = { currentTime: lezers, 'browser-screenshot': screenshot };
      if (cfg.cdp) {
        const page = await openDesktop(cfg, afsluiten);
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
    if (opdracht === 'watchfunctie') return await fase('groepsfunctieproef', () => functieproef(cfg, a, b));
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
  const gekozen = bronnen.find(o => /Multispoor/i.test(o.naam)) ?? bronnen.at(-1);
  await bron.selectOption(gekozen.id);
  const audio = p.locator('.selectAudio:visible'), subs = p.locator('.selectSubtitles:visible');
  let indices;
  if (await audio.count() && await subs.count()) {
    const kies = async veld => {
      const index = await veld.locator('option').last().getAttribute('value');
      await veld.selectOption(index);
      return Number(index);
    };
    indices = [await kies(audio), await kies(subs)];
  }
  await speel.click();
  let s;
  try {
    s = await wachtOp(async () => {
      const [sessie] = await actieveSessies(cfg);
      return sessie?.NowPlayingItem?.Id === cfg.versieItem && sessie.PlayState?.PositionTicks > 0 && sessie;
    }, 'versie start niet', 18000);
  } catch (fout) { if (fout.fase !== 'versie start niet') throw fout; }
  resultaat['server-18422'] = { ok: !!s && s.PlayState.MediaSourceId === gekozen.id, tweede_bron_gestart: !!s };
  if (indices) resultaat['server-16964'] = {
    ok: !!s && s.PlayState.AudioStreamIndex === indices[0] && s.PlayState.SubtitleStreamIndex === indices[1],
    gekozen: indices, gemeld: s ? [s.PlayState.AudioStreamIndex, s.PlayState.SubtitleStreamIndex] : null
  };
  return resultaat;
}

async function functieproef(cfg, a, b) {
  const id = await fase('groep maken en lid worden', () => openGroep(a, b));
  await fase('groepsfilm starten', () => afspelen(a, cfg));
  await wachtOp(async () => (await videoStand(b.page))?.[1] > 500, 'tweede deelnemer start niet (#17351)');
  const uit = { 'server-17351': { ok: true, spelende_deelnemers: 2 } };
  const seek = await seekProef(a, b);
  const [pa, pb] = await Promise.all([videoStand(a.page), videoStand(b.page)]);
  uit['server-16241'] = { ok: !!pa && !!pb && Math.abs(pa[1] - pb[1]) <= 1000 && pa[1] >= 9000 && pb[1] >= 9000 };
  const meldingen = seek['web-8396'].ready_posities_ms;
  uit['web-8408'] = { ...seek['web-8408'], ok: meldingen.length === 1 };
  uit['web-8396'] = { ...seek['web-8396'], ok: meldingen.length > 0 && meldingen.every(t => Math.abs(t - 10000) <= 1000) };
  const hls = seek['server-17654'];
  uit['server-17654'] = hls.segmenten ? { ...hls, ok: !hls.segmentfouten_na_seek.length }
    : { status: 'niet reproduceerbaar in de simulatie', reden: 'geen HLS-segment in het seekvenster' };
  Object.assign(uit, await versiesEnSporen(cfg, a));
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
  await a.api('POST', '/SyncPlay/Seek', { PositionTicks: 3 * 10000000 });
  await wacht(1500);
  uit['web-8727'] = { ok: b.ready.length === klaarVoor, ready_van_vertrokken_client: b.ready.length - klaarVoor };
  await a.api('POST', '/SyncPlay/Leave');
  uit['server-17352'] = { ok: !(await a.api('GET', '/SyncPlay/List')).some(g => g.GroupId === id) };
  uit['server-18121'] = { status: 'niet reproduceerbaar in de simulatie', reden: 'de Android-app is geen deelnemer aan deze twee browsers' };
  uit['desktop-1290'] = { status: 'niet gemeten', reden: 'de Ready-positie van de echte desktop wordt in S4 getoetst' };
  return uit;
}
