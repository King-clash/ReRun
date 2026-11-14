"""Phase 2: Always re-select Past Party (verified Include AI + Apply, fallbacks, re-apply points)."""
from __future__ import annotations

import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.test_scripts import Screen, Sim, fast, make_ctx, run  # noqa: E402
from rerun.scripts import AnyQuestScript, CrestScript, MultiFarmScript  # noqa: E402


def party_screens():
    return {
        "party": Screen([("past_party_button", 150, 960), ("battle_button", 500, 960)]),
        "dialog": Screen([("include_ai_button", 250, 640), ("apply_button", 350, 800)],
                         extra=[("battle_button", 500, 960)]),
        "dialog_ticked": Screen([("apply_button", 350, 800)], extra=[("battle_button", 500, 960)]),
        "party_ready": Screen([("past_party_button", 150, 960), ("battle_button", 500, 960)]),
        "autoloop": Screen([("looping_button", 450, 960)]),
    }


PARTY_TAPS = {
    ("party", "past_party_button"): "dialog",
    ("dialog", "include_ai_button"): "dialog_ticked",
    ("dialog_ticked", "apply_button"): "party_ready",
    ("party_ready", "battle_button"): "autoloop",
}


def stop_on(dev, ctx_holder, name):
    orig = Sim.tap

    def tap(self, x, y):
        orig(self, x, y)
        if self.tapped[-1] == name:
            ctx_holder["ctx"].stop_event.set()
    dev.tap = tap.__get__(dev)


def run_party(cls, settings, screens=None, taps=None, start="party", stop_at="looping_button"):
    fast()
    dev = Sim(screens or party_screens(), start, taps if taps is not None else PARTY_TAPS)
    holder = {}
    stop_on(dev, holder, stop_at)
    ctx = make_ctx(Path(tempfile.mkdtemp()), dev, cls)
    holder["ctx"] = ctx
    s = cls(ctx, settings)
    return run(s), dev, ctx, s


def test_crest_default_selects_past_party_with_ai_then_battles():
    result, dev, ctx, s = run_party(CrestScript, {"start_home": False})
    assert result == "stopped: stopped by user", result
    assert dev.tapped[:4] == ["past_party_button", "include_ai_button", "apply_button",
                              "battle_button"], dev.tapped
    assert any("dialog closed" in m for m in ctx.logs), ctx.logs


def test_old_current_party_config_migrates_to_on_for_crest_only():
    assert CrestScript.migrate_settings({"party": "Current Party"})["past_party"] is True
    assert AnyQuestScript.migrate_settings({"party": "Current Party"})["past_party"] is False
    assert AnyQuestScript.migrate_settings({"party": "Last Party"})["past_party"] is True
    # an explicit new value always wins
    assert CrestScript.migrate_settings({"party": "Last Party", "past_party": False})["past_party"] is False
    # scripts without the switch don't get one
    assert "past_party" not in MultiFarmScript.migrate_settings({"party": "Current Party"})


def test_off_uses_current_party():
    result, dev, ctx, s = run_party(CrestScript, {"past_party": False, "start_home": False})
    assert dev.tapped[0] == "battle_button", dev.tapped
    assert "past_party_button" not in dev.tapped


def test_include_ai_already_ticked_goes_straight_to_apply():
    taps = dict(PARTY_TAPS)
    taps[("party", "past_party_button")] = "dialog_ticked"
    result, dev, ctx, s = run_party(CrestScript, {"start_home": False}, taps=taps)
    assert dev.tapped[:3] == ["past_party_button", "apply_button", "battle_button"], dev.tapped


def test_never_applies_while_include_ai_is_unticked():
    """The tick doesn't register (game ignores the tap): Apply is never pressed, script stops."""
    taps = dict(PARTY_TAPS)
    del taps[("dialog", "include_ai_button")]
    result, dev, ctx, s = run_party(CrestScript, {"start_home": False}, taps=taps)
    assert result == "finished: Include AI could not be ticked", result
    assert "apply_button" not in dev.tapped, dev.tapped
    assert dev.tapped.count("include_ai_button") == 3


def test_apply_that_does_not_close_the_dialog_stops():
    taps = dict(PARTY_TAPS)
    del taps[("dialog_ticked", "apply_button")]
    result, dev, ctx, s = run_party(CrestScript, {"start_home": False}, taps=taps)
    assert result == "finished: Past Party Apply did not take", result
    assert "battle_button" not in dev.tapped


def test_no_past_party_falls_back_to_current_party_and_notifies():
    screens = party_screens()
    screens["party"] = Screen([("battle_button", 500, 960)])  # no Past Party button
    taps = {("party", "battle_button"): "autoloop"}
    result, dev, ctx, s = run_party(CrestScript, {"start_home": False}, screens=screens, taps=taps)
    assert dev.tapped[0] == "battle_button", dev.tapped
    assert any("current party" in n for n in ctx.notes), ctx.notes


def test_past_party_dialog_never_opens_falls_back():
    taps = dict(PARTY_TAPS)
    taps[("party", "past_party_button")] = "party"           # tap does nothing
    taps[("party", "battle_button")] = "autoloop"
    result, dev, ctx, s = run_party(CrestScript, {"start_home": False}, taps=taps)
    assert dev.tapped.count("past_party_button") == 1, dev.tapped
    assert "battle_button" in dev.tapped
    assert any("dialog never opened" in n for n in ctx.notes), ctx.notes


def test_redeploy_does_not_reselect_past_party():
    """Party -> loop -> results -> Redeploy -> loop again: Past Party only once."""
    fast()
    screens = party_screens()
    screens.update({
        "battle": Screen([]),
        "drop": Screen([], extra=[("drop_info", 280, 96)]),
        "results": Screen([("results_redeploy", 450, 992), ("ok_button", 300, 992)]),
    })
    taps = dict(PARTY_TAPS)
    taps[("autoloop", "looping_button")] = "battle"
    taps[("results", "results_redeploy")] = "autoloop"

    class LoopSim(Sim):
        def screencap(self):
            img = self.screens[self.current].render()
            if self.current == "battle":
                self.go("drop")
            elif self.current == "drop":
                self.go("results")
            return img

    dev = LoopSim(screens, "party", taps)
    ctx = make_ctx(Path(tempfile.mkdtemp()), dev, AnyQuestScript)
    orig = Sim.tap

    def tap(self, x, y):
        orig(self, x, y)
        if self.tapped.count("looping_button") == 2:
            ctx.stop_event.set()
    dev.tap = tap.__get__(dev)
    s = AnyQuestScript(ctx, {"past_party": True})
    run(s)
    assert "results_redeploy" in dev.tapped, dev.tapped
    assert dev.tapped.count("past_party_button") == 1, dev.tapped
    assert s.party_done


def test_quest_entry_resume_and_relaunch_reset_the_party():
    s = run_party(CrestScript, {"start_home": False})[3]
    assert s.party_done
    s.reset_party("new quest entry")
    assert not s.party_done
    s.party_done = True
    s.on_resume()
    assert not s.party_done
    s.party_done = True
    s.on_relaunch()
    assert not s.party_done


def test_pause_then_resume_reselects_past_party():
    """Pause on the party screen after the party was applied; on Resume it is re-selected."""
    fast()
    screens = party_screens()
    taps = dict(PARTY_TAPS)
    taps[("party_ready", "battle_button")] = "party"  # back on the party screen
    dev = Sim(screens, "party", taps)
    ctx = make_ctx(Path(tempfile.mkdtemp()), dev, CrestScript)
    orig = Sim.tap
    state = {"battles": 0}

    def tap(self, x, y):
        orig(self, x, y)
        if self.tapped[-1] == "battle_button":
            state["battles"] += 1
            if state["battles"] == 1:
                ctx.pause_event.set()
                threading.Timer(0.3, ctx.pause_event.clear).start()
            else:
                ctx.stop_event.set()
    dev.tap = tap.__get__(dev)
    s = CrestScript(ctx, {"start_home": False})
    run(s)
    assert dev.tapped.count("past_party_button") == 2, dev.tapped
    assert any("resumed" in m for m in ctx.logs), ctx.logs


def test_real_party_screen_past_party_lit_and_dimmed():
    """Real captures: Past Party is found and lit on the party screen, dimmed under an error popup."""
    import cv2
    from rerun.vision import TemplateStore, Vision
    store = TemplateStore(ROOT / "templates")
    if not store.has("past_party_button"):
        print("  (skipped: past_party_button template not imported)")
        return
    v = Vision(store)
    fx = ROOT / "tests" / "fixtures"
    lit = cv2.imread(str(fx / "party_reigrad.png"))
    m = v.find(lit, "past_party_button")
    assert m and v.brightness(lit, m) >= 0.6 * v.template_brightness("past_party_button")
    assert not v.find(lit, "include_ai_button") and not v.find(lit, "apply_button")
    dim = cv2.imread(str(fx / "unexpected_error_party.png"))
    m = v.find(dim, "past_party_button")
    assert m is None or v.brightness(dim, m) < 0.6 * v.template_brightness("past_party_button")


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            import traceback
            print(f"FAIL {t.__name__}: {e}")
            traceback.print_exc()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
