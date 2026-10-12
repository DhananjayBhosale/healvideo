// Draws the app icon (assets/icon.png) with Electron: a film strip whose first frame is damaged (hatched)
// and whose other two are healed (teal). Run: npx electron assets/make-icon.js
const { app, BrowserWindow, nativeImage } = require('electron');
const fs = require('fs'), path = require('path');
const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1024" viewBox="0 0 1024 1024">
  <defs><pattern id="h" width="28" height="28" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
    <rect width="28" height="28" fill="#1b2830"/><rect width="9" height="28" fill="#33474f"/></pattern></defs>
  <rect x="64" y="64" width="896" height="896" rx="200" fill="#0e151a"/>
  <g fill="#33474f">${[...Array(7)].map((_, i) => `<rect x="${150 + i * 122}" y="236" width="64" height="40" rx="8"/><rect x="${150 + i * 122}" y="748" width="64" height="40" rx="8"/>`).join('')}</g>
  <rect x="132" y="336" width="236" height="352" rx="14" fill="url(#h)"/>
  <rect x="394" y="336" width="236" height="352" rx="14" fill="#3fb8a3"/>
  <rect x="656" y="336" width="236" height="352" rx="14" fill="#2f9e8c"/>
</svg>`;
app.whenReady().then(async () => {
  const win = new BrowserWindow({ width: 1024, height: 1024, useContentSize: true, show: false, transparent: true, frame: false });
  await win.loadURL('data:text/html,' + encodeURIComponent(`<body style="margin:0;background:transparent">${svg}</body>`));
  await new Promise(r => setTimeout(r, 400));
  const img = (await win.webContents.capturePage()).resize({ width: 1024, height: 1024 });
  fs.writeFileSync(path.join(__dirname, 'icon.png'), img.toPNG());
  app.quit();
});
