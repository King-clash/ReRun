"""rerun/qol.py: the pure rules behind the quality-of-life settings."""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rerun import qol  # noqa: E402


def test_hhmm_parsing_and_next_time():
    assert qol.parse_hhmm("07:30") == (7, 30) and qol.parse_hhmm(" 7:05 ") == (7, 5)
    assert qol.parse_hhmm("24:00") is None and qol.parse_hhmm("7") is None and qol.parse_hhmm("") is None
    now = datetime(2026, 11, 14, 22, 0)
    assert qol.next_time_after(now, "23:30") == datetime(2026, 11, 14, 23, 30)
    assert qol.next_time_after(now, "07:00") == datetime(2026, 11, 15, 7, 0)      # already passed: tomorrow
    assert qol.next_time_after(now, "22:00") == datetime(2026, 11, 15, 22, 0)     # exactly now: tomorrow
    assert qol.next_time_after(now, "bad") is None


def test_quiet_hours_including_overnight_windows():
    at = lambda h, m=0: datetime(2026, 11, 14, h, m)  # noqa: E731
    assert qol.in_quiet_hours(at(23, 30), "23:00", "07:00") and qol.in_quiet_hours(at(3), "23:00", "07:00")
    assert not qol.in_quiet_hours(at(7), "23:00", "07:00") and not qol.in_quiet_hours(at(12), "23:00", "07:00")
    assert qol.in_quiet_hours(at(13), "12:00", "14:00") and not qol.in_quiet_hours(at(14), "12:00", "14:00")
    assert not qol.in_quiet_hours(at(3), "08:00", "08:00")          # same time = no window
    assert not qol.in_quiet_hours(at(3), "xx", "07:00")


def test_name_lists_and_the_weekday_table():
    assert qol.split_names("Cursed Claw, Whirlwind; Light | Last\nOne") == \
        ["Cursed Claw", "Whirlwind", "Light", "Last", "One"]
    text = "Mon: Cursed Claw, Whirlwind; Sat/Sun: Heavenly Light"
    assert qol.parse_day_table(text) == {0: ["Cursed Claw", "Whirlwind"], 5: ["Heavenly Light"],
                                         6: ["Heavenly Light"]}
    assert qol.names_for_day(0, text, "Default") == ["Cursed Claw", "Whirlwind"]
    assert qol.names_for_day(2, text, "Default One, Two") == ["Default One", "Two"]   # no row: default
    assert qol.names_for_day(2, "", "") == []
    assert qol.parse_day_table("Monday: A; tuesday: B")[1] == ["B"]                    # full names work
    assert qol.table_problems(text) == []
    bad = qol.table_problems("Funday: X; Mon Cursed")
    assert len(bad) == 2 and "Funday" in bad[0], bad


def test_ping_kinds_map_alert_colours_to_toggles():
    on = {"rare": True, "problem": False, "finished": False, "other": True}
    assert qol.ping_allowed("gold", on) and not qol.ping_allowed("red", on)
    assert not qol.ping_allowed("green", on) and qol.ping_allowed("info", on)
    assert qol.ping_allowed("red", None)                              # no toggles = unchanged behaviour


def test_saved_window_position_is_only_restored_when_it_is_on_screen():
    assert qol.clamp_geometry("1220x840+60+40", 1920, 1080) == "1220x840+60+40"
    assert qol.clamp_geometry("1220x840+-1800+40", 1920, 1080) == ""        # left monitor unplugged
    assert qol.clamp_geometry("1220x840+2500+40", 1920, 1080) == ""        # right monitor unplugged
    assert qol.clamp_geometry("1220x840+60+1200", 1920, 1080) == ""
    assert qol.clamp_geometry("garbage", 1920, 1080) == ""
    assert qol.clamp_geometry("100x100+0+0", 1920, 1080) == ""             # absurdly small
    assert qol.clamp_geometry("3000x2000+0+0", 1920, 1080) == "1920x1080+0+0"   # shrunk to the screen
    assert qol.clamp_geometry("1220x840+-10+0", 1920, 1080) == "1220x840+-10+0"  # slightly off the edge is fine


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
