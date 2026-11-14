"""Save a real 720x1280 game screenshot as a test fixture (read-only: no taps).

    py tools/capture.py <name> [serial]

Writes tests/fixtures/<name>.png using the same adb Rerun uses (the running
adb server is reused, so this is safe next to a running Rerun)."""
from __future__ import annotations

import sys
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rerun.adb import Device, find_adb  # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    name = sys.argv[1].removesuffix(".png")
    serial = sys.argv[2] if len(sys.argv) > 2 else "127.0.0.1:5555"
    dev = Device(find_adb(None), serial)
    dev.connect()
    img = dev.screencap()
    out = ROOT / "tests" / "fixtures" / f"{name}.png"
    if out.exists():
        print(f"{out.name} exists - not overwritten")
        return 1
    cv2.imwrite(str(out), img)
    print(f"saved {out} ({img.shape[1]}x{img.shape[0]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
