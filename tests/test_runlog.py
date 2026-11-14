"""rerun.log (persistent run log) and the per-run session summary."""
from __future__ import annotations

import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rerun import runlog  # noqa: E402
from rerun.manager import Instance, Manager  # noqa: E402


def test_lines_are_appended_with_level_and_instance():
    d = Path(tempfile.mkdtemp())
    try:
        runlog.init(d)
        runlog.write("Instance 1", "Tapping Battle", "info")
        runlog.write("Instance 1", "Crashed: boom\nTraceback line", "error")
        text = (d / "rerun.log").read_text(encoding="utf-8")
        assert "INFO  [Instance 1] Tapping Battle" in text and "ERROR [Instance 1] Crashed: boom" in text
        assert "\n    Traceback line" in text  # continuation lines are indented
    finally:
        shutil.rmtree(d)  # no handle is held: the folder can be deleted on Windows


def test_rotation_keeps_a_few_old_files():
    d = Path(tempfile.mkdtemp())
    try:
        runlog.init(d)
        old = runlog.MAX_BYTES
        runlog.MAX_BYTES = 200
        for i in range(60):
            runlog.write("x", f"line {i} " + "y" * 20)
        runlog.MAX_BYTES = old
        names = sorted(p.name for p in d.iterdir())
        assert "rerun.log" in names and "rerun.log.1" in names, names
        assert not (d / "rerun.log.4").exists()
    finally:
        shutil.rmtree(d)


def test_manager_log_reaches_the_file_and_session_summary_is_recorded():
    d = Path(tempfile.mkdtemp())
    try:
        m = Manager(d)
        m.log("Instance 1", "hello from a test")
        inst = Instance("Instance 1", "127.0.0.1:5555", "crest")
        before = dict(m.stats.get("Instance 1"))
        m.stats.incr("Instance 1", "crest.runs", 3)
        m.stats.incr("Instance 1", "crest.crest_lv3", 2)
        m.stats.incr("Instance 1", "crest.potions_used", 1)
        m._record_session(inst, time.time() - 125, before, "finished: runs done")
        entry = m.history.recent(5)[0]
        assert entry["kind"] == "session" and "2 min" in entry["detail"], entry
        assert "3 run(s)" in entry["detail"] and "2 crest(s)" in entry["detail"] \
            and "1 potion(s)" in entry["detail"] and "finished: runs done" in entry["detail"], entry
        text = (d / "rerun.log").read_text(encoding="utf-8")
        assert "hello from a test" in text and "Session ended after 2 min" in text, text
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_closest_screens_names_the_best_matches_on_a_real_screen():
    import cv2
    from rerun.adb import FakeDevice
    from rerun.engine import Context
    from rerun.scripts import CrestScript
    from rerun.stats import Stats
    from rerun.vision import TemplateStore, Vision
    store = TemplateStore(ROOT / "templates")
    if not store.has("exploring_button"):
        return
    img = cv2.imread(str(ROOT / "tests" / "fixtures" / "home.png"))
    ctx = Context(instance="t", device=FakeDevice([img]), vision=Vision(store), stats=Stats(), routines={},
                  base_resolution=(720, 1280), log=lambda *a: None, notify=lambda *a, **k: None)
    text = CrestScript(ctx, {"start_home": False}).closest_screens(img)
    assert text.startswith("exploring_button 0.9"), text
    assert len(text.split(",")) == 3, text


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print("PASS", t.__name__)
        except Exception as e:  # noqa: BLE001
            failed += 1
            print("FAIL", t.__name__, repr(e))
    print(f"{len(tests) - failed}/{len(tests)} passed")
    raise SystemExit(1 if failed else 0)
