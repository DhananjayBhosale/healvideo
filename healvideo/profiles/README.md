# Camera profiles

One JSON file per camera and recording mode. A profile holds the H.265 decoder settings
(VPS/SPS/PPS) that a broken file is missing, so it can be rebuilt without a reference clip.

Make one from a good clip recorded in the same mode:

```bash
python -m healvideo profile-make GOOD_CLIP.MP4 \
  --name "DJI Osmo Action 3, 1080p 50fps HEVC" \
  --match "DJI OsmoAction3"
```

`--match` is text that appears in the first megabyte of that camera's files. Profiles are
matched on it, so make it specific to the camera (and the mode, if the file carries a mode string).

**Contributing a profile:** only submit profiles made from a clip you recorded yourself.
A profile contains no picture data, only decoder settings.

Profiles in this folder ship with the app. Status: none yet. The first one
(DJI Osmo Action 3, 1080p 50fps) is made once the tools run in the dev environment.
