"""Record every distinct, settled game screen while you navigate (read-only: no taps).

    py tools/record_screens.py <out_dir> [minutes] [serial]

A frame is saved when the screen changed noticeably from the last saved frame
and then stayed still for ~1.5 s (so animations and swipes aren't saved).
Used to collect real Units / Compendium screenshots for OCR work."""
from __future__ import annotations

import sys
import time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rerun.adb import Device, find_adb  # noqa: E402


def diff(a: np.ndarray, b: np.ndarray) -> float:
    sa = cv2.resize(a, (90, 160), interpolation=cv2.INTER_AREA).astype(np.int16)
    sb = cv2.resize(b, (90, 160), interpolation=cv2.INTER_AREA).astype(np.int16)
    return float(np.abs(sa - sb).mean())


def main() -> int:
    out = Path(sys.argv[1])
    minutes = float(sys.argv[2]) if len(sys.argv) > 2 else 10
    serial = sys.argv[3] if len(sys.argv) > 3 else "127.0.0.1:5555"
    out.mkdir(parents=True, exist_ok=True)
    dev = Device(find_adb(None), serial)
    dev.connect()
    end = time.time() + minutes * 60
    saved, prev, still_since, n = None, None, None, 0
    while time.time() < end:
        img = dev.screencap()
        if prev is not None and diff(img, prev) < 1.5:
            still_since = still_since or time.time()
        else:
            still_since = None
        prev = img
        if still_since and time.time() - still_since >= 1.5 and (saved is None or diff(img, saved) > 6):
            n += 1
            name = out / f"{n:03d}_{time.strftime('%H%M%S')}.png"
            cv2.imwrite(str(name), img)
            saved = img
            print(f"saved {name.name}", flush=True)
        time.sleep(0.4)
    print(f"done: {n} screens")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
