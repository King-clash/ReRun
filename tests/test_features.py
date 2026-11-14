"""Tests for the newer pieces: energy refills and caps (on a real screenshot),
fast screenshots, the History store, stats saving, log levels, Queue's
hand-offs, and the state wiring of every script."""
from __future__ import annotations

import struct
import sys
import tempfile
import time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rerun.adb import Device, FakeDevice  # noqa: E402
from rerun.engine import Context, StopRoutine  # noqa: E402
from rerun.history import History  # noqa: E402
from rerun.manager import log_level  # noqa: E402
from rerun.scripts import SCRIPTS  # noqa: E402
from rerun.scripts.base import BaseScript, Finished, WindowElapsed  # noqa: E402
from rerun.stats import Stats  # noqa: E402
from rerun.vision import TemplateStore, Vision  # noqa: E402

FIX = ROOT / "tests" / "fixtures"
store = TemplateStore(ROOT / "templates")
vision = Vision(store)


TMP = Path(tempfile.mkdtemp(prefix="rerun_test_"))


def ctx_for(img, history=None, data_dir=None):
    return Context(instance="t", device=FakeDevice([img]), vision=vision, stats=Stats(),
                   routines={}, base_resolution=(720, 1280), log=lambda *a: None,
                   notify=lambda *a, **k: None, history=history, data_dir=data_dir or TMP)


def no_wait(script):
    script.sleep = lambda *a, **k: None
    script.wait_for = lambda *a, **k: None
    return script


# ------------------------------------------------------------------ energy
def energy_run(settings: dict, potions_used: int = 0):
    from rerun.scripts import AnyQuestScript
    img = cv2.imread(str(FIX / "energy_dialog.png"))
    ctx = ctx_for(img)
    s = no_wait(AnyQuestScript(ctx, settings))
    s.on_start()
    s.potions_used = potions_used
    try:
        s.handle_use_pot_button(img)
        return ctx.device.taps, None
    except Finished as e:
        return ctx.device.taps, str(e)


def test_energy_dialog_has_five_use_buttons():
    uses = vision.find_all(cv2.imread(str(FIX / "energy_dialog.png")), "use_pot_button")
    ys = [u.y for u in uses]
    assert len(ys) == 5 and all(abs(a - b) <= 2 for a, b in zip(ys, [316, 480, 645, 809, 974])), ys


def test_potion_choice_taps_its_own_row():
    # Rows: S at y~501, M ~666, L ~830, Cupcake ~995 (Use button centres).
    for choice, row_y in (("L Potion", 830), ("M Potion", 666), ("S Potion", 501),
                          ("Rekyuon Cupcake", 995)):
        taps, stopped = energy_run({"potion": choice})
        assert stopped is None, (choice, stopped)
        assert abs(taps[0][1] - row_y) <= 4 and taps[0][0] > 560, (choice, taps)


def test_potion_caps_and_off_switch_stop_without_tapping():
    taps, stopped = energy_run({"potion": "L Potion", "potion_limit": 2}, potions_used=2)
    assert stopped and "limit" in stopped and not taps, (stopped, taps)
    taps, stopped = energy_run({"potion": "Don't use potions"})
    assert stopped and not taps, (stopped, taps)
    taps, stopped = energy_run({"potion": "L Potion", "potion_limit": 2}, potions_used=1)
    assert stopped is None and len(taps) == 1


def test_potion_icon_needs_its_colour():
    """S/M/L potions are the same bottle in different colours: with the L row
    hidden, the L icon must not be 'found' on the M or S bottle."""
    img = cv2.imread(str(FIX / "energy_dialog.png"))
    img[760:880, 40:700] = 30
    assert vision.find(img, "potion_l") is None
    assert vision.find(img, "potion_m") is not None


# ------------------------------------------------------------------ adb
def test_raw_screencap_decoding():
    w, h = 4, 3
    rgba = np.zeros((h, w, 4), np.uint8)
    rgba[..., 0] = 200  # red
    rgba[..., 3] = 255
    for header in (struct.pack("<III", w, h, 1), struct.pack("<IIII", w, h, 1, 0)):
        img = Device._decode_raw(header + rgba.tobytes())
        assert img.shape == (h, w, 3) and tuple(img[0, 0]) == (0, 0, 200)
    assert Device._decode_raw(struct.pack("<III", w, h, 5) + rgba.tobytes()) is None  # other format
    assert Device._decode_raw(b"\x89PNG....") is None


# ------------------------------------------------------------------ history / stats / log
def test_history_records_thumbs_and_summarises():
    with tempfile.TemporaryDirectory() as d:
        h = History(d)
        img = np.full((100, 600, 3), 120, np.uint8)
        h.add("A", "crest", "crest", "lv3 scrapped", img, rarity="lv3", action="scrapped")
        h.add("A", "crest", "crest", "4+ kept", img, rarity="4+", action="kept")
        h.add("B", "crest", "energy", "Used L Potion")
        assert len(h.recent()) == 3 and h.recent()[0]["detail"] == "Used L Potion"
        assert h.thumb_path(h.recent(kind="crest")[0]).exists()
        assert h.crest_summary("A") == {"scrapped": 1, "lv3": 1, "kept": 1, "4+": 1}
        h2 = History(d)  # reloads from disk
        assert len(h2.recent()) == 3
        h2.clear()
        assert not h2.recent() and not list((Path(d) / "thumbs").iterdir())


def test_stats_are_saved_on_flush():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "stats.json"
        s = Stats(p)
        for _ in range(50):
            s.incr("A", "crest.runs")
        s.flush()
        assert Stats(p).get("A")["crest.runs"] == 50


def test_log_levels():
    assert log_level("Error: adb timed out") == "error"
    assert log_level("Crashed: ValueError()") == "error"
    assert log_level("NOTIFY: lv4 crest found") == "warn"
    assert log_level("[Crest] Could not find the new crest row") == "warn"
    assert log_level("[Crest] Run completed. 3/10") == "info"


# ------------------------------------------------------------------ queue
def test_queue_switches_and_stops_on_rare_crest():
    import rerun.scripts.queue_gc_crest as q
    from rerun.scripts.grand_crusade import OutOfStamina
    calls = []

    class FakeGC:
        def __init__(self, ctx, cfg):
            calls.append(("gc", cfg["no_stamina"], cfg["mode_247"]))

        def run(self):
            raise OutOfStamina("out of stamina")

    class FakeCrest:
        n = 0

        def __init__(self, ctx, cfg):
            self.deadline = None
            calls.append(("crest", cfg["mode_247"]))

        def run(self):
            FakeCrest.n += 1
            assert self.deadline is not None
            if FakeCrest.n == 1:
                raise WindowElapsed("time window elapsed")
            raise Finished("4+ crest")

    real = q.GrandCrusadeScript, q.CrestScript
    q.GrandCrusadeScript, q.CrestScript = FakeGC, FakeCrest
    try:
        ctx = ctx_for(np.zeros((1280, 720, 3), np.uint8))
        ctx.params["settings_of"] = lambda sid: {}
        s = no_wait(q.QueueScript(ctx, {"crest_minutes": 5}))
        s.restart_game = lambda: None
        try:
            s.run()
            raise AssertionError("queue should stop on the rare crest")
        except Finished as e:
            assert str(e) == "4+ crest", e
    finally:
        q.GrandCrusadeScript, q.CrestScript = real
    assert calls == [("gc", "Stop", True), ("crest", True), ("gc", "Stop", True), ("crest", True)], calls


# ------------------------------------------------------------------ state wiring
def synthetic(names: list[str]) -> np.ndarray:
    """A neutral 720x1280 frame with the given templates pasted on it."""
    rng = np.random.default_rng(7)
    img = (rng.integers(0, 40, (1280, 720, 3)) + 60).astype(np.uint8)
    y = 260
    for n in names:
        t = store.get(n)
        h, w = t.shape[:2]
        x = max(0, min(80, 720 - w))
        img[y:y + h, x:x + w] = t
        y += h + 40
    return img


# Grand Crusade's blue Close is the same button as the login summon prompt's
# Close; the shared popup handler taps it, which is exactly what GC wants.
SAME_BUTTON = {("close", "summon_close_button")}


def test_every_script_state_is_detected_and_handled():
    """For every script and every state: a frame showing that state's template is
    detected as that state, and its handler runs without crashing."""
    problems = []
    for sid, cls in SCRIPTS.items():
        if sid == "queue":
            continue  # runs other scripts; covered above
        for entry in cls.STATES:
            state, names = entry[0], entry[1]
            context = list(entry[2]) if len(entry) > 2 else []
            tpl = next((n for n in names if store.has(n)), None)
            if tpl is None or not all(store.has(c) for c in context):
                continue  # user-captured template (e.g. raid_ticket_target)
            img = synthetic(context + [tpl])
            ctx = ctx_for(img)
            s = no_wait(cls(ctx, {}))
            s.on_start()
            got = s.detect_state(img)
            if (state, got) in SAME_BUTTON:
                continue  # a shared handler that taps the very same button
            if got != state:
                problems.append(f"{sid}: '{tpl}' detected as '{got}', expected '{state}'")
                continue
            s.state = state
            handler = getattr(s, f"handle_{state}", None)
            if handler is None:
                handler = s._tap_handler if state in cls.TAPS else s.handle_unknown
            try:
                handler(img)
            except StopRoutine:
                pass
            except Exception as e:  # noqa: BLE001
                problems.append(f"{sid}.{state}: {type(e).__name__}: {e}")
    assert not problems, "\n".join(problems)


def test_crest_title_levels():
    from rerun.scripts.crest import text_rarity
    assert text_rarity("Dark Resistance Lv3") == "lv3"
    assert text_rarity("Fire Up Lv3+") == "lv3+"
    assert text_rarity("Water Lv 4") == "lv4"
    assert text_rarity("Breaker Lv4+") == "4+"
    assert text_rarity("Dark resistance 5% UP") is None


def test_chain_steps_parse_and_validate():
    from rerun.scripts.chain import parse_steps
    assert parse_steps("login_mail; crest 90m;arena") == [("login_mail", None), ("crest", 90),
                                                          ("arena", None)]
    for bad in ("", "any_quest", "crest ninety"):
        try:
            parse_steps(bad)
            raise AssertionError(f"accepted {bad!r}")
        except ValueError:
            pass


def test_chain_moves_on_only_when_nothing_needs_you():
    import rerun.scripts as S
    from rerun.scripts.base import Done
    from rerun.scripts.chain import ChainScript
    ran = []

    def fake(name, outcome):
        class F:
            NAME = name

            def __init__(self, ctx, cfg):
                assert cfg["mode_247"] is True
                self.deadline = None

            def run(self):
                ran.append((name, self.deadline is not None))
                raise outcome
        return F

    saved = dict(S.SCRIPTS)
    try:
        S.SCRIPTS["login_mail"] = fake("Login", Done("mailbox empty"))
        S.SCRIPTS["crest"] = fake("Crest", WindowElapsed("time"))
        S.SCRIPTS["arena"] = fake("Arena", Finished("4+ crest left on screen"))
        S.SCRIPTS["mines"] = fake("Mines", Done("runs done"))
        ctx = ctx_for(np.zeros((1280, 720, 3), np.uint8))
        s = no_wait(ChainScript(ctx, {"steps": "login_mail; crest 30m; arena; mines"}))
        restarts = []
        s.restart_game = lambda: restarts.append(1)
        try:
            s.run()
            raise AssertionError("chain should stop at Arena")
        except Finished as e:
            assert not isinstance(e, Done) and "crest" in str(e), e
    finally:
        S.SCRIPTS.clear()
        S.SCRIPTS.update(saved)
    assert ran == [("Login", False), ("Crest", True), ("Arena", False)], ran  # never reached Mines
    assert len(restarts) == 2, restarts


def test_scheduler_starts_once_a_day_and_summary():
    from datetime import datetime
    from rerun.manager import Manager
    with tempfile.TemporaryDirectory() as d:
        m = Manager(d)
        name = next(iter(m.instances))
        m.config["schedules"] = {name: {"enabled": True, "time": "06:05"}}
        started = []
        m.start = lambda n, script=None: started.append(n) or "ok"
        assert m.scheduler_tick(datetime(2026, 11, 15, 6, 4)) == []
        assert m.scheduler_tick(datetime(2026, 11, 15, 6, 5)) == [f"start {name}"]
        assert m.scheduler_tick(datetime(2026, 11, 15, 6, 5)) == []      # once per day
        assert m.scheduler_tick(datetime(2026, 11, 16, 6, 5)) == [f"start {name}"]
        m.history.add(name, "crest", "crest", "lv3 scrapped", action="scrapped", rarity="lv3")
        text = m.daily_summary()
        assert "daily summary" in text.lower() and name in text and "1 scrapped" in text, text


def test_template_health_flags_fading_templates():
    v2 = Vision(store)
    thr = store.threshold("drop_info")
    for _ in range(6):
        v2._note_hit("drop_info", thr + 0.01)
        v2._note_hit("battle_button", 0.97)
    h = v2.health()
    assert h["drop_info"]["weak"] and not h["battle_button"]["weak"], h
    v2.reset_health("drop_info")
    assert "drop_info" not in v2.health()


def test_instances_in_parallel_share_vision_safely():
    """Several instances run in their own threads but share one Vision (with a
    per-thread frame cache), History and Stats. Each thread must get exactly
    the answers it gets alone, and no counts may be lost."""
    import threading
    from rerun.scripts import CrestScript
    names = ["home.png", "loop_results.png", "crest_fragment_popup.png", "equip_crest_lv3.png",
             "auto_loop_settings.png", "unexpected_error_party.png"]
    frames = [cv2.imread(str(FIX / n)) for n in names]

    def detect(img):
        s = CrestScript(ctx_for(img), {})
        s.on_start()
        return s.detect_state(img)
    solo = [detect(f) for f in frames]
    stats = Stats()
    with tempfile.TemporaryDirectory() as d:
        hist = History(d)
        errors, results = [], {}

        def worker(k):
            try:
                out = []
                for rep in range(4):
                    for i, f in enumerate(frames):
                        out.append((i, detect(f)))
                        stats.incr(f"inst{k}", "crest.runs")
                        hist.add(f"inst{k}", "crest", "crest", f"{i}", f[:50, :50])
                results[k] = out
            except Exception as e:  # noqa: BLE001
                errors.append(repr(e))
        threads = [threading.Thread(target=worker, args=(k,)) for k in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors, errors
        for k, out in results.items():
            for i, got in out:
                assert got == solo[i], (k, names[i], got, solo[i])
        assert all(stats.get(f"inst{k}")["crest.runs"] == 24 for k in range(4))
        assert len(hist.recent(1000)) == 96


def test_beta_scripts_are_labelled():
    labels = {k: c.display_name() for k, c in SCRIPTS.items()}
    assert labels["crest"] == "Crest" and labels["arena"] == "Arena (Beta)"


if __name__ == "__main__":
    failed = 0
    t0 = time.time()
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("PASS", name)
            except Exception as e:  # noqa: BLE001
                failed += 1
                import traceback
                traceback.print_exc()
                print("FAIL", name, e)
    print(f"\n{'all passed' if not failed else f'{failed} failed'} in {time.time() - t0:.1f}s")
    sys.exit(1 if failed else 0)
