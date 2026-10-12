"""Frame carver: rebuild an H.265 stream from the raw video data (mdat) of a broken MP4.

This is the part that needs no reference clip. MP4 stores each frame as
[4-byte length][NAL unit]. Without the index we cannot know where frames start, so we
look for a length field followed by a plausible slice header, and only accept it if the
next frames also line up. Between frames, cameras place metadata and audio of varying
size, so the search allows a gap. When the chain breaks (the file is fragmented or
damaged) we skip ahead to the next keyframe and start a new segment.

The parameter sets (VPS/SPS/PPS) that normally live in the missing index come from a
camera profile or from a good clip of the same camera and mode.

Our own work, informed by how PhotoRec carves and how untrunc rebuilds indexes. See CREDITS.md.
"""
from __future__ import annotations

import mmap
import os
import re
import struct
from dataclasses import dataclass
from typing import Callable, Iterable, Optional, Tuple

START_CODE = b"\x00\x00\x00\x01"
# HEVC slice NAL headers are two bytes: (type << 1), then 0x01 (layer 0, temporal id 0).
TRAIL_R, IDR_W_RADL, IDR_N_LP = 0x02, 0x26, 0x28
IDR_TYPES = (IDR_W_RADL, IDR_N_LP)
DEFAULT_NAL_TYPES = (TRAIL_R, IDR_W_RADL, IDR_N_LP)


@dataclass
class CarveStats:
    frames: int = 0
    segments: int = 0
    bytes_out: int = 0


class _Carver:
    def __init__(self, mm, size, nal_types: Iterable[int], min_len: int, max_len: int, max_gap: int):
        self.mm, self.size = mm, size
        self.min_len, self.max_len, self.max_gap = min_len, max_len, max_gap
        types = sorted(set(nal_types))
        idr = [t for t in types if t in IDR_TYPES]
        if not idr:
            raise ValueError("nal_types must include at least one IDR type (0x26 or 0x28)")
        one = re.escape(b"\x01")
        self.any_rx = re.compile(b"[" + b"".join(re.escape(bytes([t])) for t in types) + b"]" + one)
        self.idr_rx = re.compile(b"[" + b"".join(re.escape(bytes([t])) for t in idr) + b"]" + one)

    def valid(self, q: int) -> int:
        """Frame length if a plausible [len][slice] starts at q, else 0."""
        if q < 0 or q + 6 > self.size:
            return 0
        length = struct.unpack(">I", self.mm[q:q + 4])[0]
        if not (self.min_len <= length <= self.max_len) or q + 4 + length > self.size:
            return 0
        return length if self.any_rx.fullmatch(self.mm[q + 4:q + 6]) else 0

    def next_frame(self, end: int) -> Optional[Tuple[int, int]]:
        for m in self.any_rx.finditer(self.mm, end, min(self.size, end + self.max_gap)):
            q = m.start() - 4
            if q < end:
                continue
            length = self.valid(q)
            if length:
                return q, length
        return None

    def chain(self, q: int, length: int, want: int):
        out = [(q, length)]
        while len(out) < want:
            n = self.next_frame(q + 4 + length)
            if n is None:
                break
            q, length = n
            out.append(n)
        return out


def carve_to_annexb(
    src,
    dst,
    paramsets: bytes,
    *,
    nal_types: Iterable[int] = DEFAULT_NAL_TYPES,
    min_len: int = 1000,
    max_len: int = 2_000_000,
    max_gap: int = 400_000,
    min_chain: int = 3,
    max_frames: Optional[int] = None,
    progress: Optional[Callable[[int, int], None]] = None,
) -> CarveStats:
    """Write paramsets plus every frame found in src to dst as an Annex-B H.265 stream."""
    stats = CarveStats()
    with open(src, "rb") as fh:
        size = os.fstat(fh.fileno()).st_size
        if size == 0:
            raise ValueError("input file is empty")
        mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
        try:
            c = _Carver(mm, size, nal_types, min_len, max_len, max_gap)
            pos = 0
            with open(dst, "wb") as out:
                out.write(paramsets)
                while pos < size and (max_frames is None or stats.frames < max_frames):
                    m = c.idr_rx.search(mm, pos)
                    if not m:
                        break
                    q = m.start() - 4
                    length = c.valid(q) if q >= pos else 0
                    if not length or len(c.chain(q, length, min_chain)) < min_chain:
                        pos = m.start() + 2
                        continue
                    stats.segments += 1
                    while True:
                        out.write(START_CODE)
                        out.write(mm[q + 4:q + 4 + length])
                        stats.frames += 1
                        stats.bytes_out += length + 4
                        end = q + 4 + length
                        if progress and stats.frames % 200 == 0:
                            progress(end, size)
                        if max_frames is not None and stats.frames >= max_frames:
                            pos = end
                            break
                        nxt = c.next_frame(end)
                        if nxt is None:
                            pos = end
                            break
                        q, length = nxt
        finally:
            mm.close()
    return stats
