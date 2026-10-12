import struct

import pytest

from healvideo.exfat import ExFatError, ExFatVolume

BPS = 512  # bytes per sector, one sector per cluster to keep the image tiny
FAT_SECTOR, FAT_SECTORS, HEAP_SECTOR, CLUSTERS = 2, 2, 4, 60


def atom(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I4s", 8 + len(payload), kind) + payload


def make_video() -> bytes:
    ftyp = atom(b"ftyp", b"isom\x00\x00\x02\x00isomiso2mp41")
    mdat = atom(b"mdat", bytes((i * 7) % 251 for i in range(1500)))
    moov = atom(b"moov", atom(b"mvhd", struct.pack(">B3xIIII", 0, 3_700_000_000, 0, 1000, 5000) + b"\x00" * 80))
    return ftyp + mdat + moov


def build_image(video: bytes, order, with_partition_table=False) -> bytes:
    """order: the cluster numbers the file occupies, in file order (deliberately scrambled)."""
    boot = bytearray(BPS)
    boot[3:11] = b"EXFAT   "
    boot[64:100] = struct.pack("<QQIIIII", 0, 0, FAT_SECTOR, FAT_SECTORS, HEAP_SECTOR, CLUSTERS, 4)
    boot[108], boot[109], boot[110] = 9, 0, 1
    boot[510:512] = b"\x55\xaa"

    fat = [0] * (CLUSTERS + 2)
    for a, b in zip(order, order[1:]):
        fat[a] = b
    fat[order[-1]] = 0xFFFFFFFF
    fat_bytes = struct.pack("<%dI" % len(fat), *fat).ljust(FAT_SECTORS * BPS, b"\x00")

    heap = bytearray(b"\xee" * (CLUSTERS * BPS))  # other files' data everywhere else
    for n, c in enumerate(order):
        chunk = video[n * BPS:(n + 1) * BPS].ljust(BPS, b"\x00")
        heap[(c - 2) * BPS:(c - 1) * BPS] = chunk
    body = bytes(boot) + b"\x00" * BPS + fat_bytes + bytes(heap)
    if with_partition_table:
        mbr = bytearray(BPS)
        mbr[446 + 4] = 0x07
        mbr[446 + 8:446 + 12] = struct.pack("<I", 64)
        mbr[510:512] = b"\x55\xaa"
        return bytes(mbr) + b"\x00" * (63 * BPS) + body
    return body


@pytest.mark.parametrize("partitioned", [False, True])
def test_rebuilds_scrambled_file_exactly(tmp_path, partitioned):
    video = make_video()
    n = -(-len(video) // BPS)
    order = [9, 30, 31, 12, 45, 46, 47, 7, 20, 21, 22][:n]
    assert len(order) == n, "test video needs more clusters than the scramble list"
    img = tmp_path / "card.img"
    img.write_bytes(build_image(video, order, partitioned))

    vol = ExFatVolume(img)
    try:
        assert list(vol.find_mp4_starts()) == [order[0]]
        r = vol.rebuild_mp4(order[0], tmp_path / "out")
    finally:
        vol.close()
    assert r is not None and r.has_index
    assert r.path.read_bytes() == video
    assert r.fragments > 1
    assert r.path.name.startswith("recovered_2021")  # recording time read from the index


def test_plain_carving_order_would_be_wrong(tmp_path):
    """Sanity check on the fixture: reading clusters in disk order does not give the video."""
    video = make_video()
    n = -(-len(video) // BPS)
    order = [9, 30, 31, 12, 45, 46, 47, 7, 20, 21, 22][:n]
    img = build_image(video, order)
    start = (HEAP_SECTOR + order[0] - 2) * BPS
    assert img[start:start + len(video)] != video


def test_rejects_non_exfat(tmp_path):
    p = tmp_path / "junk.img"
    p.write_bytes(b"\x00" * 4096)
    with pytest.raises(ExFatError):
        ExFatVolume(p)
