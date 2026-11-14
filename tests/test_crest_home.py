"""Crest 'Always start from the Home screen': reach Home from any screen, then walk
Home > Exploring > Crest Palace > palace tile > quest list > quest, against a simulated game."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.test_scripts import Screen, Sim, crest_equip_screen, fast, make_ctx, run  # noqa: E402
from rerun.scripts import CrestScript  # noqa: E402


def screens():
    return {
        "home": Screen([("exploring_button", 300, 900)]),
        "exploring": Screen([("crest_palace_icon", 300, 500)]),
        "palace": Screen([("crest_palace_target", 300, 600)], extra=[("crest_palace_header", 280, 32)]),
        "quest_list": Screen([("quest_list_entry", 300, 500)], extra=[("quest_list", 280, 32)]),
        "mode": Screen([("solo_quest_button", 300, 600)]),
        "party": Screen([("battle_button", 500, 960)]),
        "popup": Screen([("xpop_up", 600, 100)], extra=[("battle_button", 500, 960)]),
        "mystery": Screen([]),
        "equip": crest_equip_screen("crest_icon_lv3"),
    }


TAPS = {
    ("home", "exploring_button"): "exploring",
    ("exploring", "crest_palace_icon"): "palace",
    ("palace", "crest_palace_target"): "quest_list",
    ("quest_list", "quest_list_entry"): "mode",
    ("popup", "xpop_up"): "party",
}
BACKS = {"party": "home", "quest_list": "palace", "palace": "exploring", "exploring": "home"}


def start(start_screen, backs=None, settings=None, hook=None):
    fast()
    dev = Sim(screens(), start_screen, TAPS)
    dev.back_presses = 0
    table = BACKS if backs is None else backs

    def back(self):
        self.back_presses += 1
        if self.current in table:
            self.go(table[self.current])
    dev.back = back.__get__(dev)
    holder = {}
    orig = Sim.tap

    def tap(self, x, y):
        orig(self, x, y)
        if self.tapped[-1] == "solo_quest_button":
            holder["ctx"].stop_event.set()
    dev.tap = tap.__get__(dev)
    ctx = make_ctx(Path(tempfile.mkdtemp()), dev, CrestScript)
    holder["ctx"] = ctx
    s = CrestScript(ctx, settings or {})
    if hook:
        hook(s)
    return run(s), dev, ctx


def test_from_party_screen_goes_back_to_home_then_walks_to_the_quest():
    result, dev, ctx = start("party")
    assert result == "stopped: stopped by user", result  # stopped by the test once Solo was tapped
    assert dev.back_presses == 1, dev.back_presses
    assert dev.tapped[:4] == ["exploring_button", "crest_palace_icon", "crest_palace_target",
                              "quest_list_entry"], dev.tapped
    assert dev.tapped[-1] == "solo_quest_button"
    assert dev.history[:2] == ["party", "home"], dev.history


def test_from_deep_screen_presses_back_until_home():
    result, dev, ctx = start("quest_list")
    assert dev.back_presses == 3, dev.back_presses  # quest list > palace > exploring > home
    assert dev.history[:4] == ["quest_list", "palace", "exploring", "home"], dev.history
    assert "solo_quest_button" in dev.tapped


def test_already_home_presses_nothing_extra():
    result, dev, ctx = start("home")
    assert dev.back_presses == 0
    assert dev.tapped[0] == "exploring_button"


def test_popup_is_closed_with_its_handler_not_back():
    result, dev, ctx = start("popup", backs={"party": "home"})
    assert dev.tapped[0] == "xpop_up", dev.tapped
    assert dev.back_presses == 1  # then Back from the party screen it revealed


def test_pending_crest_screen_is_never_left_with_back():
    result, dev, ctx = start("equip")
    assert result.startswith("finished: crest decision pending"), result
    assert dev.back_presses == 0 and dev.tapped == [], (dev.back_presses, dev.tapped)
    assert any("crest screen" in n for n in ctx.notes)


def test_unreachable_home_stops_with_a_message():
    result, dev, ctx = start("mystery", backs={})
    assert result == "finished: could not reach the Home screen", result
    assert dev.back_presses == CrestScript.HOME_MAX_BACKS + 0 or dev.back_presses > 0
    assert any("couldn't reach the Home screen" in n for n in ctx.notes)
    assert dev.tapped == []


def test_missing_palace_tile_template_stops_before_touching_the_game():
    def hook(s):
        real = s.has_template
        tiles = set(s.palace_tile_names())
        s.has_template = lambda n: False if n in tiles else real(n)
    result, dev, ctx = start("party", hook=hook)
    assert result.startswith("finished: Home navigation templates missing"), result
    assert dev.back_presses == 0 and dev.tapped == []
    assert any("crest_palace_target" in n for n in ctx.notes)


def test_switch_off_keeps_the_old_start_behaviour():
    result, dev, ctx = start("party", settings={"start_home": False})
    assert dev.back_presses == 0
    assert "exploring_button" not in dev.tapped


def test_unrecognised_quest_row_stops_with_a_message_instead_of_sitting_silent():
    """Seen live: each palace's quest looks different; a row picture from another palace never
    matched and Crest just sat on the quest list."""
    fast()
    scr = {"quest_list": Screen([], extra=[("quest_list", 280, 32)])}
    dev = Sim(scr, "quest_list", {})
    ctx = make_ctx(Path(tempfile.mkdtemp()), dev, CrestScript)
    s = CrestScript(ctx, {"start_home": False})
    result = run(s)
    assert result == "finished: quest row not recognised", result
    assert dev.tapped == []
    assert any("quest_list_entry" in n and "Stopped" in n for n in ctx.notes), ctx.notes
    assert any("no quest row picture or name" in l for l in ctx.logs)


def test_second_palaces_row_picture_is_used():
    fast()
    scr = {"quest_list": Screen([("quest_list_entry2", 100, 600)], extra=[("quest_list", 280, 32)]),
           "mode": Screen([("solo_quest_button", 300, 600)])}
    dev = Sim(scr, "quest_list", {("quest_list", "quest_list_entry2"): "mode"})
    holder = {}
    orig = Sim.tap

    def tap(self, x, y):
        orig(self, x, y)
        if self.tapped[-1] == "solo_quest_button":
            holder["ctx"].stop_event.set()
    dev.tap = tap.__get__(dev)
    ctx = make_ctx(Path(tempfile.mkdtemp()), dev, CrestScript)
    holder["ctx"] = ctx
    run(CrestScript(ctx, {"start_home": False}))
    assert dev.tapped[0] == "quest_list_entry2" and dev.tapped[-1] == "solo_quest_button", dev.tapped


def test_home_button_is_tapped_instead_of_pressing_back():
    fast()
    scr = screens()
    scr["party"] = Screen([("battle_button", 500, 960), ("home_nav_button", 20, 1160)])
    dev = Sim(scr, "party", {**TAPS, ("party", "home_nav_button"): "home"})
    dev.back_presses = 0
    dev.back = (lambda self: setattr(self, "back_presses", self.back_presses + 1)).__get__(dev)
    holder = {}
    orig = Sim.tap

    def tap(self, x, y):
        orig(self, x, y)
        if self.tapped[-1] == "solo_quest_button":
            holder["ctx"].stop_event.set()
    dev.tap = tap.__get__(dev)
    ctx = make_ctx(Path(tempfile.mkdtemp()), dev, CrestScript)
    holder["ctx"] = ctx
    run(CrestScript(ctx, {}))
    assert dev.tapped[0] == "home_nav_button" and dev.back_presses == 0, (dev.tapped, dev.back_presses)
    assert "exploring_button" in dev.tapped


def test_home_button_that_does_nothing_falls_back_to_back_after_a_few_taps():
    fast()
    scr = screens()
    scr["party"] = Screen([("battle_button", 500, 960), ("home_nav_button", 20, 1160)])
    dev = Sim(scr, "party", TAPS)       # tapping the button changes nothing
    dev.back_presses = 0

    def back(self):
        self.back_presses += 1
        self.go("home")
    dev.back = back.__get__(dev)
    ctx = make_ctx(Path(tempfile.mkdtemp()), dev, CrestScript)
    holder = {"ctx": ctx}
    orig = Sim.tap

    def tap(self, x, y):
        orig(self, x, y)
        if self.tapped[-1] == "solo_quest_button":
            holder["ctx"].stop_event.set()
    dev.tap = tap.__get__(dev)
    run(CrestScript(ctx, {}))
    assert dev.tapped[:CrestScript.HOME_MAX_NAV_TAPS] == ["home_nav_button"] * CrestScript.HOME_MAX_NAV_TAPS
    assert dev.back_presses == 1, dev.back_presses


def test_real_home_button_found_when_lit_and_ignored_when_dimmed():
    import cv2
    from rerun.adb import FakeDevice
    from rerun.engine import Context
    from rerun.stats import Stats
    from rerun.vision import TemplateStore, Vision
    store = TemplateStore(ROOT / "templates")
    if not store.has("home_nav_button"):
        return
    v = Vision(store)
    lit = cv2.imread(str(ROOT / "tests" / "fixtures" / "crest_palace_list.png"))
    for img, expect in ((lit, True), ((lit * 0.45).astype("uint8"), False)):
        dev = FakeDevice([img])
        ctx = Context(instance="t", device=dev, vision=v, stats=Stats(), routines={},
                      base_resolution=(720, 1280), log=lambda *a: None, notify=lambda *a, **k: None)
        s = CrestScript(ctx, {"start_home": False})
        s.sleep = lambda *a, **k: None
        assert s._tap_home_button(img) is expect
        assert (len(dev.taps) == 1) is expect
        if expect:
            assert dev.taps[0] == (60, 1215), dev.taps


def test_dimmed_home_is_not_the_home_screen():
    """A popup over Home dims the Exploring button: Crest must not count that as Home."""
    import cv2
    from rerun.adb import FakeDevice
    from rerun.engine import Context
    from rerun.stats import Stats
    from rerun.vision import TemplateStore, Vision
    fx = ROOT / "tests" / "fixtures"
    store = TemplateStore(ROOT / "templates")
    if not store.has("exploring_button"):
        return
    v = Vision(store)
    home = cv2.imread(str(fx / "home.png"))
    dimmed = (home * 0.45).astype("uint8")  # what a popup's dark overlay does
    for label, img, is_home in (("home.png", home, True), ("home_after_error.png",
                                cv2.imread(str(fx / "home_after_error.png")), True),
                                ("dimmed", dimmed, False)):
        ctx = Context(instance="t", device=FakeDevice([img]), vision=v, stats=Stats(), routines={},
                      base_resolution=(720, 1280), log=lambda *a: None, notify=lambda *a, **k: None)
        s = CrestScript(ctx, {"start_home": False})
        s.on_start()
        got = s.detect_state(img)
        assert (got == "home_screen") == is_home, (label, got)


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
