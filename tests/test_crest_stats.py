"""Phase 1: crest ledger, 4+/Burst/Lv4 statistics and History reconstruction."""
from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from rerun.crest_stats import CrestLedger, crest_summary, format_summary, game_day, rate_text  # noqa: E402
from tests.test_scripts import Sim, Screen, crest_equip_screen, fast, make_ctx, run  # noqa: E402
from rerun.scripts import CrestScript  # noqa: E402

DAY = 86400.0
# 2026-11-14 18:00 UTC = 12:00 game time (UTC-6), well inside one game day
NOW = 1794679200.0


def test_rate_text_is_plain():
    assert rate_text(1, 140) == "1 drop per 140 runs"
    assert rate_text(0, 30) == "none in 30 runs"
    assert rate_text(3, 10) == "1 drop per 3.3 runs"
    assert rate_text(0, 0) == "no runs recorded"


def test_game_day_rolls_over_at_reset():
    # 11:59 UTC = 05:59 game time -> still the previous game day
    from datetime import datetime, timezone
    reset = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc).timestamp()  # 06:00 UTC-6
    assert (game_day(reset + 60) - game_day(reset - 60)).days == 1
    assert game_day(reset + 60) == game_day(reset + DAY - 60)


def test_lv4_is_never_counted_as_4plus_and_windows_are_separate():
    with tempfile.TemporaryDirectory() as d:
        led = CrestLedger(d)
        old = NOW - 3 * DAY
        for i in range(10):
            led.add_run("A", "s1", t=old + i)
        led.add_drop("A", "s1", "lv4", "scrapped", t=old + 5)
        led.add_drop("A", "s1", "4+", "kept", t=old + 9)
        for i in range(5):
            led.add_run("A", "s2", t=NOW - 100 + i)
        led.add_drop("A", "s2", "burst", "kept", t=NOW - 50)
        led.add_drop("A", "s2", "lv3", "scrapped", t=NOW - 40)
        s = led.summary("A", now=NOW)
    assert s["all"]["drops"]["4+"] == 1 and s["all"]["drops"]["lv4"] == 1, s["all"]
    assert s["all"]["drops"]["burst"] == 1 and s["all"]["runs"] == 15
    assert s["today"]["drops"]["4+"] == 0 and s["today"]["drops"]["burst"] == 1
    assert s["today"]["runs"] == 5
    assert s["session_id"] == "s2" and s["session"]["drops"]["burst"] == 1
    assert s["session"]["drops"]["4+"] == 0
    assert s["since_4+"] == 5, s["since_4+"]      # runs after the 4+
    assert s["rate_4+"] == "1 drop per 15 runs"
    assert s["last_notable"]["rarity"] == "burst"


def test_ledger_survives_restart_and_torn_line():
    with tempfile.TemporaryDirectory() as d:
        led = CrestLedger(d)
        led.add_run("A", "s", t=NOW)
        led.add_drop("A", "s", "4+", "kept", t=NOW)
        with (Path(d) / "crest_log.jsonl").open("a", encoding="utf-8") as f:
            f.write('{"type": "run", "t": 1')  # crash mid-write
        again = CrestLedger(d)
        assert len(again.records) == 2
        again.add_drop("A", "s", "burst", "kept", t=NOW)   # must not be glued to the torn line
        third = CrestLedger(d)
        assert len(third.records) == 3
        assert third.summary("A", now=NOW)["all"]["drops"]["burst"] == 1


def test_notable_drop_keeps_a_screenshot():
    with tempfile.TemporaryDirectory() as d:
        led = CrestLedger(d)
        img = np.zeros((1280, 720, 3), np.uint8)
        r4 = led.add_drop("A", "s", "4+", "kept", image=img)
        r3 = led.add_drop("A", "s", "lv3", "scrapped", image=img)
        assert led.shot_path(r4) is not None and led.shot_path(r4).exists()
        assert "shot" not in r3 or r3["shot"] is None


def test_reconstruction_is_repeatable_and_maps_rarities():
    hist = [
        {"t": NOW - 500, "instance": "A", "script": "crest", "kind": "crest", "rarity": "lv3",
         "action": "scrapped", "detail": "x"},
        {"t": NOW - 400, "instance": "A", "script": "crest", "kind": "crest", "rarity": "5+",
         "action": "kept", "detail": "x", "thumb": "b.jpg"},
        {"t": NOW - 300, "instance": "A", "script": "crest", "kind": "crest", "rarity": "?",
         "action": "stopped", "detail": "x"},
        {"t": NOW - 200, "instance": "A", "script": "crest", "kind": "energy", "detail": "potion"},
    ]
    with tempfile.TemporaryDirectory() as d:
        thumbs = Path(d) / "thumbs"
        thumbs.mkdir()
        (thumbs / "b.jpg").write_bytes(b"jpg")
        led = CrestLedger(d)
        first = led.reconstruct(hist, {"A": {"crest.runs": 30}}, thumbs)
        second = CrestLedger(d).reconstruct(hist, {"A": {"crest.runs": 30}}, thumbs)
        s = CrestLedger(d).summary("A", now=NOW)
        assert (Path(d) / "crest_shots" / "b.jpg").exists()
    assert first == {"drops": 3, "baselines": 1}, first
    assert second == {"drops": 0, "baselines": 0}, second
    assert s["all"]["drops"]["burst"] == 1 and s["all"]["drops"]["lv3"] == 1
    assert s["all"]["drops"]["?"] == 1 and s["uncertain"] == 1
    assert s["all"]["runs"] == 30 and s["baseline_runs"] == 30
    assert s["reconstructed"] == 3
    text = format_summary(s)
    assert "not a prediction" in text and "no dates" in text


def test_restart_does_not_reimport_crests_already_logged_live():
    """Seen on the installed app 2026-11-14 14:10: after a restart the History
    rebuild imported 11 crests the script had already logged live."""
    with tempfile.TemporaryDirectory() as d:
        led = CrestLedger(d)
        led.add_drop("A", "s", "lv3", "scrapped", t=NOW)          # live
        hist = [{"t": NOW + 0.004, "instance": "A", "script": "crest", "kind": "crest",
                 "rarity": "lv3", "action": "scrapped", "detail": "x"},   # same crest in History
                {"t": NOW - 600, "instance": "A", "script": "crest", "kind": "crest",
                 "rarity": "lv3", "action": "scrapped", "detail": "x"}]   # older, not live
        added = CrestLedger(d).reconstruct(hist, {})
        assert added["drops"] == 1, added
        assert CrestLedger(d).summary("A", now=NOW)["all"]["drops"]["lv3"] == 2


def test_duplicates_written_by_the_early_build_are_ignored_not_deleted():
    with tempfile.TemporaryDirectory() as d:
        led = CrestLedger(d)
        led.add_drop("A", "s", "lv3", "scrapped", t=NOW)
        # what the early Phase 1 build appended on restart
        led._append({"type": "drop", "t": NOW + 0.004, "instance": "A", "session": "history",
                     "script": "crest", "rarity": "lv3", "action": "scrapped",
                     "source": "history", "confidence": "verified", "key": f"h:A:{NOW + 0.004}"})
        again = CrestLedger(d)
        assert len(again.records) == 2                         # file untouched
        s = again.summary("A", now=NOW)
        assert s["all"]["drops"]["lv3"] == 1 and s["reconstructed"] == 0, s["all"]


def test_reconstruction_on_real_installed_history_copy():
    """The user's real History (backed up in Phase 0) rebuilds without errors."""
    backups = sorted((ROOT / "backups").glob("installed_*/history/history.jsonl"))
    if not backups:
        print("  (skipped: no backup of the installed History)")
        return
    path = backups[-1]
    entries = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    stats = json.loads((path.parents[1] / "stats.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as d:
        led = CrestLedger(d)
        added = led.reconstruct(entries, stats, path.parent / "thumbs")
        s = led.summary(None)
    crest_entries = [e for e in entries if e.get("kind") == "crest"]
    assert added["drops"] == len(crest_entries)
    assert sum(s["all"]["drops"].values()) == len(crest_entries)


def _crest_run(icon: str, keep: str = "4+ and Burst only"):
    fast()
    screens = {"equip": crest_equip_screen(icon), "autoloop": Screen([("looping_button", 450, 960)])}
    dev = Sim(screens, "equip", {("equip", "redeploy_button"): "autoloop"})
    orig = Sim.tap

    def tap(self, x, y):
        orig(self, x, y)
        if self.tapped[-1] == "looping_button":
            ctx.stop_event.set()
    dev.tap = tap.__get__(dev)
    d = tempfile.mkdtemp()
    ctx = make_ctx(Path(d), dev, CrestScript)
    ctx.crests = CrestLedger(d)
    result = run(CrestScript(ctx, {"keep": keep}))
    return result, ctx


def test_crest_script_records_4plus_lv4_and_lv3_in_the_ledger():
    result, ctx = _crest_run("crest_icon_lv4plus")
    assert result == "finished: 4+ crest"
    s = ctx.crests.summary("Test")
    assert s["all"]["drops"]["4+"] == 1 and s["session"]["drops"]["4+"] == 1
    assert s["last_notable"]["action"] == "kept"
    assert ctx.crests.shot_path(s["last_notable"]) is not None

    result, ctx = _crest_run("crest_icon_lv4")  # scrapped with the default keep setting
    s = ctx.crests.summary("Test")
    assert s["all"]["drops"]["lv4"] == 1 and s["all"]["drops"]["4+"] == 0, s["all"]

    result, ctx = _crest_run("crest_icon_lv3")
    s = ctx.crests.summary("Test")
    assert s["all"]["drops"]["lv3"] == 1 and s["last_drop"]["action"] == "scrapped"


def test_crest_script_records_burst():
    fast()
    dev = Sim({"burst": Screen([], extra=[("crest_icon_lv5plus", 250, 480)])}, "burst", {})
    d = tempfile.mkdtemp()
    ctx = make_ctx(Path(d), dev, CrestScript)
    ctx.crests = CrestLedger(d)
    assert run(CrestScript(ctx, {})) == "finished: crest burst"
    s = ctx.crests.summary("Test")
    assert s["all"]["drops"]["burst"] == 1 and s["today"]["drops"]["burst"] == 1


def test_same_crest_seen_again_after_a_popup_is_not_counted_twice():
    """Seen live 2026-11-14 14:00: Redeploy -> out of energy -> potion -> the same
    Equip Crest screen again; 'Freeze Resistance Lv3' was recorded twice."""
    fast()
    dev = Sim({"equip": crest_equip_screen("crest_icon_lv3")}, "equip", {})
    d = tempfile.mkdtemp()
    ctx = make_ctx(Path(d), dev, CrestScript)
    ctx.crests = CrestLedger(d)
    s = CrestScript(ctx, {"verify_text": False})
    s.on_start()
    s.handle_equip_crest_screen(dev.screencap())
    s.crest_handled_at = 0.0          # popup handled, screen is back
    s.handle_equip_crest_screen(dev.screencap())
    st = ctx.stats.get("Test")
    assert st["crest.crest_lv3"] == 1 and st["crest.scrapped"] == 1, st
    assert ctx.crests.summary("Test")["all"]["drops"]["lv3"] == 1
    assert dev.tapped.count("redeploy_button") == 2, dev.tapped  # still scraps / moves on
    # After a finished run the next crest is new, even with the same rarity.
    s.count_run()
    s.crest_handled_at = 0.0
    s.handle_equip_crest_screen(dev.screencap())
    assert ctx.stats.get("Test")["crest.crest_lv3"] == 2
    assert ctx.crests.summary("Test")["all"]["drops"]["lv3"] == 2


def test_same_rarity_different_title_is_a_new_crest():
    fast()
    dev = Sim({"equip": crest_equip_screen("crest_icon_lv3")}, "equip", {})
    ctx = make_ctx(Path(tempfile.mkdtemp()), dev, CrestScript)
    s = CrestScript(ctx, {})
    s.judged = {"rarity": "lv3", "title": "Freeze Resistance Lv3"}
    assert s.same_crest_again("lv3", "Freeze Resistance Lv3")
    assert s.same_crest_again("lv3", "")            # title unreadable: trust the run count
    assert not s.same_crest_again("lv3", "Break Power Lv3")
    assert not s.same_crest_again("lv3+", "Freeze Resistance Lv3")


def test_crest_script_without_ledger_still_works():
    """Contexts built elsewhere (Queue, tests, custom tools) have no ledger."""
    fast()
    dev = Sim({"burst": Screen([], extra=[("crest_icon_lv5plus", 250, 480)])}, "burst", {})
    ctx = make_ctx(Path(tempfile.mkdtemp()), dev, CrestScript)
    assert ctx.crests is None
    assert run(CrestScript(ctx, {})) == "finished: crest burst"


def test_manager_rebuilds_from_history_once():
    import shutil
    from rerun.manager import Manager
    root = Path(tempfile.mkdtemp())
    shutil.copytree(ROOT / "routines", root / "routines")
    (root / "history").mkdir()
    (root / "history" / "history.jsonl").write_text(json.dumps(
        {"t": time.time(), "instance": "Instance 1", "script": "crest", "kind": "crest",
         "rarity": "4+", "action": "kept", "detail": "4+ crest - kept"}) + "\n", encoding="utf-8")
    m = Manager(root)
    assert m._crest_rebuild["drops"] == 1
    m2 = Manager(root)
    assert m2._crest_rebuild["drops"] == 0
    assert m2.crests.summary("Instance 1")["all"]["drops"]["4+"] == 1
    assert crest_summary(m2.crests.records)["today"]["drops"]["4+"] == 1


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            import traceback
            print(f"FAIL {t.__name__}: {e}")
            traceback.print_exc()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
