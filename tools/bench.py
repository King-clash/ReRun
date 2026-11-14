"""Timing numbers for Rerun's hot paths, so optimisations are decided by measurement.

    py tools/bench.py             fixtures only (no emulator touched)
    py tools/bench.py --live      also times real ADB screenshots (read-only, ~10 captures)

Prints a table and writes it to BENCHMARKS.md. Numbers depend on the PC: compare runs from the
same machine, before and after a change."""
from __future__ import annotations

import statistics
import sys
import time
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rerun.adb import FakeDevice  # noqa: E402
from rerun.engine import Context  # noqa: E402
from rerun.ocr import OcrUnavailable, get_ocr, read_energy  # noqa: E402
from rerun.scripts import CrestScript  # noqa: E402
from rerun.stats import Stats  # noqa: E402
from rerun.vision import TemplateStore, Vision  # noqa: E402

FIX = ROOT / "tests" / "fixtures"
FRAMES = ["home.png", "party_reigrad.png", "loop_results.png", "equip_crest_lv3.png",
          "crest_palace_list.png", "quest_list_cursed_claw.png"]


def timed(fn, n: int = 7) -> tuple[float, float]:
    """(median ms, best ms) over n runs (one warm-up first)."""
    fn()
    xs = []
    for _ in range(n):
        t = time.perf_counter()
        fn()
        xs.append((time.perf_counter() - t) * 1000)
    return statistics.median(xs), min(xs)


def make_script(img):
    store = TemplateStore(ROOT / "templates")
    ctx = Context(instance="bench", device=FakeDevice([img]), vision=Vision(store), stats=Stats(),
                  routines={}, base_resolution=(720, 1280), log=lambda *a: None,
                  notify=lambda *a, **k: None)
    s = CrestScript(ctx, {"start_home": False})
    s.on_start()
    return s


def main() -> int:
    rows = []
    frames = {n: cv2.imread(str(FIX / n)) for n in FRAMES if (FIX / n).exists()}
    first = next(iter(frames.values()))
    s = make_script(first)
    v = s.ctx.vision

    # 1. one template search (coarse grey pass + colour refine) on a frame where it is absent / present
    for name in ("exploring_button", "battle_button", "crest_palace_target"):
        if not v.store.has(name):
            continue
        for fname in ("home.png", "party_reigrad.png"):
            if fname in frames:
                m, b = timed(lambda: v.find(frames[fname], name))
                rows.append((f"find('{name}') on {fname}", m, b))

    # 2. full state detection (every template of the Crest script, in priority order)
    for fname, img in frames.items():
        sc = make_script(img)
        m, b = timed(lambda: sc.detect_state(img), n=5)
        rows.append((f"Crest detect_state on {fname}  ->  {sc.detect_state(img)}", m, b))

    # 3. diagnostics and OCR
    m, b = timed(lambda: s.closest_screens(first), n=3)
    rows.append(("closest_screens (stuck report)", m, b))
    try:
        ocr = get_ocr(None)
        m, b = timed(lambda: read_energy(ocr, frames["home.png"]), n=3)
        rows.append(("read_energy (OCR, 6 voters)", m, b))
        m, b = timed(lambda: ocr.screen_words(frames["crest_palace_list.png"]), n=3)
        rows.append(("OCR whole screen (screen_words)", m, b))
    except OcrUnavailable:
        rows.append(("OCR (not available on this PC)", 0.0, 0.0))

    # 4. repeated searches of the same template on the same frame within a tick
    calls: dict[tuple, int] = {}
    real = v.find

    def counting(screen, name, threshold=None, region=None):
        k = (id(screen), name, threshold, region)
        calls[k] = calls.get(k, 0) + 1
        return real(screen, name, threshold, region)
    v.find = counting
    img = frames.get("loop_results.png", first)
    sc = s
    state = sc.detect_state(img)
    handler = getattr(sc, f"handle_{state}", None)
    sc.sleep = lambda *a, **k: None
    try:
        if handler:
            handler(img)
    except Exception:  # noqa: BLE001 - a handler may stop the script; only the call counts matter
        pass
    v.find = real
    total, unique = sum(calls.values()), len(calls)
    rows.append((f"one tick on loop_results.png: {total} searches, {unique} distinct "
                 f"({total - unique} repeated)", 0.0, 0.0))

    if "--live" in sys.argv:
        from rerun.adb import Device, find_adb
        dev = Device(find_adb(None), "127.0.0.1:5555")
        dev.connect()
        m, b = timed(dev.screencap, n=8)
        rows.append(("ADB screenshot (live, read-only)", m, b))

    width = max(len(r[0]) for r in rows)
    lines = ["| What | median ms | best ms |", "|---|---:|---:|"]
    for name, m, b in rows:
        lines.append(f"| {name} | {m:.1f} | {b:.1f} |" if m or b else f"| {name} | | |")
    text = "\n".join(lines)
    print(text)
    (ROOT / "BENCHMARKS.md").write_text(
        "# Benchmarks\n\nWritten by `py tools/bench.py` on " + time.strftime("%Y-%m-%d") +
        ". Same-PC comparisons only.\n\n" + text + "\n", encoding="utf-8")
    del width
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
