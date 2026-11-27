// De browserklok begint bij de afspeelklik. Ook een error van een inmiddels vervangen videospeler telt.
import fs from 'node:fs';

export function beoordeling(s, grensMs, fout, teruggevallen = false) {
  return !!s && s.t >= 0 && s.t <= grensMs && s.ct >= 2 && s.w > 0 && !s.p && !s.err && !fout && !teruggevallen;
}

export function cpuSeconden(id) {
  if (!id || !/^[a-f0-9]{64}$/.test(id)) return null;
  for (const dir of [`system.slice/docker-${id}.scope`, `docker/${id}`]) {
    try {
      const regel = fs.readFileSync(`/sys/fs/cgroup/${dir}/cpu.stat`, 'ascii').match(/^usage_usec (\d+)$/m);
      if (regel) return Number(regel[1]) / 1e6;
    } catch { /* Andere cgroup-indeling of geen toegang. */ }
  }
  return null;
}

export async function sessieInfo(page, itemId) {
  return page.evaluate(async (id) => {
    const server = JSON.parse(localStorage.getItem('jellyfin_credentials')).Servers.find((s) => s.AccessToken);
    const device = localStorage.getItem('_deviceId2');
    const r = await fetch('/Sessions', { headers: { Authorization: `MediaBrowser Token="${server.AccessToken}"` } });
    if (!r.ok) throw new Error('Sessiemeting gaf HTTP ' + r.status);
    const sessie = (await r.json()).find((s) => s.NowPlayingItem?.Id === id && s.DeviceId === device);
    const info = sessie?.TranscodingInfo;
    return info ? { video_direct: info.IsVideoDirect, hardware: info.HardwareAccelerationType ?? null,
      frames_per_s: info.Framerate ?? null } : null;
  }, itemId);
}

// Een afzonderlijk video-element op dezelfde testserver. Alleen het statische bronbestand mag worden opgevraagd.
export async function geforceerdeProef(page, itemId) {
  const pad = `/Videos/${itemId}/stream`;
  const bron = new URL(pad, page.url());
  bron.searchParams.set('static', 'true');
  bron.searchParams.set('MediaSourceId', itemId);
  const token = await page.evaluate(() => JSON.parse(localStorage.getItem('jellyfin_credentials')).Servers.find((s) => s.AccessToken).AccessToken);
  const auth = (route) => route.continue({ headers: { ...route.request().headers(), Authorization: `MediaBrowser Token="${token}"` } });
  let status = null;
  const opAntwoord = (r) => {
    if (r.url() === bron.href && r.request().method() === 'GET') status = r.status();
  };
  await page.route(bron.href, auth);
  page.on('response', opAntwoord);
  try {
    const speelt = await page.evaluate(async (url) => {
      const v = document.createElement('video');
      v.muted = true;
      document.body.append(v);
      let fout = false;
      v.addEventListener('error', () => { fout = true; });
      const begin = performance.now();
      try {
        v.src = url;
        v.play().catch(() => { fout = true; });
        while (performance.now() - begin <= 10000) {
          if (fout || v.error) break;
          if (!v.paused && v.currentTime >= 2 && v.videoWidth > 0) return true;
          await new Promise((r) => setTimeout(r, 100));
        }
        return false;
      } finally {
        v.pause();
        v.removeAttribute('src');
        v.load();
        v.remove();
      }
    }, bron.href);
    if (status !== 200 && status !== 206) throw new Error('Statische bron niet geleverd, HTTP ' + (status ?? 'onbekend'));
    return speelt;
  } finally {
    page.off('response', opAntwoord);
    await page.unroute(bron.href, auth);
  }
}
