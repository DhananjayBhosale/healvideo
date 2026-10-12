"""Starting point for the frozen engine (PyInstaller). Same program as `python -m healvideo`."""
from healvideo.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
