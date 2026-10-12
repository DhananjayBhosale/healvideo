// HealVideo desktop shell. Starts the Python engine (`healvideo serve`) and passes messages to the window.
const { app, BrowserWindow, ipcMain, dialog, shell, nativeTheme } = require('electron');
const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');

const IS_WIN = process.platform === 'win32';
const ROOT = path.resolve(__dirname, '..');

function engineCommand() {
  if (app.isPackaged) {
    const res = process.resourcesPath;
    const exe = path.join(res, 'engine', IS_WIN ? 'healvideo-engine.exe' : 'healvideo-engine');
    return { cmd: exe, args: ['serve'], cwd: res, pathPrefix: path.join(res, 'bin') };
  }
  const venv = path.join(ROOT, '.venv', IS_WIN ? 'Scripts/python.exe' : 'bin/python');
  const python = fs.existsSync(venv) ? venv : (IS_WIN ? 'python' : 'python3');
  return { cmd: python, args: ['-m', 'healvideo', 'serve'], cwd: ROOT, pathPrefix: null };
}

class Engine {
  constructor() { this.proc = null; this.seq = 0; this.pending = new Map(); this.buf = ''; this.err = ''; }

  start() {
    if (this.proc) return;
    const { cmd, args, cwd, pathPrefix } = engineCommand();
    const env = { ...process.env, PYTHONUNBUFFERED: '1', PYTHONIOENCODING: 'utf-8' };
    if (pathPrefix) {
      // Windows spells it "Path"; reuse whichever spelling exists so we don't create a second, conflicting entry.
      const key = Object.keys(env).find(k => k.toUpperCase() === 'PATH') || 'PATH';
      env[key] = pathPrefix + path.delimiter + (env[key] || '');
    }
    const proc = spawn(cmd, args, { cwd, env, windowsHide: true });
    this.proc = proc; this.buf = ''; this.err = '';
    proc.stdout.setEncoding('utf8');
    proc.stdout.on('data', chunk => {
      this.buf += chunk;
      let i;
      while ((i = this.buf.indexOf('\n')) >= 0) {
        const line = this.buf.slice(0, i); this.buf = this.buf.slice(i + 1);
        if (line.trim()) this.handleLine(line);
      }
    });
    proc.stderr.setEncoding('utf8');
    proc.stderr.on('data', t => { this.err = (this.err + t).slice(-2000); });
    proc.stdin.on('error', () => {});
    proc.on('error', e => this.fail(proc, `The repair engine could not start (${e.message}).`));
    proc.on('exit', () => this.fail(proc, 'The repair engine stopped unexpectedly.' + (this.err ? ` ${this.err.trim().split('\n').pop()}` : '')));
  }

  handleLine(line) {
    let msg; try { msg = JSON.parse(line); } catch { return; }
    const p = this.pending.get(msg.id);
    if (!p) return;
    if (msg.event === 'progress') { if (p.onProgress) p.onProgress(msg); return; }
    this.pending.delete(msg.id);
    if (msg.event === 'result') p.resolve(msg.data); else p.reject(new Error(msg.message || 'Something went wrong.'));
  }

  fail(proc, message) {
    if (this.proc !== proc) return; // an old process, already replaced
    this.proc = null;
    for (const p of this.pending.values()) p.reject(new Error(message));
    this.pending.clear();
  }

  request(cmd, payload, onProgress) {
    return new Promise((resolve, reject) => {
      this.start();
      const id = ++this.seq;
      this.pending.set(id, { resolve, reject, onProgress });
      this.proc.stdin.write(JSON.stringify({ id, cmd, ...payload }) + '\n');
    });
  }

  cancel() {
    const proc = this.proc;
    if (!proc) return;
    this.fail(proc, 'cancelled');
    proc.kill();
  }
}

// AppImage on recent Ubuntu cannot use Chromium's sandbox helper without root. This app only opens its own
// local pages, so we turn the helper off there instead of failing to start.
if (process.platform === 'linux' && process.env.APPIMAGE) app.commandLine.appendSwitch('no-sandbox');

const engine = new Engine();

ipcMain.handle('engine', async (event, { rid, cmd, payload }) => {
  try {
    const data = await engine.request(cmd, payload || {}, m => event.sender.send('engine-progress', { rid, done: m.done, total: m.total, phase: m.phase }));
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e.message };
  }
});
ipcMain.handle('cancel', () => engine.cancel());
ipcMain.handle('choose-files', async () => {
  const r = await dialog.showOpenDialog({ title: 'Choose videos', properties: ['openFile', 'multiSelections'],
    filters: [{ name: 'Video', extensions: ['mp4', 'MP4', 'mov', 'MOV', 'm4v', 'M4V'] }, { name: 'All files', extensions: ['*'] }] });
  return r.canceled ? [] : r.filePaths;
});
ipcMain.handle('choose-image', async () => {
  const r = await dialog.showOpenDialog({ title: 'Choose a memory card image', properties: ['openFile'],
    filters: [{ name: 'Card images', extensions: ['img', 'dd', 'raw', 'bin', 'iso'] }, { name: 'All files', extensions: ['*'] }] });
  return r.canceled ? null : r.filePaths[0];
});
ipcMain.handle('choose-folder', async () => {
  const r = await dialog.showOpenDialog({ title: 'Choose where to save repaired videos', properties: ['openDirectory', 'createDirectory'] });
  return r.canceled ? null : r.filePaths[0];
});
ipcMain.handle('default-out', () => path.join(app.getPath('videos'), 'Repaired'));
ipcMain.handle('show-in-folder', (_e, p) => shell.showItemInFolder(p));
ipcMain.handle('open-path', (_e, p) => shell.openPath(p));

function createWindow() {
  const win = new BrowserWindow({
    width: 1040, height: 700, minWidth: 860, minHeight: 600, title: 'HealVideo', autoHideMenuBar: true,
    backgroundColor: nativeTheme.shouldUseDarkColors ? '#10171D' : '#EDF0F2',
    webPreferences: { preload: path.join(__dirname, 'preload.js'), contextIsolation: true, nodeIntegration: false, sandbox: true },
  });
  win.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  win.webContents.on('will-navigate', e => e.preventDefault());
  win.loadFile(path.join(__dirname, 'renderer', 'index.html'));
}

app.whenReady().then(createWindow);
app.on('window-all-closed', () => { engine.cancel(); app.quit(); });
app.on('before-quit', () => engine.cancel());
