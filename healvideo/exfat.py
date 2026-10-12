"""Rejoin scattered video files on an exFAT card image by following the FAT cluster chains.

Why: a camera that records to a nearly full card writes one file in many pieces. Carving
tools read the file as one unbroken block and get the wrong bytes at every break. The
card's own allocation table (FAT) still records the correct order of the pieces, often
even after the file was deleted. Following it gives back the complete original file,
index included.

Read-only on the image. Layout described in Microsoft's published exFAT specification.
Our own work. See CREDITS.md.
"""
from __future__ import annotations

import os
import struct
import sys
from array import array
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator, List, Optional

from .mp4 import ReadAt, read_creation_time, scan_top_level

EXFAT_EOC = 0xFFFFFFF7  # values at or above this end a chain (bad cluster / end of chain)


class ExFatError(Exception):
    pass


@dataclass
class Rebuilt:
    start_cluster: int
    path: Path
    size: int
    has_index: bool
    fragments: int


class ExFatVolume:
    def __init__(self, image_path, partition_offset: Optional[int] = None):
        self.f = open(image_path, "rb")
        self.base = self._find_exfat(partition_offset)
        boot = self._read(self.base, 512)
        if boot[3:11] != b"EXFAT   ":
            raise ExFatError("no exFAT volume found (FAT32 and NTFS are not supported yet)")
        _, _, fat_off, fat_len, heap_off, self.cluster_count, self.root = struct.unpack("<QQIIIII", boot[64:100])
        self.bps = 1 << boot[108]
        self.cluster_size = self.bps << boot[109]
        self.heap_start = self.base + heap_off * self.bps
        n = self.cluster_count + 2
        raw = self._read(self.base + fat_off * self.bps, n * 4)
        self.fat = array("I")
        self.fat.frombytes(raw[: (len(raw) // 4) * 4])
        if sys.byteorder == "big":
            self.fat.byteswap()

    def close(self) -> None:
        self.f.close()

    def _read(self, offset: int, n: int) -> bytes:
        self.f.seek(offset)
        return self.f.read(n)

    def _find_exfat(self, forced: Optional[int]) -> int:
        if forced is not None:
            return forced
        if self._read(3, 8) == b"EXFAT   ":
            return 0
        mbr = self._read(0, 512)
        candidates: List[int] = []
        if mbr[510:512] == b"\x55\xaa":
            for i in range(4):
                e = mbr[446 + 16 * i:462 + 16 * i]
                if e[4] and struct.unpack("<I", e[8:12])[0]:
                    candidates.append(struct.unpack("<I", e[8:12])[0] * 512)
        gpt = self._read(512, 92)
        if gpt[:8] == b"EFI PART":
            entries_lba = struct.unpack("<Q", gpt[72:80])[0]
            count = min(struct.unpack("<I", gpt[80:84])[0], 128)
            size = struct.unpack("<I", gpt[84:88])[0]
            table = self._read(entries_lba * 512, count * size)
            for i in range(count):
                ent = table[i * size:(i + 1) * size]
                if len(ent) >= 48 and any(ent[:16]):
                    candidates.append(struct.unpack("<Q", ent[32:40])[0] * 512)
        for off in candidates:
            if self._read(off + 3, 8) == b"EXFAT   ":
                return off
        raise ExFatError("no exFAT partition found in the image")

    def cluster_offset(self, c: int) -> int:
        return self.heap_start + (c - 2) * self.cluster_size

    def chain(self, start: int) -> List[int]:
        out, seen, c = [], set(), start
        while 2 <= c < self.cluster_count + 2 and c not in seen:
            out.append(c)
            seen.add(c)
            nxt = self.fat[c]
            if nxt >= EXFAT_EOC or nxt == 0:
                break
            c = nxt
        return out

    def reader(self, chain: List[int]) -> ReadAt:
        cs = self.cluster_size

        def read_at(pos: int, n: int) -> bytes:
            out = b""
            while n > 0:
                i, o = divmod(pos, cs)
                if i >= len(chain):
                    break
                k = min(n, cs - o)
                out += self._read(self.cluster_offset(chain[i]) + o, k)
                pos += k
                n -= k
            return out

        return read_at

    def find_mp4_starts(self, progress: Optional[Callable[[int, int], None]] = None) -> Iterator[int]:
        """Clusters whose first bytes look like the start of an MP4 file (an ftyp atom)."""
        total = self.cluster_count
        for i in range(total):
            c = i + 2
            head = self._read(self.cluster_offset(c), 12)
            if len(head) == 12 and head[4:8] == b"ftyp" and 16 <= struct.unpack(">I", head[:4])[0] <= 64:
                yield c
            if progress and i % 20000 == 0:
                progress(i, total)

    def rebuild_mp4(self, start: int, out_dir) -> Optional[Rebuilt]:
        chain = self.chain(start)
        if not chain:
            return None
        read_at = self.reader(chain)
        scan = scan_top_level(read_at, len(chain) * self.cluster_size)
        if not scan.atoms:
            return None
        # a zero-filled tail after the last atom stops the scan as "unknown-type"; the file ends there
        length = scan.atoms[-1].end
        has_index = any(a.type == b"moov" for a in scan.atoms)
        moov = next((a for a in scan.atoms if a.type == b"moov"), None)
        created = read_creation_time(read_at, moov) if moov else None
        stamp = created.strftime("%Y%m%d_%H%M%S") if created else "unknown"
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"recovered_{stamp}_c{start}.mp4"
        left = length
        with open(path, "wb") as o:
            for c in chain:
                if left <= 0:
                    break
                o.write(self._read(self.cluster_offset(c), min(self.cluster_size, left)))
                left -= self.cluster_size
        frags = 1 + sum(1 for a, b in zip(chain, chain[1:]) if b != a + 1)
        return Rebuilt(start, path, length, has_index, frags)
