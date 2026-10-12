// The only way the window talks to the computer. Exposes a small, fixed set of actions as window.vr.
const { contextBridge, ipcRenderer, webUtils } = require('electron');

// The sandboxed preload has no url.pathToFileURL, so build the file:// address by hand.
const fileUrl = p => {
  let s = String(p).replace(/\\/g, '/');
  if (!s.startsWith('/')) s = '/' + s;
  return 'file://' + encodeURI(s).replace(/[?#]/g, c => encodeURIComponent(c));
};

let seq = 0;
const progress = new Map();
ipcRenderer.on('engine-progress', (_e, m) => { const f = progress.get(m.rid); if (f) f(m); });

contextBridge.exposeInMainWorld('vr', {
  mode: 'app',
  async engine(cmd, payload, onProgress) {
    const rid = ++seq;
    if (onProgress) progress.set(rid, onProgress);
    try {
      const r = await ipcRenderer.invoke('engine', { rid, cmd, payload });
      if (!r.ok) throw new Error(r.error);
      return r.data;
    } finally { progress.delete(rid); }
  },
  cancel: () => ipcRenderer.invoke('cancel'),
  chooseFiles: () => ipcRenderer.invoke('choose-files'),
  chooseImage: () => ipcRenderer.invoke('choose-image'),
  chooseFolder: () => ipcRenderer.invoke('choose-folder'),
  defaultOutDir: () => ipcRenderer.invoke('default-out'),
  showInFolder: p => ipcRenderer.invoke('show-in-folder', p),
  openPath: p => ipcRenderer.invoke('open-path', p),
  pathFor: file => webUtils.getPathForFile(file),
  fileUrl,
});
