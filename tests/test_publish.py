"""tools/publish.py helpers: version bump keeps line endings, notes/changelog checks, checksums,
left-out-work detection and live-page verification (no git, no GitHub, nothing published)."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools import publish  # noqa: E402

GOOD_NOTES = ("# Rerun 1.2.3\n\n" + "This update changes things you can see. " * 12
              + "\n\nWhat has and has not been checked: tests pass; the game part was not tested.\n")


def test_version_bump_keeps_the_files_own_line_endings():
    for eol in ("\n", "\r\n"):
        src = f'__version__ = "1.0.2"{eol}other = 1{eol}'
        out = publish.bump_version_text(src, "1.0.3")
        assert out == f'__version__ = "1.0.3"{eol}other = 1{eol}', repr(out)
    try:
        publish.bump_version_text("x = 1\n", "1.0.3")
        raise AssertionError("should refuse a file without __version__")
    except ValueError:
        pass


def test_changelog_needs_a_heading_for_the_version():
    log = "# Changelog\n\n## 1.2.3 — Something\n- x\n\n## Unreleased — y\n"
    assert publish.changelog_has("1.2.3", log) and not publish.changelog_has("1.2.4", log)
    assert not publish.changelog_has("1.2", log)          # no partial matches
    assert publish.changelog_has("1.2.3", "## v1.2.3\n")


def test_thin_or_untested_notes_are_refused():
    assert publish.notes_problems(GOOD_NOTES) == []
    assert publish.notes_problems("Rerun 1.2.3. See CHANGELOG.md.")            # far too short
    assert publish.notes_problems("word " * 100 + "See CHANGELOG for details.")  # no testing section
    no_testing = "This update adds a lot of things for you. " * 15
    assert any("tested" in p for p in publish.notes_problems(no_testing))


def test_checksums_use_the_sha256sum_format():
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "a.zip"
        f.write_bytes(b"hello")
        text = publish.sums_text([f])
        assert text == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824  a.zip\n", text


def test_branches_with_work_not_in_head_are_listed():
    merged = {"main", "release/x"}
    left = publish.unmerged_branches(["main", "feat/icon", "release/x", "data/gsc"], "release/x",
                                     lambda b: b in merged)
    assert left == ["feat/icon", "data/gsc"], left


def test_live_release_page_is_checked_against_the_notes():
    notes = "Line one.\n\nLine   two.\n"
    ok = {"body": "Line one.\r\n\r\nLine two.", "isDraft": False,
          "assets": [{"name": "Rerun-1.2.3.zip", "size": 10}, {"name": "SHA256SUMS.txt", "size": 80}]}
    assert publish.verify_release(ok, notes, "Rerun-1.2.3.zip") == []
    assert publish.verify_release({**ok, "body": "See CHANGELOG"}, notes, "Rerun-1.2.3.zip")
    assert any("SHA256SUMS" in p for p in publish.verify_release(
        {**ok, "assets": ok["assets"][:1]}, notes, "Rerun-1.2.3.zip"))
    assert any("empty" in p for p in publish.verify_release(
        {**ok, "assets": [{"name": "Rerun-1.2.3.zip", "size": 0}, ok["assets"][1]]}, notes, "Rerun-1.2.3.zip"))
    assert any("draft" in p for p in publish.verify_release({**ok, "isDraft": True}, notes, "Rerun-1.2.3.zip"))
    assert publish.verify_release({**ok, "isDraft": True}, notes, "Rerun-1.2.3.zip", expect_draft=True) == []


def test_real_notes_files_pass_the_notes_check():
    for f in sorted((ROOT / "release_notes").glob("v*.md")):
        assert publish.notes_problems(f.read_text(encoding="utf-8")) == [], f.name


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
