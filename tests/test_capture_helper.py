"""Templates tab 'Suggest Crop': boxes for palace tiles, quest rows and the Home button."""
from __future__ import annotations

import shutil
import sys
import tempfile
import time
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rerun import ios, textnav  # noqa: E402
from rerun.manager import Manager  # noqa: E402
from rerun.ocr import Word, OcrUnavailable, get_ocr  # noqa: E402

FIX = ROOT / "tests" / "fixtures"


def W(text, x, y, h=30, conf=95.0):
    return Word(text, conf, x, y, 100, h)


def ocr():
    try:
        return get_ocr(None)
    except OcrUnavailable:
        return None


# ---------------------------------------------------------------- pure rules
def test_home_button_box_is_fixed_and_unknown_templates_get_no_suggestion():
    rect, why = textnav.suggest_crop("home_nav_button", [])
    assert rect == (4, 1156, 112, 118) and "Home button" in why
    assert textnav.suggest_crop("battle_button", []) is None
    assert textnav.suggest_crop("crest_palace_icon", [W("Cursed", 300, 400)]) is None      # not a tile
    assert textnav.suggest_crop("crest_palace_target", []) is None                         # nothing readable


def test_palace_box_follows_the_preferred_name_else_the_topmost_banner():
    words = [W("Cursed", 330, 385, h=88), W("Whirl.", 340, 549, h=70), W("18h", 558, 332, h=16)]
    (x, y, w, h), _ = textnav.suggest_crop("crest_palace_target", words, ["Whirlwind"])
    assert (x, w, h) == (95, 530, 110) and 584 - 60 <= y + 50 <= 584 + 10, (x, y, w, h)
    (x, y, w, h), _ = textnav.suggest_crop("crest_palace_sat", words)          # no preference: topmost banner
    assert y + 50 == 385 + 44, (x, y, w, h)                                     # the tiny '18h' badge is ignored


def test_quest_row_box_uses_the_first_card():
    words = [W("Rank", 567, 734, h=10), W("Rank", 567, 934, h=10)]
    (x, y, w, h), why = textnav.suggest_crop("quest_list_entry2", words)
    assert (x, w, h) == (36, 340, 34) and y == 734 - 55 - 15 and "quest" in why, (x, y, w, h)
    assert textnav.suggest_crop("quest_list_entry", []) is None


# ---------------------------------------------------------------- real screens
def test_suggestions_match_the_boxes_that_worked_by_hand():
    if ocr() is None:
        return
    o = ocr()
    pal = cv2.imread(str(FIX / "crest_palace_list.png"))
    rect, _ = textnav.suggest_crop("crest_palace_target", o.screen_words(pal, min_conf=40), ["Cursed Claw"])
    x, y, w, h = rect                                                            # by hand: (95, 380, 530, 110)
    assert abs(y - 380) <= 8 and (x, w, h) == (95, 530, 110), rect
    # the crop holds the name and tagline, not the red time-left badge (which sits above y=360)
    assert y >= 370
    quest = cv2.imread(str(FIX / "quest_list_cursed_claw.png"))
    rect, _ = textnav.suggest_crop("quest_list_entry", o.screen_words(quest, min_conf=40))
    assert abs(rect[1] - 664) <= 6 and rect[0] == 36, rect                       # by hand: (36, 664, 340, 34)


# ---------------------------------------------------------------- the button
def test_suggest_crop_button_draws_the_box_for_the_selected_template():
    if ocr() is None:
        return
    from rerun.gui import App
    root = Path(tempfile.mkdtemp())
    shutil.copytree(ROOT / "routines", root / "routines")
    shutil.copytree(ROOT / "templates", root / "templates")
    m = Manager(root)
    m.config["live_view_fps"] = 0
    m.config["setup_seen"] = True
    app = App(m)
    alerts = []
    real = ios.alert
    ios.alert = lambda r, msg, title="Rerun": alerts.append(msg)
    try:
        app.nb.select(2)
        app.geometry("1220x900+40+40")
        for _ in range(5):
            app.update()
            time.sleep(0.05)
        # nothing to suggest on without a screenshot
        app.tpl_suggest()
        assert alerts and "screenshot" in alerts[-1].lower()
        app.set_tpl_image(cv2.imread(str(FIX / "quest_list_cursed_claw.png")))
        app.update()
        app.tpl_suggest()                                                       # no template picked yet
        assert "Pick a template" in alerts[-1]
        app.tpl_tree.selection_set("quest_list_entry")
        app.update()
        app.tpl_suggest()
        assert app.sel_rect, "the box should be drawn"
        s = app.tpl_scale
        x0, y0, x1, y1 = (v / s for v in app.sel_rect)                          # back to screenshot pixels
        assert abs(x0 - 36) < 2 and abs(y0 - 664) < 8 and abs((x1 - x0) - 340) < 2, (x0, y0, x1, y1)
        # a template with no rule: told so, the box is not touched
        app.sel_rect = None
        app.tpl_tree.selection_set("battle_button")
        app.tpl_suggest()
        assert app.sel_rect is None
    finally:
        ios.alert = real
        app.update()
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
