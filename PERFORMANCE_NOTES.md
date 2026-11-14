# Performance notes (Phase E, measured 2026-11-14)

Numbers: `py tools/bench.py [--live]` -> `BENCHMARKS.md`. Same-PC comparisons only.

## What the measurements say

| Thing | Cost | Verdict |
|---|---|---|
| One template search | ~5 ms | cheap |
| Whole-frame state check (`detect_state`, Crest) | 55-125 ms | fine: scripts pause 0.8 s per tick anyway |
| ADB screenshot (live) | 180-230 ms | the biggest single cost per tick |
| Repeated searches of the same template on one frame (one tick) | 2 of 21 | a per-frame cache would save ~10 ms: **not done** |
| Energy read (OCR, 6 voters) | ~0.8 s | runs in a background thread once a minute: fine |
| Whole-screen OCR (palace/quest names) | ~0.5 s | only on the palace / quest list screens |
| GUI idle (Dashboard, Live View off) | ~1-3% of one core | fine (includes the measuring loop) |

A tick is ~230 ms screenshot + ~100 ms detection + the 0.8 s pause. Faster vision cannot make
farming faster; only a shorter `TICK` could, and that changes timing against the real game
(double taps), so it needs live testing before anyone tries it.

## Decisions
- **No hot-path code changed.** The ideas in IMPROVEMENT_PLAN phase E (per-frame cache, reordering
  the state search, regions) gain ~1-10% of a tick or change which state wins (the order of `STATES`
  is the priority), so the risk is not worth it.
- **Feeding scripts from the Live View video** (saves ~200 ms per tick) is the only sizeable idea. Not done:
  it touches the core capture path and only pays off together with a shorter `TICK`; try it behind a
  setting with live testing.
- **Download size (90 MB zip):** the text-reader model is only 4 MB (the plan's "29 MB model" was wrong:
  29 MB is the whole `tesseract/` folder, mostly DLLs). `Rerun.exe` is 78 MB, dominated by OpenCV
  (cv2 ~113 MB on disk, the Live View needs its FFmpeg), numpy (~55 MB with its libs) and Pillow.
  `opencv-python-headless` might save a few MB; untested, so not changed.
