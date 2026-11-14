"""Smoke tests: manager, custom routine engine, Discord bot wiring, GUI startup."""
from __future__ import annotations

import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rerun.engine import Runner, load_routines  # noqa: E402
from rerun.manager import CUSTOM_PREFIX, Manager  # noqa: E402
from tests.test_scripts import Screen, Sim, make_ctx, AnyQuestScript  # noqa: E402


def temp_root() -> Path:
    d = Path(tempfile.mkdtemp())
    shutil.copytree(ROOT / "routines", d / "routines")
    return d


def test_manager_basics():
    root = temp_root()
    m = Manager(root)
    assert (root / "config.yaml").exists()
    avail = m.scripts_available()
    assert list(avail)[:3] == ["any_quest", "crest", "login_mail"], avail
    assert CUSTOM_PREFIX + "example_tap_through" in avail
    checklist = m.template_checklist("crest")
    names = [c[0] for c in checklist]
    assert "equip_crest_screen" in names and "crest_icon_lv4plus" in names
    assert "equip_crest_screen" in m.missing_templates("crest")
    # settings round trip
    m.save_script_settings("Instance 1", "crest", {"runs": 50, "keep": "Lv4 and better"})
    m2 = Manager(root)
    s = m2.script_settings("Instance 1", "crest")
    # Phase 2: 'party' choice became 'Always re-select Past Party' (on by default for Crest)
    assert s["runs"] == 50 and s["keep"] == "Lv4 and better" and s["past_party"] is True
    # instance editing
    m2.set_instances([{"name": "A", "serial": "127.0.0.1:5555", "script": "any_quest"},
                      {"name": "B", "serial": "127.0.0.1:5565", "script": "crest"}])
    assert set(m2.instances) == {"A", "B"}
    assert m2.start("nope").startswith("No instance")
    assert m2.start("A", "bogus").startswith("Unknown script")


def test_custom_routine_runs():
    import tests.test_scripts as ts
    screens = {
        "results": Screen([("ok_button", 300, 960)]),
        "results2": Screen([("small_next_button", 300, 960)]),
        "quest": Screen([], extra=[("solo_quest_button", 450, 960)]),
    }
    on_tap = {("results", "ok_button"): "results2", ("results2", "small_next_button"): "quest"}
    dev = Sim(screens, "results", on_tap)
    with tempfile.TemporaryDirectory() as d:
        ctx = make_ctx(Path(d), dev, AnyQuestScript)
        from tests.test_scripts import patch, background
        for n in ("small_next_button",):
            canvas = background()
            p = patch(n)
            canvas[100:100 + p.shape[0], 100:100 + p.shape[1]] = p
            ctx.vision.store.save(n, canvas, 100, 100, p.shape[1], p.shape[0])
        ctx.routines = load_routines(ROOT / "routines")
        import rerun.engine as eng
        eng.POLL = 0.01
        Runner(ctx, "example_tap_through").run()
    assert dev.tapped == ["ok_button", "small_next_button"], dev.tapped


def test_restart_import_keeps_own_captures():
    import cv2
    import numpy as np
    from rerun.restart_import import MAPPING, import_templates
    from rerun.vision import TemplateStore
    src = Path(tempfile.mkdtemp())
    for rel in MAPPING.values():
        p = src / "templates" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(p), np.full((20, 30, 3), 128, np.uint8))
    store = TemplateStore(Path(tempfile.mkdtemp()))
    own = np.zeros((1280, 720, 3), np.uint8)
    store.save("ok_button", own, 0, 0, 40, 40)  # a user capture
    res = import_templates(store, src)
    assert "ok_button" in res["skipped_own"] and len(res["imported"]) == len(MAPPING) - 1
    assert store.resolution("drop_info") == (720, 1280)
    assert store.get("ok_button").shape[:2] == (40, 40)  # untouched
    res = import_templates(store, src)  # re-import refreshes ReStart ones only
    assert len(res["imported"]) == len(MAPPING) - 1
    res = import_templates(store, src, overwrite_own=True)
    assert len(res["imported"]) == len(MAPPING)


def test_discord_bot_requires_token():
    from rerun.discord_bot import DiscordBot
    m = Manager(temp_root())
    try:
        DiscordBot(m)
    except RuntimeError as e:
        assert "token" in str(e).lower()
    else:
        raise AssertionError("expected RuntimeError for empty token")
    m.config["discord"]["token"] = "x"
    bot = DiscordBot(m)
    client = bot._build_client()  # builds slash-command tree without connecting
    assert client is not None


def test_log_tab_shows_lines_logged_before_the_window_opened():
    """Start-up lines (config warnings, import notes) are logged before the App exists; the Log tab
    used to start empty and never show them. Lines logged afterwards must appear exactly once."""
    from rerun.gui import App
    root = temp_root()
    (root / "config.yaml").write_text("close_to_tray: maybe\n", encoding="utf-8")
    m = Manager(root)
    m.config["live_view_fps"] = 0
    m.config["setup_seen"] = True
    m.log("app", "logged before the window")
    app = App(m)
    try:
        m.log("app", "logged after the window")
        for _ in range(8):
            app.update()
            time.sleep(0.05)
        text = app.log_box.get("1.0", "end")
        assert text.count("logged before the window") == 1, text
        assert text.count("logged after the window") == 1, text
        assert "'close_to_tray' should be true/false" in text, text      # the config warning
    finally:
        app.destroy()


def test_gui_starts_and_closes():
    from rerun.gui import App
    m = Manager(temp_root())
    m.config["live_view_fps"] = 0   # no video stream from a real emulator in tests
    app = App(m)
    errors = []
    app.report_callback_exception = lambda *a: errors.append(a)
    # exercise a few UI paths
    m.history.add("Instance 1", "crest", "crest", "lv3 crest - scrapped", rarity="lv3",
                  action="scrapped")
    m.log("Instance 1", "Error: test error line")

    def popover_open_close():
        from rerun import ios
        import tkinter as tk
        app.nb.select(1)
        app.update()
        app.set_script._open()
        app.update()
        pops = [w for w in app.winfo_children() if isinstance(w, tk.Toplevel)]
        assert pops, "popover did not open"
        for p in pops:
            p.destroy()
        # Close only after this step ran: with fixed timers a slow (busy) PC let
        # app.update() above process the destroy timer mid-step (flaky TclError).
        app.after(200, lambda: app.nb.select(0))
        app.after(700, app.destroy)

    app.after(300, lambda: (app.nb.select(1), app._load_settings_form()))
    app.after(600, lambda: (app.nb.select(2), app.refresh_checklist()))
    app.after(900, lambda: (app.nb.select(3), app.refresh_history()))
    app.after(1100, lambda: (app.hist_kind.set("Crests"), app.refresh_history()))
    app.after(1200, lambda: (app.nb.select(4), app.units_q.set("a"), app.refresh_units()))
    app.after(1250, lambda: (app.comp_show.set("Near target"), app.refresh_units(),
                             app._refresh_compendium_tiles(force=True)))
    app.after(1300, lambda: app.nb.select(5))
    app.after(1500, lambda: (app.nb.select(6), app.log_level.set("Errors"), app._rebuild_log()))
    # GS Companion tab (last) and its link back to Rerun
    app.after(1600, lambda: (app.companion is not None and app.nb.select(app._tab_companion),
                             app._companion_refresh()))
    app.after(1700, lambda: app.flash("hello", "ok"))
    app.after(1900, popover_open_close)
    app.after(30000, app.destroy)  # safety net if a step above never ran
    app.mainloop()
    assert not errors, errors
    assert len(app._hist_rows) == 1, app._hist_rows


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
