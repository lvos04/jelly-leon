// QtWebEngine 6.4 ondersteunt pagina-CDP. De native speler heeft zijn eigen afspeelklok in het Xvfb-raster.
import { doelen, verbind } from '../desktop/pagina.mjs';

export async function openDesktop(cfg, afsluiten, wachtOp) {
  const ready = [], segmenten = [];
  let autorisatie;
  function gebeurtenis(soort, data) {
    if (soort === 'Network.requestWillBeSent') {
      const r = data.request, url = new URL(r.url);
      if (url.origin !== cfg.desktopUrl) return;
      for (const [naam, waarde] of Object.entries(r.headers)) {
        if (/^(Authorization|X-Emby-Authorization)$/i.test(naam) && /Token="[^"]+"/i.test(waarde)) autorisatie = waarde;
      }
      if (r.method === 'POST' && url.pathname.endsWith('/SyncPlay/Ready') && r.postData) {
        ready.push({ positie_ms: JSON.parse(r.postData).PositionTicks / 10000 });
      }
    } else if (soort === 'Network.responseReceived') {
      if (/\.(ts|m4s)$/i.test(new URL(data.response.url).pathname)) segmenten.push(data.response.status);
    }
  }
  const eerste = await wachtOp(async () => (await doelen(cfg.cdp))[0], 'desktop-CDP niet beschikbaar', 60000);
  let p = await verbind(cfg.cdp, eerste, gebeurtenis);
  afsluiten.push(() => p.sluit());
  if (eerste.url.startsWith('qrc:')) {
    await wachtOp(() => p.evalueer("!!document.getElementById('address')"), 'desktop mist de serverkeuze');
    await p.evalueer(`(() => { const a = document.getElementById('address'); a.value = ${JSON.stringify(cfg.desktopUrl)};
      a.dispatchEvent(new Event('input', {bubbles:true})); document.getElementById('connect-form').requestSubmit(); })()`);
    const web = await wachtOp(async () => (await doelen(cfg.cdp)).find(d => d.url.startsWith(cfg.desktopUrl + '/')),
      'desktop opent de testserver niet');
    if (web.id !== eerste.id) { p.sluit(); p = await verbind(cfg.cdp, web, gebeurtenis); }
  }
  async function klik(selector, groep = '') {
    const pos = await wachtOp(() => p.evalueer(`(() => {
      const e = [...document.querySelectorAll(${JSON.stringify(selector)})].find(e =>
        e.offsetParent && (e.closest('li') || e).textContent.includes(${JSON.stringify(groep)}));
      if (!e) return null;
      e.scrollIntoView({block:'center'}); const r=e.getBoundingClientRect(); return {x:r.x+r.width/2,y:r.y+r.height/2};
    })()`), 'desktopbediening ontbreekt');
    for (const type of ['mousePressed', 'mouseReleased']) {
      await p.stuur('Input.dispatchMouseEvent', { type, ...pos, button: 'left', clickCount: 1 });
    }
  }
  async function login() {
    if (cfg.instellingen) {
      await p.evalueer(`Object.entries(${JSON.stringify(cfg.instellingen)}).forEach(([k,v])=>localStorage.setItem(k,v))`);
      await p.stuur('Page.reload');
    }
    await wachtOp(() => p.evalueer("!!document.querySelector('#txtManualName, .btnManual')"), 'desktop mist de inlogpagina');
    await p.evalueer("if (!document.querySelector('#txtManualName')?.offsetParent) document.querySelector('.btnManual')?.click()");
    await wachtOp(() => p.evalueer("!!document.querySelector('#txtManualName')?.offsetParent"), 'desktop mist het aanmeldformulier');
    const velden = { '#txtManualName': cfg.namen[1], '#txtManualPassword': cfg.wachtwoord };
    await p.evalueer(`(() => {
      if (location.origin !== ${JSON.stringify(cfg.desktopUrl)}) throw Error();
      for(const [k,v] of Object.entries(${JSON.stringify(velden)})){const e=document.querySelector(k);e.value=v;
        for(const t of ['input','change'])e.dispatchEvent(new Event(t,{bubbles:true}));}
    })()`);
    await klik('.manualLoginForm button[type=submit]');
    await wachtOp(() => autorisatie, 'desktop heeft geen ingelogde sessie');
  }
  async function sluitAan(naam) {
    await p.stuur('Page.reload');
    await klik('button[aria-label="SyncPlay"], .headerSyncButton');
    await klik('[role=menu] li button, .actionSheetMenuItem', naam);
  }
  async function api(method, pad) {
    const status = await p.evalueer(`fetch(${JSON.stringify(pad)}, {method:${JSON.stringify(method)}, redirect:'error',
      headers:{Authorization:${JSON.stringify(autorisatie)}}}).then(r=>r.status)`);
    if (status !== 204) throw new Error('desktop-groepsactie geweigerd');
  }
  const toonKlok = html => p.evalueer(`document.open(); document.write(${JSON.stringify(html)}); document.close();`);
  return { ready, segmenten, login, sluitAan, api, toonKlok };
}
