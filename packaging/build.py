"""Prepare what the installer needs: the frozen engine and the FFmpeg tools, in app/staging/.

Run from the repository root on the system you are building for (PyInstaller cannot cross-build):
    python packaging/build.py
then, in app/:  npm run dist

Needs: PyInstaller (pip), and `npm install` already run in app/ (it fetches the FFmpeg programs).
Standard library only apart from PyInstaller.
"""
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "app"
STAGING = APP / "staging"
IS_WIN = sys.platform == "win32"
EXE = ".exe" if IS_WIN else ""


def step(msg):
    print(f"\n== {msg}", flush=True)


def fail(msg):
    sys.exit(f"error: {msg}")


def freeze_engine():
    step("Freezing the engine with PyInstaller")
    work = ROOT / "build" / "pyinstaller"
    out = STAGING / "engine"
    shutil.rmtree(out, ignore_errors=True)
    subprocess.run([
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir", "--name", "healvideo-engine",
        "--distpath", str(out), "--workpath", str(work), "--specpath", str(work),
        "--add-data", f"{ROOT / 'healvideo' / 'profiles'}{os.pathsep}healvideo/profiles",
        "--hidden-import", "healvideo.serve",
        str(ROOT / "packaging" / "entry.py"),
    ], check=True)
    exe = out / "healvideo-engine" / f"healvideo-engine{EXE}"
    if not exe.is_file():
        fail(f"engine was not built: {exe}")
    return exe


def copy_ffmpeg():
    step("Copying FFmpeg and ffprobe")
    plat = {"darwin": "darwin", "linux": "linux", "win32": "win32"}.get(sys.platform)
    arch = {"arm64": "arm64", "aarch64": "arm64", "x86_64": "x64", "amd64": "x64"}.get(platform.machine().lower())
    if not plat or not arch:
        fail(f"unsupported system: {sys.platform} {platform.machine()}")
    ffmpeg = APP / "node_modules" / "ffmpeg-static" / f"ffmpeg{EXE}"
    ffprobe = APP / "node_modules" / "ffprobe-static" / "bin" / plat / arch / f"ffprobe{EXE}"
    for p in (ffmpeg, ffprobe):
        if not p.is_file():
            fail(f"missing {p}. Run `npm install` in app/ first (no ffprobe build for {plat}/{arch}?).")
    out = STAGING / "bin"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    for p in (ffmpeg, ffprobe):
        shutil.copy2(p, out / p.name)
    return out


def copy_licenses():
    step("Copying license files")
    out = STAGING / "licenses"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    for name in ("LICENSE", "CREDITS.md"):
        shutil.copy2(ROOT / name, out / name)
    shutil.copy2(APP / "node_modules" / "ffmpeg-static" / "ffmpeg.LICENSE", out / "FFmpeg-LICENSE.txt")
    shutil.copy2(APP / "node_modules" / "ffmpeg-static" / "ffmpeg.README", out / "FFmpeg-README.txt")


def smoke_test(engine, bin_dir):
    step("Checking the frozen engine starts and finds FFmpeg")
    env = dict(os.environ, PATH=str(bin_dir) + os.pathsep + os.environ.get("PATH", ""))
    r = subprocess.run([str(engine), "doctor"], env=env, capture_output=True, text=True)
    print(r.stdout + r.stderr)
    if r.returncode != 0 or "ffmpeg" not in r.stdout.lower() or "MISSING" in r.stdout:
        fail("the frozen engine did not pass `doctor`")


def main():
    STAGING.mkdir(parents=True, exist_ok=True)
    engine = freeze_engine()
    bin_dir = copy_ffmpeg()
    copy_licenses()
    smoke_test(engine, bin_dir)
    print(f"\nStaged in {STAGING}. Next: cd app && npm run dist")


if __name__ == "__main__":
    main()
