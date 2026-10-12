// Sample-data stand-in for the desktop bridge, used only when this page is opened in a plain browser
// (no Electron). Lets the screens be reviewed without the engine. The file name picks the scenario:
// a name with "unknown" has no camera profile, "part" gives a partial result, "fail" fails.
if (!window.vr) {
  let timer = null, rejectRepair = null;
  const name = p => p.split(/[\\/]/).pop();
  const frames = n => Array.from({ length: n }, (_, i) => {
    const c = document.createElement('canvas'); c.width = 160; c.height = 90;
    const g = c.getContext('2d'); const grad = g.createLinearGradient(0, 0, 160, 90);
    grad.addColorStop(0, `hsl(${200 + i * 6} 35% ${28 + i * 2}%)`); grad.addColorStop(1, `hsl(${30 + i * 5} 40% ${45 - i}%)`);
    g.fillStyle = grad; g.fillRect(0, 0, 160, 90);
    return { path: c.toDataURL('image/jpeg', 0.7), time: i * 20 };
  });
  const handlers = {
    diagnose: ({ paths }) => ({ files: paths.map(p => {
      const n = name(p), apple = /apple|iphone/i.test(n), dji = !apple && !/unknown/i.test(n);
      return { path: p, name: n, size: 1.4e9, problem: 'no_index', needs_repair: true, camera: apple ? 'Apple' : dji ? 'DJI OsmoAction3' : null,
        profile: dji ? 'DJI Osmo Action 3, 1080p 50fps HEVC' : null,
        summary: 'The video data is there, but the index (moov) is missing. This usually means the camera stopped before it finished saving.' };
    }) }),
    improve: ({ path, reference }) => {
      const dji = !/unknown|apple|iphone/i.test(name(path));
      const base = { camera: dji ? 'DJI OsmoAction3' : null, profile: dji ? 'DJI Osmo Action 3, 1080p 50fps HEVC' : null, reference: null,
        reference_ok: null, reference_message: null, found_automatically: false };
      if (reference) return { ...base, reference: { path: reference, name: name(reference) }, reference_ok: !/bad/i.test(name(reference)),
        reference_message: /bad/i.test(name(reference)) ? 'That clip is damaged too, so it cannot show us how the camera stores video.' : 'Looks good.' };
      return base;
    },
    rebuild_card: () => ({ videos: Array.from({ length: 12 }, (_, i) => ({
      path: `/Users/you/Movies/Repaired/From card/recovered_20260922_06${10 + i * 4}00_c${100 + i}.mp4`,
      name: `recovered_20260922_06${10 + i * 4}00_c${100 + i}.mp4`, size: (300 + i * 90) * 1e6, has_index: i % 5 !== 0, fragments: 3 + i,
      recorded: `2026-09-22T06:${10 + i * 4}:00` })) }),
    thumbs: () => ({ duration: 346, frames: frames(12) }),
  };
  const repair = ({ path }, onProgress) => new Promise((resolve, reject) => {
    rejectRepair = reject; let done = 0; const total = 1.4e9; const n = name(path);
    timer = setInterval(() => {
      done += total / 40; onProgress({ done, total });
      if (done >= total) {
        clearInterval(timer);
        if (/fail/i.test(n)) return resolve({ ok: false, partial: false, output: null, info: {}, needs_repair: true, summary: '',
          attempts: [{ strategy: 'untrunc', ok: false, partial: false, message: 'no reference clip from the same camera was found' },
                     { strategy: 'carve', ok: false, partial: false, message: 'no camera profile or reference clip available' }] });
        const partial = /part/i.test(n);
        resolve({ ok: true, partial, output: '/Users/you/Movies/Repaired/' + n.replace(/\.\w+$/, '') + '_repaired.mp4', needs_repair: true, summary: '',
          info: { width: 1920, height: 1080, fps: 50, duration: partial ? 135 : 346, size: partial ? 836e6 : 1.4e9 },
          attempts: [{ strategy: 'carve', ok: !partial, partial, message: partial
            ? '12,847 frames recovered in 3 pieces using camera profile \'DJI Osmo Action 3, 1080p 50fps HEVC\' (video only, no audio), but the result has 195 decoding errors in its first 30 seconds'
            : '17,300 frames recovered using camera profile \'DJI Osmo Action 3, 1080p 50fps HEVC\' (video only, no audio)' }] });
      }
    }, 90);
  });
  const cardScan = ({ }, onProgress) => new Promise(resolve => {
    let i = 0; const t = setInterval(() => {
      i++; onProgress({ phase: i <= 5 ? 'scan' : 'rebuild', done: i <= 5 ? i * 100 : i - 5, total: i <= 5 ? 500 : 20 });
      if (i >= 25) { clearInterval(t); resolve(handlers.rebuild_card()); }
    }, 120); timer = t;
  });
  window.vr = {
    mode: 'preview',
    engine: (cmd, payload, onProgress) => cmd === 'repair' ? repair(payload, onProgress)
      : cmd === 'rebuild_card' ? cardScan(payload, onProgress)
      : new Promise(r => setTimeout(() => r(handlers[cmd](payload)), 350)),
    cancel: async () => { clearInterval(timer); if (rejectRepair) rejectRepair(new Error('cancelled')); },
    chooseFiles: () => new Promise(resolve => {
      const i = document.createElement('input'); i.type = 'file'; i.multiple = true;
      i.onchange = () => resolve([...i.files].map(f => '/Volumes/CARD/' + f.name)); i.oncancel = () => resolve([]); i.click();
    }),
    chooseImage: async () => '/Volumes/CARD/sd_image.dd',
    chooseFolder: async () => '/Users/you/Desktop/Repaired',
    defaultOutDir: async () => '/Users/you/Movies/Repaired',
    showInFolder: async () => {}, openPath: async () => {},
    pathFor: f => '/Volumes/CARD/' + f.name,
    fileUrl: p => p,
  };
}
