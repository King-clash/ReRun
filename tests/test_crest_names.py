"""Crest finds the palace and quest by the words on screen when no picture matches
(palaces rotate and every quest looks different). Real screens: tests/fixtures/crest_palace_list.png
and quest_list_cursed_claw.png (taken from the live game 2026-11-14)."""
from __future__ import annotations

import sys
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rerun import textnav  # noqa: E402
from rerun.adb import FakeDevice  # noqa: E402
from rerun.engine import Context  # noqa: E402
from rerun.ocr import OcrUnavailable, Word, get_ocr  # noqa: E402
from rerun.scripts import CrestScript  # noqa: E402
from rerun.scripts.base import Finished  # noqa: E402
from rerun.stats import Stats  # noqa: E402
from rerun.vision import TemplateStore, Vision  # noqa: E402

FIX = ROOT / "tests" / "fixtures"
VISION = Vision(TemplateStore(ROOT / "templates"))


def W(text, x, y, h=30, conf=95.0):
    return Word(text, conf, x, y, 100, h)


# ---------------------------------------------------------------- pure logic (no OCR needed)
def test_distinctive_words_ignore_common_ones():
    assert textnav.distinctive("Shrine of Cursed Claw") == ["cursed", "claw"]
    assert textnav.distinctive("The Temple") == ["the", "temple"]  # only common words: keep all


def test_partial_and_cut_off_words_still_match():
    words = [W("Shrine", 85, 385), W("Cursed", 330, 385, h=88), W("Whirl.", 340, 549, h=70)]
    assert textnav.find_name(words, "Shrine of Cursed Claw").y == 385 + 44
    assert textnav.find_name(words, "Whirlwind").y == 549 + 35
    assert textnav.find_name(words, "Heavenly Light") is None


def test_two_palaces_sharing_a_word_is_never_guessed():
    words = [W("Light", 100, 400), W("Light", 100, 700)]
    assert textnav.find_name(words, "Light") is None


def test_quest_rows_counts_cards():
    words = [W("Rank", 567, 734, h=10), W("[Extreme]", 43, 670), W("Scars", 288, 670),
             W("Rank", 567, 934, h=10), W("Other", 43, 870), W("Quest", 120, 870)]
    rows = textnav.quest_rows(words)
    assert [r["title"] for r in rows] == ["[Extreme] Scars", "Other Quest"], rows


# ---------------------------------------------------------------- real screens (need the text reader)
def _ocr():
    try:
        return get_ocr(None)
    except OcrUnavailable:
        return None


def _script(img, settings):
    notes, logs = [], []
    dev = FakeDevice([img])
    ctx = Context(instance="t", device=dev, vision=VISION, stats=Stats(), routines={},
                  base_resolution=(720, 1280), log=lambda i, m: logs.append(m),
                  notify=lambda i, m, **k: notes.append(m))
    s = CrestScript(ctx, {"start_home": False, **settings})
    s.sleep = lambda *a, **k: None
    s.on_start()
    s.nav_active = True
    return s, dev, notes, logs


def test_palace_chosen_by_name_on_the_real_screen():
    if _ocr() is None:
        return
    img = cv2.imread(str(FIX / "crest_palace_list.png"))
    for name, lo, hi in (("Cursed Claw", 335, 490), ("Whirlwind", 520, 670), ("Heavenly Light", 700, 850)):
        s, dev, notes, logs = _script(img, {"palace_name": name})
        s.handle_crest_palace_screen(img)
        (x, y), = dev.taps
        assert lo <= y <= hi and 100 < x < 620, (name, dev.taps)
        assert any("by name" in l for l in logs), logs


def test_palace_not_on_the_list_stops_and_says_what_it_can_read():
    if _ocr() is None:
        return
    img = cv2.imread(str(FIX / "crest_palace_list.png"))
    s, dev, notes, logs = _script(img, {"palace_name": "Tower of Nowhere"})
    try:
        s.handle_crest_palace_screen(img)
        raise AssertionError("should stop")
    except Finished:
        pass
    assert dev.taps == [] and notes and "Tower of Nowhere" in notes[0] and "I can read" in notes[0], notes


def test_quest_chosen_by_name_and_as_the_only_quest():
    if _ocr() is None:
        return
    img = cv2.imread(str(FIX / "quest_list_cursed_claw.png"))
    for settings, expect in (({"quest_name": "Experimental Scars"}, "by name"), ({}, "only quest")):
        s, dev, notes, logs = _script(img, settings)
        s.handle_quest_list(img)
        (x, y), = dev.taps
        assert 655 <= y <= 700, dev.taps
        assert any(expect in l for l in logs), logs


def test_wrong_quest_name_is_a_miss_not_a_guess():
    if _ocr() is None:
        return
    img = cv2.imread(str(FIX / "quest_list_cursed_claw.png"))
    s, dev, notes, logs = _script(img, {"quest_name": "Glittering Dragon Defense"})
    s.handle_quest_list(img)
    assert dev.taps == [] and any("no quest row picture or name" in l for l in logs), logs


def test_preflight_accepts_a_palace_name_instead_of_a_tile_picture():
    have = {"exploring_button", "quest_list", "crest_palace_icon"}
    assert CrestScript.nav_missing(have.__contains__)[0].startswith("crest_palace_target")
    assert CrestScript.nav_missing(have.__contains__, "Cursed Claw") == []
    assert "text reader" in CrestScript.nav_missing(have.__contains__, "Cursed Claw", ocr_ok=False)[0]


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
