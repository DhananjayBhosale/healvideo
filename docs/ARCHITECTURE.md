# Architecture

Goal: a desktop app (Windows, macOS, Linux) where someone drops in a broken video and gets
a playable copy back, without knowing what an "index" or a "cluster" is.

```
 desktop window (Electron, app/)       command line (works today)
              \  JSON lines (serve)         /
               +---------- healvideo ----+
                   diagnose  →  repair strategies  →  verify by decoding
                                  |        |        |
                               remux   untrunc    carve (own)       rebuild-image (own)
                               FFmpeg  separate   hevc.py +         exfat.py
                                       program    camera profiles
```

## Modules (`healvideo/`)

| Module | Job |
|---|---|
| `mp4.py` | Read MP4/MOV top-level atoms from a file or from stitched-together clusters. |
| `diagnose.py` | Say what is wrong in one plain sentence and list which repair strategies to try. |
| `repair.py` | Run strategies in order. Every result is decoded and rejected if it has errors. Never edits the original. |
| `hevc.py` | Frame carver: rebuild an H.265 stream from raw video data with no index. Skips damage to the next keyframe. |
| `profiles.py` | Camera profiles: decoder settings per camera and mode, so no reference clip is needed. |
| `exfat.py` | Rejoin scattered files on an exFAT card image using the card's allocation table. |
| `engines.py` | Find and run FFmpeg, ffprobe and untrunc as separate programs. |
| `serve.py` | JSON-lines server the desktop app talks to: `doctor`, `diagnose`, `improve`, `repair`, `thumbs`, `rebuild_card`. |
| `cli.py` | `doctor`, `diagnose`, `repair`, `profile-make`, `rebuild-image`, `serve`. |

## Design rules

1. **Read-only on inputs.** Output always goes to a new file.
2. **Verify, don't trust.** A strategy only counts as success if the result decodes.
3. **External tools stay separate programs** (untrunc is GPL-2.0). The project itself is GPL-3.0-or-later.
4. **Standard library only** for our own code, so the engine is easy to package for all three systems.
5. **Say what happened** in plain words, including when a repair is partial (for example, video without audio).

## Known limits (v0.1)

- The frame carver handles H.265 (HEVC) only. H.264 is next.
- Carved output has no audio yet.
- `rebuild-image` handles exFAT only. FAT32 is next. It needs the card's allocation table to still be intact,
  so it does not help after a full format or heavy overwriting.
- One camera profile is bundled: DJI Osmo Action 3, 1080p 50 fps HEVC. It matches the HD files only, not the
  camera's H.264 proxy files. Other cameras need a profile made from a real clip.
- Tested so far: 28 unit tests (all pass); `rebuild-image` on one real 64 GB exFAT card (115 videos rebuilt;
  one recording's HD file was not on the card at all); `repair` with the bundled profile on one real broken
  Osmo Action 3 clip; the desktop app end to end on macOS in development mode. Windows, Linux and other
  cameras are untested.
- `rebuild-image` finds files by their first cluster (an `ftyp` atom). A file whose first cluster was
  overwritten is not found; matching proxy/HD pairs can reveal such gaps.

## Roadmap

1. Engine tests green; bundle the Osmo Action 3 profile; run end to end on the 59 GB test card image.
2. Audio in carved output; H.264 carver; FAT32.
3. Desktop window (Electron, `app/`): drag and drop, plain-language diagnosis, filmstrip preview, progress. Started.
4. Installers for Windows, macOS and Linux with FFmpeg bundled and credited. Build scripts and workflows written; macOS app built and run here; Windows and Linux built only by the workflow (not run yet). untrunc is not bundled.
5. Camera profile library contributed by users.

## Desktop app (`app/`)

Electron shell. `main.js` starts `python -m healvideo serve` (a frozen engine in the installed app) and passes
messages between it and the window. `preload.js` exposes a small fixed set of actions as `window.vr`.
The window (`renderer/`) is plain HTML, CSS and JavaScript with no framework. Opened in a plain browser, it
uses `renderer/mock.js` and shows "Preview with sample data". Installers: `packaging/build.py` freezes the engine (PyInstaller) and stages FFmpeg;
electron-builder makes the installer (see [RELEASING.md](RELEASING.md)). The card screen reads exFAT card images only (no direct reading of a card, which would need admin rights on each system).

Run it in development: `cd app && npm install && npm start` (needs the `.venv` from the repository root).
