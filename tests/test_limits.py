"""Quality-of-life limits for loop farms: stop after N minutes / at a time, keep an energy floor,
cap game restarts per day."""
from __future__ import annotations

import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import rerun.ocr as ocr_mod  # noqa: E402
import rerun.scripts.base as base_mod  # noqa: E402
from rerun.adb import FakeDevice  # noqa: E402
from rerun.engine import Context  # noqa: E402
from rerun.scripts import AnyQuestScript, CrestScript  # noqa: E402
from rerun.scripts.base import Done, Finished  # noqa: E402
from rerun.stats import Stats  # noqa: E402
from rerun.vision import TemplateStore, Vision  # noqa: E402

FIX = ROOT / "tests" / "fixtures"
VISION = Vision(TemplateStore(ROOT / "templates"))


def script(settings=None, cls=CrestScript, img=None):
    notes, logs = [], []
    dev = FakeDevice([img if img is not None else cv2.imread(str(FIX / "home.png"))])
    ctx = Context(instance="t", device=dev, vision=VISION, stats=Stats(), routines={},
                  base_resolution=(720, 1280), log=lambda i, m: logs.append(m),
                  notify=lambda i, m, **k: notes.append(m))
    s = cls(ctx, {"start_home": False, **(settings or {})})
    s.sleep = lambda *a, **k: None
    s.on_start()
    return s, dev, notes, logs


# ---------------------------------------------------------------- time limit
def test_minutes_and_clock_time_limits_combine_to_the_earliest():
    s, _, _, logs = script({"max_minutes": 90})
    assert 89 * 60 < s.time_deadline - time.time() < 91 * 60
    soon = (datetime.now() + timedelta(minutes=30)).strftime("%H:%M")
    s, _, _, logs = script({"max_minutes": 90, "stop_at": soon})
    assert 28 * 60 < s.time_deadline - time.time() < 31 * 60, s.time_deadline - time.time()   # the clock wins
    s, _, _, logs = script({"stop_at": "7:5x"})
    assert s.time_deadline is None and any("not a 24-hour HH:MM" in l for l in logs), logs
    s, _, _, logs = script({})
    assert s.time_deadline is None and not s.time_up() and not s.target_reached()


def test_a_passed_clock_time_means_tomorrow_not_stop_now():
    earlier = (datetime.now() - timedelta(minutes=5)).strftime("%H:%M")
    s, *_ = script({"stop_at": earlier})
    assert 23 * 3600 < s.time_deadline - time.time() < 24 * 3600 + 120
    assert not s.time_up()


def test_time_limit_ends_the_farm_gracefully_with_a_clear_message():
    s, dev, notes, logs = script({"max_minutes": 1})
    s.time_deadline = time.time() - 1                    # the limit has passed
    assert s.time_up() and s.target_reached()
    try:
        s.finish()
        raise AssertionError("should finish")
    except Done as e:
        assert "Time limit reached." in str(e), str(e)


def test_time_limit_on_the_results_screen_closes_it_instead_of_redeploying():
    store = VISION.store
    if not (store.has("results_redeploy") and store.has("ok_button")):
        return
    img = cv2.imread(str(FIX / "loop_results.png"))
    s, dev, notes, logs = script({"max_minutes": 1}, img=img)
    s.time_deadline = time.time() - 1
    redeploy = s.find("results_redeploy", img).center
    try:
        s.handle_results_redeploy(img)
        raise AssertionError("should finish")
    except Done:
        pass
    assert dev.taps and dev.taps[0] != redeploy, (dev.taps, redeploy)
    assert any("Time limit reached - closing results" in l for l in logs), logs


def test_time_limit_applies_to_any_quest_too():
    s, *_ = script({"max_minutes": 5}, cls=AnyQuestScript)
    assert s.time_deadline is not None


# ---------------------------------------------------------------- energy floor
def stub_energy(energy, cost=None):
    real = (ocr_mod.read_energy, ocr_mod.read_energy_cost)
    ocr_mod.read_energy = lambda ocr, screen: energy
    ocr_mod.read_energy_cost = lambda ocr, screen: cost
    return real


def test_energy_floor_stops_before_dropping_below_it():
    s, dev, notes, logs = script({"energy_floor": 80})
    if s.ocr is None:
        return
    real = stub_energy((100, 517), cost=25)
    try:
        try:
            s.energy_gate(None, with_cost=True)                       # 100 - 25 = 75 < 80
            raise AssertionError("should stop")
        except Done as e:
            assert "keep at least 80" in str(e) or "80" in str(e), str(e)
        s._floor_checked_at = -1e9
        s.cfg["energy_floor"] = 70
        s.energy_gate(None, with_cost=True)                           # 75 >= 70: carries on
        # without a cost on this screen (results bar) the last known quest cost is used
        s._floor_checked_at = -1e9
        s.cfg["energy_floor"] = 80
        ocr_mod.read_energy_cost = lambda ocr, screen: None
        try:
            s.energy_gate(None)                                       # still 100 - 25 < 80
            raise AssertionError("should stop on the remembered cost")
        except Done:
            pass
    finally:
        ocr_mod.read_energy, ocr_mod.read_energy_cost = real


def test_energy_floor_off_unreadable_or_throttled_never_stops():
    s, *_ = script({"energy_floor": 0})
    s.energy_gate(None)                                               # off: nothing to read
    s, dev, notes, logs = script({"energy_floor": 500})
    if s.ocr is None:
        return
    real = stub_energy(None)                                          # energy bar unreadable
    try:
        s.energy_gate(None)
        assert any("could not read the energy bar" in l for l in logs), logs
        ocr_mod.read_energy = lambda ocr, screen: (10, 517)
        s.energy_gate(None)                                           # within 20 s of the last look: skipped
    finally:
        ocr_mod.read_energy, ocr_mod.read_energy_cost = real


def test_energy_floor_with_the_real_energy_bar():
    s, dev, notes, logs = script({"energy_floor": 400})
    if s.ocr is None:
        return
    img = cv2.imread(str(FIX / "home.png"))                           # reads 383/517
    try:
        s.energy_gate(img)
        raise AssertionError("383 is below a floor of 400")
    except Done as e:
        assert "383/517" in str(e), str(e)
    s, *_ = script({"energy_floor": 300})
    s.energy_gate(img)


# ---------------------------------------------------------------- restart cap
def test_restart_cap_counts_crashes_but_not_scheduled_restarts():
    s, dev, notes, logs = script({"max_restarts_per_day": 2, "mode_247": True})
    s.restart_game(scheduled=True)                                    # daily relogin / maintenance: free
    s.restart_game(scheduled=True)
    s.restart_game()                                                  # 1
    s.recover_crash()                                                 # 2 (24/7 relaunch after a crash)
    try:
        s.restart_game()                                              # 3 > cap
        raise AssertionError("should stop")
    except Finished as e:
        assert "restart limit reached (2 per game day)" in str(e), str(e)
    assert notes and "limit is 2" in notes[-1], notes


def test_restart_cap_resets_each_game_day_and_zero_means_unlimited():
    s, *_ = script({"max_restarts_per_day": 1})
    s.restart_game()
    real = base_mod.game_now
    base_mod.game_now = lambda: real() + timedelta(days=1)           # next game day
    try:
        s.restart_game()                                              # fresh count: allowed
    finally:
        base_mod.game_now = real
    s, *_ = script({"max_restarts_per_day": 0})
    for _ in range(6):
        s.restart_game()


def test_new_settings_are_offered_with_safe_defaults():
    keys = {x.key: x.default for x in CrestScript.SETTINGS}
    assert keys["max_minutes"] == 0 and keys["stop_at"] == "" and keys["energy_floor"] == 0
    assert keys["max_restarts_per_day"] == 0 and keys["palace_by_day"] == ""


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
