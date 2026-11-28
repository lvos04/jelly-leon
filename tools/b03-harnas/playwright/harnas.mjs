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
import { beeldmetingAfgerond, beoordeling, cpuSeconden, geforceerdeProef, sessieInfo } from './apparaten.mjs';
import path from 'node:path';

const BROWSERS = { chromium, firefox, webkit };
const [, , opdracht, invoer] = process.argv;
const cfg = JSON.parse(invoer && invoer.trim().startsWith('{') ? invoer : fs.readFileSync(invoer === '-' ? 0 : invoer, 'utf8'));
const base = cfg.url.replace(/\/$/, '');

const HAAK = `(() => {
  if (window.__b03) return;
  window.__b03 = { events: [] };
  document.addEventListener('click', () => {
    if (window.__b03.wachtOpKlik) {
      window.__b03.klik = performance.now();
      window.__b03.wachtOpKlik = false;
    }
  }, true);
  for (const ev of ['loadedmetadata', 'playing', 'error', 'waiting', 'stalled', 'ended']) {
    document.addEventListener(ev, (e) => {
      const t = e.target;
      if (t && (t.tagName === 'VIDEO' || t.tagName === 'AUDIO')) {
        window.__b03.events.push({ ev, soort: t.tagName, t: performance.now(), ct: t.currentTime, err: t.error ? t.error.code : null });
      }
    }, true);
  }
})();`;

async function login(page, gebruiker = cfg.gebruiker, wachtwoord = cfg.wachtwoord, server = base) {
  await page.goto(server + '/web/', { waitUntil: 'domcontentloaded' });
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
  await page.locator('#txtManualName').fill(gebruiker);
  await page.locator('#txtManualPassword').fill(wachtwoord);
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
  const vang = { profiel: null, antwoord: null, hls: false, statisch: false, ingebrand: false };
  const isBesluit = (r) => r.method() === 'POST' && new URL(r.url()).pathname.toLowerCase() === `/items/${item.id}/playbackinfo`.toLowerCase();
  let eersteBesluit = null;
  const opVerzoek = (r) => {
    const u = r.url();
    if (isBesluit(r) && !eersteBesluit) {
      eersteBesluit = r;
      try {
        const aanvraag = r.postDataJSON();
        vang.profiel = aanvraag?.DeviceProfile ?? null;
        if (Number.isInteger(aanvraag?.SubtitleStreamIndex) && aanvraag.SubtitleStreamIndex >= 0) vang.subIndex = aanvraag.SubtitleStreamIndex;
      } catch { /* geen JSON */ }
    }
    if (/\.m3u8/i.test(u)) {
      vang.hls = true;
      const q = new URL(u).searchParams;
      if (q.get('SubtitleMethod')?.toLowerCase() === 'encode' && q.has('SubtitleStreamIndex') && Number(q.get('SubtitleStreamIndex')) >= 0) {
        vang.ingebrand = true;
        vang.subIndex = Number(q.get('SubtitleStreamIndex'));
      }
    }
    if (/\/(Videos|Audio)\/[0-9a-f]+\/stream/i.test(u) && /static=true/i.test(u)) vang.statisch = true;
  };
  const opAntwoord = async (r) => {
    if (r.request() === eersteBesluit && r.ok()) {
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
      await page.evaluate(() => { window.__b03.events = []; window.__b03.wachtOpKlik = true; });
      try { await knop.click({ timeout: 10000, force: poging >= 2 }); break; } catch (e) {
        if (poging >= 2) throw e;
        await page.waitForTimeout(1500);
      }
    }
    const spoor = [];
    let ok = false;
    let tot2 = null;
    let herstel = null;
    let vorigeNaFout = null;
    let info = null;
    let cpu0 = null;
    let cpuBegin = null;
    let cpuKernen = null;
    const grens = opts.orakelMs;
    const muurBegin = performance.now();
    let laatsteSessiepeiling = -500;
    while (true) {
      const s = await page.evaluate((grensMs) => {
        const v = document.querySelector('video');
        return { ct: v?.currentTime ?? 0, w: v?.videoWidth ?? 0, rs: v?.readyState ?? 0,
          err: v?.error?.code ?? null, p: v?.paused ?? true, ab: v?.webkitAudioDecodedByteCount ?? null,
          ma: v?.mozHasAudio ?? null, t: performance.now() - window.__b03.klik,
          fout: window.__b03.events.some((e) => e.ev === 'error' && e.t - window.__b03.klik <= grensMs) };
      }, grens);
      if (!Number.isFinite(s.t) || performance.now() - muurBegin > Math.max(grens, 60000) + 5000) {
        throw new Error('Klik of meetklok ontbreekt');
      }
      spoor.push(s);
      const dp = vang.antwoord?.MediaSources?.[0]?.SupportsDirectPlay;
      if (opts.apparaten && vang.hls && !info && s.t - laatsteSessiepeiling >= 500) {
        laatsteSessiepeiling = s.t;
        info = await sessieInfo(page, item.id);
        if (info?.video_direct === false) {
          cpu0 = cpuSeconden(cfg.containerId);
          cpuBegin = performance.now();
        }
      }
      const metAudio = vang.antwoord?.MediaSources?.[0]?.MediaStreams?.some((x) => x.Type === 'Audio');
      const decodeOntbreekt = metAudio && (s.ab === 0 || s.ma === false);
      if (s.fout || (dp && vang.hls)) {
        ok = false;
        tot2 = null;
      }
      if (tot2 === null && !decodeOntbreekt && beoordeling(s, grens, s.fout, dp && vang.hls)) {
        tot2 = Math.round(s.t);
        ok = true;
      }
      // Voor een video-encode nog een actief venster bemonsteren. Niet de inlogtijd of de geforceerde proef meerekenen.
      if (cpuBegin !== null && cpuKernen === null && performance.now() - cpuBegin >= 1000) {
        const einde = cpuSeconden(cfg.containerId);
        const nu = await sessieInfo(page, item.id);
        if (cpu0 !== null && einde !== null && nu?.video_direct === false) cpuKernen = (einde - cpu0) * 1000 / (performance.now() - cpuBegin);
      }
      if (beeldmetingAfgerond(ok, s.t, grens, opts.apparaten)) break;
      if (opts.apparaten && dp && !ok && (s.fout || vang.hls || s.t >= grens)) {
        // Twee opeenvolgende waarnemingen ná de mislukte start bewijzen dat het herstelde beeld vooruitgaat.
        if (vorigeNaFout && s.t <= 60000 && !s.p && !s.err && s.w > 0 && s.ct > vorigeNaFout.ct) {
          herstel = Math.round(s.t);
          break;
        }
        vorigeNaFout = s;
        if (s.t >= 60000) break;
      } else if (s.t >= grens) break;
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
    const playing = ev.find((e) => e.ev === 'playing' && e.soort === 'VIDEO');
    const klik = await page.evaluate(() => window.__b03.klik);
    const ms = vang.antwoord?.MediaSources?.[0] ?? {};
    const tu = ms.TranscodingUrl || '';
    const heeftAudio = (ms.MediaStreams || []).some((x) => x.Type === 'Audio');
    const l = spoor[spoor.length - 1] ?? {};
    res.heeft_audio = heeftAudio;
    res.audio_gedecodeerd = !heeftAudio ? null : (l.ab != null ? l.ab > 0 : l.ma != null ? !!l.ma : null);
    res.audio_niet_stil = 'niet gemeten';
    if (!ok && l.ct >= 2 && l.w > 0 && !l.err && heeftAudio && res.audio_gedecodeerd === false) {
      // Bestaande clientmatrix gebruikt dit label voor een ontbrekende decoder op de CI-runner.
      res.orakel_reden = 'geen audio gedecodeerd (stil)';
    }
    res.besluit_gemeten = !!vang.antwoord?.MediaSources?.length;
    if (opts.apparaten) {
      const video = (ms.MediaStreams || []).find((x) => x.Type === 'Video');
      const ot = (ms.MediaStreams || []).find((x) => x.Type === 'Subtitle' && x.Index === (vang.subIndex ?? ms.DefaultSubtitleStreamIndex));
      res.videobereik = video?.VideoRangeType ?? video?.VideoRange ?? null;
      res.herstel_ms = herstel;
      res.transcoding_info = info;
      res.cpu_kernen = cpuKernen;
      res.ingebrand = vang.ingebrand;
      res.foutmiddel_actief = await page.evaluate(() => Array.isArray(window.__b03_liegt) && window.__b03_liegt.length > 0);
      res.ondertitel = ot?.Codec ?? null;
      const formaat = (naam) => ({ subrip: 'srt', webvtt: 'vtt' }[naam?.toLowerCase()] ?? naam?.toLowerCase());
      res.extern_mogelijk = !!ot && !!vang.profiel?.SubtitleProfiles?.some((x) =>
        formaat(x.Format) === formaat(ot.Codec) && x.Method === 'External');
    }
    res.besluit = ms.SupportsDirectPlay ? 'DirectPlay' : ms.SupportsDirectStream ? 'DirectStream' : ms.SupportsTranscoding ? 'Transcode' : 'Geen';
    res.redenen = (tu.match(/TranscodeReasons=([^&]*)/) || [])[1] || '';
    res.playSessionId = vang.antwoord?.PlaySessionId ?? null;
    res.hls = vang.hls;
    res.statisch = vang.statisch;
    res.orakel_ok = ok && !ev.some((e) => e.ev === 'error' && e.t - klik <= opts.orakelMs);
    res.eerste_frame_ms = playing ? Math.round(playing.t - klik) : null;
    res.tijd_tot_2s_ms = res.orakel_ok ? tot2 : null;
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
    // Een gecrashte afspeelpagina heeft al een fout op de meetrij. Behoud die rij voor de clientmatrix.
    await page.waitForTimeout(800).catch(() => {});
  }
  return res;
}

async function main() {
  if (['watchtogether', 'watchklok', 'watchfunctie', 'watchandroid'].includes(opdracht)) {
    const { meet } = await import('./watchtogether.mjs');
    const resultaat = await meet(opdracht, cfg, login);
    process.stdout.write(JSON.stringify(resultaat) + '\n');
    return;
  }
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
    if (opdracht === 'homescherm') {
      const secties = page.locator('.homeSectionsContainer:visible .verticalSection');
      await secties.first().waitFor({ state: 'attached' });
      const layout = await page.evaluate(() => localStorage.getItem('layout'));
      await page.locator('.homeSectionsContainer:visible .card').first().waitFor({ state: 'visible' });
      const modern = (await page.locator('header.MuiAppBar-root').count()) > 0;
      const zichtbaar = modern === (layout === 'modern');
      process.stdout.write(JSON.stringify({ layout, secties: await secties.count(), zichtbaar }) + '\n');
      return;
    }
    const opts = { orakelMs: cfg.orakelMs ?? 10000, duurMs: opdracht === 'speel' ? (cfg.duurMs ?? 0) : 0,
      metProfiel: opdracht === 'profiel', schermMap: cfg.schermMap, apparaten: opdracht === 'apparaten' };
    for (const item of cfg.items) {
      const starts = opts.apparaten ? 2 : 1;
      for (let start = 1; start <= starts; start++) {
        const rij = await speelItem(page, item, opts);
        if (opts.apparaten) {
          rij.start = start;
          if (!rij.fout) rij.geforceerd_ok = await geforceerdeProef(page, item.id);
        }
        uit.items.push(rij);
      }
    }
    if (opdracht === 'profiel') uit.deviceProfile = uit.items.find((i) => i.deviceProfile)?.deviceProfile ?? null;
    await ctx.close();
  } finally {
    await browser.close();
  }
  process.stdout.write(JSON.stringify(uit) + '\n');
}

main().catch((e) => {
  // Playwright-fouten kunnen URL's en ingevulde velden bevatten. Voor deze proef alleen de vaste fasenaam bewaren.
  const fout = opdracht.startsWith('watch') ? 'Watch Together: ' + (e.fase || 'clientproef onderbroken') : String(e).slice(0, 600);
  process.stdout.write(JSON.stringify({ fout }) + '\n');
  process.exit(1);
});
