// B03-016 clientmatrix — jellyfin-web (zoals de server hem serveert) in Chromium, Firefox en WebKit via Playwright 1.63.
//
//   node harnas.mjs profiel '<json>'   echt DeviceProfile vangen (POST /Items/{id}/PlaybackInfo) + beslissing + videostand
//   node harnas.mjs speel   '<json>'   items via de UI afspelen: tijd tot eerste frame, currentTime-verloop, orakel
//
// Invoer (JSON): {browser, url, gebruiker, wachtwoord, items:[{id,naam}], ua?, initScript?, orakelMs?, duurMs?, schermMap?}
// Uitvoer: één JSON-object op stdout. WebKit op Linux is géén Safari (decodeert via GStreamer van de host).
// Alleen voor ontwikkeling/CI; draait nooit op de NAS.
import { chromium, firefox, webkit } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';

const BROWSERS = { chromium, firefox, webkit };
const [, , opdracht, invoer] = process.argv;
const cfg = JSON.parse(invoer && invoer.trim().startsWith('{') ? invoer : fs.readFileSync(invoer, 'utf8'));
const base = cfg.url.replace(/\/$/, '');

const HAAK = `(() => {
  if (window.__b03) return;
  window.__b03 = { events: [] };
  for (const ev of ['loadedmetadata', 'playing', 'error', 'waiting', 'stalled', 'ended']) {
    document.addEventListener(ev, (e) => {
      const t = e.target;
      if (t && (t.tagName === 'VIDEO' || t.tagName === 'AUDIO')) {
        window.__b03.events.push({ ev, t: performance.now(), ct: t.currentTime, err: t.error ? t.error.code : null });
      }
    }, true);
  }
})();`;

async function login(page) {
  await page.goto(base + '/web/', { waitUntil: 'domcontentloaded' });
  // Wachten tot het inlogveld óf de knop 'handmatig inloggen' echt zichtbaar is (niet alleen in de DOM).
  await page.waitForFunction(() => {
    const zichtbaar = (e) => !!e && e.offsetParent !== null;
    return zichtbaar(document.querySelector('#txtManualName')) || [...document.querySelectorAll('.btnManual')].some(zichtbaar);
  }, null, { timeout: 60000 });
  if (!(await page.locator('#txtManualName').isVisible().catch(() => false))) {
    // Gebruikerstegels zichtbaar: 'handmatig aanmelden'. Valt de Playwright-klik (animatie/stabiliteit) uit, dan een DOM-klik.
    await page.locator('.btnManual').filter({ visible: true }).first().click({ timeout: 8000 }).catch(() =>
      page.evaluate(() => [...document.querySelectorAll('.btnManual')].find((e) => e.offsetParent !== null)?.click()));
  }
  await page.locator('#txtManualName').waitFor({ state: 'visible', timeout: 20000 });
  await page.locator('#txtManualName').fill(cfg.gebruiker);
  await page.locator('#txtManualPassword').fill(cfg.wachtwoord);
  const verstuur = page.locator('.manualLoginForm button[type=submit]').filter({ visible: true }).first();
  if (await verstuur.count()) await verstuur.click({ timeout: 10000 }).catch(() => page.locator('#txtManualPassword').press('Enter'));
  else await page.locator('#txtManualPassword').press('Enter');
  await page.waitForFunction(() => {
    try { return JSON.parse(localStorage.getItem('jellyfin_credentials') || '{}').Servers?.some((s) => s.AccessToken); } catch { return false; }
  }, null, { timeout: 30000 });
}

async function stopEncodering(page, playSessionId) {
  if (!playSessionId) return null;
  return page.evaluate(async (psid) => {
    try {
      const creds = JSON.parse(localStorage.getItem('jellyfin_credentials'));
      const token = creds.Servers.find((s) => s.AccessToken).AccessToken;
      const dev = localStorage.getItem('_deviceId2') || '';
      const auth = `MediaBrowser Client="Jellyfin Web", Device="b03", DeviceId="${dev}", Version="0", Token="${token}"`;
      const r = await fetch(`/Videos/ActiveEncodings?deviceId=${encodeURIComponent(dev)}&playSessionId=${encodeURIComponent(psid)}`,
        { method: 'DELETE', headers: { Authorization: auth } });
      return r.status;
    } catch (e) { return String(e); }
  }, playSessionId);
}

async function speelItem(page, item, opts) {
  const vang = { profiel: null, antwoord: null, hls: false, statisch: false };
  const opVerzoek = (r) => {
    const u = r.url();
    if (r.method() === 'POST' && /\/Items\/[0-9a-f]+\/PlaybackInfo/i.test(u) && !vang.profiel) {
      try { vang.profiel = r.postDataJSON()?.DeviceProfile ?? null; } catch { /* geen JSON */ }
    }
    if (/\.m3u8/i.test(u)) vang.hls = true;
    if (/\/(Videos|Audio)\/[0-9a-f]+\/stream/i.test(u) && /static=true/i.test(u)) vang.statisch = true;
  };
  const opAntwoord = async (r) => {
    if (/\/Items\/[0-9a-f]+\/PlaybackInfo/i.test(r.url()) && !vang.antwoord) {
      try { vang.antwoord = await r.json(); } catch { /* leeg */ }
    }
  };
  page.on('request', opVerzoek);
  page.on('response', opAntwoord);
  const res = { id: item.id, naam: item.naam };
  try {
    const knop = page.locator('.mainDetailButtons .btnPlay, button.btnPlay, [data-action="resume"], [data-action="play"]')
      .filter({ visible: true }).first();
    // De tv-layout (webOS/Tizen-UA) negeert soms een hash-navigatie vlak na het inloggen: dan opnieuw via location.hash.
    for (let poging = 0; ; poging++) {
      if (poging === 0) await page.goto(base + `/web/#/details?id=${item.id}`, { waitUntil: 'domcontentloaded' });
      else await page.evaluate((id) => { location.hash = `#/details?id=${id}`; }, item.id);
      try { await knop.waitFor({ state: 'visible', timeout: poging < 2 ? 10000 : 30000 }); break; } catch (e) { if (poging >= 2) throw e; }
    }
    // Klikken met herhaling: vlak na een scan kan de detailpagina nog opnieuw renderen (knop niet 'stabiel').
    for (let poging = 0; ; poging++) {
      await page.evaluate(() => { window.__b03.events = []; window.__b03.klik = performance.now(); });
      try { await knop.click({ timeout: 10000, force: poging >= 2 }); break; } catch (e) {
        if (poging >= 2) throw e;
        await page.waitForTimeout(1500);
      }
    }
    const spoor = [];
    const t0 = Date.now();
    let ok = false;
    while (Date.now() - t0 < opts.orakelMs) {
      const s = await page.evaluate(() => {
        const v = document.querySelector('video');
        return v ? { ct: v.currentTime, w: v.videoWidth, rs: v.readyState, err: v.error ? v.error.code : null, p: v.paused,
          ab: v.webkitAudioDecodedByteCount ?? null, ma: v.mozHasAudio ?? null, t: performance.now() - window.__b03.klik } : null;
      });
      if (s) spoor.push(s);
      if (s && s.ct >= 2 && s.w > 0 && !s.err) { ok = true; break; }
      await page.waitForTimeout(100);
    }
    if (ok && opts.duurMs > 0) {
      const tEind = Date.now() + opts.duurMs;
      while (Date.now() < tEind) {
        const s = await page.evaluate(() => { const v = document.querySelector('video');
          return v ? { ct: v.currentTime, w: v.videoWidth, rs: v.readyState, err: v.error ? v.error.code : null, p: v.paused,
            t: performance.now() - window.__b03.klik } : null; });
        if (s) spoor.push(s);
        await page.waitForTimeout(250);
      }
    }
    const ev = await page.evaluate(() => window.__b03.events);
    const playing = ev.find((e) => e.ev === 'playing');
    const klik = await page.evaluate(() => window.__b03.klik);
    const ms = vang.antwoord?.MediaSources?.[0] ?? {};
    const tu = ms.TranscodingUrl || '';
    const heeftAudio = (ms.MediaStreams || []).some((x) => x.Type === 'Audio');
    const l = spoor[spoor.length - 1] ?? {};
    // Orakel (F5 K1): ook stilte bij een item met audio telt als falen (Chromium/WebKit: gedecodeerde audiobytes; Firefox: mozHasAudio).
    res.heeft_audio = heeftAudio;
    res.audio_gedecodeerd = !heeftAudio ? null : (l.ab != null ? l.ab > 0 : l.ma != null ? !!l.ma : null);
    if (ok && heeftAudio && res.audio_gedecodeerd === false) { ok = false; res.orakel_reden = 'geen audio gedecodeerd (stil)'; }
    res.besluit = ms.SupportsDirectPlay ? 'DirectPlay' : ms.SupportsDirectStream ? 'DirectStream' : ms.SupportsTranscoding ? 'Transcode' : 'Geen';
    res.redenen = (tu.match(/TranscodeReasons=([^&]*)/) || [])[1] || '';
    res.playSessionId = vang.antwoord?.PlaySessionId ?? null;
    res.hls = vang.hls;
    res.statisch = vang.statisch;
    res.orakel_ok = ok;
    res.eerste_frame_ms = playing ? Math.round(playing.t - klik) : null;
    res.tijd_tot_2s_ms = ok ? Math.round(spoor[spoor.length - 1].t) : null;
    res.laatste = spoor[spoor.length - 1] ?? null;
    res.fouten = ev.filter((e) => e.ev === 'error');
    res.spoor = spoor.filter((_, i) => i % 5 === 0).map((s) => [Math.round(s.t), +s.ct.toFixed(3)]);
    if (opts.metProfiel) res.deviceProfile = vang.profiel;
    if (opts.schermMap) {
      fs.mkdirSync(opts.schermMap, { recursive: true });
      await page.screenshot({ path: path.join(opts.schermMap, `${cfg.label || cfg.browser}-${item.naam || item.id}.png`) });
    }
  } catch (e) {
    res.fout = String(e).slice(0, 400);
    if (opts.schermMap) {
      fs.mkdirSync(opts.schermMap, { recursive: true });
      await page.screenshot({ path: path.join(opts.schermMap, `${cfg.label || cfg.browser}-${item.naam || item.id}-fout.png`) }).catch(() => {});
    }
  } finally {
    page.off('request', opVerzoek);
    page.off('response', opAntwoord);
    res.stop_status = await stopEncodering(page, res.playSessionId).catch(() => null);
    await page.evaluate(() => { const v = document.querySelector('video'); if (v) v.pause(); }).catch(() => {});
    // Volledig herladen (niet alleen de hash): een vastgelopen speler of foutdialoog mag het volgende item niet blokkeren.
    await page.goto('about:blank').catch(() => {});
    await page.goto(base + '/web/#/home', { waitUntil: 'domcontentloaded' }).catch(() => {});
    await page.waitForTimeout(800);
  }
  return res;
}

async function main() {
  const bt = BROWSERS[cfg.browser];
  if (!bt) throw new Error(`onbekende browser ${cfg.browser}`);
  const browser = await bt.launch({ headless: true });
  const uit = { browser: cfg.browser, versie: browser.version(), ua: cfg.ua || null, initScript: cfg.initScript || null, items: [] };
  try {
    const ctx = await browser.newContext({ locale: 'nl-NL', viewport: { width: 1600, height: 900 }, ...(cfg.ua ? { userAgent: cfg.ua } : {}) });
    await ctx.addInitScript(HAAK);
    if (cfg.initScript) await ctx.addInitScript({ path: cfg.initScript });
    if (cfg.localStorage) {
      await ctx.addInitScript((kv) => { for (const [k, v] of Object.entries(kv)) localStorage.setItem(k, v); }, cfg.localStorage);
    }
    const page = await ctx.newPage();
    await login(page);
    uit.ua_effectief = await page.evaluate(() => navigator.userAgent);
    const opts = { orakelMs: cfg.orakelMs ?? 10000, duurMs: opdracht === 'speel' ? (cfg.duurMs ?? 0) : 0,
      metProfiel: opdracht === 'profiel', schermMap: cfg.schermMap };
    for (const item of cfg.items) uit.items.push(await speelItem(page, item, opts));
    if (opdracht === 'profiel') uit.deviceProfile = uit.items.find((i) => i.deviceProfile)?.deviceProfile ?? null;
    await ctx.close();
  } finally {
    await browser.close();
  }
  process.stdout.write(JSON.stringify(uit) + '\n');
}

main().catch((e) => { process.stdout.write(JSON.stringify({ fout: String(e).slice(0, 600) }) + '\n'); process.exit(1); });
