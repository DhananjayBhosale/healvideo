import struct

from healvideo.hevc import START_CODE, carve_to_annexb

PARAMSETS = START_CODE + b"\x40\x01PARAMS"
# Payload bytes stay in 0x50..0xFF so they can never look like a slice header (0x02/0x26/0x28 then 0x01).
FILL = b"\x55"


def frame(i: int, idr: bool) -> bytes:
    nal = (b"\x28\x01" if idr else b"\x02\x01") + bytes([0x60 + (i % 100)]) * (3000 + 17 * i)
    return struct.pack(">I", len(nal)) + nal


def build(n_frames: int, gap: int = 9000, hole_before=None, hole: int = 0) -> bytes:
    data = FILL * 700  # leading junk (index-less files start with metadata)
    for i in range(n_frames):
        if hole_before == i:
            data += FILL * hole
        data += frame(i, idr=(i % 10 == 0)) + FILL * gap
    return data


def expected(n_frames: int) -> bytes:
    out = PARAMSETS
    for i in range(n_frames):
        out += START_CODE + frame(i, idr=(i % 10 == 0))[4:]
    return out


def test_carves_every_frame_in_order(tmp_path):
    src, dst = tmp_path / "broken.mp4", tmp_path / "out.h265"
    src.write_bytes(build(20))
    stats = carve_to_annexb(src, dst, PARAMSETS)
    assert stats.frames == 20 and stats.segments == 1
    assert dst.read_bytes() == expected(20)


def test_skips_a_hole_and_restarts_at_the_next_keyframe(tmp_path):
    src, dst = tmp_path / "broken.mp4", tmp_path / "out.h265"
    src.write_bytes(build(20, hole_before=10, hole=100_000))  # frame 10 is a keyframe
    stats = carve_to_annexb(src, dst, PARAMSETS, max_gap=20_000)
    assert stats.frames == 20 and stats.segments == 2
    assert dst.read_bytes() == expected(20)


def test_ignores_leftover_frames_after_a_hole_until_a_keyframe(tmp_path):
    src, dst = tmp_path / "broken.mp4", tmp_path / "out.h265"
    src.write_bytes(build(20, hole_before=13, hole=100_000))  # frames 13..19 follow, next keyframe is 10
    stats = carve_to_annexb(src, dst, PARAMSETS, max_gap=20_000)
    # frames 13..19 have no keyframe in front of them, so only 0..12 are written
    assert stats.frames == 13 and stats.segments == 1


def test_max_frames(tmp_path):
    src, dst = tmp_path / "broken.mp4", tmp_path / "out.h265"
    src.write_bytes(build(20))
    assert carve_to_annexb(src, dst, PARAMSETS, max_frames=5).frames == 5


def test_no_frames_found(tmp_path):
    src, dst = tmp_path / "broken.mp4", tmp_path / "out.h265"
    src.write_bytes(FILL * 50_000)
    assert carve_to_annexb(src, dst, PARAMSETS).frames == 0
