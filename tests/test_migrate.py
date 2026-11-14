"""Updates keep your data: rerun/migrate.py (+ the start-up window rerun/migrate_ui.py)."""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rerun import migrate as mg  # noqa: E402


def old_rerun(d: Path) -> Path:
    """A folder that looks like a used Rerun."""
    (d / "history").mkdir(parents=True)
    (d / "history" / "history.jsonl").write_text('{"kind": "crest"}\n{"kind": "crest"}\n', encoding="utf-8")
    (d / "history" / "thumb_1.jpg").write_bytes(b"jpg")
    (d / "units").mkdir()
    (d / "units" / "roster.json").write_text(json.dumps({"Clyde": {}, "Nies": {}}), encoding="utf-8")
    (d / "units" / "targets.json").write_text('{"global": 100}', encoding="utf-8")
    (d / "stats.json").write_text('{"Instance 1": {"crest.runs": 55}}', encoding="utf-8")
    (d / "crest_log.jsonl").write_text('{"type": "run"}\n', encoding="utf-8")
    (d / "license.json").write_text('{"key": "RERUN-X"}', encoding="utf-8")
    (d / "config.yaml").write_text("appearance: dark\n", encoding="utf-8")
    (d / "data" / "gscompanion" / "raw").mkdir(parents=True)
    (d / "data" / "gscompanion" / "units.json").write_text("{}", encoding="utf-8")
    (d / "data" / "gscompanion" / "raw" / "page.md").write_text("x", encoding="utf-8")
    (d / "templates").mkdir()
    (d / "templates" / "stock.png").write_bytes(b"same")
    (d / "templates" / "mine.png").write_bytes(b"captured by you")
    (d / "templates" / "tuned.png").write_bytes(b"same2")
    (d / "templates" / "_meta.json").write_text(json.dumps({
        "stock": {"source": "restart"}, "mine": {"source": None},
        "tuned": {"source": "restart", "threshold": 0.7}}), encoding="utf-8")
    (d / "routines").mkdir()
    (d / "routines" / "my_route.yaml").write_text("steps: []\n", encoding="utf-8")
    (d / "Rerun.exe").write_bytes(b"old exe")
    return d


def new_copy(d: Path) -> Path:
    """A freshly built Rerun folder: exe, stock templates, a default config."""
    d.mkdir(parents=True, exist_ok=True)
    (d / "Rerun.exe").write_bytes(b"new exe")
    (d / "config.yaml").write_text("appearance: auto\n", encoding="utf-8")
    (d / "templates").mkdir()
    (d / "templates" / "stock.png").write_bytes(b"same")
    (d / "templates" / "tuned.png").write_bytes(b"same2")
    (d / "templates" / "_meta.json").write_text(json.dumps({
        "stock": {"source": "restart"}, "tuned": {"source": "restart"}}), encoding="utf-8")
    return d


def tree_hash(d: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(d.rglob("*")):
        if p.is_file():
            h.update(str(p.relative_to(d)).encode() + p.read_bytes())
    return h.hexdigest()


def test_new_copy_gets_everything_and_old_folder_is_untouched():
    with tempfile.TemporaryDirectory() as t:
        old, new = old_rerun(Path(t) / "old"), new_copy(Path(t) / "new")
        before = tree_hash(old)
        assert mg.has_user_data(old) and not mg.has_user_data(new)
        done = mg.import_data(old, new)
        assert tree_hash(old) == before                                  # never changed
        assert mg.has_user_data(new)
        for f in ("stats.json", "crest_log.jsonl", "license.json", "history/history.jsonl",
                  "history/thumb_1.jpg", "units/roster.json", "units/targets.json",
                  "data/gscompanion/units.json", "routines/my_route.yaml", "templates/mine.png"):
            assert (new / f).read_bytes() == (old / f).read_bytes(), f
        assert not (new / "data" / "gscompanion" / "raw").exists()        # scraped pages stay
        assert (new / "config.yaml").read_text() == "appearance: dark\n"
        assert (new / "config.before_import.yaml").read_text() == "appearance: auto\n"
        assert (new / "Rerun.exe").read_bytes() == b"new exe"             # the update stays
        meta = json.loads((new / "templates" / "_meta.json").read_text())
        assert meta["tuned"]["threshold"] == 0.7 and "mine" in meta       # your template changes
        assert "templates/" in done and done["templates/"] == 2           # stock one not copied
        assert json.loads((new / "migrated_from.json").read_text())["from"] == str(old.resolve())
        again = mg.import_data(old, new)
        assert set(again) == {"config.yaml"}                              # nothing doubled


def test_replace_keeps_a_backup_of_this_folders_data():
    with tempfile.TemporaryDirectory() as t:
        old, new = old_rerun(Path(t) / "old"), new_copy(Path(t) / "new")
        (new / "stats.json").write_text('{"fresh": {}}', encoding="utf-8")
        (new / "history").mkdir()
        (new / "history" / "history.jsonl").write_text('{"kind": "new"}\n', encoding="utf-8")
        mg.import_data(old, new, replace=True)
        assert json.loads((new / "stats.json").read_text()) == {"Instance 1": {"crest.runs": 55}}
        assert (new / "history" / "history.jsonl").read_text().count("crest") == 2
        backup = next((new / "backups").glob("before_import_*"))
        assert json.loads((backup / "stats.json").read_text()) == {"fresh": {}}
        assert "new" in (backup / "history" / "history.jsonl").read_text()


def test_refuses_own_folder_and_empty_folders():
    with tempfile.TemporaryDirectory() as t:
        old, new = old_rerun(Path(t) / "old"), new_copy(Path(t) / "new")
        for a, b in ((old, old), (new, old)):
            try:
                mg.import_data(a, b)
            except ValueError:
                continue
            raise AssertionError((a, b))


def test_finds_previous_installs_newest_and_remembers_choice():
    with tempfile.TemporaryDirectory() as t:
        home, reg = Path(t), Path(t) / "registry" / "installs.json"
        a = old_rerun(home / "Downloads" / "Rerun" / "Rerun")       # found by scanning
        b = old_rerun(home / "Games" / "Rerun")                     # found through the registry
        mg.remember(b, reg)
        new = new_copy(home / "Desktop" / "Rerun new")
        found = mg.find_previous(new, reg, home)
        assert set(found) == {a.resolve(), b.resolve()}, found
        assert new.resolve() not in found
        assert "2 units" in mg.describe(a) and "2 History entries" in mg.describe(a)
        assert not mg.was_declined(new, reg)
        mg.mark_declined(new, reg)
        assert mg.was_declined(new, reg)


def test_start_up_window_imports_the_chosen_folder():
    import tkinter as tk
    from rerun import ios
    from rerun.migrate_ui import ImportPage
    with tempfile.TemporaryDirectory() as t:
        old, new = old_rerun(Path(t) / "old"), new_copy(Path(t) / "new")
        root = tk.Tk()
        try:
            ios.init(root, "light")
            got = []
            page = ImportPage(root, new, [old], got.append)
            page.pack()
            root.update()
            assert page.choice.get() == str(old)                    # the fullest is preselected
            page.do_import()
            assert got and "Units" in got[0] and (new / "units" / "roster.json").exists()
        finally:
            root.destroy()


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
