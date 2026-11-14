"""Regression tests on real Grand Summoners screenshots (needs the imported templates)."""
from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rerun.vision import TemplateStore, Vision  # noqa: E402

FIX = ROOT / "tests" / "fixtures"
store = TemplateStore(ROOT / "templates")
v = Vision(store)


def need(*names):
    missing = [n for n in names if not store.has(n)]
    if missing:
        print(f"SKIP (templates not imported: {missing})")
        return False
    return True


def test_home_screen():
    if not need("exploring_button", "mail_chest", "drop_info", "equip_crest_screen"):
        return
    img = cv2.imread(str(FIX / "home.png"))
    assert v.find(img, "exploring_button"), "Exploring not found on Home"
    assert v.find(img, "mail_chest"), "mail chest not found on Home"
    for wrong in ("drop_info", "equip_crest_screen", "battle_button", "claim_all_button"):
        if store.has(wrong):
            assert not v.find(img, wrong), f"false positive: {wrong}"


def test_empty_mailbox_claim_all_is_greyed():
    if not need("claim_all_button", "claim_all_button_dim", "mail_close_button"):
        return
    img = cv2.imread(str(FIX / "mailbox_empty.png"))
    m = v.find(img, "claim_all_button")
    assert m, "Claim All not found"
    assert v.closest_by_brightness(img, m, ["claim_all_button", "claim_all_button_dim"]) \
        == "claim_all_button_dim"
    assert v.find(img, "mail_close_button")
    if store.has("mail_empty_text"):
        assert v.find(img, "mail_empty_text")


def crest_state(fixture: str) -> str:
    from rerun.adb import FakeDevice
    from rerun.engine import Context
    from rerun.scripts import CrestScript
    from rerun.stats import Stats
    img = cv2.imread(str(FIX / fixture))
    ctx = Context(instance="t", device=FakeDevice([img]), vision=v, stats=Stats(), routines={},
                  base_resolution=(720, 1280), log=lambda *a: None, notify=lambda *a, **k: None)
    s = CrestScript(ctx, {"start_home": False})
    s.on_start()
    return s.detect_state(img)


def test_crest_states_on_real_screens():
    if not need("crest_fragment", "drop_info", "results_redeploy", "looping_button", "select_crest_ok2"):
        return
    assert crest_state("crest_fragment_popup.png") == "crest_fragment"
    # Loop results: Drop Info + Redeploy bar. Must NOT be read as a scrap confirmation.
    assert crest_state("loop_results.png") == "drop_info"
    assert crest_state("auto_loop_settings.png") == "looping_button"
    assert crest_state("home.png") == "home_screen"


def test_equip_crest_real_frame():
    """Real Equip Crest screen with a NEW Dark Resistance Lv3 crest."""
    if not need("equip_crest_screen", "crest_checkbox", "crest_icon_lv3", "crest_icon_lv3plus",
                "crest_icon_lv4", "crest_icon_lv4plus"):
        return
    assert crest_state("equip_crest_lv3.png") == "equip_crest_screen"
    from rerun.adb import FakeDevice
    from rerun.engine import Context
    from rerun.scripts import CrestScript
    from rerun.stats import Stats
    img = cv2.imread(str(FIX / "equip_crest_lv3.png"))
    ctx = Context(instance="t", device=FakeDevice([img]), vision=v, stats=Stats(), routines={},
                  base_resolution=(720, 1280), log=lambda *a: None, notify=lambda *a, **k: None)
    s = CrestScript(ctx, {"start_home": False})
    s.on_start()
    box = s.find_orange_box(img)
    assert box and 600 < box[1] + box[3] // 2 < 850, box   # the NEW row
    rarity, scores = s.identify_crest(img, box)
    assert rarity == "lv3", scores
    blue = s.find_blue_boxes(img, box[1])
    assert len(blue) == 1 and 480 < blue[0][1] < 550, blue  # the "No Crest" slot's box


def test_loop_results_redeploys_instead_of_waiting():
    """The real loop-results screen must lead to a Redeploy tap, not an idle wait."""
    if not need("drop_info", "results_redeploy"):
        return
    from rerun.adb import FakeDevice
    from rerun.engine import Context
    from rerun.scripts import CrestScript
    from rerun.stats import Stats
    img = cv2.imread(str(FIX / "loop_results.png"))
    dev = FakeDevice([img])
    ctx = Context(instance="t", device=dev, vision=v, stats=Stats(), routines={},
                  base_resolution=(720, 1280), log=lambda *a: None, notify=lambda *a, **k: None)
    s = CrestScript(ctx, {"runs": 0, "start_home": False})
    s.on_start()
    s.sleep = lambda *a, **k: None
    s.handle_drop_info(img)
    r = v.find(img, "results_redeploy")
    assert dev.taps and dev.taps[0] == r.center, dev.taps


def test_mode_selection_picks_solo_play():
    """Real 'Mode Selection' screen (Solo-play / Multiplayer) reached from a quest."""
    if not need("solo_quest_button"):
        return
    from rerun.adb import FakeDevice
    from rerun.engine import Context
    from rerun.scripts import AnyQuestScript
    from rerun.stats import Stats
    img = cv2.imread(str(FIX / "mode_select.png"))
    dev = FakeDevice([img])
    ctx = Context(instance="t", device=dev, vision=v, stats=Stats(), routines={},
                  base_resolution=(720, 1280), log=lambda *a: None, notify=lambda *a, **k: None)
    s = AnyQuestScript(ctx, {})
    s.on_start()
    s.sleep = lambda *a, **k: None
    assert s.detect_state(img) == "solo_quest_button"  # ReStart's Solo template is this card
    s.handle_solo_quest_button(img)
    x, y = dev.taps[0]
    assert x < 360 and 400 < y < 700, dev.taps  # the Solo-play card, not Multiplayer


def test_unexpected_error_popup_is_dismissed_not_battle():
    """Seen live: the 'An unexpected error has occurred.' popup over the party
    screen. It must be handled as the popup (tap its OK), never as Battle."""
    if not need("unexpected_error", "unexpected_error_text", "battle_button"):
        return
    from rerun.adb import FakeDevice
    from rerun.engine import Context
    from rerun.scripts import AnyQuestScript, CrestScript
    from rerun.stats import Stats
    img = cv2.imread(str(FIX / "unexpected_error_party.png"))
    for cls in (AnyQuestScript, CrestScript):
        dev = FakeDevice([img])
        ctx = Context(instance="t", device=dev, vision=v, stats=Stats(), routines={},
                      base_resolution=(720, 1280), log=lambda *a: None, notify=lambda *a, **k: None)
        s = cls(ctx, {"start_home": False})
        s.on_start()
        s.sleep = lambda *a, **k: None
        assert s.detect_state(img) == "unexpected_error", cls.NAME
        s.handle_unexpected_error(img)
        x, y = dev.taps[0]
        assert 300 < x < 420 and 660 < y < 720, dev.taps  # the popup's OK
    # Without the popup's own templates the dimmed Battle must still not be tapped.
    s = AnyQuestScript(ctx, {})
    s.COMMON_STATES = []
    assert s.detect_state(img) != "battle_button"


def test_any_quest_stops_when_game_goes_home():
    """Seen live: after the error popup the game went to title and then Home."""
    if not need("exploring_button"):
        return
    from rerun.adb import FakeDevice
    from rerun.engine import Context
    from rerun.scripts import AnyQuestScript
    from rerun.scripts.base import Finished
    from rerun.stats import Stats
    img = cv2.imread(str(FIX / "home_after_error.png"))
    notes = []
    ctx = Context(instance="t", device=FakeDevice([img]), vision=v, stats=Stats(), routines={},
                  base_resolution=(720, 1280), log=lambda *a: None,
                  notify=lambda i, m, **k: notes.append(m))
    s = AnyQuestScript(ctx, {})
    s.on_start()
    assert s.detect_state(img) == "home_screen"
    try:
        s.handle_home_screen(img)
        raise AssertionError("should stop")
    except Finished:
        pass
    assert notes and "Home" in notes[0]


def test_results_on_screen_at_start_are_not_counted():
    """Seen live: starting on a finished batch's results counted it as a new run."""
    if not need("drop_info", "results_redeploy"):
        return
    from rerun.adb import FakeDevice
    from rerun.engine import Context
    from rerun.scripts import AnyQuestScript
    from rerun.stats import Stats
    img = cv2.imread(str(FIX / "loop_results.png"))
    ctx = Context(instance="t", device=FakeDevice([img]), vision=v, stats=Stats(), routines={},
                  base_resolution=(720, 1280), log=lambda *a: None, notify=lambda *a, **k: None)
    s = AnyQuestScript(ctx, {"runs": 1})
    s.on_start()
    assert s.detect_state(img) == "drop_info"
    assert s.session_runs == 0 and not s.target_reached()


def test_potion_used_popup_is_dismissed():
    """Seen live: after an L Potion, 'Used L Potion to restore your energy.' with a
    BLUE OK sat over the Equip Crest screen; Crest judged the dimmed row and stopped."""
    if not need("potion_used_ok", "potion_used_text", "equip_crest_screen"):
        return
    from rerun.adb import FakeDevice
    from rerun.engine import Context
    from rerun.scripts import AnyQuestScript, CrestScript
    from rerun.stats import Stats
    img = cv2.imread(str(FIX / "potion_used_popup.png"))

    def make(cls):
        dev = FakeDevice([img])
        ctx = Context(instance="t", device=dev, vision=v, stats=Stats(), routines={},
                      base_resolution=(720, 1280), log=lambda *a: None, notify=lambda *a, **k: None)
        s = cls(ctx, {"start_home": False})
        s.on_start()
        s.sleep = lambda *a, **k: None
        return s, dev

    for cls in (CrestScript, AnyQuestScript):
        s, dev = make(cls)
        assert s.detect_state(img) == "potion_used", cls.NAME
        s.handle_potion_used(img)
        x, y = dev.taps[0]
        assert 300 < x < 420 and 670 < y < 710, dev.taps  # the popup's blue OK
    # Right after tapping Use, the energy code taps the same OK itself.
    s, dev = make(CrestScript)
    s.confirm_potion_used()
    x, y = dev.taps[0]
    assert 300 < x < 420 and 670 < y < 710, dev.taps
    # And a dimmed Equip Crest screen is never judged as a crest screen.
    s, dev = make(CrestScript)
    s.COMMON_STATES = []
    assert s.detect_state(img) != "equip_crest_screen"
    # ...while the normal, lit Equip Crest screen still is.
    lit = cv2.imread(str(FIX / "equip_crest_lv3.png"))
    assert s.detect_state(lit) == "equip_crest_screen"


def test_read_loop_counter():
    if not need("loops_label", "loopdigit_1_0", "loopdigit_0_0"):
        return
    from rerun.loop_count import read_loops
    img = cv2.imread(str(FIX / "auto_loop_settings.png"))
    assert read_loops(v, img) == 100
    assert read_loops(v, cv2.imread(str(FIX / "home.png"))) is None
    # Same real screen with the two zeros painted out -> a lone "1" (the thick
    # '1' glyph used to match twice here and read as "11").
    one = img.copy()
    zeros = one[560:600, 605:645]
    zeros[:] = np.median(one[560:600, 660:690].reshape(-1, 3), axis=0).astype(np.uint8)
    assert read_loops(v, one) == 1, read_loops(v, one)
    # Live Auto-Loop screen showing 1: the counter box's vertical edge used to
    # read as a second '1' ("11"), so Rerun thought the game wouldn't go lower.
    assert read_loops(v, cv2.imread(str(FIX / "auto_loop_one.png"))) == 1
    # Second live capture: the edge's top/bottom ends still slipped through
    # the peak check; digits must also sit on the label's text line.
    assert read_loops(v, cv2.imread(str(FIX / "auto_loop_one_b.png"))) == 1


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
