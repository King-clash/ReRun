"""Text reading (Tesseract) on real game screenshots. Skipped when Tesseract
isn't available (it ships with ReStart)."""
from __future__ import annotations

import sys
import time
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rerun.ocr import OcrUnavailable, get_ocr  # noqa: E402

FIX = ROOT / "tests" / "fixtures"
try:
    ocr = get_ocr()
except OcrUnavailable:
    ocr = None


def img(name):
    return cv2.imread(str(FIX / name))


def test_reads_the_error_popup():
    r = ocr.read_region(img("unexpected_error_party.png"), 150, 565, 420, 45)
    assert r.text == "An unexpected error has occurred." and r.confidence > 85, r


def test_reads_quest_titles():
    s = img("quest_list_story.png")
    got = [ocr.read_region(s, 30, y, 440, 35).text for y in (485, 672, 858)]
    assert got == ["Things Which Don't Change", "Where Determination Leads",
                   "Another Day in Reigrad"], got


def test_reads_numbers():
    assert ocr.read_number(img("auto_loop_settings.png")[560:600, 560:710]) == 100
    assert ocr.read_number(img("auto_loop_one.png")[560:600, 560:710]) == 1
    assert ocr.read_number(img("auto_loop_one_b.png")[560:600, 560:710]) == 1


def test_loop_counter_falls_back_to_ocr():
    """With no digit templates matching, set_loops still reads the counter."""
    from rerun.adb import FakeDevice
    from rerun.engine import Context
    from rerun.loop_count import read_loops_ocr
    from rerun.scripts import AnyQuestScript
    from rerun.stats import Stats
    from rerun.vision import TemplateStore, Vision
    v = Vision(TemplateStore(ROOT / "templates"))
    for name, want in (("auto_loop_settings.png", 100), ("auto_loop_one_b.png", 1)):
        frame = img(name)
        ctx = Context(instance="t", device=FakeDevice([frame]), vision=v, stats=Stats(),
                      routines={}, base_resolution=(720, 1280), log=lambda *a: None,
                      notify=lambda *a, **k: None)
        s = AnyQuestScript(ctx, {})
        assert read_loops_ocr(s, frame) == want, name


def test_screen_text_names_the_popup():
    words = ocr.screen_text(img("unexpected_error_party.png")).lower()
    assert "unexpected" in words and "error" in words, words


def _ctx(frame):
    from rerun.adb import FakeDevice
    from rerun.engine import Context
    from rerun.stats import Stats
    from rerun.vision import TemplateStore, Vision
    return Context(instance="t", device=FakeDevice([frame]), vision=Vision(TemplateStore(ROOT / "templates")),
                   stats=Stats(), routines={}, base_resolution=(720, 1280), log=lambda *a: None,
                   notify=lambda *a, **k: None, data_dir=ROOT / "tests" / "_tmp")


def test_energy_bar_reads_right_or_not_at_all():
    from rerun.ocr import read_energy, read_energy_cost
    truth = {"party_reigrad.png": (214, 517), "quest_list_story.png": (215, 517),
             "home.png": (383, 517), "home_after_error.png": (204, 517),
             "equip_crest_lv3.png": (40, 517), "loop_results.png": (51, 517)}
    for f, want in truth.items():
        assert read_energy(ocr, img(f)) == want, (f, read_energy(ocr, img(f)))
    for f in ("auto_loop_settings.png", "energy_dialog.png"):  # bar hidden/dimmed
        assert read_energy(ocr, img(f)) in (None,), f
    assert read_energy_cost(ocr, img("party_reigrad.png")) == 1
    assert read_energy_cost(ocr, img("unexpected_error_party.png")) == 20


def test_crest_title_agrees_with_icon_on_real_screen():
    from rerun.scripts import CrestScript
    frame = img("equip_crest_lv3.png")
    s = CrestScript(_ctx(frame), {"start_home": False})
    s.on_start()
    box = s.find_orange_box(frame)
    assert s.read_crest_text(frame, box) == ("lv3", "Dark Resistance Lv3")


def test_crest_stops_when_title_and_icon_disagree():
    from rerun.scripts import CrestScript
    from rerun.scripts.base import Finished
    frame = img("equip_crest_lv3.png")
    ctx = _ctx(frame)
    s = CrestScript(ctx, {"start_home": False})
    s.on_start()
    s.sleep = lambda *a, **k: None
    s.read_crest_text = lambda screen, box: ("lv4", "Dark Resistance Lv4")
    try:
        s.handle_equip_crest_screen(frame)
        raise AssertionError("should stop")
    except Finished as e:
        assert "disagree" in str(e)
    assert ctx.device.taps == [], ctx.device.taps  # nothing ticked or scrapped


def test_text_safety_net_taps_the_popups_ok():
    """With no template for it, the error popup is recognised by its words."""
    from rerun.scripts.base import BaseScript
    frame = img("unexpected_error_party.png")
    ctx = _ctx(frame)
    s = BaseScript(ctx, {})
    s.sleep = lambda *a, **k: None
    s._unknown_since = time.monotonic() - 30
    assert s._text_safety_net(frame) is True
    x, y = ctx.device.taps[0]
    assert 320 < x < 400 and 670 < y < 710, ctx.device.taps


def test_no_energy_no_battle_when_refills_are_off():
    from rerun.scripts import AnyQuestScript
    from rerun.scripts.base import Done
    import rerun.ocr as o
    frame = img("party_reigrad.png")  # energy 214/517
    s = AnyQuestScript(_ctx(frame), {"potion": "Don't use potions"})
    s.on_start()
    real = o.read_energy_cost
    o.read_energy_cost = lambda ocr_, screen: 500
    try:
        s.check_energy_for_quest(frame)
        raise AssertionError("should stop")
    except Done as e:
        assert "214/517" in str(e) or "out of energy" in str(e), e
    finally:
        o.read_energy_cost = real


def test_find_text():
    assert ocr.find_text(img("unexpected_error_party.png")[540:640, :], "unexpected error")
    assert not ocr.find_text(img("home.png")[540:640, :], "unexpected error")


if __name__ == "__main__":
    if ocr is None:
        print("SKIP: Tesseract not available")
        sys.exit(0)
    failed = 0
    t0 = time.time()
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("PASS", name)
            except Exception as e:  # noqa: BLE001
                failed += 1
                print("FAIL", name, repr(e))
    print(f"\n{'all passed' if not failed else f'{failed} failed'} in {time.time() - t0:.1f}s")
    sys.exit(1 if failed else 0)
