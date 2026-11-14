"""Discord QoL settings: quiet hours, 'Ping me for' per alert kind, daily summary contents."""
from __future__ import annotations

import shutil
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rerun.manager import Manager  # noqa: E402

RARE = "4+ crest found on Instance 1! Left on the Equip Crest screen for you."
PROBLEM = "Crest: stopped - the game says 'unexpected error'. This needs you."
FINISHED = "Crest finished: 3 run(s)."
OTHER = "Hello there"


def manager(**discord):
    d = Path(tempfile.mkdtemp())
    m = Manager(d)
    m.config["discord"].update(discord)
    return m, d


def at(h, mi=0):
    return datetime(2026, 11, 14, h, mi)


def test_defaults_change_nothing_every_kind_still_pings():
    m, d = manager()
    try:
        for msg in (RARE, PROBLEM, FINISHED, OTHER):
            assert m.effective_ping(msg, True) == (True, ""), msg
        assert m.effective_ping(RARE, False) == (False, "")          # a script that didn't ask stays silent
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_ping_me_for_switches_off_individual_kinds():
    m, d = manager(ping={"rare": True, "problem": False, "finished": False, "other": True})
    try:
        assert m.effective_ping(RARE, True)[0] is True
        ok, why = m.effective_ping(PROBLEM, True)
        assert ok is False and "Ping me for" in why, (ok, why)
        assert m.effective_ping(FINISHED, True)[0] is False
        assert m.effective_ping(OTHER, True)[0] is True
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_quiet_hours_silence_pings_overnight_and_only_then():
    m, d = manager(quiet={"enabled": True, "start": "23:00", "end": "07:00"})
    try:
        for hour, expect in ((23, False), (3, False), (6, False), (7, True), (12, True), (22, True)):
            m._now = lambda h=hour: at(h, 30 if h == 23 else 0)
            assert m.effective_ping(RARE, True)[0] is expect, hour
        m._now = lambda: at(3)
        assert "quiet hours (23:00-07:00)" in m.effective_ping(RARE, True)[1]
        m.config["discord"]["quiet"]["enabled"] = False                # switched off: pings again
        assert m.effective_ping(RARE, True)[0] is True
    finally:
        shutil.rmtree(d, ignore_errors=True)


class FakeBot:
    def __init__(self):
        self.sent = []

    def alert(self, instance, message, png, ping):
        self.sent.append((message, ping))


def test_notify_still_posts_the_alert_but_without_the_mention():
    m, d = manager(quiet={"enabled": True, "start": "23:00", "end": "07:00"})
    try:
        m.discord = FakeBot()
        m._now = lambda: at(2)
        m.notify("Instance 1", RARE, ping=True)
        m._now = lambda: at(12)
        m.notify("Instance 1", RARE, ping=True)
        assert m.discord.sent == [(RARE, False), (RARE, True)], m.discord.sent       # posted both times
        assert any("no Discord @mention: quiet hours" in e["message"] for e in m.log_entries)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_daily_summary_lists_only_what_is_switched_on():
    m, d = manager()
    try:
        m.history.add("Instance 1", "crest", "crest", "lv3 crest - scrapped", rarity="lv3", action="scrapped")
        m.history.add("Instance 1", "crest", "crest", "4+ crest - kept", rarity="4+", action="kept")
        m.history.add("Instance 1", "crest", "energy", "Used L Potion")
        m.history.add("Instance 1", "crest", "failure", "Party wiped")
        full = m.daily_summary(update_baseline=False)
        assert "Crests: 1 kept, 1 scrapped" in full and "Energy refills: 1" in full and "Problems (1)" in full, full
        m.config["summary"]["include"] = {"runs": False, "crests": False, "refills": True, "problems": False}
        part = m.daily_summary(update_baseline=False)
        assert "Crests:" not in part and "Problems" not in part and "Energy refills: 1" in part, part
        assert "run(s)" not in part, part
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_discord_tab_saves_quiet_hours_pings_and_summary_choices():
    from rerun import ios
    from rerun.gui import App
    root = Path(tempfile.mkdtemp())
    shutil.copytree(ROOT / "routines", root / "routines")
    m = Manager(root)
    m.config["live_view_fps"] = 0
    m.config["setup_seen"] = True
    app = App(m)
    alerts = []
    real_alert = ios.alert
    ios.alert = lambda root_, msg, title="Rerun": alerts.append(msg)
    try:
        app.quiet_on.set(True)
        app.quiet_start.set("22:30")
        app.quiet_end.set("06:15")
        app.ping_vars["finished"].set(False)
        app.sum_inc["crests"].set(False)
        app.save_discord()
        cfg = m.config
        assert cfg["discord"]["quiet"] == {"enabled": True, "start": "22:30", "end": "06:15"}, cfg["discord"]
        assert cfg["discord"]["ping"]["finished"] is False and cfg["discord"]["ping"]["rare"] is True
        assert cfg["summary"]["include"]["crests"] is False and cfg["summary"]["include"]["runs"] is True
        # a bad time is refused with a message and nothing is saved
        app.quiet_start.set("25:99")
        app.save_discord()
        assert alerts and "HH:MM" in alerts[-1], alerts
        assert m.config["discord"]["quiet"]["start"] == "22:30"
        # and it survives a restart: a fresh Manager reads the saved values
        again = Manager(root)
        assert again.config["discord"]["quiet"]["end"] == "06:15", again.config["discord"]["quiet"]
        assert again.config["summary"]["include"]["crests"] is False
    finally:
        ios.alert = real_alert
        app.update()
        time.sleep(0.05)
        app.destroy()
        shutil.rmtree(root, ignore_errors=True)


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
