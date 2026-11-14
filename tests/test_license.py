"""Key system: Ed25519, key format, expiry, PC lock, clock rollback, saved key, key
generator time frames and log, and the sign-in screen. Uses a throw-away test signing key
(never the real one)."""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rerun import ed25519, license as lic_mod  # noqa: E402
from rerun.license import (ANY_PC, KeyError_, KeyStore, check, format_pc, make_key,  # noqa: E402
                           parse_key, parse_pc)

SEED = bytes(range(32))
PUB = ed25519.public_key(SEED)
PC_A, PC_B = bytes.fromhex("0102030405060708"), bytes.fromhex("1111111111111111")
NOW = 1_800_000_000.0


def raises(fn, text: str):
    try:
        fn()
    except KeyError_ as e:
        assert text.lower() in str(e).lower(), str(e)
        return
    raise AssertionError(f"expected a refusal containing {text!r}")


def test_ed25519_rfc8032_vector():
    sk = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
    assert ed25519.public_key(sk).hex() == "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"
    sig = ed25519.sign(sk, b"")
    assert sig.hex() == ("e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8"
                         "821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b")
    assert ed25519.verify(ed25519.public_key(sk), b"", sig)
    assert not ed25519.verify(ed25519.public_key(sk), b"x", sig)


def test_key_round_trip_and_tolerant_input():
    key = make_key(SEED, NOW + 86400, issued=NOW)
    assert key.startswith("RERUN-")
    lic = check(key, NOW, public=PUB, pc=PC_A)
    assert lic.expires == NOW + 86400 and lic.pc == ANY_PC and not lic.lifetime
    messy = "  " + key.lower().replace("-", " ") + "\n"
    assert check(messy, NOW, public=PUB, pc=PC_A).key == key


def test_rejects_changed_wrong_and_incomplete_keys():
    key = make_key(SEED, 0, issued=NOW)
    body = key.replace("-", "")
    flipped = body[:20] + ("A" if body[20] != "A" else "B") + body[21:]
    raises(lambda: check(flipped, NOW, public=PUB), "not valid")
    other = ed25519.public_key(bytes(32))
    raises(lambda: check(key, NOW, public=other), "not valid")      # made with another signing key
    raises(lambda: check(key[:60], NOW, public=PUB), "incomplete")
    raises(lambda: check("hello", NOW, public=PUB), "starts with RERUN-")
    raises(lambda: check("not a key!!", NOW, public=PUB), "starts with RERUN-")


def test_expiry_lifetime_and_pc_lock():
    k = make_key(SEED, NOW + 3600, issued=NOW)
    assert check(k, NOW + 3599, public=PUB)
    raises(lambda: check(k, NOW + 3600, public=PUB), "expired")
    life = make_key(SEED, 0, issued=NOW)
    assert check(life, NOW + 50 * 365 * 86400, public=PUB).lifetime
    locked = make_key(SEED, 0, PC_A, issued=NOW)
    assert check(locked, NOW, public=PUB, pc=PC_A)
    raises(lambda: check(locked, NOW, public=PUB, pc=PC_B), "another pc")


def test_clock_rollback_is_refused():
    k = make_key(SEED, NOW + 10 * 86400, issued=NOW)
    raises(lambda: check(k, NOW, last_seen=NOW + 2 * 86400, public=PUB), "clock")
    assert check(k, NOW, last_seen=NOW + 1800, public=PUB)            # small corrections are fine


def test_saved_key_store():
    with tempfile.TemporaryDirectory() as d:
        st = KeyStore(d)
        raises(lambda: st.current(NOW, PUB, PC_A), "enter your rerun key")
        k = make_key(SEED, NOW + 86400, issued=NOW)
        st.save(k, NOW)
        assert st.current(NOW + 10, PUB, PC_A).key == k
        st.touch(NOW + 5 * 3600)
        assert st.last_seen == NOW + 5 * 3600
        st.save(k, NOW)                                               # last_seen never goes back
        assert st.last_seen == NOW + 5 * 3600
        raises(lambda: st.current(NOW, PUB, PC_A), "clock")           # clock turned back 5 h
        raises(lambda: st.current(NOW + 86400, PUB, PC_A), "expired")
        st.sign_out()
        assert st.saved_key() == ""


def test_pc_id_format():
    assert format_pc(PC_A) == "0102-0304-0506-0708"
    assert parse_pc(" 0102-0304-0506-0708 ") == PC_A
    try:
        parse_pc("12-34")
    except ValueError:
        pass
    else:
        raise AssertionError
    assert len(lic_mod.machine_id()) == 8 and lic_mod.machine_id() == lic_mod.machine_id()


def _keygen():
    spec = importlib.util.spec_from_file_location("keygen", ROOT / "tools" / "keygen.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_keygen_time_frames():
    kg = _keygen()
    t0 = datetime(2026, 1, 31, 12, 0).timestamp()
    assert kg.expiry("days", 30, t0) == t0 + 30 * 86400
    assert kg.expiry("hours", 1, t0) == t0 + 3600
    assert datetime.fromtimestamp(kg.expiry("months", 1, t0)) == datetime(2026, 2, 28, 12, 0)
    assert datetime.fromtimestamp(kg.expiry("years", 1, t0)) == datetime(2027, 1, 31, 12, 0)
    assert kg.expiry("lifetime", 0, t0) == 0
    for bad in (("days", 0), ("months", 1.5), ("years", 200)):
        try:
            kg.expiry(*bad, t0)
        except ValueError:
            continue
        raise AssertionError(bad)
    assert datetime.fromtimestamp(kg.parse_until("2026-12-31", t0)) == datetime(2026, 12, 31, 23, 59)
    assert datetime.fromtimestamp(kg.parse_until("2026-12-31 18:00", t0)) == datetime(2026, 12, 31, 18, 0)
    for bad in ("2025-01-01", "31/12/2026"):
        try:
            kg.parse_until(bad, t0)
        except ValueError:
            continue
        raise AssertionError(bad)


def test_keygen_issues_keys_and_logs_them():
    kg_mod = _keygen()
    with tempfile.TemporaryDirectory() as d:
        kg = kg_mod.Keygen(Path(d))
        assert kg.secret() is None
        pub = kg.init()
        try:
            kg.init()
        except FileExistsError:
            pass
        else:
            raise AssertionError("init must never overwrite a signing key")
        key = kg.issue(NOW + 7 * 86400, PC_A, "for Sam", "7 days", now=NOW)
        lic = check(key, NOW + 1, public=pub, pc=PC_A)
        assert lic.expires == NOW + 7 * 86400
        rows = kg.issued()
        assert rows[0]["note"] == "for Sam" and rows[0]["pc"] == "0102-0304-0506-0708"
        assert rows[0]["key"] == key and rows[0]["time_frame"] == "7 days"
        assert not kg.matches_rerun()          # a test key never opens the real Rerun


def test_sign_in_screen():
    import tkinter as tk
    from rerun import ios
    from rerun.license_gate import SignIn
    old = lic_mod.PUBLIC_KEY
    lic_mod.PUBLIC_KEY = PUB
    root = tk.Tk()
    try:
        ios.init(root, "light")
        with tempfile.TemporaryDirectory() as d:
            st = KeyStore(d)
            got = []
            page = SignIn(root, st, on_done=got.append)
            page.pack()
            root.update()
            page.text.insert("1.0", "RERUN-NOPE")
            page.submit()
            assert not got and "starts with rerun-" in page.msg.cget("text").lower()
            page.text.delete("1.0", "end")
            page.text.insert("1.0", make_key(SEED, time.time() + 3600))
            page.submit()
            assert got and got[0].remaining() > 0 and st.saved_key()
    finally:
        lic_mod.PUBLIC_KEY = old
        root.destroy()


def test_dashboard_timer_text():
    from rerun.gui import App
    from rerun.license import License
    lic = License("k", NOW, NOW + 29 * 86400 + 3 * 3600 + 4 * 60 + 5, ANY_PC, "id")
    assert App.key_timer_text(lic, NOW) == ("Key: 29d 03:04:05 left", "secondary")
    assert App.key_timer_text(lic, lic.expires - 5400) == ("Key: 01:30:00 left", "orange")
    assert App.key_timer_text(lic, lic.expires - 59) == ("Key: 00:00:59 left", "red")
    assert App.key_timer_text(lic, lic.expires + 10)[0] == "Key: 00:00:00 left"
    assert App.key_timer_text(License("k", NOW, 0, ANY_PC, "id"))[0] == "Key: Lifetime"


def test_signed_in_app_shows_notice_and_countdown():
    import shutil
    from rerun import gui, ios
    from rerun.license import License
    from rerun.manager import Manager
    root = Path(tempfile.mkdtemp())
    shutil.copytree(ROOT / "routines", root / "routines")
    m = Manager(root)
    m.config["live_view_fps"] = 0
    shown = []
    old_alert = ios.alert
    ios.alert = lambda master, text, title="Rerun": shown.append(title)
    try:
        app = gui.App(m, license=License("k", time.time(), time.time() + 2 * 86400 + 60, ANY_PC, "id"))
        app._start_hotkeys = lambda: None
        texts = []
        app.after(2500, lambda: (texts.append(app.key_timer.cget("text")), app.tray.stop(), app.destroy()))
        app.mainloop()
    finally:
        ios.alert = old_alert
    assert shown == ["Work In Progress"], shown
    assert texts and texts[0].startswith("Key: 2d "), texts


def test_real_public_key_is_set():
    assert lic_mod.PUBLIC_KEY != bytes(32) and len(lic_mod.PUBLIC_KEY) == 32


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
