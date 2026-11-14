"""Typed events (rerun/events.py) and the config.yaml sanity check (rerun/configcheck.py)."""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rerun import events  # noqa: E402
from rerun.configcheck import check_config  # noqa: E402
from rerun.manager import DEFAULT_CONFIG, Instance, Manager  # noqa: E402


def test_every_event_the_manager_emits_is_well_formed():
    d = Path(tempfile.mkdtemp())
    try:
        m = Manager(d)
        seen = []
        m.listeners.append(seen.append)
        m.log("Instance 1", "hello")
        m.notify("Instance 1", "a message", ping=False)
        m._set_status(Instance("Instance 1", "x", "crest"), "running", "crest")
        m.history.add("Instance 1", "crest", "crest", "lv3 crest - scrapped", rarity="lv3")
        kinds = {e["type"] for e in seen}
        assert {"log", "notify", "status", "history"} <= kinds, kinds
        bad = [p for e in seen for p in events.problems(e)]
        assert not bad, bad
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_problems_flags_unknown_and_incomplete_events():
    assert events.problems({"type": "nope"})
    assert events.problems({"type": "log", "instance": "x"})
    assert not events.problems({"type": "notify", "instance": "x", "message": "m"})


def test_default_config_is_clean_and_typos_are_reported():
    assert check_config(DEFAULT_CONFIG, DEFAULT_CONFIG) == []
    out = check_config({"discord": {"enable": True, "token": 5}, "close_to_tray": "yes",
                        "colour": "red", "script_settings": {"anything": {"goes": 1}}}, DEFAULT_CONFIG)
    text = "\n".join(out)
    assert "'discord.enable'" in text and "'discord.token' should be text" in text, text
    assert "'close_to_tray' should be true/false but is text" in text and "'colour'" in text, text
    assert "script_settings" not in text, text        # free-form sections are not checked
    assert check_config({"discord": {"channel_id": None}}, DEFAULT_CONFIG) == []   # empty = default


def test_manager_logs_config_warnings_at_start():
    d = Path(tempfile.mkdtemp())
    try:
        (d / "config.yaml").write_text("close_to_tray: maybe\nbogus: 1\n", encoding="utf-8")
        m = Manager(d)
        warn = [e["message"] for e in m.log_entries if e["level"] == "warn"]
        assert any("'close_to_tray'" in w for w in warn) and any("'bogus'" in w for w in warn), warn
    finally:
        shutil.rmtree(d, ignore_errors=True)


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
