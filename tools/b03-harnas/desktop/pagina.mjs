// Gedeelde ruwe pagina-CDP voor QtWebEngine onder Xvfb.
export async function doelen(cdp) {
  try {
    const r = await fetch(cdp + '/json/list', { redirect: 'error', signal: AbortSignal.timeout(2000) });
    return (await r.json()).filter((d) => d.type === 'page');
  } catch { return []; } // Xvfb en Qt zijn nog aan het starten.
}

export async function verbind(cdp, doel, gebeurtenis) {
  if (!/^[\w-]+$/.test(doel.id)) throw new Error('ongeldig CDP-paginadoel');
  const ws = new WebSocket(cdp.replace(/^http:/, 'ws:') + '/devtools/page/' + doel.id);
  const wachtend = new Map();
  let id = 0;
  function sluit() {
    for (const vraag of wachtend.values()) {
      clearTimeout(vraag.timer);
      vraag.weiger(new Error('CDP-pagina gesloten'));
    }
    wachtend.clear();
    ws.close();
  }
  ws.onclose = sluit;
  ws.onmessage = ({ data }) => {
    const d = JSON.parse(data);
    const vraag = wachtend.get(d.id);
    if (vraag) {
      clearTimeout(vraag.timer);
      wachtend.delete(d.id);
      if (d.error) vraag.weiger(new Error('CDP-opdracht geweigerd: ' + vraag.method));
      else vraag.klaar(d.result);
    } else if (d.method) gebeurtenis(d.method, d.params);
  };
  try {
    await new Promise((klaar, weiger) => {
      const timer = setTimeout(() => weiger(new Error('CDP-verbinding liep vast')), 10000);
      ws.onopen = () => { clearTimeout(timer); klaar(); };
      ws.onerror = () => { clearTimeout(timer); weiger(new Error('CDP-verbinding mislukt')); };
    });
    function stuur(method, params = {}) {
      return new Promise((klaar, weiger) => {
        const nummer = ++id;
        const timer = setTimeout(() => {
          wachtend.delete(nummer);
          weiger(new Error('CDP-time-out: ' + method));
        }, 10000);
        wachtend.set(nummer, { method, timer, klaar, weiger });
        try { ws.send(JSON.stringify({ id: nummer, method, params })); }
        catch { sluit(); }
      });
    }
    async function evalueer(expression) {
      const r = await stuur('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
      if (r.exceptionDetails) throw new Error('pagina kon de UI-opdracht niet uitvoeren');
      return r.result?.value;
    }
    await stuur('Runtime.enable');
    await stuur('Log.enable');
    await stuur('Network.enable', { maxPostDataSize: 65536 });
    return { stuur, evalueer, sluit };
  } catch (fout) { sluit(); throw fout; }
}
