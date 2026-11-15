"""Account Manager + Macro Farming windows: every section draws, forms validate, accounts stay separate,
the Terms-of-Service warning is on screen, and controls reach real Manager functions."""
from __future__ import annotations

import shutil
import sys
import tempfile
import time
import tkinter as tk
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rerun import gui_accounts, gui_accounts2, gui_farming, ios, safety  # noqa: E402
from rerun.manager import Manager  # noqa: E402


def open_app():
    from rerun.gui import App
    root = Path(tempfile.mkdtemp())
    shutil.copytree(ROOT / "routines", root / "routines")
    shutil.copytree(ROOT / "templates", root / "templates")
    m = Manager(root)
    m.config["live_view_fps"] = 0
    m.config["setup_seen"] = True
    app = App(m)
    app.errors = []
    app.report_callback_exception = lambda *a: app.errors.append(a)
    app.geometry("1220x900+30+30")
    pump(app)
    return root, m, app


def pump(app, n=6):
    for _ in range(n):
        app.update()
        time.sleep(0.03)


def close(app, root):
    app.update()
    app.destroy()
    shutil.rmtree(root, ignore_errors=True)


def texts(w) -> list[str]:
    out = []
    for c in w.winfo_children():
        try:
            t = c.cget("text")
            if t:
                out.append(str(t))
        except tk.TclError:
            pass
        out += texts(c)
    return out


def fill_form(monkey_values: dict):
    """A stand-in for gui_forms.form_dialog: feeds `monkey_values` to the form's submit() like a user would."""
    calls = []

    def fake(app, title, fields, submit, ok="Save", intro=""):
        vals = {f["key"]: f.get("value", "") for f in fields}
        vals.update(monkey_values.get(title, {}))
        msg = submit(vals)
        calls.append((title, msg))
        return msg is None
    fake.calls = calls
    return fake


def patch_forms(values):
    fake = fill_form(values)
    gui_accounts.form_dialog = fake
    gui_accounts2.form_dialog = fake
    return fake


def test_tabs_and_every_section_draw_without_errors():
    root, m, app = open_app()
    try:
        assert app._tab_accounts == 0 and app._tab_farming == 1
        aid = m.ops.store.active_id
        m.ops.store.set_field(aid, "gems", 5000)
        m.ops.goals.add(aid, "resource", "Save gems", 20000, key="gems")
        m.ops.vault.add_manual(aid, "4+", "Moon Crest", ["ATK +12%"])
        m.ops.store.save_event("Summer", time.time() - 3600, time.time() + 86400)
        for key, _ in gui_accounts.SECTIONS:
            app.nb.select(app._tab_accounts)
            app._am_nav.select(key)
            pump(app, 3)
        for key, _ in gui_farming.FARM_SECTIONS:
            app.nb.select(app._tab_farming)
            app._farm_nav.select(key)
            pump(app, 3)
        assert not app.errors, app.errors
    finally:
        close(app, root)


def test_terms_warning_is_on_the_farming_workspace_in_every_section():
    root, m, app = open_app()
    try:
        app.nb.select(app._tab_farming)
        for key, _ in gui_farming.FARM_SECTIONS:
            app._farm_nav.select(key)
            pump(app, 2)
            assert any("permanent bans" in t for t in texts(app._farm_nav.master.master)), key
            page = app._farm_nav.master.master
            banner = [w for w in page.winfo_children() if isinstance(w, ios.Banner)]
            assert banner and banner[0].winfo_ismapped(), "the warning must be visible, not hidden"
        assert safety.TOS_WARNING in texts(app._farm_nav.master.master)
    finally:
        close(app, root)


def test_create_edit_switch_and_remove_accounts_keep_data_separate():
    root, m, app = open_app()
    try:
        main = m.ops.store.active_id
        m.ops.store.set_field(main, "gems", 111)
        patch_forms({"New Account": {"name": "Alt", "label": "alt", "instance": ""}})
        app.am_new()
        alt = m.ops.store.active_id
        assert alt != main and m.ops.store.get(alt)["name"] == "Alt"
        assert m.ops.store.value(alt, "gems") is None and m.ops.store.value(main, "gems") == 111
        assert app._am_picker.get() == "Alt" and app._farm_picker.get() == "Alt"
        assert m.units is not m.ops.legacy_units, "the new account has its own unit roster"
        # duplicate name: the form stays open with a message
        fake = patch_forms({"New Account": {"name": "alt"}})
        app.am_new()
        assert fake.calls[-1][1] and "already exists" in fake.calls[-1][1]
        # edit
        patch_forms({"Edit Account": {"name": "Alt Two", "label": "x", "instance": "", "notes": "n"}})
        app.am_edit(m.ops.store.get(alt))
        assert m.ops.store.get(alt)["name"] == "Alt Two"
        # switch back through the picker
        app._am_picker.set("Main")
        app._am_pick()
        assert m.ops.store.active_id == main and m.units is m.ops.legacy_units
        # a manual value on one account never shows on the other
        patch_forms({"Edit Gems": {"value": "9,999"}})
        app.am_edit_field(alt, "gems")
        assert m.ops.store.value(alt, "gems") == 9999 and m.ops.store.value(main, "gems") == 111
        # bad input is refused with a readable message
        fake = patch_forms({"Edit Gems": {"value": "lots"}})
        app.am_edit_field(alt, "gems")
        assert "whole number" in fake.calls[-1][1] and m.ops.store.value(alt, "gems") == 9999
        # removal asks first, keeps the files, and refuses to remove the last account
        real = ios.confirm
        ios.confirm = lambda *a, **k: True
        try:
            app.am_remove(m.ops.store.get(alt))
            assert alt not in m.ops.store.ids()
            alerts = []
            real_alert = ios.alert
            ios.alert = lambda r, msg, title="Rerun": alerts.append(msg)
            app.am_remove(m.ops.store.get(main))
            ios.alert = real_alert
            assert main in m.ops.store.ids() and alerts and "at least one" in alerts[0]
        finally:
            ios.confirm = real
        assert not app.errors, app.errors
    finally:
        close(app, root)


def test_checklist_goals_events_and_vault_forms_work_from_the_window():
    root, m, app = open_app()
    try:
        aid = m.ops.store.active_id
        patch_forms({"Add Task": {"name": "Guild check-in", "period": "daily", "priority": "1"}})
        app.am_add_task()
        assert any(d["name"] == "Guild check-in" for d in m.ops.checklist.definitions(aid))
        app._am_task(aid, "mark_done", "daily_missions")
        assert {r["id"]: r for r in m.ops.checklist.rows(aid)}["daily_missions"]["state"] == "completed"
        # automation: only tasks with a script that exists can be started; the rest say so
        assert "manual task" in m.ops.run_task(aid, "daily_missions")
        assert "Link this account" in m.ops.run_task(aid, "login_reward") or m.ops.store.get(aid)["instance"]
        patch_forms({"Add Goal": {"type": gui_accounts2.GOAL_TYPE_LABELS["crest"], "title": "3 crests", "target": "3", "rarity": "4+", "priority": "2"}})
        app.am_add_goal()
        assert any(g["title"] == "3 crests" for g in m.ops.store.get(aid)["goals"])
        fake = patch_forms({"Add Goal": {"type": gui_accounts2.GOAL_TYPE_LABELS["unit_level"], "title": "Ira", "target": "80", "unit": ""}})
        app.am_add_goal()
        assert "Name the unit" in fake.calls[-1][1]
        patch_forms({"Add Event": {"title": "Fest", "start": "2026-12-01", "end": "2026-12-08"}})
        app.am_event_form()
        assert [e["title"] for e in m.ops.store.events()] == ["Fest"]
        fake = patch_forms({"Add Event": {"title": "Bad", "start": "tomorrow", "end": "2026-12-08"}})
        app.am_event_form()
        assert "not a date" in fake.calls[-1][1]
        patch_forms({"Add Crest By Hand": {"rarity": "lv4", "name": "Sun Crest", "substats": "HP +5%, ATK +2%"}})
        app.am_add_crest()
        assert any(i["name"] == "Sun Crest" and i["substats"] == ["HP +5%", "ATK +2%"] for i in m.ops.vault.items(aid))
        assert not app.errors, app.errors
    finally:
        close(app, root)


def test_farming_strip_follows_the_account_and_dry_run_reaches_the_manager():
    root, m, app = open_app()
    try:
        main = m.ops.store.active_id
        m.ops.store.set_field(main, "energy_max", 100)
        m.ops.store.set_field(main, "energy", 40)
        m.ops.store.update_settings(main, "safety", dry_run=True, daily_minutes_limit=30)
        app._refresh_farm_account()
        info = app._farm_info.cget("text")
        assert "Energy 40/100" in info and "DRY-RUN MODE" in info and "of 30" in info, info
        started = []
        m.start = lambda name, script=None, **kw: started.append((name, script, kw)) or "ok"
        app._farm_nav.select("dashboard")
        app.dry_run_sel()
        assert started and started[0][2]["dry_run"] is True
        # emergency stop is a real control
        stopped = []
        m.stop_all = lambda: stopped.append(1) or ["x"]
        app.stop_all()
        assert stopped
        # the status light follows the instances
        m.instances[next(iter(m.instances))].status = "running"
        app._farm_update_status()
        assert "running" in app._farm_state.cget("text").lower()
        assert not app.errors, app.errors
    finally:
        close(app, root)


def test_shared_emulator_asks_which_account_is_open():
    root, m, app = open_app()
    try:
        inst = next(iter(m.instances))
        main = m.ops.store.active_id
        m.ops.store.update(main, instance=inst)
        other = m.ops.store.create("Other", instance=inst)
        seen = []
        real = ios._dialog
        ios._dialog = lambda root_, title, msg, buttons, **k: (seen.append(buttons), (1, None))[1]
        got = []
        m.start = lambda name, script=None, **kw: got.append(kw) or "ok"
        try:
            app._start_checked(inst)
        finally:
            ios._dialog = real
        assert [b[0] for b in seen[0]] == ["Main", "Other", "Cancel"]
        assert got[0]["confirm_account"] == other, got
    finally:
        close(app, root)


def test_keyboard_navigation_and_empty_states():
    root, m, app = open_app()
    try:
        app.nb.select(app._tab_accounts)
        nav = app._am_nav
        nav.select("overview")
        assert nav.bind("<Down>") and nav.bind("<Up>") and nav.bind("<Home>") and nav.bind("<End>"), "arrow keys are bound"
        assert str(nav.cget("takefocus")) == "1"
        nav._step(1)                                    # what the Down key runs (a test window has no keyboard focus)
        pump(app, 2)
        assert nav.current == "scan"
        nav._step(-1)
        nav._step(-1)
        assert nav.current == "overview", "Up at the top stays at the top"
        app._am_nav.select("vault")
        pump(app, 2)
        assert any("No crests recorded" in t for t in texts(app._am_inner)), "empty state must say so"
        app._am_nav.select("events")
        pump(app, 2)
        assert any("No upcoming events" in t for t in texts(app._am_inner))
        b = ios.Button(app, "x", lambda: None)
        assert str(b.cget("takefocus")) == "1"
        b.destroy()
        assert not app.errors, app.errors
    finally:
        close(app, root)


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
