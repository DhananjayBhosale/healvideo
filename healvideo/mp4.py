"""Minimal MP4 / MOV (ISO base media file format) top-level atom reader.

Read-only and pure Python. The format is described in ISO/IEC 14496-12 and Apple's
QuickTime File Format specification.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import BinaryIO, Callable, List, Optional

# read_at(offset, n) -> up to n bytes at offset. Lets the same code read a plain
# file or a file whose clusters are stitched together from a card image.
ReadAt = Callable[[int, int], bytes]

KNOWN_TOP_LEVEL = {
    b"ftyp", b"free", b"skip", b"wide", b"mdat", b"moov", b"udta", b"uuid",
    b"pnot", b"meta", b"moof", b"mfra", b"sidx", b"styp", b"prft",
}
_MAC_EPOCH = datetime(1904, 1, 1, tzinfo=timezone.utc)


@dataclass(frozen=True)
class Atom:
    offset: int
    type: bytes
    size: int  # total size including the header; size 0 ("to end of file") is resolved
    header: int

    @property
    def end(self) -> int:
        return self.offset + self.size

    @property
    def name(self) -> str:
        return self.type.decode("latin1")


@dataclass
class Scan:
    atoms: List[Atom]
    file_size: int
    stop_offset: int
    # "eof" (clean), "truncated" (last atom runs past the end), "trailing-bytes",
    # "bad-header", "unknown-type"
    stop_reason: str


def file_reader(f: BinaryIO) -> ReadAt:
    def read_at(offset: int, n: int) -> bytes:
        f.seek(offset)
        return f.read(n)

    return read_at


def scan_top_level(read_at: ReadAt, file_size: int) -> Scan:
    """Walk the top-level atoms until the data stops looking like MP4."""
    atoms: List[Atom] = []
    pos = 0
    while pos < file_size:
        if file_size - pos < 8:
            return Scan(atoms, file_size, pos, "trailing-bytes")
        h = read_at(pos, 16)
        if len(h) < 8:
            return Scan(atoms, file_size, pos, "trailing-bytes")
        size, typ = struct.unpack(">I4s", h[:8])
        header = 8
        if size == 1:
            if len(h) < 16:
                return Scan(atoms, file_size, pos, "bad-header")
            size = struct.unpack(">Q", h[8:16])[0]
            header = 16
        elif size == 0:
            size = file_size - pos
        if size < header:
            return Scan(atoms, file_size, pos, "bad-header")
        if typ not in KNOWN_TOP_LEVEL:
            return Scan(atoms, file_size, pos, "unknown-type")
        atoms.append(Atom(pos, typ, size, header))
        if pos + size > file_size:
            return Scan(atoms, file_size, pos, "truncated")
        pos += size
    return Scan(atoms, file_size, pos, "eof")


def read_creation_time(read_at: ReadAt, moov: Atom) -> Optional[datetime]:
    """Recording time from the movie header (mvhd), or None if absent or zero."""
    body = read_at(moov.offset + moov.header, 512)
    i = body.find(b"mvhd")
    if i < 0:
        return None
    try:
        version = body[i + 4]
        if version == 1:
            seconds = struct.unpack(">Q", body[i + 8:i + 16])[0]
        else:
            seconds = struct.unpack(">I", body[i + 8:i + 12])[0]
        if seconds == 0:
            return None
        return _MAC_EPOCH + timedelta(seconds=seconds)
    except (IndexError, struct.error, OverflowError):
        return None
