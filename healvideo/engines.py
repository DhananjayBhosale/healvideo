"""Locate and run the external tools we build on (FFmpeg, untrunc, and so on).

They run as separate programs, never linked in, so their licenses stay their own.
See CREDITS.md.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_EXTRA_DIRS = ["/opt/homebrew/bin", "/usr/local/bin", "/usr/bin"]
# In the installed app the engine sits in <resources>/engine and the tools in <resources>/bin.
if getattr(sys, "frozen", False):
    _BUNDLED = Path(sys.executable).resolve().parent.parent / "bin"
else:
    _BUNDLED = Path(__file__).resolve().parent.parent / "bin"


def find_tool(name: str) -> Optional[str]:
    """Order: HEALVIDEO_<NAME> env var, bundled bin/ folder, PATH, common install folders."""
    env = os.environ.get("HEALVIDEO_" + name.upper().replace("-", "_"))
    if env and os.access(env, os.X_OK):
        return env
    exe = name + (".exe" if sys.platform == "win32" else "")
    bundled = _BUNDLED / exe
    if bundled.is_file() and os.access(bundled, os.X_OK):
        return str(bundled)
    found = shutil.which(name)
    if found:
        return found
    for d in _EXTRA_DIRS:
        p = Path(d) / exe
        if p.is_file() and os.access(p, os.X_OK):
            return str(p)
    return None


@dataclass
class Tools:
    ffmpeg: Optional[str]
    ffprobe: Optional[str]
    untrunc: Optional[str]

    @classmethod
    def discover(cls) -> "Tools":
        untrunc = find_tool("untrunc")
        if untrunc is None:
            # untrunc builds are often named untrunc-<ffmpeg version>, for example untrunc-81
            for d in [str(_BUNDLED)] + os.environ.get("PATH", "").split(os.pathsep):
                try:
                    for p in sorted(Path(d).glob("untrunc*")):
                        if p.is_file() and os.access(p, os.X_OK) and p.suffix in ("", ".exe"):
                            untrunc = str(p)
                            break
                except OSError:
                    pass
                if untrunc:
                    break
        return cls(find_tool("ffmpeg"), find_tool("ffprobe"), untrunc)


def run(cmd: List[str], timeout: Optional[int] = None) -> subprocess.CompletedProcess:
    # On Windows, stop a console window from flashing up for every tool we start.
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.run(cmd, capture_output=True, timeout=timeout, creationflags=flags)


def probe(ffprobe: str, path) -> Dict:
    r = run([ffprobe, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)], timeout=120)
    if r.returncode != 0:
        return {}
    try:
        return json.loads(r.stdout)
    except ValueError:
        return {}


def video_info(info: Dict) -> Tuple[Optional[float], Optional[float]]:
    """(frames per second, duration in seconds) from probe() output."""
    fps = dur = None
    for s in info.get("streams", []):
        if s.get("codec_type") == "video":
            num, _, den = str(s.get("r_frame_rate", "0/1")).partition("/")
            try:
                fps = float(num) / float(den or 1) or None
            except (ValueError, ZeroDivisionError):
                fps = None
            break
    try:
        dur = float(info.get("format", {}).get("duration"))
    except (TypeError, ValueError):
        dur = None
    return fps, dur


def decode_errors(ffmpeg: str, path, seconds: Optional[int] = None) -> int:
    """Number of error lines FFmpeg prints while decoding (0 means it decodes cleanly)."""
    cmd = [ffmpeg, "-v", "error"]
    if seconds:
        cmd += ["-t", str(seconds)]
    cmd += ["-i", str(path), "-f", "null", "-"]
    r = run(cmd)
    if r.returncode != 0:
        return max(1, len(r.stderr.splitlines()))
    return len([ln for ln in r.stderr.decode("utf-8", "replace").splitlines() if ln.strip()])


def extract_paramsets(ffmpeg: str, reference) -> bytes:
    """VPS/SPS/PPS (and SEI) NAL units of a good H.265 clip, as Annex-B bytes."""
    raw = run([ffmpeg, "-v", "error", "-i", str(reference), "-map", "0:v:0", "-c", "copy",
               "-bsf:v", "hevc_mp4toannexb", "-frames:v", "1", "-f", "hevc", "-"]).stdout
    starts = [m.start() for m in re.finditer(rb"\x00\x00\x01", raw)]
    nals = []
    for a, b in zip(starts, starts[1:] + [len(raw)]):
        nal = raw[a + 3:b].rstrip(b"\x00")
        if nal and ((nal[0] >> 1) & 0x3F) in (32, 33, 34, 39, 40):
            nals.append(nal)
    if not any(((n[0] >> 1) & 0x3F) == 33 for n in nals):
        raise ValueError("no H.265 parameter sets found in the reference clip")
    return b"".join(b"\x00\x00\x00\x01" + n for n in nals)
