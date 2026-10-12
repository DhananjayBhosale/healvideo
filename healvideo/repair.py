"""Repair pipeline: diagnose, then try strategies in order until one produces a clean video.

Strategies (each writes a new file, the original is never touched):
  remux   FFmpeg stream copy. Fixes files whose index is fine but whose tail is cut off.
  untrunc Rebuild the index from a good clip of the same camera (found automatically
          next to the broken file when possible). Uses anthwlock/untrunc.
  carve   Our own frame carver (hevc.py) with decoder settings from a camera profile or
          reference clip. Needs no reference when a profile matches.

Every result is checked by decoding it, so a strategy that produces junk is rejected.
"""
from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from . import engines, hevc, profiles as profiles_mod
from .diagnose import Diagnosis, Problem, diagnose

VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v"}
CHECK_SECONDS = 30  # decode this much of each result to accept it


@dataclass
class Attempt:
    strategy: str
    ok: bool
    message: str
    output: Optional[Path] = None
    errors: int = 0  # decoding errors in a kept partial result (ok is False, output is set)

    @property
    def partial(self) -> bool:
        return not self.ok and self.output is not None


@dataclass
class RepairResult:
    source: Path
    diagnosis: Diagnosis
    attempts: List[Attempt] = field(default_factory=list)
    output: Optional[Path] = None
    partial: bool = False  # output plays but has decoding errors (expect glitches)

    @property
    def ok(self) -> bool:
        return self.output is not None


def unique_path(directory: Path, stem: str, suffix: str = ".mp4") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    p = directory / f"{stem}{suffix}"
    n = 2
    while p.exists():
        p = directory / f"{stem}_{n}{suffix}"
        n += 1
    return p


def find_reference(src: Path, camera: Optional[str]) -> Optional[Path]:
    """A healthy clip from the same camera in the same folder, closest in size."""
    best, best_gap = None, None
    try:
        siblings = [p for p in src.parent.iterdir() if p.suffix.lower() in VIDEO_SUFFIXES and p != src][:200]
    except OSError:
        return None
    size = src.stat().st_size
    for p in siblings:
        try:
            d = diagnose(p)
        except OSError:
            continue
        if d.problem is not Problem.HEALTHY or (camera and d.camera != camera):
            continue
        gap = abs(d.size - size)
        if best is None or gap < best_gap:
            best, best_gap = p, gap
    return best


def check_reference(path, camera: Optional[str]) -> Tuple[bool, str]:
    """Is this clip usable as a reference? It must play, and come from the same camera when we know it."""
    try:
        d = diagnose(path)
    except OSError:
        return False, "That file could not be read."
    if d.problem is not Problem.HEALTHY:
        return False, "That clip is damaged too, so it cannot show us how the camera stores video."
    if camera and d.camera and d.camera != camera:
        return False, f"That clip is from a different camera ({d.camera})."
    return True, "Looks good."


def _accept(tools: engines.Tools, out: Path) -> Tuple[Optional[str], int]:
    """(reason, errors). reason None: clean. errors > 0: plays but has glitches. errors -1: unusable."""
    if not out.exists() or out.stat().st_size == 0:
        return "no output was produced", -1
    if tools.ffprobe:
        _, dur = engines.video_info(engines.probe(tools.ffprobe, out))
        if not dur or dur <= 0:
            return "the result has no playable duration", -1
    if tools.ffmpeg:
        n = engines.decode_errors(tools.ffmpeg, out, CHECK_SECONDS)
        if n:
            return f"the result has {n} decoding errors in its first {CHECK_SECONDS} seconds", n
    return None, 0


def _verdict(tools, strategy: str, out: Path, ok_message: str) -> Attempt:
    """Clean result: success. Glitchy result: kept as partial. Unusable: deleted."""
    why, errors = _accept(tools, out)
    if why is None:
        return Attempt(strategy, True, ok_message, out)
    if errors > 0:
        return Attempt(strategy, False, f"{ok_message}, but {why}", out, errors)
    out.unlink(missing_ok=True)
    return Attempt(strategy, False, why)


def _remux(tools, src: Path, out: Path) -> Attempt:
    if not tools.ffmpeg:
        return Attempt("remux", False, "FFmpeg is not installed")
    r = engines.run([tools.ffmpeg, "-y", "-v", "error", "-i", str(src), "-c", "copy",
                     "-movflags", "+faststart", str(out)])
    if r.returncode != 0:
        return Attempt("remux", False, "FFmpeg could not read the file")
    return _verdict(tools, "remux", out, "rebuilt with FFmpeg")


def _untrunc(tools, src: Path, reference: Optional[Path], out: Path) -> Attempt:
    if not tools.untrunc:
        return Attempt("untrunc", False, "untrunc is not installed")
    if reference is None:
        return Attempt("untrunc", False, "no reference clip from the same camera was found")
    with tempfile.TemporaryDirectory() as tmp:
        engines.run([tools.untrunc, "-n", "-dst", tmp, str(reference), str(src)])
        made = sorted((p for p in Path(tmp).iterdir() if p.is_file()), key=lambda p: p.stat().st_size, reverse=True)
        if not made:
            return Attempt("untrunc", False, "untrunc produced no file")
        shutil.move(str(made[0]), out)
    return _verdict(tools, "untrunc", out, f"index rebuilt using {reference.name}")


def _carve(tools, src: Path, profile, reference: Optional[Path], out: Path, on_progress) -> Attempt:
    if not tools.ffmpeg:
        return Attempt("carve", False, "FFmpeg is not installed")
    if profile is not None:
        paramsets, fps, nal_types = profile.paramsets, profile.fps, profile.nal_types
        source_note = f"camera profile '{profile.name}'"
    elif reference is not None:
        try:
            paramsets = engines.extract_paramsets(tools.ffmpeg, reference)
        except ValueError as e:
            return Attempt("carve", False, str(e))
        fps = engines.video_info(engines.probe(tools.ffprobe, reference))[0] if tools.ffprobe else None
        nal_types = hevc.DEFAULT_NAL_TYPES
        source_note = f"settings from {reference.name}"
    else:
        return Attempt("carve", False, "no camera profile or reference clip available")
    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "stream.h265"
        try:
            stats = hevc.carve_to_annexb(src, raw, paramsets, nal_types=nal_types, progress=on_progress)
        except (OSError, ValueError) as e:
            return Attempt("carve", False, f"could not read the video data: {e}")
        if stats.frames == 0:
            return Attempt("carve", False, "no video frames were found")
        r = engines.run([tools.ffmpeg, "-y", "-v", "error", "-f", "hevc", "-framerate", str(fps or 30),
                         "-i", str(raw), "-c", "copy", "-tag:v", "hvc1", str(out)])
    if r.returncode != 0:
        return Attempt("carve", False, "the carved frames could not be packed into an MP4")
    pieces = "" if stats.segments == 1 else f" in {stats.segments} pieces"
    return _verdict(tools, "carve", out,
                    f"{stats.frames} frames recovered{pieces} using {source_note} (video only, no audio)")


def repair(src, out_dir, *, tools: Optional[engines.Tools] = None, reference=None, profile_name: Optional[str] = None,
           profile_dirs=(), on_progress: Optional[Callable[[int, int], None]] = None) -> RepairResult:
    src, out_dir = Path(src), Path(out_dir)
    tools = tools or engines.Tools.discover()
    d = diagnose(src)
    result = RepairResult(src, d)
    if d.problem in (Problem.HEALTHY, Problem.EMPTY, Problem.NOT_VIDEO, Problem.NO_VIDEO_DATA):
        return result

    all_profiles = profiles_mod.load_all(profile_dirs)
    profile = None
    if profile_name:
        profile = next((p for p in all_profiles if p.name == profile_name), None)
    else:
        profile = profiles_mod.detect(src, all_profiles)
    ref = Path(reference) if reference else find_reference(src, d.camera)

    for strategy in d.suggested:
        out = unique_path(out_dir, f"{src.stem}_repaired")
        if strategy == "remux":
            a = _remux(tools, src, out)
        elif strategy == "untrunc":
            a = _untrunc(tools, src, ref, out)
        elif strategy == "carve":
            a = _carve(tools, src, profile, ref, out, on_progress)
        else:
            continue
        result.attempts.append(a)
        if a.ok:
            result.output = a.output
            break
    if result.output is None:
        # no clean result: hand back the least damaged partial one and remove the others
        partials = sorted((a for a in result.attempts if a.partial), key=lambda a: a.errors)
        for a in partials[1:]:
            a.output.unlink(missing_ok=True)
        if partials:
            result.output, result.partial = partials[0].output, True
    return result
