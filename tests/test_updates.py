"""rerun/updates.py: repo parsing and version comparison (no network)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from rerun import updates


def test_parse_repo():
    assert updates.parse_repo("me/rerun") == "me/rerun"
    assert updates.parse_repo("https://github.com/me/rerun") == "me/rerun"
    assert updates.parse_repo("https://github.com/me/rerun.git/") == "me/rerun"
    assert updates.parse_repo("") is None
    assert updates.parse_repo("not a repo") is None


def test_is_newer():
    assert updates.is_newer("v1.0.1", "1.0.0")
    assert updates.is_newer("2.0.0", "1.9.9")
    assert not updates.is_newer("v1.0.0", "1.0.0")
    assert not updates.is_newer("0.9", "1.0.0")
    assert not updates.is_newer("", "1.0.0")


def test_bad_setting_raises():
    try:
        updates.check("nonsense")
    except ValueError:
        return
    raise AssertionError("expected ValueError")


if __name__ == "__main__":
    tests = [test_parse_repo, test_is_newer, test_bad_setting_raises]
    for t in tests:
        t()
        print("PASS", t.__name__)
    print(f"{len(tests)}/{len(tests)} passed")
