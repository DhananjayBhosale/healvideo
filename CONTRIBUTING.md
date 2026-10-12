# Contributing to HealVideo

Thanks for helping. The most useful contributions are small and specific.

## Add a camera profile

A profile lets HealVideo repair that camera's files without a reference clip.

1. Get one **healthy** clip from the camera, in the mode you want to support.
2. Run: `python -m healvideo profile-make good.mp4 --name "Camera, mode" --match "text found in its files"`
3. Test it by repairing a deliberately damaged copy.
4. Add the new file under `healvideo/profiles/` and open a pull request. Do not attach the clip. Share the profile only.

## Report a problem

Open an issue and say what the file's camera is, what the app showed, and which system you use.
**Never attach private videos.** If we need a sample, we will ask for the smallest one that shows the problem.

## Code

- Python engine in `healvideo/`, window in `app/`. The two talk through JSON lines (`healvideo serve`). See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
- Run `python -m pytest` before you open a pull request. Add a test when you change behavior.
- Keep changes small. Prefer deleting code to adding it.
- Contributions are accepted under GPL-3.0-or-later.
