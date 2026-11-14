"""rerun/errlog.py: quiet failures are written once, rate-limited, and never raise."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from rerun import errlog


def test_note_writes_once_per_window():
    with tempfile.TemporaryDirectory() as d:
        errlog.init(d)
        errlog._last.clear()
        for _ in range(3):
            try:
                raise ValueError("boom")
            except ValueError as e:
                errlog.note("test.place", e)
        text = (Path(d) / "error.log").read_text(encoding="utf-8")
        assert text.count("ValueError: boom") == 1 and "[test.place]" in text
        try:
            raise KeyError("other")
        except KeyError as e:
            errlog.note("test.place", e)
        assert "other" in (Path(d) / "error.log").read_text(encoding="utf-8")


def test_note_without_init_is_silent():
    errlog._path = None
    errlog.note("x", ValueError("y"))


if __name__ == "__main__":
    tests = [test_note_writes_once_per_window, test_note_without_init_is_silent]
    for t in tests:
        t()
        print("PASS", t.__name__)
    print(f"{len(tests)}/{len(tests)} passed")
