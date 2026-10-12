"""JSON-lines server: how the desktop app talks to the engine.

One JSON object per line on stdin, one per line on stdout. Nothing else is ever written to stdout.
  request  {"id": 1, "cmd": "diagnose", "paths": ["a.mp4"]}
  events   {"id": 1, "event": "progress", "done": 10, "total": 100}
           {"id": 1, "event": "result", "data": {...}}
           {"id": 1, "event": "error", "message": "plain words"}
Requests run one at a time. To cancel, the app stops this process and starts a new one.
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Callable, Dict, TextIO

from . import __version__, engines, profiles
from .diagnose import diagnose
from .exfat import ExFatError, ExFatVolume
from .repair import check_reference, find_reference, repair

Emit = Callable[[Dict], None]


def _file_info(path: Path) -> Dict:
    d = diagnose(path)
    prof = profiles.detect(path) if d.needs_repair else None
    return {
        "path": str(path), "name": path.name, "size": d.size, "problem": d.problem.value,
        "summary": d.summary, "camera": d.camera, "needs_repair": d.needs_repair,
        "profile": prof.name if prof else None,
    }


def _doctor(req, emit, tools):
    return {"version": __version__, "ffmpeg": tools.ffmpeg, "ffprobe": tools.ffprobe, "untrunc": tools.untrunc,
            "profiles": [p.name for p in profiles.load_all()]}


def _diagnose(req, emit, tools):
    files = []
    for p in req["paths"]:
        try:
            files.append(_file_info(Path(p)))
        except OSError as e:
            files.append({"path": p, "name": Path(p).name, "problem": "unreadable",
                          "summary": f"This file could not be read ({e.strerror or e}).", "needs_repair": False})
    return {"files": files}


def _improve(req, emit, tools):
    """What helps the repair: a known camera profile, and a good clip from the same camera."""
    src = Path(req["path"])
    d = diagnose(src)
    prof = profiles.detect(src)
    out = {"camera": d.camera, "profile": prof.name if prof else None, "reference": None,
           "reference_ok": None, "reference_message": None, "found_automatically": False}
    ref = req.get("reference")
    if ref:
        ok, msg = check_reference(ref, d.camera)
        out.update(reference={"path": ref, "name": Path(ref).name}, reference_ok=ok, reference_message=msg)
    else:
        found = find_reference(src, d.camera)
        if found:
            out.update(reference={"path": str(found), "name": found.name}, reference_ok=True,
                       reference_message="Found in the same folder.", found_automatically=True)
    return out


def _repair(req, emit, tools):
    r = repair(req["path"], req["out_dir"], tools=tools, reference=req.get("reference"),
               on_progress=lambda done, total: emit({"event": "progress", "done": done, "total": total}))
    info = {}
    if r.output and tools.ffprobe:
        meta = engines.probe(tools.ffprobe, r.output)
        video = next((x for x in meta.get("streams", []) if x.get("codec_type") == "video"), {})
        fps, dur = engines.video_info(meta)
        info = {"width": video.get("width"), "height": video.get("height"), "fps": fps, "duration": dur,
                "size": r.output.stat().st_size}
    return {
        "ok": r.ok, "partial": r.partial, "output": str(r.output) if r.output else None, "info": info,
        "summary": r.diagnosis.summary, "needs_repair": r.diagnosis.needs_repair,
        "attempts": [{"strategy": a.strategy, "ok": a.ok, "partial": a.partial, "message": a.message}
                     for a in r.attempts],
    }


def _thumbs(req, emit, tools):
    """Evenly spaced still frames, for the filmstrip."""
    if not (tools.ffmpeg and tools.ffprobe):
        raise RuntimeError("FFmpeg is needed to make previews.")
    src, count = Path(req["path"]), int(req.get("count", 12))
    out_dir = Path(req.get("out_dir") or tempfile.mkdtemp(prefix="healvideo-thumbs-"))
    out_dir.mkdir(parents=True, exist_ok=True)
    _, dur = engines.video_info(engines.probe(tools.ffprobe, src))
    frames = []
    for i in range(count if dur else 0):
        t = dur * (i + 0.5) / count
        dst = out_dir / f"{src.stem}_{i:02d}.jpg"
        engines.run([tools.ffmpeg, "-y", "-v", "error", "-ss", f"{t:.3f}", "-i", str(src),
                     "-frames:v", "1", "-vf", "scale=320:-2", str(dst)])
        if dst.exists() and dst.stat().st_size:
            frames.append({"path": str(dst), "time": round(t, 2)})
    return {"duration": dur, "frames": frames}


def _rebuild_card(req, emit, tools):
    """Find the videos on an exFAT card image and rejoin their scattered pieces into whole files."""
    try:
        vol = ExFatVolume(req["image"])
    except ExFatError as e:
        raise ValueError(f"{e}. This tool reads exFAT card images (the format most cameras use).") from e
    videos = []
    try:
        starts = list(vol.find_mp4_starts(
            lambda done, total: emit({"event": "progress", "phase": "scan", "done": done, "total": total})))
        for k, c in enumerate(starts):
            emit({"event": "progress", "phase": "rebuild", "done": k, "total": len(starts)})
            r = vol.rebuild_mp4(c, req["out_dir"])
            if r is None:
                continue
            stamp = re.match(r"recovered_(\d{8})_(\d{6})_", r.path.name)
            videos.append({"path": str(r.path), "name": r.path.name, "size": r.size, "has_index": r.has_index,
                           "fragments": r.fragments,
                           "recorded": f"{stamp[1][:4]}-{stamp[1][4:6]}-{stamp[1][6:]}T{stamp[2][:2]}:{stamp[2][2:4]}:{stamp[2][4:]}" if stamp else None})
    finally:
        vol.close()
    videos.sort(key=lambda v: (v["recorded"] or "", v["name"]))
    return {"videos": videos}


COMMANDS = {"rebuild_card": _rebuild_card, "doctor": _doctor, "diagnose": _diagnose, "improve": _improve, "repair": _repair, "thumbs": _thumbs}


def serve(stdin: TextIO = None, stdout: TextIO = None) -> int:
    stdin, stdout = stdin or sys.stdin, stdout or sys.stdout
    for stream in (stdin, stdout):  # Windows defaults to a legacy code page; file names need UTF-8
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    tools = engines.Tools.discover()
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        rid = None

        def emit(msg: Dict) -> None:
            stdout.write(json.dumps({"id": rid, **msg}) + "\n")
            stdout.flush()

        try:
            req = json.loads(line)
            rid = req.get("id")
            fn = COMMANDS.get(req.get("cmd"))
            if fn is None:
                raise ValueError(f"unknown command: {req.get('cmd')}")
            emit({"event": "result", "data": fn(req, emit, tools)})
        except Exception as e:  # one bad request must not stop the server
            emit({"event": "error", "message": str(e) or e.__class__.__name__})
    return 0
