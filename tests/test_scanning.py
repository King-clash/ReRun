"""Everything in Account Manager scanning, end to end: the top-bar and energy readers on every real screen,
a scan through a fake emulator, uncertain/locked/impossible readings, isolation between accounts, the unit scan
hook, scan history, and the Scan button on the window."""
from __future__ import annotations

import glob
import shutil
import sys
import tempfile
import time
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rerun.accounts import FIELDS, SCAN_SUPPORT, AccountError  # noqa: E402
from rerun.adb import FakeDevice  # noqa: E402
from rerun.manager import Manager  # noqa: E402
from rerun.ocr import OcrUnavailable, get_ocr, read_energy, read_header  # noqa: E402

FX = ROOT / "tests" / "fixtures"
GOOD_GEMS = {184, 186, 111}


def ocr():
    try:
        return get_ocr(None)
    except OcrUnavailable:
        return None


def frames():
    for f in sorted(glob.glob(str(FX / "*.png"))):
        img = cv2.imread(f)
        if img is not None and img.shape[:2] == (1280, 720):
            yield Path(f).name, img


def mgr():
    root = Path(tempfile.mkdtemp())
    shutil.copytree(ROOT / "routines", root / "routines")
    shutil.copytree(ROOT / "templates", root / "templates")
    m = Manager(root)
    m.config["live_view_fps"] = 0
    m.config["setup_seen"] = True
    return root, m


def test_alch_replaces_tickets_in_the_labels_only():
    assert FIELDS["tickets"][0] == "Alch" and "Tickets" not in [v[0] for v in FIELDS.values()]
    assert SCAN_SUPPORT["tickets"][0] == "unsupported" and "Alch" in SCAN_SUPPORT["tickets"][1]


def test_readers_on_every_real_screen_are_never_wrong():
    o = ocr()
    if o is None:
        return
    n_head = n_energy = 0
    for name, img in frames():
        for k, (v, _c) in read_header(o, img).items():
            ok = {"gold": {999999999}, "gems": GOOD_GEMS, "player_level": {435}}[k]
            assert v in ok, (name, k, v)
            n_head += 1
        e = read_energy(o, img)
        if e:
            assert e[1] == 517 and 0 <= e[0] <= 517 * 3, (name, e)
            n_energy += 1
    assert n_head >= 30 and n_energy >= 8, (n_head, n_energy)


def test_scan_across_every_screen_never_corrupts_a_stored_value():
    """Scan screen after screen (good, dimmed, popup, no bar): values only ever move to plausible numbers and a
    screen that cannot be read leaves the last good value alone."""
    if ocr() is None:
        return
    root, m = mgr()
    try:
        inst = next(iter(m.instances))
        aid = m.ops.store.active_id
        st = m.ops.store
        st.update(aid, instance=inst)
        reads = unreadable = 0
        for name, img in frames():
            m.instances[inst].device = FakeDevice([img])
            before = {k: st.value(aid, k) for k in ("gems", "gold", "player_level", "energy_max")}
            rep = m.ops.scan_screen(aid)
            if not rep["detected"]:
                unreadable += 1
                assert {k: st.value(aid, k) for k in before} == before, name
            else:
                reads += 1
            assert st.value(aid, "gems") in (None, *GOOD_GEMS) and st.value(aid, "gold") in (None, 999999999), name
            assert st.value(aid, "player_level") in (None, 435) and st.value(aid, "energy_max") in (None, 517), name
        assert reads >= 15 and unreadable >= 5, (reads, unreadable)
        assert len(st.get(aid)["scan_history"]) == reads + unreadable
        assert st.get(aid)["last_scan_ok"] is not None
        assert not st.get(aid)["pending"], st.get(aid)["pending"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_manual_values_locks_and_unsupported_fields_survive_scans():
    if ocr() is None:
        return
    root, m = mgr()
    try:
        inst = next(iter(m.instances))
        st = m.ops.store
        aid = st.active_id
        st.update(aid, instance=inst)
        st.set_field(aid, "tickets", 12)                      # Alch: no reader, so only you set it
        st.set_field(aid, "gems", 5)
        st.set_locked(aid, "gems", True)
        m.instances[inst].device = FakeDevice([cv2.imread(str(FX / "home.png"))])
        rep = m.ops.scan_screen(aid)
        assert st.value(aid, "gems") == 5 and st.get(aid)["pending"]["gems"]["value"] == 184, "locked: parked, not applied"
        assert any(u["key"] == "gems" for u in rep["uncertain"])
        assert st.value(aid, "tickets") == 12 and st.field(aid, "tickets")["status"] == "manual"
        assert st.value(aid, "gold") == 999999999 and st.value(aid, "energy") == 383
        st.accept_pending(aid, "gems")
        assert st.value(aid, "gems") == 184
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_two_accounts_on_two_emulators_never_mix_scans():
    if ocr() is None:
        return
    root, m = mgr()
    try:
        st = m.ops.store
        a = st.active_id
        m.set_instances(m.config["instances"] + [{"name": "Second", "serial": "127.0.0.1:5565", "script": "crest"}])
        inst1 = list(m.instances)[0]
        b = st.create("Alt", instance="Second")
        st.update(a, instance=inst1)
        m.instances[inst1].device = FakeDevice([cv2.imread(str(FX / "home.png"))])
        m.instances["Second"].device = FakeDevice([cv2.imread(str(FX / "units_grid_dark.png"))])
        m.ops.scan_screen(a)
        m.ops.scan_screen(b)
        assert st.value(a, "gems") == 184 and st.value(b, "gems") == 186
        assert st.value(a, "energy") == 383 and st.value(b, "energy") != 383
        # an account with no emulator, or a shared one that is not active, refuses instead of guessing
        c = st.create("Unlinked")
        try:
            m.ops.scan_screen(c)
            raise AssertionError("must refuse")
        except AccountError as e:
            assert "Link this account" in str(e)
        d = st.create("Shares", instance=inst1)
        st.set_active(b)
        try:
            m.ops.scan_screen(d)
            raise AssertionError("must refuse")
        except AccountError as e:
            assert "share" in str(e)
        assert st.value(d, "gems") is None
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_scan_failure_modes_are_reported_and_change_nothing():
    root, m = mgr()
    try:
        inst = next(iter(m.instances))
        st = m.ops.store
        aid = st.active_id
        st.update(aid, instance=inst)
        st.set_field(aid, "gems", 77)

        class Broken(FakeDevice):
            def screencap(self):
                raise RuntimeError("emulator disconnected")
        m.instances[inst].device = Broken([])
        try:
            m.ops.scan_screen(aid)
            raise AssertionError("must raise")
        except AccountError as e:
            assert "disconnected" in str(e)
        assert st.value(aid, "gems") == 77
        assert any("scan failed" in x["detail"].lower() for x in st.activity(aid))
        # impossible readings are rejected with a reason, not stored
        rep = st.record_scan(aid, {"gems": (-5, 99.0), "player_level": (0, 99.0), "energy": (10, 99.0)}, "t")
        assert len(rep["rejected"]) == 2 and st.value(aid, "gems") == 77
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_unit_scan_button_starts_the_compendium_counter_for_that_account():
    root, m = mgr()
    try:
        from rerun import ios
        from rerun.gui import App
        inst = next(iter(m.instances))
        aid = m.ops.store.active_id
        m.ops.store.update(aid, instance=inst)
        app = App(m)
        app.errors = []
        app.report_callback_exception = lambda *a: app.errors.append(a)
        got = []
        m.start = lambda name, script=None, **kw: got.append((name, script, kw)) or "ok"
        app.am_scan_units(m.ops.store.get(aid))
        assert got and got[0][:2] == (inst, "compendium_counter") and got[0][2]["confirm_account"] in (aid, None)
        b = m.ops.store.create("NoLink")
        alerts = []
        real = ios.alert
        ios.alert = lambda r, msg, title="Rerun": alerts.append(msg)
        try:
            app.am_scan_units(m.ops.store.get(b))
        finally:
            ios.alert = real
        assert alerts and "Link this account" in alerts[0] and len(got) == 1
        app.destroy()
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_scan_button_runs_in_the_background_and_updates_the_window():
    if ocr() is None:
        return
    root, m = mgr()
    try:
        from rerun.gui import App
        inst = next(iter(m.instances))
        aid = m.ops.store.active_id
        m.ops.store.update(aid, instance=inst)
        m.instances[inst].device = FakeDevice([cv2.imread(str(FX / "home.png"))])
        app = App(m)
        app.errors = []
        app.report_callback_exception = lambda *a: app.errors.append(a)
        app.nb.select(app._tab_accounts)
        app._am_nav.select("scan")
        app.am_scan(aid)
        t0 = time.time()
        while time.time() - t0 < 60 and (app._am_scan_busy or m.ops.store.value(aid, "gems") is None):
            app.update()
            time.sleep(0.05)
        for _ in range(10):
            app.update()
            time.sleep(0.03)
        assert m.ops.store.value(aid, "gems") == 184 and not app._am_scan_busy
        shown = []

        def walk(w):
            for c in w.winfo_children():
                try:
                    shown.append(str(c.cget("text")))
                except Exception:  # noqa: BLE001
                    pass
                walk(c)
        walk(app._am_inner)
        text = " ".join(shown)
        assert "top bar (scan)" in text and "Beta" in text and "Not supported yet" in text, text[:400]
        assert not app.errors, app.errors
        app.destroy()
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
