import io
import json

from healvideo import profiles
from healvideo.profiles import Profile
from healvideo.serve import serve
from tests.test_diagnose import FTYP, MDAT, MOOV, write
from tests.test_exfat import build_image, make_video

DJI_FREE = b"\x00\x00\x00\x10free" + b"DJI OsmoAction3"[:8]


def talk(*requests):
    out = io.StringIO()
    serve(io.StringIO("".join(json.dumps(r) + "\n" for r in requests)), out)
    return [json.loads(line) for line in out.getvalue().splitlines()]


def test_doctor_and_unknown_command():
    a, b = talk({"id": 1, "cmd": "doctor"}, {"id": 2, "cmd": "nope"})
    assert a["id"] == 1 and a["event"] == "result" and "profiles" in a["data"]
    assert b["event"] == "error" and "unknown command" in b["message"]


def test_bad_json_does_not_stop_the_server():
    out = io.StringIO()
    serve(io.StringIO("not json\n" + json.dumps({"id": 3, "cmd": "doctor"}) + "\n"), out)
    lines = [json.loads(x) for x in out.getvalue().splitlines()]
    assert [x["event"] for x in lines] == ["error", "result"]


def test_diagnose_reports_each_file(tmp_path):
    good = write(tmp_path, FTYP + MDAT + MOOV, "good.mp4")
    bad = write(tmp_path, FTYP + MDAT, "bad.mp4")
    (r,) = talk({"id": 1, "cmd": "diagnose", "paths": [str(good), str(bad), str(tmp_path / "missing.mp4")]})
    good_i, bad_i, missing_i = r["data"]["files"]
    assert not good_i["needs_repair"] and bad_i["problem"] == "no_index"
    assert missing_i["problem"] == "unreadable"


def test_improve_finds_a_healthy_clip_in_the_same_folder(tmp_path):
    write(tmp_path, FTYP + MDAT + MOOV, "good.mp4")
    bad = write(tmp_path, FTYP + MDAT, "bad.mp4")
    (r,) = talk({"id": 1, "cmd": "improve", "path": str(bad)})
    assert r["data"]["reference"]["name"] == "good.mp4" and r["data"]["found_automatically"]


def test_improve_rejects_a_damaged_reference(tmp_path):
    bad = write(tmp_path, FTYP + MDAT, "bad.mp4")
    other = write(tmp_path, FTYP + MDAT, "other.mp4")
    (r,) = talk({"id": 1, "cmd": "improve", "path": str(bad), "reference": str(other)})
    assert r["data"]["reference_ok"] is False


def test_repair_of_a_healthy_file_does_nothing(tmp_path):
    good = write(tmp_path, FTYP + MDAT + MOOV, "good.mp4")
    (r,) = talk({"id": 1, "cmd": "repair", "path": str(good), "out_dir": str(tmp_path / "out")})
    assert r["data"]["needs_repair"] is False and r["data"]["output"] is None


def test_profile_exclude_rules_out_the_proxy_files():
    p = Profile("x", ["DJI OsmoAction3"], 50, 1920, 1080, "00", exclude=["avc1"])
    assert p.matches(b"isomiso2mp41 DJI OsmoAction3")
    assert not p.matches(b"isomiso2avc1mp41 DJI OsmoAction3")


def test_bundled_dji_profile_is_found():
    names = [p.name for p in profiles.load_all()]
    assert any("Osmo Action 3" in n for n in names)


def test_rebuild_card_rejoins_scattered_video(tmp_path):
    video = make_video()
    img = tmp_path / "card.img"
    img.write_bytes(build_image(video, [9, 30, 31, 12]))
    events = talk({"id": 1, "cmd": "rebuild_card", "image": str(img), "out_dir": str(tmp_path / "out")})
    (v,) = events[-1]["data"]["videos"]
    assert v["has_index"] and v["fragments"] > 1 and v["recorded"].startswith("2021-")
    assert open(v["path"], "rb").read() == video


def test_rebuild_card_explains_a_wrong_file(tmp_path):
    junk = tmp_path / "junk.img"
    junk.write_bytes(b"\x00" * 4096)
    (r,) = talk({"id": 1, "cmd": "rebuild_card", "image": str(junk), "out_dir": str(tmp_path / "out")})
    assert r["event"] == "error" and "exFAT" in r["message"]
