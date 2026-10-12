# Credits

This project stands on the work of many people. Thank you to all of them.
If we use something and forgot to list it, please open an issue and we will add it.

## Programs we run

These run as separate programs. We do not copy or link their code, so each keeps its own license.

| Project | By | License | What we use it for |
|---|---|---|---|
| [FFmpeg](https://ffmpeg.org) | The FFmpeg developers | LGPL-2.1+, or GPL-2.0+ depending on the build | Reading and checking video, packing repaired frames into MP4, extracting decoder settings |
| [untrunc](https://github.com/anthwlock/untrunc) | Federico Ponchio (original), anthwlock and contributors (maintained fork) | GPL-2.0 (the `COPYING` file in the repository) | Rebuilding a missing index from a good clip of the same camera |
| [PhotoRec and TestDisk](https://www.cgsecurity.org) | Christophe Grenier, CGSecurity | GPL-2.0-or-later | The file-carving approach we learned from; planned engine for recovering deleted photos and other files |
| [GNU ddrescue](https://www.gnu.org/software/ddrescue/) | Antonio Diaz Diaz | GPL-3.0-or-later | Planned: copying a failing card to an image safely |
| [ExifTool](https://exiftool.org) | Phil Harvey | Artistic License or GPL | Planned: reading camera and date information |
| [GPAC / MP4Box](https://gpac.io) | The GPAC team | LGPL-2.1-or-later | Planned: a second opinion when rebuilding MP4 structure |

## What the app is built with

| Project | By | License | What we use it for |
|---|---|---|---|
| [Electron](https://www.electronjs.org) | OpenJS Foundation and contributors | MIT | The desktop window on Windows, macOS and Linux |
| [Geist](https://vercel.com/font) | Vercel and Basement Studio | SIL Open Font License 1.1 | The app's typefaces (Geist and Geist Mono), bundled with its license file |
| [Phosphor Icons](https://phosphoricons.com) | Helena Zhang and Tobias Fried | MIT | Icons |

| [ffmpeg-static](https://github.com/eugeneware/ffmpeg-static) and [ffprobe-static](https://github.com/joshwnj/ffprobe-static) | Eugene Ware, Josh Wnj and contributors | GPL-3.0-or-later and MIT (they package FFmpeg's own programs, which keep FFmpeg's license) | Where the installers get the FFmpeg and ffprobe programs they bundle |
| [PyInstaller](https://pyinstaller.org) | The PyInstaller team | GPL-2.0-or-later with a bootloader exception | Packing the engine into one program for the installers |
| [electron-builder](https://www.electron.build) | Vladimir Krivosheev and contributors | MIT | Making the installers |

Licenses above are written from what each project states publicly. Check each project's own
repository before a release, and keep this table in step with the versions we bundle.

## Source code for programs we bundle

The installers include FFmpeg and ffprobe as separate programs. Their source code is available from
<https://ffmpeg.org/download.html>, and the exact builds come from the `ffmpeg-static` and `ffprobe-static`
packages named above. The license texts are in the `licenses` folder inside each installed app.

## Ideas and methods we learned from

- **untrunc** showed that a good clip from the same camera can teach a tool how to rebuild a broken file's index.
- **PhotoRec** showed that files can be found by their content alone, without a working file system. It also showed where that stops working: it reads each file as one unbroken block.
- **Community forum threads** (Apple Community, Hacker News and others) described what people actually try, and where they get stuck.

## Standards and specifications

- ISO/IEC 14496-12 (ISO base media file format) and Apple's QuickTime File Format specification: the MP4 and MOV structure.
- ITU-T H.265 / ISO/IEC 23008-2 (HEVC): the video format our frame carver reads.
- Microsoft's published exFAT file system specification: the card layout our cluster-chain rebuild follows.

## What is new here

- **Camera profiles:** decoder settings stored per camera and recording mode, so some broken files can be rebuilt with no reference clip.
- **Frame carver with resync:** rebuilds an H.265 stream from raw video data and skips damaged or missing parts to the next keyframe.
- **Cluster-chain rebuild for exFAT cards:** puts scattered pieces of a file back in the right order using the card's own allocation table.
- **The filmstrip:** repair progress and the result are shown as a real strip of frames from your video.
- **Plain-language diagnosis** and automatic strategy order, with every result checked by decoding it.

## Test footage

The first camera we test against is a DJI Osmo Action 3. DJI and Osmo are trademarks of SZ DJI Technology.
We are not affiliated with or endorsed by DJI, Microsoft, Apple, or any project listed above.
