import struct

import pytest

from healvideo.diagnose import Problem, diagnose
from healvideo.mp4 import file_reader, read_creation_time, scan_top_level


def atom(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I4s", 8 + len(payload), kind) + payload


def mvhd(created_secs: int) -> bytes:
    # version 0: version/flags(4) created(4) modified(4) timescale(4) duration(4) ...
    body = struct.pack(">B3xIIII", 0, created_secs, created_secs, 1000, 5000) + b"\x00" * 80
    return atom(b"mvhd", body)


FTYP = atom(b"ftyp", b"isom\x00\x00\x02\x00isomiso2mp41")
MDAT = atom(b"mdat", b"\x55" * 4000)
MOOV = atom(b"moov", mvhd(3_700_000_000))


def write(tmp_path, data: bytes, name="clip.mp4"):
    p = tmp_path / name
    p.write_bytes(data)
    return p


def test_healthy(tmp_path):
    d = diagnose(write(tmp_path, FTYP + MDAT + MOOV))
    assert d.problem is Problem.HEALTHY
    assert not d.needs_repair


def test_missing_index(tmp_path):
    d = diagnose(write(tmp_path, FTYP + MDAT))
    assert d.problem is Problem.NO_INDEX
    assert d.suggested == ["untrunc", "carve"]


def test_cut_off_inside_video_data(tmp_path):
    d = diagnose(write(tmp_path, (FTYP + MDAT + MOOV)[: len(FTYP) + 1500]))
    assert d.problem is Problem.CUT_OFF
    assert "carve" in d.suggested


def test_cut_off_inside_index_is_not_healthy(tmp_path):
    d = diagnose(write(tmp_path, (FTYP + MDAT + MOOV)[:-20]))
    assert d.problem is Problem.CUT_OFF


def test_cut_off_with_front_index_suggests_remux(tmp_path):
    d = diagnose(write(tmp_path, (FTYP + MOOV + MDAT)[:-1000]))
    assert d.problem is Problem.CUT_OFF
    assert d.suggested == ["remux"]


def test_empty_file(tmp_path):
    assert diagnose(write(tmp_path, b"")).problem is Problem.EMPTY


def test_random_bytes_are_not_video(tmp_path):
    assert diagnose(write(tmp_path, bytes(range(256)) * 20)).problem is Problem.NOT_VIDEO


def test_index_without_data(tmp_path):
    assert diagnose(write(tmp_path, FTYP + MOOV)).problem is Problem.NO_VIDEO_DATA


def test_zero_tail_after_index_is_still_healthy(tmp_path):
    d = diagnose(write(tmp_path, FTYP + MDAT + MOOV + b"\x00" * 3000))
    assert d.problem is Problem.HEALTHY


def test_camera_hint(tmp_path):
    data = FTYP + atom(b"mdat", b"junk DJI OsmoAction3 junk" + b"\x55" * 100) + MOOV
    assert diagnose(write(tmp_path, data)).camera == "DJI OsmoAction3"


def test_creation_time(tmp_path):
    p = write(tmp_path, FTYP + MDAT + MOOV)
    with open(p, "rb") as f:
        read_at = file_reader(f)
        scan = scan_top_level(read_at, p.stat().st_size)
        moov = next(a for a in scan.atoms if a.type == b"moov")
        created = read_creation_time(read_at, moov)
    assert created is not None and created.year == 2021  # 3.7e9 s after 1904-01-01


def test_apple_clip_is_recognised(tmp_path):
    apple_ftyp = atom(b"ftyp", b"qt  \x00\x00\x00\x00qt  ")
    assert diagnose(write(tmp_path, apple_ftyp + MDAT, "iphone.mov")).camera == "Apple"
