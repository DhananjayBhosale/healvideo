"""Command line front end. The desktop app will call the same functions."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__, engines, profiles
from .diagnose import diagnose
from .exfat import ExFatError, ExFatVolume
from .repair import repair


def _cmd_doctor(args) -> int:
    t = engines.Tools.discover()
    rows = [("FFmpeg", t.ffmpeg, True), ("ffprobe", t.ffprobe, True), ("untrunc", t.untrunc, False)]
    for name, path, required in rows:
        state = path or ("MISSING (needed)" if required else "not found (optional, enables reference-based repair)")
        print(f"{name:8} {state}")
    print(f"profiles {len(profiles.load_all())} built in")
    return 0 if t.ffmpeg and t.ffprobe else 1


def _cmd_diagnose(args) -> int:
    for p in args.files:
        d = diagnose(p)
        cam = f"  camera: {d.camera}" if d.camera else ""
        print(f"{p}\n  {d.problem.value}: {d.summary}{cam}")
        if d.suggested:
            print(f"  will try: {', '.join(d.suggested)}")
    return 0


def _cmd_repair(args) -> int:
    code = 0
    for p in args.files:
        r = repair(p, args.out, reference=args.reference, profile_name=args.profile,
                   profile_dirs=args.profiles_dir or ())
        print(f"{p}\n  {r.diagnosis.problem.value}: {r.diagnosis.summary}")
        if not r.diagnosis.needs_repair:
            continue
        for a in r.attempts:
            tag = "ok  " if a.ok else ("part" if a.partial else "fail")
            print(f"  {tag} {a.strategy}: {a.message}")
        if r.ok and r.partial:
            print(f"  saved (partial, expect glitches): {r.output}")
        elif r.ok:
            print(f"  saved: {r.output}")
        else:
            print("  could not be repaired. Try a reference clip from the same camera: --reference GOOD.mp4")
            code = 2
    return code


def _cmd_profile_make(args) -> int:
    tools = engines.Tools.discover()
    prof = profiles.make_from_reference(tools, args.reference, args.name, args.match, args.note or "", args.exclude)
    path = profiles.save(prof, Path(args.out))
    print(f"saved profile '{prof.name}' ({prof.width}x{prof.height} at {prof.fps:g} fps) to {path}")
    return 0


def _cmd_rebuild_image(args) -> int:
    try:
        vol = ExFatVolume(args.image, args.partition_offset)
    except ExFatError as e:
        print(f"error: {e}")
        return 1
    found = 0
    try:
        starts = list(vol.find_mp4_starts(lambda i, n: print(f"\rscanning card: {i * 100 // n}%", end="", file=sys.stderr)))
        print(file=sys.stderr)
        for c in starts:
            r = vol.rebuild_mp4(c, args.out)
            if r is None:
                continue
            found += 1
            note = "" if r.has_index else "  (index missing: run `repair` on it)"
            print(f"{r.path.name}  {r.size / 1e6:.0f} MB, {r.fragments} pieces rejoined{note}")
    finally:
        vol.close()
    print(f"{found} videos rebuilt into {args.out}")
    return 0


def _cmd_serve(args) -> int:
    from .serve import serve
    return serve()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="healvideo", description="Diagnose and repair corrupted video files.")
    ap.add_argument("--version", action="version", version=f"healvideo {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("doctor", help="check that the tools we build on are installed").set_defaults(fn=_cmd_doctor)

    p = sub.add_parser("diagnose", help="say what is wrong with a file, without changing anything")
    p.add_argument("files", nargs="+")
    p.set_defaults(fn=_cmd_diagnose)

    p = sub.add_parser("repair", help="repair broken videos into a new folder")
    p.add_argument("files", nargs="+")
    p.add_argument("--out", default="repaired", help="folder for repaired copies (default: ./repaired)")
    p.add_argument("--reference", help="a good clip from the same camera and settings")
    p.add_argument("--profile", help="name of a camera profile to use")
    p.add_argument("--profiles-dir", action="append", help="extra folder of camera profiles")
    p.set_defaults(fn=_cmd_repair)

    p = sub.add_parser("profile-make", help="make a camera profile from a good clip")
    p.add_argument("reference")
    p.add_argument("--name", required=True)
    p.add_argument("--match", action="append", required=True,
                   help="text found in this camera's files, for example 'DJI OsmoAction3' (repeatable)")
    p.add_argument("--exclude", action="append", default=[],
                   help="text that rules the profile out, for example 'avc1' to skip the camera's H.264 proxy files (repeatable)")
    p.add_argument("--note")
    p.add_argument("--out", default=str(profiles.BUILTIN_DIR))
    p.set_defaults(fn=_cmd_profile_make)

    sub.add_parser("serve", help="talk to the desktop app over JSON lines (used by the app)").set_defaults(fn=_cmd_serve)

    p = sub.add_parser("rebuild-image", help="rejoin scattered videos on an exFAT card image")
    p.add_argument("image")
    p.add_argument("--out", default="rebuilt")
    p.add_argument("--partition-offset", type=int, help="byte offset of the exFAT volume (auto-detected by default)")
    p.set_defaults(fn=_cmd_rebuild_image)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
