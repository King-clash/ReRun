"""debug/ keeps only the newest screenshots."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rerun.scripts.base import prune_debug_folder  # noqa: E402


def test_oldest_screenshots_go_and_other_files_stay():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        for i in range(10):
            (d / f"20261115_10000{i}_crest_stuck.png").write_bytes(b"x")
        (d / "notes.txt").write_text("keep me")
        assert prune_debug_folder(d, keep=4) == 6
        left = sorted(p.name for p in d.iterdir())
        assert left == ["20261115_100006_crest_stuck.png", "20261115_100007_crest_stuck.png",
                        "20261115_100008_crest_stuck.png", "20261115_100009_crest_stuck.png", "notes.txt"], left
        assert prune_debug_folder(d, keep=4) == 0               # nothing more to remove


def test_missing_folder_is_not_an_error():
    assert prune_debug_folder(Path(tempfile.gettempdir()) / "no_such_debug_folder_xyz") == 0


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
