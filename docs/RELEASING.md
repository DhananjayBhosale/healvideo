# Building and releasing HealVideo

## Build an installer on your own computer

```bash
python -m venv .venv && .venv/bin/pip install -e ".[dev,build]"    # once (on Windows: .venv\Scripts\pip)
cd app && npm install                                              # once; fetches Electron and FFmpeg
python ../packaging/build.py                                       # freezes the engine, stages FFmpeg
npm run dist                                                       # installer goes to app/dist/
npm run pack                                                       # or: an unpacked app, quicker, for testing
```

Each system has to build its own installer (macOS the `.dmg`, Windows the `.exe`, Linux the `.AppImage` and `.deb`). The workflow in `.github/workflows/release.yml` does this on GitHub for all four targets.

## What is checked automatically

`.github/workflows/ci.yml` runs the engine tests on Windows, macOS and Linux (Python 3.9 and 3.13) and
syntax-checks the window code. This does not open the window. Someone still needs to try each installer by hand.

## Signing

Releases are made by pushing a tag (`git tag v0.1.0 && git push origin v0.1.0`). The workflow builds all installers
and attaches them to a GitHub pre-release. Names are fixed (`HealVideo-mac-arm64.dmg`, `HealVideo-mac-x64.dmg`,
`HealVideo-windows-setup.exe`, `HealVideo-linux.AppImage`, `HealVideo-linux.deb`).

**macOS.** Needs an Apple Developer account and a **Developer ID Application** certificate (the Apple Development and
Apple Distribution certificates do not work outside the App Store). The workflow signs and notarizes when these
repository secrets exist, and builds unsigned when they do not:

| Secret | What it is |
|---|---|
| `MAC_CERTIFICATE_P12_BASE64` | The Developer ID Application certificate, exported as .p12, base64 |
| `MAC_CERTIFICATE_PASSWORD` | The password you chose when exporting the .p12 |
| `APPLE_API_KEY_P8_BASE64` | App Store Connect API key (.p8), base64 |
| `APPLE_API_KEY_ID`, `APPLE_API_ISSUER_ID` | The key's ID and the issuer ID from App Store Connect |

To sign on your own Mac instead, install the certificate, then run `npm run dist` in `app/` with
`APPLE_API_KEY`, `APPLE_API_KEY_ID`, `APPLE_API_ISSUER` set and `-c.mac.notarize=true`.

The Mac App Store is a different route and does not fit the GPL. Distribute the notarized `.dmg` directly.

**Windows.** Without a certificate, SmartScreen warns "unknown publisher". [SignPath Foundation](https://signpath.org) signs open-source projects for free.

**Linux.** Nothing needed.

## Before the first public release

- Pick the real app identifier and website (`appId` in `app/package.json`), then update them.
- Test every installer on a clean computer of that system, with one real broken video.
- Re-check the licenses in `CREDITS.md` against the versions that are bundled.
- The FFmpeg programs come from npm packages. Look at what version each ships and decide whether to pin your own build.
- untrunc is not bundled. The app works without it (it uses its own repair method and camera profiles).
