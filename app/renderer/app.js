// HealVideo window. Four steps: Add, Improve, Repair, Done.
// All work is done by the engine through window.vr (see preload.js). This file only draws screens.
(() => {
  const vr = window.vr;
  const $ = s => document.querySelector(s);
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const icon = n => window.ICONS[n] || '';
  const fmtSize = b => !b ? '' : b >= 1e9 ? (b / 1e9).toFixed(1) + ' GB' : (b / 1e6).toFixed(b >= 1e8 ? 0 : 1) + ' MB';
  const fmtTime = s => { s = Math.round(s || 0); return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0'); };
  const sentence = t => { t = String(t || '').trim(); return t ? t[0].toUpperCase() + t.slice(1) + (/[.!?]$/.test(t) ? '' : '.') : ''; };
  const CELLS = 12;

  const STEPS = [['add', 'Add'], ['improve', 'Improve'], ['repair', 'Repair'], ['done', 'Done']];
  const REPAIRABLE = ['no_index', 'cut_off'];
  const S = { step: 'add', card: null, keep: null, files: [], reading: 0, improve: null, outDir: '', results: [], sel: 0, current: 0, progress: null, cancelled: false };

  const repairable = () => S.files.filter(f => REPAIRABLE.includes(f.problem));
  const pl = (n, w) => `${n} ${w}${n === 1 ? '' : 's'}`;
  const deviceOf = f => f.camera || 'an unknown camera';

  // Videos from different cameras can't share settings, so we repair one camera's videos at a time:
  // the largest group by default (the first one added, if tied). The user can switch groups.
  function groups() {
    const out = [];
    for (const f of repairable()) {
      const key = deviceOf(f);
      let g = out.find(x => x.key === key);
      if (!g) out.push(g = { key, files: [] });
      g.files.push(f);
    }
    return out;
  }
  function keepKey() {
    const gs = groups();
    if (S.keep && gs.some(g => g.key === S.keep)) return S.keep;
    return gs.reduce((best, g) => (!best || g.files.length > best.files.length ? g : best), null)?.key;
  }
  const active = () => repairable().filter(f => deviceOf(f) === keepKey());
  const skipped = () => repairable().filter(f => deviceOf(f) !== keepKey());
  const cells = (n, on = 0) => Array.from({ length: n }, (_, i) => `<div class="cell${i < on ? ' on' : ''}"></div>`).join('');

  // ---------- Add ----------
  async function addPaths(paths) {
    paths = paths.filter(p => p && !S.files.some(f => f.path === p));
    if (!paths.length) return;
    S.reading++; render();
    try {
      const r = await vr.engine('diagnose', { paths });
      S.files.push(...r.files);
    } catch (e) {
      S.files.push(...paths.map(p => ({ path: p, name: p.split(/[\\/]/).pop(), problem: 'unreadable', needs_repair: false, summary: e.message })));
    }
    S.reading--; render();
  }

  function viewAdd() {
    const head = `<h1>Fix a video that won’t play</h1>
      <p class="lede">Add the broken file. We’ll tell you what’s wrong and save a repaired copy. The original is never changed.</p>`;
    if (!S.files.length && !S.reading) {
      return head + `<button class="drop" data-act="choose" aria-label="Choose video files">${icon('film-strip')}
        <strong>Drop videos here</strong><span class="muted">or choose files. MP4 and MOV.</span></button>
        <p class="alt muted small">Lost videos from a memory card? <button class="btn quiet" data-act="card">Recover from a card image</button></p>`;
    }
    const seen = new Set();
    const rows = S.files.map((f, i) => {
      const ok = f.problem === 'healthy', can = REPAIRABLE.includes(f.problem);
      const skip = can && deviceOf(f) !== keepKey();
      const finding = skip ? `Skipped. This video is from ${deviceOf(f)}, not ${keepKey()}.` : ok ? 'This video plays fine, so it doesn’t need repair.' : f.summary;
      const same = !ok && !skip && seen.has(finding);
      seen.add(finding);
      const cls = ok ? 'ok' : can && !skip ? '' : skip ? 'skipped' : 'bad';
      return `<li class="file${skip ? ' skipped' : ''}">${icon('file-video')}
        <div><div class="name">${esc(f.name)}</div>
          <div class="meta mono">${[fmtSize(f.size), f.camera].filter(Boolean).map(esc).join('   ')}</div>
          <div class="finding ${cls}">${same ? 'Same problem as above.' : esc(finding)}</div></div>
        <button class="icon-btn" data-act="remove" data-i="${i}" aria-label="Remove ${esc(f.name)}">${icon('x')}</button></li>`;
    }).join('');
    const reading = S.reading ? `<li class="file"><span></span><div class="reading">Looking at the file</div><span></span></li>` : '';
    return head + mixedNotice() + `<ul class="files">${rows}${reading}</ul>
      <div class="actions"><button class="btn" data-act="choose">Add more</button><span class="grow"></span>
        <button class="btn primary" data-act="next" ${active().length && !S.reading ? '' : 'disabled'}>Continue</button></div>`;
  }

  function mixedNotice() {
    const gs = groups();
    if (gs.length < 2) return '';
    const keep = keepKey(), kept = active().length, others = skipped();
    const names = [...new Set(others.map(deviceOf))].join(' and ');
    const switches = gs.map((g, i) => g.key === keep ? '' :
      `<button class="btn" data-act="keep" data-i="${i}">Repair the ${pl(g.files.length, 'video')} from ${esc(g.key)} instead</button>`).join('');
    return `<div class="note warn"><div class="head">${icon('warning')}These videos are from different cameras</div>
      <p>We’ll repair the ${pl(kept, 'video')} from ${esc(keep)} and skip the ${others.length} from ${esc(names)}. Each camera stores video differently, so they need to be repaired separately.</p>
      <div class="row">${switches}</div></div>`;
  }

  // ---------- Memory card image ----------
  const cardOut = () => S.outDir + (S.outDir.includes('\\') ? '\\' : '/') + 'From card';

  async function pickImage() {
    const image = await vr.chooseImage();
    if (!image) return;
    S.card = { phase: 'scanning', image, progress: null };
    render();
    try {
      const r = await vr.engine('rebuild_card', { image, out_dir: cardOut() }, m => { if (S.card) { S.card.progress = m; paintCard(); } });
      S.card = { phase: 'done', image, videos: r.videos };
    } catch (e) {
      if (!S.card || S.card.phase !== 'scanning') return; // cancelled
      S.card = { phase: 'error', error: e.message };
    }
    render();
  }

  async function repairFromCard() {
    const paths = S.card.videos.filter(v => !v.has_index).map(v => v.path);
    const r = await vr.engine('diagnose', { paths });
    S.files = r.files; S.keep = null; S.card = null;
    goImprove();
  }

  function viewCard() {
    const c = S.card;
    if (c.phase === 'scanning') {
      return `<h1>Reading the card image</h1>
        <p class="lede">This can take a while for a large card. Keep this window open.</p>
        <div class="film" role="progressbar" aria-label="Progress" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0" id="film">
          <div class="cells" id="cells">${cells(CELLS)}</div></div>
        <div class="progress-line"><span id="stage">Looking for videos</span><span class="mono" id="amount"></span></div>
        <div class="actions"><button class="btn" data-act="cardcancel">Cancel</button></div>`;
    }
    if (c.phase === 'error') {
      return `<h1>We couldn’t read that file</h1>
        <div class="note bad"><div class="head">${icon('warning-circle')}Something went wrong</div><p>${esc(sentence(c.error))}</p></div>
        <div class="actions"><button class="btn primary" data-act="card">Choose another image</button><span class="grow"></span>
          <button class="btn quiet" data-act="cardback">Back</button></div>`;
    }
    if (c.phase === 'done') {
      const v = c.videos, need = v.filter(x => !x.has_index);
      const when = x => x.recorded ? new Date(x.recorded).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }) : 'Unknown time';
      const rows = v.map(x => `<li><span>${esc(when(x))}</span><span class="mono">${esc(fmtSize(x.size))}</span>
        <span class="${x.has_index ? 'st ok' : 'st warn'}">${x.has_index ? 'Complete' : 'Needs repair'}</span></li>`).join('');
      return `<h1>${v.length ? `Found ${pl(v.length, 'video')}` : 'No videos found'}</h1>
        <p class="lede">${v.length ? `${pl(v.length - need.length, 'video')} ${v.length - need.length === 1 ? 'came' : 'came'} back complete${need.length ? `, and ${need.length} still ${need.length === 1 ? 'needs' : 'need'} repair` : ''}. We saved ${v.length === 1 ? 'it' : 'them'} to ${esc(cardOut())}.`
          : 'We couldn’t find the start of any video on this card image. If the card was formatted or heavily overwritten, this tool can’t bring the videos back.'}</p>
        ${v.length ? `<ul class="vlist">${rows}</ul>` : ''}
        <div class="actions">${v.length ? `<button class="btn ${need.length ? '' : 'primary'}" data-act="cardreveal">${icon('folder-open')}Show in folder</button>` : ''}
          ${need.length ? `<button class="btn primary" data-act="cardrepair">Repair the ${need.length}</button>` : ''}
          <span class="grow"></span><button class="btn quiet" data-act="cardback">Start over</button></div>`;
    }
    return `<h1>Recover videos from a card image</h1>
      <p class="lede">A card image is a complete copy of your memory card, saved as one file. We read it, find the videos and put their scattered pieces back in order.</p>
      <button class="drop" data-act="pickimage" aria-label="Choose a card image">${icon('file-video')}
        <strong>Choose a card image</strong><span class="muted">A .img or .dd file. exFAT cards only for now.</span></button>
      <p class="muted small gap-top">Make the image first with a disk-imaging tool such as ddrescue. Working from an image keeps the card itself safe.</p>
      <div class="actions"><button class="btn quiet" data-act="cardback">Back</button></div>`;
  }

  function paintCard() {
    const p = S.card && S.card.progress, film = $('#film');
    if (!p || !film || !p.total) return;
    const scan = p.phase === 'scan';
    const frac = Math.min(1, scan ? 0.2 * p.done / p.total : 0.2 + 0.8 * p.done / p.total);
    document.querySelectorAll('#cells .cell').forEach((c, i) => c.classList.toggle('on', i < Math.floor(frac * CELLS)));
    film.setAttribute('aria-valuenow', Math.round(frac * 100));
    $('#stage').textContent = scan ? 'Looking for videos' : `Putting video ${Math.min(p.done + 1, p.total)} of ${p.total} back together`;
    $('#amount').textContent = scan ? '' : `${p.done} of ${p.total} done`;
  }

  // ---------- Improve ----------
  async function goImprove() {
    S.step = 'improve'; S.improve = null; render();
    const first = active()[0];
    if (!first) return;
    try { S.improve = await vr.engine('improve', { path: first.path }); }
    catch (e) { S.improve = { error: e.message }; }
    render();
  }

  async function chooseClip() {
    const [p] = await vr.chooseFiles();
    const first = active()[0];
    if (!p || !first) return;
    try { S.improve = await vr.engine('improve', { path: first.path, reference: p }); }
    catch (e) { S.improve = { error: e.message }; }
    render();
  }

  function viewImprove() {
    const im = S.improve;
    let body = '';
    if (!im) body = `<p class="reading">Checking what we know about your camera</p>`;
    else if (im.error) body = `<div class="note bad"><div class="head">${icon('warning-circle')}Something went wrong</div><p>${esc(im.error)}</p></div>`;
    else {
      if (im.profile) body += `<div class="note"><div class="head">${icon('check-circle')}We know this camera</div>
        <p>${esc(im.profile)}. Adding a clip is optional.</p></div>`;
      if (im.reference) {
        const good = im.reference_ok;
        body += `<div class="note ${good ? '' : 'warn'}"><div class="head">${icon(good ? 'check-circle' : 'warning')}${good ? 'Using ' : 'Can’t use '}${esc(im.reference.name)}</div>
          <p>${esc(im.reference_message || '')}</p><div class="row"><button class="btn" data-act="clip">Choose a different clip</button></div></div>`;
      } else {
        body += `<div class="lone"><button class="btn" data-act="clip">${icon('video-camera')}Choose a clip</button></div>`;
        if (!im.profile) body += `<div class="note warn"><div class="head">${icon('warning')}No clip? We’ll try anyway</div>
          <p>We can’t promise the result without one.</p></div>`;
      }
    }
    return `<h1>Add a clip from the same camera</h1>
      <p class="lede">A clip recorded on the same camera with the same settings gives the best result. It shows us how your camera stores video.</p>
      ${body}
      <div class="where"><span>Repaired copies are saved to</span><span class="mono">${esc(S.outDir)}</span><button class="btn quiet" data-act="folder">Change</button></div>
      <div class="actions"><button class="btn quiet" data-act="back">Back</button><span class="grow"></span>
        <button class="btn primary" data-act="start" ${im && !im.error ? '' : 'disabled'}>Start repair</button></div>`;
  }

  // ---------- Repair ----------
  async function startRepair() {
    const todo = active();
    S.step = 'repair'; S.results = []; S.cancelled = false; S.sel = 0; S.skippedAtStart = skipped().length;
    const ref = S.improve && S.improve.reference && S.improve.reference_ok ? S.improve.reference.path : undefined;
    for (let i = 0; i < todo.length; i++) {
      S.current = i; S.progress = null; render();
      const f = todo[i];
      let res;
      try {
        res = { file: f, ...(await vr.engine('repair', { path: f.path, out_dir: S.outDir, reference: ref }, m => { S.progress = m; paintProgress(); })) };
        if (res.output) {
          try { res.thumbs = (await vr.engine('thumbs', { path: res.output, count: CELLS })).frames; } catch { res.thumbs = []; }
        }
      } catch (e) {
        if (S.cancelled || e.message === 'cancelled') return;
        res = { file: f, ok: false, error: e.message };
      }
      S.results.push(res);
    }
    S.step = 'done'; S.sel = 0; render();
  }

  function viewRepair() {
    const todo = active();
    const many = todo.length > 1;
    return `<h1>${many ? `Repairing video ${S.current + 1} of ${todo.length}` : 'Repairing your video'}</h1>
      <p class="lede">${esc(todo[S.current].name)}. Large files can take a few minutes. Keep this window open.</p>
      <div class="film" role="progressbar" aria-label="Repair progress" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0" id="film">
        <div class="cells" id="cells">${cells(CELLS)}</div></div>
      <div class="progress-line"><span id="stage">Looking at the file</span><span class="mono" id="amount"></span></div>
      <div class="actions"><button class="btn" data-act="cancel">Cancel</button></div>`;
  }

  function paintProgress() {
    const p = S.progress, film = $('#film');
    if (!p || !film || !p.total) return;
    const frac = Math.min(1, p.done / p.total);
    const on = Math.floor(frac * CELLS);
    document.querySelectorAll('#cells .cell').forEach((c, i) => c.classList.toggle('on', i < on));
    film.setAttribute('aria-valuenow', Math.round(frac * 100));
    $('#stage').textContent = 'Putting the video back together';
    $('#amount').textContent = `${fmtSize(p.done)} of ${fmtSize(p.total)}`;
  }

  // ---------- Done ----------
  const kind = r => r.error || !r.ok ? 'bad' : r.partial ? 'warn' : 'ok';
  const kindText = { ok: 'Repaired', warn: 'Partly recovered', bad: 'Could not repair' };

  function viewDone() {
    const all = S.results, r = all[S.sel] || all[0];
    const k = kind(r);
    const counts = { ok: 0, warn: 0, bad: 0 }; all.forEach(x => counts[kind(x)]++);
    let title;
    if (all.length === 1) title = { ok: 'Your video is repaired', warn: 'Part of your video was recovered', bad: 'We couldn’t repair this one' }[k];
    else title = `${counts.ok + counts.warn} of ${all.length} videos recovered`;
    const vicon = { ok: 'check-circle', warn: 'warning', bad: 'warning-circle' }[k];

    const good = k !== 'bad';
    const thumbs = good ? (r.thumbs || []) : [];
    const strip = Array.from({ length: CELLS }, (_, i) => thumbs[i]
      ? `<div class="cell"><img src="${esc(vr.fileUrl(thumbs[i].path))}" alt=""></div>` : '<div class="cell gap"></div>').join('');

    const used = (r.attempts || []).filter(a => a.ok || a.partial).pop();
    const info = r.info || {};
    let detail = '';
    if (good) {
      const facts = [[fmtTime(info.duration), 'Length'], [info.height ? `${info.height}p${info.fps ? ' ' + Math.round(info.fps) + ' fps' : ''}` : '', 'Quality'], [fmtSize(info.size), 'Size']]
        .filter(f => f[0]).map(f => `<div><span class="mono">${esc(f[0])}</span><span>${f[1]}</span></div>`).join('');
      detail = `<div class="facts">${facts}</div>
        ${k === 'warn' ? `<div class="note warn"><div class="head">${icon('warning')}Expect a few glitches</div>
          <p>Some pieces of this video were missing or damaged. If you still have the memory card, recovering from the card itself can bring back more.</p></div>` : ''}
        <p class="muted small">${esc(sentence(used ? used.message : ''))}</p>`;
    } else {
      const tried = (r.attempts || []).map(a => `<li>${esc(sentence(a.message))}</li>`).join('');
      detail = `${r.error ? `<div class="note bad"><div class="head">${icon('warning-circle')}Something went wrong</div><p>${esc(r.error)}</p></div>` : ''}
        ${tried ? `<h2>What we tried</h2><ul class="todo muted">${tried}</ul>` : ''}
        <h2 class="gap-top">What you can try</h2>
        <ul class="todo"><li>Add a working clip from the same camera and settings, then try again.</li>
        <li>Keep the original file. A newer version of this app may handle it.</li></ul>`;
    }

    const list = all.length > 1 ? `<ul class="results">${all.map((x, i) => `<li><button data-act="select" data-i="${i}" ${i === S.sel ? 'aria-current="true"' : ''}>
        <span>${esc(x.file.name)}</span><span class="st ${kind(x)}">${kindText[kind(x)]}</span></button></li>`).join('')}</ul>` : '';

    const actions = good
      ? `<button class="btn primary" data-act="reveal">${icon('folder-open')}Show in folder</button><button class="btn" data-act="play">${icon('play')}Play</button>`
      : `<button class="btn primary" data-act="retry">Add a clip and try again</button>`;
    return `<div class="verdict ${k}">${icon(vicon)}<h1 class="tight">${esc(title)}</h1></div>
      <p class="lede under">${esc(r.file.name)}</p>
      <div class="film"><div class="cells">${strip}</div></div>
      ${detail}${list}${S.skippedAtStart ? `<p class="muted small gap-top">${pl(S.skippedAtStart, 'video')} from a different camera ${S.skippedAtStart === 1 ? 'was' : 'were'} skipped. Add ${S.skippedAtStart === 1 ? 'it' : 'them'} again on their own to repair ${S.skippedAtStart === 1 ? 'it' : 'them'}.</p>` : ''}
      <div class="actions">${actions}<span class="grow"></span><button class="btn quiet" data-act="restart">Repair another video</button></div>`;
  }

  // ---------- shell ----------
  function renderSteps() {
    const at = STEPS.findIndex(s => s[0] === S.step);
    $('#steps').innerHTML = STEPS.map(([id, label], i) => {
      const cls = i < at ? 'done' : i === at ? 'now' : '';
      return `<li class="${cls}"${i === at ? ' aria-current="step"' : ''}><span class="n">${i < at ? icon('check') : i + 1}</span><span>${label}</span></li>`;
    }).join('');
  }

  function render() {
    renderSteps();
    $('#view').innerHTML = (S.step === 'add' && S.card ? viewCard : { add: viewAdd, improve: viewImprove, repair: viewRepair, done: viewDone }[S.step])();
    if (S.step === 'repair') paintProgress();
    if (S.card && S.card.phase === 'scanning') paintCard();
  }

  const actions = {
    card: () => { S.card = { phase: 'choose' }; render(); },
    cardback: () => { S.card = null; render(); },
    pickimage: pickImage,
    cardcancel: async () => { S.card = { phase: 'choose' }; await vr.cancel(); render(); },
    cardreveal: () => { const v = S.card.videos[0]; if (v) vr.showInFolder(v.path); },
    cardrepair: repairFromCard,
    choose: async () => addPaths(await vr.chooseFiles()),
    remove: el => { S.files.splice(+el.dataset.i, 1); render(); },
    next: goImprove,
    back: () => { S.step = 'add'; render(); },
    clip: chooseClip,
    folder: async () => { const d = await vr.chooseFolder(); if (d) { S.outDir = d; render(); } },
    start: startRepair,
    cancel: async () => { S.cancelled = true; await vr.cancel(); goImprove(); },
    keep: el => { S.keep = groups()[+el.dataset.i].key; S.improve = null; render(); },
    select: el => { S.sel = +el.dataset.i; render(); },
    reveal: () => { const r = S.results[S.sel]; if (r && r.output) vr.showInFolder(r.output); },
    play: () => { const r = S.results[S.sel]; if (r && r.output) vr.openPath(r.output); },
    retry: goImprove,
    restart: () => { S.card = null; S.keep = null; S.files = []; S.improve = null; S.results = []; S.step = 'add'; render(); },
  };

  document.addEventListener('click', e => {
    const el = e.target.closest('[data-act]');
    if (el && actions[el.dataset.act]) actions[el.dataset.act](el);
  });
  document.addEventListener('dragover', e => { e.preventDefault(); const d = $('.drop'); if (d) d.classList.add('over'); });
  document.addEventListener('dragleave', () => { const d = $('.drop'); if (d) d.classList.remove('over'); });
  document.addEventListener('drop', e => {
    e.preventDefault();
    const d = $('.drop'); if (d) d.classList.remove('over');
    if (S.step === 'add') addPaths([...e.dataTransfer.files].map(f => vr.pathFor(f)));
  });

  if (vr.mode === 'preview') $('#flag').hidden = false;
  vr.defaultOutDir().then(d => { S.outDir = d; });
  render();
})();
