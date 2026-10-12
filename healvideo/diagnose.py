"""Work out, in plain words, what is wrong with a video file. Read-only."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional

from .mp4 import Atom, Scan, file_reader, scan_top_level


class Problem(str, Enum):
    HEALTHY = "healthy"
    EMPTY = "empty"
    NOT_VIDEO = "not_video"
    NO_INDEX = "no_index"
    CUT_OFF = "cut_off"
    NO_VIDEO_DATA = "no_video_data"


@dataclass
class Diagnosis:
    path: Path
    size: int
    problem: Problem
    summary: str  # one plain-language sentence for the user
    camera: Optional[str] = None
    atoms: List[Atom] = field(default_factory=list)
    suggested: List[str] = field(default_factory=list)  # repair strategies, best first

    @property
    def needs_repair(self) -> bool:
        return self.problem not in (Problem.HEALTHY,)


_START_TYPES = (b"ftyp", b"moov", b"mdat", b"free", b"wide", b"skip")
_CAMERA_PATTERNS = [
    (re.compile(rb"DJI ?[A-Za-z0-9]{3,32}"), None),  # label taken from the match
    (re.compile(rb"GoPro ?[A-Za-z0-9 ]{0,24}"), None),
]


def detect_camera(head: bytes) -> Optional[str]:
    if head[4:12] == b"ftypqt  " or b"com.apple.quicktime" in head:
        return "Apple"
    for rx, label in _CAMERA_PATTERNS:
        m = rx.search(head)
        if m:
            return label or m.group(0).decode("latin1").strip()
    return None


def diagnose(path) -> Diagnosis:
    path = Path(path)
    size = os.path.getsize(path)
    if size == 0:
        return Diagnosis(path, 0, Problem.EMPTY, "The file is empty (0 bytes). There is nothing to repair.")
    with open(path, "rb") as f:
        read_at = file_reader(f)
        scan: Scan = scan_top_level(read_at, size)
        camera = detect_camera(read_at(0, 1 << 20))
    atoms = scan.atoms
    types = [a.type for a in atoms]
    has_moov = b"moov" in types
    has_mdat = b"mdat" in types

    def make(problem, summary, suggested=()):
        return Diagnosis(path, size, problem, summary, camera, atoms, list(suggested))

    if not atoms or types[0] not in _START_TYPES:
        return make(Problem.NOT_VIDEO, "This does not look like an MP4 or MOV file, so it cannot be repaired here.")
    if scan.stop_reason == "truncated":
        cut = atoms[-1]
        if cut.type == b"moov":
            return make(Problem.CUT_OFF,
                        "The file ends in the middle of its index, so players cannot read it.",
                        ["untrunc", "carve"])
        if has_moov:
            return make(Problem.CUT_OFF,
                        "The recording was cut short. The index is there, but part of the video is missing.",
                        ["remux"])
        return make(Problem.CUT_OFF,
                    "The recording was cut short and the index is missing, so players cannot open it.",
                    ["untrunc", "carve"])
    if has_moov and has_mdat:
        return make(Problem.HEALTHY, "The file structure looks fine. Damage inside the video, if any, needs a deeper check.")
    if has_mdat and not has_moov:
        return make(Problem.NO_INDEX,
                    "The video data is there, but the index (moov) is missing. "
                    "This usually means the camera stopped before it finished saving.",
                    ["untrunc", "carve"])
    if has_moov and not has_mdat:
        return make(Problem.NO_VIDEO_DATA, "The index is there, but the video data is gone. Nothing can be rebuilt from this file.")
    return make(Problem.NOT_VIDEO, "This does not look like a complete MP4 or MOV file.")
