"""Account Manager: data isolation, provenance, scans, checklist resets, goals, vault, safety, Manager glue."""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rerun import safety  # noqa: E402
from rerun.account_ops import AccountOps  # noqa: E402
from rerun.accounts import AccountError, AccountStore, validate_value  # noqa: E402
from rerun.checklist import GAME_TZ, Checklist, next_reset, period_start  # noqa: E402
from rerun.crest_stats import CrestLedger  # noqa: E402
from rerun.goals import Goals  # noqa: E402
from rerun.manager import Manager  # noqa: E402
from rerun.vault import Vault  # noqa: E402


def tmp():
    return Path(tempfile.mkdtemp())


def gt(y, mo, d, h, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=GAME_TZ).timestamp()


# ---------------------------------------------------------------- accounts + isolation
def test_accounts_are_isolated_and_names_unique():
    r = tmp()
    try:
        s = AccountStore(r)
        a, b = s.create("Alpha"), s.create("Beta", label="alt")
        s.set_field(a, "gems", 1000)
        s.set_field(b, "gems", 5)
        assert s.value(a, "gems") == 1000 and s.value(b, "gems") == 5
        s.update(a, name="Alpha 2")
        assert s.get(b)["name"] == "Beta"
        for bad in ("beta", "  "):
            try:
                s.create(bad)
                raise AssertionError("should refuse")
            except AccountError:
                pass
        try:
            s.set_field("nope", "gems", 1)
            raise AssertionError("unknown account must fail")
        except AccountError:
            pass
        # a second store (a restart) sees the same data
        s2 = AccountStore(r)
        assert s2.value(a, "gems") == 1000 and s2.active_id == a
    finally:
        shutil.rmtree(r, ignore_errors=True)


def test_remove_moves_files_aside_and_switches_active():
    r = tmp()
    try:
        s = AccountStore(r)
        a, b = s.create("A"), s.create("B")
        s.set_active(a)
        s.remove(a)
        assert s.active_id == b and a not in s.ids()
        assert list((r / "accounts" / "_removed").glob(f"{a}-*")), "files must be recoverable"
    finally:
        shutil.rmtree(r, ignore_errors=True)


def test_validation_rejects_bad_numbers_with_a_readable_message():
    assert validate_value("gems", "12,500") == 12500
    for key, bad in (("gems", "lots"), ("gems", -5), ("player_level", 0), ("energy", 2.5), ("gems", True)):
        try:
            validate_value(key, bad)
            raise AssertionError(f"{key}={bad!r} should fail")
        except AccountError as e:
            assert str(e)


# ---------------------------------------------------------------- provenance + scans
def test_scan_never_overwrites_with_an_uncertain_reading():
    r = tmp()
    try:
        s = AccountStore(r)
        a = s.create("A")
        s.set_field(a, "energy_max", 100)
        s.set_field(a, "energy", 80, status="manual")
        rep = s.record_scan(a, {"energy": (40, 30.0)}, "test")            # low confidence
        assert s.value(a, "energy") == 80 and rep["uncertain"] and not rep["detected"]
        assert s.get(a)["last_scan_ok"] is None, "an all-uncertain scan is not a successful scan"
        assert s.get(a)["pending"]["energy"]["value"] == 40
        rep = s.record_scan(a, {"energy": (55, 90.0)}, "test")
        assert s.value(a, "energy") == 55 and s.field(a, "energy")["status"] == "ocr" and rep["detected"]
        assert s.get(a)["last_scan_ok"] is not None
        # impossible: energy above max is parked, the good value stays
        rep = s.record_scan(a, {"energy": (500, 95.0)}, "test")
        assert s.value(a, "energy") == 55 and rep["uncertain"]
        # a failed read changes nothing
        assert s.record_scan(a, {}, "test", expected=["energy"])["missing"] == ["energy"]
        assert s.value(a, "energy") == 55
    finally:
        shutil.rmtree(r, ignore_errors=True)


def test_locked_fields_are_hand_maintained():
    r = tmp()
    try:
        s = AccountStore(r)
        a = s.create("A")
        s.set_field(a, "gems", 100)
        s.set_locked(a, "gems", True)
        res = s.set_field(a, "gems", 999, status="ocr", confidence=99)
        assert not res["applied"] and s.value(a, "gems") == 100
        s.accept_pending(a, "gems")                                          # you decide to trust the reading
        assert s.value(a, "gems") == 999 and s.field(a, "gems")["status"] == "manual"
        s.set_field(a, "gems", 120)                                          # manual always works
        assert s.value(a, "gems") == 120
    finally:
        shutil.rmtree(r, ignore_errors=True)


def test_resource_history_records_only_real_changes():
    r = tmp()
    try:
        s = AccountStore(r)
        a = s.create("A")
        for v in (10, 10, 12):
            s.set_field(a, "gems", v)
        assert [v for _, v in s.resource_history(a, "gems")] == [10, 12]
    finally:
        shutil.rmtree(r, ignore_errors=True)


def test_damaged_file_is_set_aside_not_lost():
    r = tmp()
    try:
        s = AccountStore(r)
        a = s.create("A")
        s.set_field(a, "gems", 7)
        s.set_field(a, "gems", 8)              # writes a .bak of the previous version
        p = r / "accounts" / a / "account.json"
        p.write_text("{ not json", encoding="utf-8")
        s2 = AccountStore(r)
        assert s2.value(a, "gems") == 7, "falls back to the backup"
        assert list(p.parent.glob("account.json.corrupt-*"))
    finally:
        shutil.rmtree(r, ignore_errors=True)


# ---------------------------------------------------------------- checklist
def test_reset_follows_the_game_clock_not_midnight():
    before = gt(2026, 11, 15, 5, 59)      # 05:59 UTC-6 is still the previous game day
    after = gt(2026, 11, 15, 6, 0)
    assert period_start(before, "daily") == gt(2026, 11, 14, 6)
    assert period_start(after, "daily") == gt(2026, 11, 15, 6)
    assert next_reset(after, "daily") == gt(2026, 11, 16, 6)
    # weekly: 2026-11-15 is a Sunday; Monday-reset weeks start on 2026-11-09
    assert period_start(after, "weekly", 0) == gt(2026, 11, 9, 6)
    assert period_start(after, "weekly", 6) == gt(2026, 11, 15, 6)          # Sunday-reset: today
    assert next_reset(after, "weekly", 0) == gt(2026, 11, 16, 6)


def test_checklist_completion_reset_and_no_duplicate_runs():
    r = tmp()
    try:
        s = AccountStore(r)
        a, b = s.create("A"), s.create("B")
        c = Checklist(s)
        t0 = gt(2026, 11, 15, 8)
        assert c.state_of(a, c.definitions(a)[0], t0) == "available"
        c.mark_done(a, "daily_missions", now=t0)
        row = {x["id"]: x for x in c.rows(a, t0 + 60)}
        assert row["daily_missions"]["state"] == "completed"
        assert {x["id"]: x for x in c.rows(b, t0 + 60)}["daily_missions"]["state"] == "available", "isolation"
        assert {x["id"]: x for x in c.rows(a, gt(2026, 11, 16, 6, 1))}["daily_missions"]["state"] == "available"
        try:
            c.begin_run(a, "daily_missions", now=t0 + 5)
            raise AssertionError("a completed task must not run again")
        except AccountError:
            pass
        c.begin_run(a, "login_reward", now=t0)
        assert c.state_of(a, next(d for d in c.definitions(a) if d["id"] == "login_reward"), t0) == "in_progress"
        c.end_run(a, "login_reward", ok=True, now=t0 + 30)                     # a script finished it
        st = {x["id"]: x for x in c.rows(a, t0 + 60)}["login_reward"]["state"]
        assert st == "unverified", st
        c.confirm(a, "login_reward")
        assert {x["id"]: x for x in c.rows(a, t0 + 60)}["login_reward"]["state"] == "completed"
        c.begin_run(a, "raid_tickets", now=t0)
        c.end_run(a, "raid_tickets", ok=False, now=t0 + 9)
        assert {x["id"]: x for x in c.rows(a, t0 + 60)}["raid_tickets"]["state"] == "failed"
        c.undo(a, "daily_missions")
        assert {x["id"]: x for x in c.rows(a, t0 + 60)}["daily_missions"]["state"] == "available"
    finally:
        shutil.rmtree(r, ignore_errors=True)


def test_custom_tasks_priorities_and_due_automatable():
    r = tmp()
    try:
        s = AccountStore(r)
        a = s.create("A")
        c = Checklist(s)
        tid = c.add_task(a, "Guild check-in", "daily", priority=1)
        assert c.definitions(a)[0]["id"] in (tid, "login_reward")
        try:
            c.add_task(a, "guild check-in")
            raise AssertionError("duplicate names refused")
        except AccountError:
            pass
        due = c.due_automatable(a, {"login_mail": "Login & Mail"})
        assert [d["id"] for d in due] == ["login_reward"], "only tasks with a real script can be automated"
        c.remove_task(a, "weekly_shop")
        assert "weekly_shop" not in [d["id"] for d in c.definitions(a)]
        c.remove_task(a, tid)
        assert tid not in [d["id"] for d in c.definitions(a)]
    finally:
        shutil.rmtree(r, ignore_errors=True)


# ---------------------------------------------------------------- goals + vault
def _ledger(root):
    return CrestLedger(root)


def test_goals_progress_and_recommendations_use_real_numbers():
    r = tmp()
    try:
        s = AccountStore(r)
        a = s.create("A", instance="Inst")
        led = _ledger(r)
        v = Vault(s, led)

        class Roster:
            units = {"Ira": {"fields": {"level": {"value": 60}}}}

            @staticmethod
            def value(u, f):
                return u["fields"][f]["value"]

        g = Goals(s, v, lambda aid: Roster, led)
        g1 = g.add(a, "resource", "Save gems", 30000, key="gems")
        g2 = g.add(a, "unit_level", "Ira 80", 80, unit="Ira", priority=1)
        g3 = g.add(a, "crest", "3 Heavenly Light 4+", 3, rarity="4+")
        s.set_field(a, "gems", 12000)
        led.add_drop("Inst", "s1", "4+", "kept", palace="Heavenly Light")
        led.add_drop("Inst", "s1", "lv3", "scrapped")
        prog = {p["goal"]["id"]: p for p in g.refresh(a)}
        assert prog[g1]["remaining"] == 18000 and prog[g2]["remaining"] == 20 and prog[g3]["remaining"] == 2
        recs = {x["goal_id"]: x for x in g.recommend(a, {"crest": "Crest"})}
        assert recs[g3]["script"] == "crest" and "2 more needed" in recs[g3]["why"]
        assert "Not enough data" in recs[g3]["why"], "no run estimate without enough runs"
        assert recs[g1]["script"] is None and recs[g2]["script"] is None
        s.set_field(a, "gems", 30000)
        g.refresh(a)
        assert next(x for x in s.get(a)["goals"] if x["id"] == g1)["status"] == "done"
        g.remove(a, g2)
        assert g2 not in [p["goal"]["id"] for p in g.refresh(a)]
        for bad in (dict(gtype="resource", title="x", target=1, key="player_name"),
                    dict(gtype="crest", title="x", target=0)):
            try:
                g.add(a, **bad)
                raise AssertionError("bad goal accepted")
            except AccountError:
                pass
    finally:
        shutil.rmtree(r, ignore_errors=True)


def test_vault_attribution_rules_verdicts_and_never_acts():
    r = tmp()
    try:
        s = AccountStore(r)
        a = s.create("A", instance="Inst")
        b = s.create("B", instance="Other")
        led = _ledger(r)
        led.add_drop("Inst", "s", "4+", "kept")
        led.add_drop("Inst", "s", "lv3", "scrapped")
        led.add_drop("Other", "s", "burst", "kept")
        v = Vault(s, led)
        ia, ib = v.items(a), v.items(b)
        assert [i["rarity"] for i in ia] == ["4+", "lv3"] and [i["rarity"] for i in ib] == ["burst"]
        assert [i["verdict"] for i in ia] == ["keep", "consider discarding"]
        v.annotate(a, ia[1]["key"], substats=["ATK +12%"])
        v.set_rules(a, wanted_substats=["atk"])
        assert v.items(a)[1]["verdict"] == "keep", "a wanted substat turns it into a keep"
        k = v.add_manual(a, "lv4", "Moon Crest", ["HP +5%"])
        v.add_manual(a, "lv4", "Moon Crest")
        v.add_manual(a, "lv4", "Moon Crest")
        assert any(i["verdict"] == "possible duplicate" for i in v.items(a))
        assert v.duplicates(a) and len(v.search(v.items(a), text="moon")) == 3
        v.remove_manual(a, k)
        try:
            v.set_rules(a, keep_rarities=["mythic"])
            raise AssertionError("unknown rarity")
        except AccountError:
            pass
        assert not any(hasattr(v, n) for n in ("scrap", "discard", "sell", "destroy"))
        # two accounts on one emulator: a drop cannot be attributed, so it belongs to neither
        c2 = s.create("C", instance="Inst")
        led.add_drop("Inst", "s2", "burst", "kept")
        assert c2 and not v.items(c2), "an ambiguous drop belongs to no vault"
        assert all(i["source"] == "manual" for i in v.items(a)), "and is no longer claimed by either"
    finally:
        shutil.rmtree(r, ignore_errors=True)


# ---------------------------------------------------------------- safety
def test_dry_run_device_taps_nothing_and_ends_itself():
    class Real:
        taps = 0

        def tap(self, *a):
            Real.taps += 1

        def screencap(self):
            return "frame"

        def shell(self, c, timeout=20):
            return "out"

    d = safety.DryRunDevice(Real())
    assert d.screencap() == "frame" and d.shell("pm list packages") == "out"
    try:
        for i in range(100):
            d.tap(10 + i % 2, 20)
        raise AssertionError("must stop itself")
    except Exception as e:  # noqa: BLE001
        assert "dry run complete" in str(e)
    assert Real.taps == 0 and d.plan
    assert "none sent" in safety.plan_summary(d.plan)
    d2 = safety.DryRunDevice(Real())
    assert d2.shell("rm -rf /") == "" and d2.plan[-1]["action"] == "run shell command"


def test_safety_limits_block_starts():
    r = tmp()
    try:
        s = AccountStore(r)
        a = s.create("A")
        assert safety.check_start(s, a, "crest") is None
        s.update_settings(a, "safety", automation_allowed=False)
        assert "switched off" in safety.check_start(s, a, "crest")
        s.update_settings(a, "safety", automation_allowed=True, allowed_scripts=["login_mail"])
        assert "only allowed" in safety.check_start(s, a, "crest") and safety.check_start(s, a, "login_mail") is None
        s.update_settings(a, "safety", allowed_scripts=[], daily_minutes_limit=30)
        sid = s.begin_session(a, "i", "crest")
        s.end_session(a, sid, "completed")
        sess = s.sessions(a)[0]
        # fake 45 minutes used today
        s.read_log  # noqa: B018
        with (r / "accounts" / a / "sessions.jsonl").open("a") as f:
            f.write(json.dumps({**sess, "start": time.time() - 2700, "end": time.time(), "status": "completed"}) + "\n")
        assert "30 minute limit" in safety.check_start(s, a, "crest")
        try:
            s.update_settings(a, "safety", daily_minutes_limit="abc")
            raise AssertionError("bad number")
        except AccountError:
            pass
        assert "risk" in safety.SAFETY_NOTE.lower() and "permanent bans" in safety.TOS_WARNING
    finally:
        shutil.rmtree(r, ignore_errors=True)


# ---------------------------------------------------------------- manager glue
def make_manager():
    root = tmp()
    shutil.copytree(ROOT / "routines", root / "routines")
    shutil.copytree(ROOT / "templates", root / "templates")
    return root, Manager(root)


def test_manager_creates_main_account_and_keeps_legacy_units():
    root, m = make_manager()
    try:
        assert [a["name"] for a in m.ops.store.all()] == ["Main"]
        main = m.ops.store.active()
        assert main["legacy_units"] and m.ops.roster_for(main["id"]) is m.units
        b = m.ops.store.create("Second")
        m.ops.use_account(b)
        assert m.units is not m.ops.legacy_units and m.units.dir == root / "accounts" / b / "units"
        m.ops.use_account(main["id"])
        assert m.units is m.ops.legacy_units
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_shared_emulator_needs_confirmation_and_sessions_are_attributed():
    root, m = make_manager()
    try:
        inst = next(iter(m.instances))
        main = m.ops.store.active_id
        b = m.ops.store.create("Second", instance=inst)
        m.ops.store.update(main, instance=inst)
        msg = m.start(inst, "crest")
        assert "share" in msg and m.instances[inst].status == "idle", msg
        aid, err, dry = m.ops.before_start(inst, "crest", b, False)
        assert aid == b and err is None and not dry
        m.ops.store.update_settings(b, "safety", dry_run=True)
        assert m.ops.before_start(inst, "crest", b, False)[2] is True, "account-level dry run applies"
        m.ops.store.update_settings(b, "safety", automation_allowed=False)
        assert "switched off" in m.start(inst, "crest", confirm_account=b)
        # session bookkeeping goes to the right account only
        i = m.instances[inst]
        m.ops.session_started(i, b, False)
        m.ops.session_ended(i, {"x.runs": 3, "x.crest_4+": 1}, "finished: done")
        ses = m.ops.store.sessions(b)
        assert ses and ses[-1]["status"] == "completed" and ses[-1]["results"] == {"runs": 3, "crests": 1}
        assert not m.ops.store.sessions(main)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_notifications_are_account_scoped_and_not_duplicated():
    root, m = make_manager()
    try:
        inst = next(iter(m.instances))
        main = m.ops.store.active_id
        m.ops.store.update(main, instance=inst)
        sent = []

        class D:
            def alert(self, i, msg, png, ping):
                sent.append((msg, ping))

            def send(self, text, png, ping):
                sent.append((text, ping))

        m.discord = D()
        m.ops.store.create("Other", instance="elsewhere")
        m.notify(inst, "Rare crest found", ping=True)
        assert sent[-1][0].startswith("[Main] "), sent
        m.ops.store.update_settings(main, "notify", ping=False)
        m.notify(inst, "Rare crest found", ping=True)
        assert sent[-1][1] is False
        m.ops.store.update_settings(main, "notify", enabled=False)
        n = len(sent)
        m.notify(inst, "anything", ping=True)
        assert len(sent) == n, "a muted account sends nothing to Discord"
        m.ops.store.update_settings(main, "notify", enabled=True, low_energy_below=50)
        m.ops.store.set_field(main, "energy_max", 100)
        m.ops.store.set_field(main, "energy", 10)
        t = time.time()
        assert len(m.ops.check_alerts(t)) == 1 and m.ops.check_alerts(t + 60) == [], "an alert is sent once a game day"
        now = time.time()
        m.ops.store.save_event("Summer Event", now - 3600, now + 3600, "x")
        assert any("Summer Event" in x for x in m.ops.check_alerts(now))
        rep = m.ops.daily_report(main)
        assert "Main" in rep and "Daily tasks" in rep and "Energy: 10/100" in rep
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_dashboard_series_never_invent_data():
    root, m = make_manager()
    try:
        main = m.ops.store.active_id
        assert m.ops.series(main, "gems_by_week") == []
        assert all(v == 0 for _, v in m.ops.series(main, "crests_per_day"))
        m.ops.store.set_field(main, "gems", 100)
        assert [v for _, v in m.ops.series(main, "gems_by_week")] == [100]
        assert "unknown" in m.ops.energy_refill(main)
        m.ops.store.set_field(main, "energy_max", 100)
        m.ops.store.set_field(main, "energy", 40)
        m.ops.store.update_settings(main, "prefs", energy_regen_minutes=5)
        assert "full in about" in m.ops.energy_refill(main)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_dry_run_through_the_manager_taps_nothing_and_is_recorded_as_a_dry_run():
    import cv2
    from rerun.adb import FakeDevice
    root, m = make_manager()
    try:
        m.config["game_package"] = "fake.grandsummoners"
        inst = next(iter(m.instances))
        dev = FakeDevice([cv2.imread(str(ROOT / "tests" / "fixtures" / "home.png"))])
        m.instances[inst].device = dev
        assert "Dry run" in m.start(inst, "any_quest", dry_run=True)
        t0 = time.time()
        while m.instances[inst].status not in ("idle", "error") and time.time() - t0 < 60:
            time.sleep(0.1)
        assert dev.taps == [], dev.taps
        main = m.ops.store.active_id
        ses = m.ops.store.sessions(main)
        assert len(ses) == 1 and ses[0]["dry_run"] and ses[0]["status"] == "completed", ses
        assert any("DRY RUN RESULT" in line for line in m.log_lines)
        # a dry run never completes a checklist task
        c = m.ops.checklist
        c.begin_run(main, "login_reward")
        i = m.instances[inst]
        i.account, i.dry_run, i.task, i.session_id = main, True, "login_reward", m.ops.store.begin_session(main, inst, "login_mail", True)
        m.ops.session_ended(i, {}, "finished: done")
        row = {r["id"]: r for r in c.rows(main)}["login_reward"]
        assert row["state"] == "available", row["state"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_session_limit_stops_the_run():
    root, m = make_manager()
    try:
        import threading

        class Ctx:
            stop_event, pause_event = threading.Event(), threading.Event()

        class I:
            name, ctx, limit_timer = "x", Ctx(), None
        i = I()
        m.arm_limit(i, 0.005)
        assert Ctx.stop_event.wait(3), "the session limit must set the stop event"
        i.limit_timer.cancel()
    finally:
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
            import traceback
            traceback.print_exc()
            print("FAIL", t.__name__, repr(e))
    print(f"{len(tests) - failed}/{len(tests)} passed")
    raise SystemExit(1 if failed else 0)
