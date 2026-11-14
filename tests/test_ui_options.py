"""Window memory, start options, Stop All confirmation and logging settings."""
from __future__ import annotations

import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rerun import ios, runlog  # noqa: E402
from rerun.manager import Manager  # noqa: E402


def make_root(**ui):
    root = Path(tempfile.mkdtemp())
    shutil.copytree(ROOT / "routines", root / "routines")
    m = Manager(root)
    m.config["live_view_fps"] = 0
    m.config["setup_seen"] = True
    m.config["ui"].update(ui)
    return root, m


def open_app(m):
    from rerun.gui import App
    app = App(m)
    app.update()
    return app


def close_app(app, root):
    try:
        app.update()
        time.sleep(0.05)
        app.destroy()
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ---------------------------------------------------------------- logging
def test_log_file_level_size_and_count_are_applied_and_clamped():
    d = Path(tempfile.mkdtemp())
    try:
        runlog.init(d)
        runlog.configure(file_mb=0.0001, file_count=99, file_level="warnings")
        assert runlog.MAX_BYTES == 100_000 and runlog.KEEP == 20          # clamped (0.1 MB .. 20 files)
        runlog.write("x", "just info", "info")
        runlog.write("x", "a warning", "warn")
        runlog.write("x", "an error", "error")
        text = (d / "rerun.log").read_text(encoding="utf-8")
        assert "just info" not in text and "a warning" in text and "an error" in text, text
        runlog.configure(file_level="errors")
        runlog.write("x", "another warning", "warn")
        assert "another warning" not in (d / "rerun.log").read_text(encoding="utf-8")
        runlog.configure(file_level="nonsense")                          # unknown = everything
        runlog.write("x", "info again", "info")
        assert "info again" in (d / "rerun.log").read_text(encoding="utf-8")
    finally:
        runlog.configure()
        shutil.rmtree(d, ignore_errors=True)


def test_memory_lines_setting_limits_the_log_tab_history():
    root = Path(tempfile.mkdtemp())
    try:
        m = Manager(root)
        assert m.log_keep() == 3000
        m.config["logging"]["memory_lines"] = 50           # below the floor: clamped to 500
        assert m.log_keep() == 500
        m.config["logging"]["memory_lines"] = "junk"
        assert m.log_keep() == 3000
        m.config["logging"]["memory_lines"] = 500
        for i in range(1300):
            m.log("app", f"line {i}")
        assert len(m.log_entries) <= 1000 and m.log_entries[-1]["message"] == "line 1299", len(m.log_entries)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_settings_tab_saves_logging_choices_and_clamps_bad_numbers():
    root, m = make_root()
    app = open_app(m)
    try:
        app.log_file_level.set("Errors only")
        app.log_vars["file_mb"].set("500")
        app.log_vars["file_count"].set("abc")
        app.log_vars["memory_lines"].set("100")
        app._save_logging()
        lg = m.config["logging"]
        assert lg["file_level"] == "errors" and lg["file_mb"] == 100 and lg["memory_lines"] == 500, lg
        assert lg["file_count"] == 3, lg                                   # unreadable: kept the old value
        assert app.log_vars["file_mb"].get() == "100" and app.log_vars["memory_lines"].get() == "500"
        assert runlog._min_level == 2 and runlog.MAX_BYTES == 100_000_000   # applied immediately
        assert Manager(root).config["logging"]["file_level"] == "errors"   # and saved to config.yaml
    finally:
        runlog.configure()
        close_app(app, root)


# ---------------------------------------------------------------- window memory
def test_window_position_and_tab_are_remembered_between_runs():
    root, m = make_root()
    app = open_app(m)
    try:
        app.geometry("1150x780+80+90")
        app.nb.select(3)
        app.update()
        app._save_ui_state()
        ui = Manager(root).config["ui"]
        assert ui["geometry"].endswith("+80+90") and ui["tab"] == 3, ui
    finally:
        app.destroy()
    m2 = Manager(root)
    m2.config["live_view_fps"] = 0
    m2.config["setup_seen"] = True
    app2 = open_app(m2)
    try:
        assert app2.winfo_x() == 80 and app2.winfo_y() == 90, (app2.winfo_x(), app2.winfo_y())
        assert app2.nb.index() == 3
    finally:
        close_app(app2, root)


def test_a_saved_position_that_is_off_screen_is_ignored():
    root, m = make_root(geometry="1200x800+9000+0", tab=99)
    app = open_app(m)
    try:
        assert app.winfo_x() < app.winfo_screenwidth(), app.winfo_x()
        assert app.nb.index() == 0                                          # impossible tab: stays on the first
    finally:
        close_app(app, root)


# ---------------------------------------------------------------- Stop All confirmation
def test_stop_all_button_asks_only_when_enabled_and_something_runs():
    root, m = make_root()
    app = open_app(m)
    asked, stopped = [], []
    real = ios.confirm
    ios.confirm = lambda *a, **k: (asked.append(a[1]), answer["v"])[1]
    answer = {"v": False}
    app.stop_all = lambda: stopped.append(1)
    try:
        inst = next(iter(m.instances.values()))
        # off by default: no dialog even while running
        inst.status = "running"
        app.stop_all_clicked()
        assert stopped == [1] and not asked
        # on + something running + user says no: nothing is stopped
        m.config["ui"]["confirm_stop_all"] = True
        app.stop_all_clicked()
        assert len(asked) == 1 and stopped == [1], (asked, stopped)
        # on + yes
        answer["v"] = True
        app.stop_all_clicked()
        assert stopped == [1, 1] and len(asked) == 2
        # on but nothing running: no dialog
        inst.status = "idle"
        app.stop_all_clicked()
        assert len(asked) == 2 and stopped == [1, 1, 1]
    finally:
        ios.confirm = real
        close_app(app, root)


def test_the_emergency_stop_path_never_asks():
    root, m = make_root(confirm_stop_all=True)
    app = open_app(m)
    asked = []
    real = ios.confirm
    ios.confirm = lambda *a, **k: asked.append(1) or False
    try:
        next(iter(m.instances.values())).status = "running"
        app.stop_all()                      # what the F12 hotkey and the tray menu call
        assert not asked
    finally:
        ios.confirm = real
        close_app(app, root)


# ---------------------------------------------------------------- start options
def test_start_options_are_off_by_default_and_ignored_on_a_first_run():
    root, m = make_root()
    app = open_app(m)
    try:
        assert app._apply_start_options() == []
        # switched on, but this is a brand-new setup (Setup check not seen yet): never hide or auto-start
        m.config["ui"].update(autostart=True, start_minimized=True)
        m.config["setup_seen"] = False
        assert app._apply_start_options() == []
    finally:
        close_app(app, root)


def test_autostart_and_start_minimized_do_what_they_say():
    root, m = make_root()
    app = open_app(m)           # created with both options off, so nothing real is scheduled
    scheduled, started = [], []
    app.after = lambda ms, fn=None, *a: scheduled.append((ms, getattr(fn, "__name__", "")))
    m.start_all = lambda: started.append(1) or ["Instance 1: started"]
    try:
        m.config["ui"].update(autostart=True, start_minimized=True)
        app._tray_on = False
        assert app._apply_start_options() == ["autostart"]                  # no tray icon: cannot hide
        app._tray_on = True
        scheduled.clear()
        assert app._apply_start_options() == ["minimized", "autostart"]
        assert any("withdraw" in name for _, name in scheduled), scheduled
        app._autostart()
        assert started == [1]
        assert any("Start scripts when Rerun opens: Instance 1: started" in e["message"] for e in m.log_entries)
        m.config["ui"]["autostart"] = False                                  # switched off meanwhile
        app._autostart()
        assert started == [1]
    finally:
        del app.after
        close_app(app, root)


def test_settings_tab_saves_the_ui_switches():
    root, m = make_root()
    app = open_app(m)
    try:
        app.ui_vars["autostart"].set(True)
        app.ui_vars["confirm_stop_all"].set(True)
        app._save_ui_options()
        ui = Manager(root).config["ui"]
        assert ui["autostart"] is True and ui["confirm_stop_all"] is True and ui["start_minimized"] is False, ui
    finally:
        close_app(app, root)


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
