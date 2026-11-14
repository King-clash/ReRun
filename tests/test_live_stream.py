"""Live View video stream (rerun/live_stream.py) without an emulator: a fake 'adb' plays a
real one-second screenrecord clip (tests/fixtures/live_stream.h264, 180x320)."""
from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rerun.live_stream import LiveStream  # noqa: E402

CLIP = ROOT / "tests" / "fixtures" / "live_stream.h264"
FAKE_ADB = """import sys, time
data = open(sys.argv[1], 'rb').read()
for i in range(0, len(data), 4096):
    sys.stdout.buffer.write(data[i:i + 4096]); sys.stdout.buffer.flush(); time.sleep(0.002)
"""


class ClipStream(LiveStream):
    def __init__(self, script: Path, clip: Path, **kw):
        super().__init__("adb", "fake", **kw)
        self.script, self.clip = script, clip

    def _cmd(self):
        return [sys.executable, str(self.script), str(self.clip)]


def wait(cond, s=15.0):
    end = time.monotonic() + s
    while time.monotonic() < end and not cond():
        time.sleep(0.05)
    return cond()


def test_decodes_frames_and_restarts_after_each_recording():
    with tempfile.TemporaryDirectory() as d:
        script = Path(d) / "fake_adb.py"
        script.write_text(FAKE_ADB, encoding="utf-8")
        s = ClipStream(script, CLIP).start()
        try:
            assert wait(lambda: s.seq > 5), (s.seq, s.error)
            f = s.frame
            assert f.ndim == 3 and f.shape[2] == 3 and f.shape[0] > f.shape[1]   # portrait BGR
            first = s.seq
            # the clip ends like screenrecord's time limit: the stream starts a new session
            assert wait(lambda: s.seq > first + 20, 20), (first, s.seq)
            assert not s.failed
        finally:
            s.stop()
        assert wait(lambda: not s._thread.is_alive(), 10)


def test_gives_up_when_there_is_no_video():
    with tempfile.TemporaryDirectory() as d:
        script = Path(d) / "fake_adb.py"
        script.write_text("import sys\n", encoding="utf-8")          # exits at once, no video
        s = ClipStream(script, CLIP)
        try:
            s.start()
            assert wait(lambda: s.failed, 30), s.error
            assert s.seq == 0 and s.error
        finally:
            s.stop()


def test_size_follows_orientation():
    assert LiveStream("adb", "x").size == (450, 800)
    assert LiveStream("adb", "x", portrait=False).size == (800, 450)


if __name__ == "__main__":
    failed = 0
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as e:  # noqa: BLE001
            import traceback
            failed += 1
            print(f"FAIL {t.__name__}: {e!r}")
            traceback.print_exc()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
