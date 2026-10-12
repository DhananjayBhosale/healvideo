"""Camera profiles: what the rebuild needs to know about one camera and recording mode.

A profile stores the H.265 parameter sets (the decoder settings that normally sit in the
missing index) so a broken file can be rebuilt with no reference clip. Profiles are small
JSON files. Anyone can make one from a good clip with `healvideo profile-make`.

This is the idea that sets the project apart from reference-based tools. See CREDITS.md.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional

from . import engines
from .hevc import DEFAULT_NAL_TYPES

BUILTIN_DIR = Path(__file__).resolve().parent / "profiles"


@dataclass
class Profile:
    name: str
    match: List[str]  # ASCII strings that must all appear in the first MB of the broken file
    fps: float
    width: int
    height: int
    paramsets_hex: str
    codec: str = "hevc"
    nal_types: List[int] = field(default_factory=lambda: list(DEFAULT_NAL_TYPES))
    note: str = ""
    exclude: List[str] = field(default_factory=list)  # strings that rule this profile out

    @property
    def paramsets(self) -> bytes:
        return bytes.fromhex(self.paramsets_hex)

    def matches(self, head: bytes) -> bool:
        return (bool(self.match) and all(m.encode("latin1") in head for m in self.match)
                and not any(x.encode("latin1") in head for x in self.exclude))


def load_dir(directory: Path) -> List[Profile]:
    out = []
    if directory.is_dir():
        for p in sorted(directory.glob("*.json")):
            try:
                out.append(Profile(**json.loads(p.read_text(encoding="utf-8"))))
            except (ValueError, TypeError):
                continue  # a bad profile file must not break repairs
    return out


def load_all(extra_dirs=()) -> List[Profile]:
    profiles = load_dir(BUILTIN_DIR)
    for d in extra_dirs:
        profiles += load_dir(Path(d))
    return profiles


def detect(path, profiles: Optional[List[Profile]] = None) -> Optional[Profile]:
    profiles = load_all() if profiles is None else profiles
    with open(path, "rb") as f:
        head = f.read(1 << 20)
    for p in profiles:
        if p.matches(head):
            return p
    return None


def make_from_reference(tools: engines.Tools, reference, name: str, match: List[str], note: str = "",
                        exclude: Optional[List[str]] = None) -> Profile:
    if not (tools.ffmpeg and tools.ffprobe):
        raise RuntimeError("FFmpeg and ffprobe are needed to make a profile")
    info = engines.probe(tools.ffprobe, reference)
    video = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)
    if not video or video.get("codec_name") != "hevc":
        raise ValueError("the reference clip must contain H.265 (HEVC) video")
    fps, _ = engines.video_info(info)
    with open(reference, "rb") as f:
        head = f.read(1 << 20)
    missing = [m for m in match if m.encode("latin1") not in head]
    if missing:
        raise ValueError(f"match text not found in the reference clip: {missing}")
    return Profile(
        name=name,
        match=match,
        fps=fps or 0.0,
        width=int(video["width"]),
        height=int(video["height"]),
        paramsets_hex=engines.extract_paramsets(tools.ffmpeg, reference).hex(),
        note=note,
        exclude=list(exclude or []),
    )


def save(profile: Profile, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    slug = "".join(c.lower() if c.isalnum() else "-" for c in profile.name).strip("-")
    path = directory / f"{slug}.json"
    path.write_text(json.dumps(asdict(profile), indent=2) + "\n", encoding="utf-8")
    return path
