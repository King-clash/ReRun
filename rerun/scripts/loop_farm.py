"""Shared flow for scripts built on the game's Auto-Loop system.

Quest page (Solo/Challenge) -> party screen (Past Party, Include AI, Apply)
-> Battle -> Auto-Loop screen (turn on potion refill, Start Looping)
-> runs are counted each time "Drop Info" appears
-> loop results -> Redeploy (same quest, same party) or OK.
"""
from __future__ import annotations

import time

import numpy as np

from ..loop_count import set_loops
from .base import BaseScript, Done, Finished, Setting, T
from .energy import ENERGY_SETTINGS, ENERGY_TEMPLATES, NO_POTION, EnergyMixin

LOOP_TEMPLATES = [
    T("solo_quest_button", "The 'Solo-play' card on the Mode Selection screen (Solo-play / Multiplayer)."),
    T("challenge_button", "'Challenge' button on a quest's detail page.", optional=True),
    T("past_party_button", "'Past Party' button on the party screen."),
    T("include_ai_button", "The UNTICKED 'Include AI' checkbox in the Past Party dialog (crop just the empty box)."),
    T("apply_button", "'Apply' button in the Past Party dialog."),
    T("auto_button", "The Auto toggle on the party screen while it is OFF.", optional=True),
    T("battle_button", "'Battle' button on the party screen."),
    T("use_potions_button", "The 'OFF' toggle for 'Refill energy with potions' on the Auto-Loop screen."),
    T("looping_button", "'Start Looping' button on the Auto-Loop screen."),
    T("drop_info", "'Drop Info' title on the results screen after each run."),
    T("results_redeploy", "Green 'Redeploy' button on the loop results screen."),
    T("loops_label", "'Loops' label on the Auto-Loop Settings screen (for setting the loop count).",
      optional=True),
    T("loop_minus_button", "The '-' button left of the Auto-Loop slider.", optional=True),
    T("loop_plus_button", "The '+' button right of the Auto-Loop slider.", optional=True),
    T("ok_button", "Generic orange 'OK' button (results / dialogs)."),
    *ENERGY_TEMPLATES,
    T("continue_box", "'Continue?' title shown when the party is wiped."),
    T("cancel_btn", "'Cancel' on the Continue? dialog."),
    T("restart_btn", "'Restart' button shown after cancelling Continue?.", optional=True),
]

LOOP_SETTINGS = [
    Setting("runs", "Number of runs (0 = no limit)", "int", 0),
    Setting("party", "Party", "choice", "Last Party", ["Last Party", "Current Party"],
            "Last Party re-selects the party from your previous run (with its AI). "
            "Current Party uses whatever is set in-game."),
    *ENERGY_SETTINGS,
    Setting("game_refill", "Let the game refill energy mid-loop", "bool", False,
            help="Turns on Auto-Loop's own 'Refill energy with potions'. Fewer interruptions, "
                 "but the game picks the potion and Rerun can't count or cap it."),
    Setting("mode_247", "24/7 mode (recover crashes, survive daily reset)", "bool", False),
]


class LoopFarmScript(EnergyMixin, BaseScript):
    STATES = [
        ("continue_box", ["continue_box"]),
        ("crystal_dialog", ["crystal_dialog"]),
        ("use_pot_button", ["use_pot_button"]),
        # The Auto-Loop dialog opens on top of the results, whose Redeploy bar
        # stays visible (dimmed) underneath - so it must win over them.
        ("looping_button", ["looping_button"]),
        ("drop_info", ["drop_info"]),
        ("results_redeploy", ["results_redeploy"]),
        ("include_ai_button", ["include_ai_button"]),
        ("apply_button", ["apply_button"]),
        ("battle_button", ["battle_button"]),
        ("solo_quest_button", ["solo_quest_button", "challenge_button"]),
        ("ok_button", ["ok_button"]),
    ]

    DROP_IDLE_S = 12
    last_drop: bool | None = None  # Drop Info seen on the previous frame (None = no frame yet)
    # Seen live: an error popup dimmed the party screen and Battle (brightness
    # 48 vs 153) kept matching, so it was tapped 25 times to no effect.
    LIT_STATES = {"battle_button", "solo_quest_button", "apply_button", "include_ai_button"}

    def on_start(self) -> None:
        self.drop_since = None
        self.target = int(self.cfg.get("runs") or 0)
        self.in_loop = False
        self.party_done = False
        self.last_drop = None  # unknown until the first frame
        self.failures = 0
        self.potions_used = self.crystals_used = 0
        cap = int(self.cfg.get("potion_limit") or 0)
        self.log(f"Target runs: {self.target or 'no limit'} | Party: {self.cfg['party']} | "
                 f"Refill: {self.cfg.get('potion')}{f' (max {cap})' if cap else ''} | "
                 f"Crystals: {'on' if self.cfg.get('crystal_refresh') else 'off'}")

    # ------------------------------------------------------------ counting
    def detect_state(self, screen: np.ndarray) -> str:
        state = super().detect_state(screen)
        # Count a run on the rising edge of Drop Info, whatever handler runs.
        drop = state == "drop_info"
        if self.last_drop is None:
            # First frame: a Drop Info already on screen belongs to a run that
            # finished before Start (seen live: it was counted, and with a
            # 1-run target the script stopped without playing).
            self.last_drop = drop
            return state
        if drop and not self.last_drop:
            self.count_run()
        self.last_drop = drop
        return state

    def count_run(self) -> None:
        self.session_runs += 1
        self.count("runs")
        self.progress()
        lifetime = self.ctx.stats.get(self.ctx.instance).get(f"{self.ID}.runs", 0)
        target = f"/{self.target}" if self.target else ""
        self.log(f"Run completed. {self.session_runs}{target} | Lifetime: {lifetime}")

    def target_reached(self) -> bool:
        return bool(self.target) and self.session_runs >= self.target

    def finish(self, why: str = "") -> None:
        msg = f"{self.NAME} finished: {self.session_runs} run(s). {why}".strip()
        self.record("finished", msg)
        self.notify(msg, screenshot=False, ping=False)
        raise Done(msg)

    # ------------------------------------------------------------ handlers
    def handle_solo_quest_button(self, screen):
        if self.target_reached():
            self.finish()
        self.log("Quest page - tapping Solo")
        self.tap_template("solo_quest_button", screen) or self.tap_template("challenge_button", screen)
        self.party_done = False

    def handle_battle_button(self, screen):
        if self.cfg["party"] == "Last Party" and not self.party_done and self.has_template("past_party_button"):
            if self.tap_template("past_party_button", screen, settle=1.0):
                self.log("Selecting Past Party")
                return
        if self.find("auto_button", screen):
            self.log("Turning Auto on")
            self.tap_template("auto_button", screen)
            return
        self.check_energy_for_quest(screen)
        self.log("Tapping Battle")
        self.tap_template("battle_button", screen, settle=2.0)
        self.progress()

    def check_energy_for_quest(self, screen) -> None:
        """When no refill may be used, compare energy with the quest's cost first
        and stop with a clear message instead of meeting the refill dialog."""
        no_refill = self.cfg.get("potion") == NO_POTION or (
            int(self.cfg.get("potion_limit") or 0) and
            self.potions_used >= int(self.cfg.get("potion_limit") or 0))
        if not no_refill or self.ocr is None:
            return
        if time.monotonic() - getattr(self, "_cost_checked_at", -1e9) < 30:
            return
        self._cost_checked_at = time.monotonic()
        from ..ocr import read_energy, read_energy_cost
        energy, cost = read_energy(self.ocr, screen), read_energy_cost(self.ocr, screen)
        if energy:
            self.ctx.params["energy"] = (energy[0], energy[1], time.time())
        if energy and cost:
            self.log(f"Energy {energy[0]}/{energy[1]}, this quest costs {cost}")
            if energy[0] < cost:
                self.out_of_energy(f"energy is {energy[0]}/{energy[1]} and the quest costs "
                                   f"{cost}, with no refill allowed")

    def handle_include_ai_button(self, screen):
        # The template is the *unticked* box, so this only ever ticks it.
        self.log("Including past AI settings")
        self.tap_template("include_ai_button", screen)

    def handle_apply_button(self, screen):
        if self.tap_template("apply_button", screen, settle=1.0):
            self.log("Party applied")
            self.party_done = True

    def handle_looping_button(self, screen):
        if self.cfg.get("game_refill") and self.cfg.get("potion") != NO_POTION \
                and self.find("use_potions_button", screen):
            self.log("Turning on 'Refill energy with potions'")
            self.tap_template("use_potions_button", screen)
            return
        if self.target and self.has_template("loops_label"):
            remaining = max(1, self.target - self.session_runs)
            got = set_loops(self, remaining)
            if got is not None:
                self.log(f"Loops set to {got}" + ("" if got == remaining else
                                                   f" (wanted {remaining}; game limit)"))
            screen = self.grab()
        self.log("Start Looping")
        self.tap_template("looping_button", screen, settle=2.0)
        self.in_loop = True
        self.progress()

    def handle_drop_info(self, screen):
        # Mid-loop, Drop Info passes by on its own. When the loop has finished,
        # the same screen also carries the Redeploy / OK bar - act on that.
        if self.results_bar_live(screen):
            self.drop_since = None
            self.handle_results_redeploy(screen)
            return
        # When a loop ends, Drop Info waits for a tap before the next screen
        # (fragments popup, Equip Crest, results bar). Mid-loop it moves on
        # by itself within a few seconds, so only tap once it has sat idle.
        now = time.monotonic()
        if self.drop_since is None:
            self.drop_since = now
        elif now - self.drop_since > self.DROP_IDLE_S:
            self.log("Drop Info is waiting - tapping to continue")
            self.tap_base(360, 640, settle=2.0)
            self.drop_since = None

    def results_bar_live(self, screen) -> bool:
        """Redeploy visible and lit - not dimmed under a dialog (energy, fragments,
        Auto-Loop settings). ReStart measures the same thing by brightness."""
        m = self.find("results_redeploy", screen)
        if not m:
            return False
        v = self.ctx.vision
        return v.brightness(screen, m) >= 0.75 * v.template_brightness("results_redeploy")

    def handle_results_redeploy(self, screen):
        """A loop batch finished. Redeploy repeats it with the same party."""
        if not self.results_bar_live(screen):
            return  # dimmed under a popup; that popup's own handler goes first
        self.in_loop = False
        if self.target_reached():
            self.log("Target reached - closing results")
            # Seen live: one tap while the bar was still sliding in did nothing,
            # leaving the results open. Tap until the bar is really gone.
            for _ in range(3):
                self.tap_template("ok_button", screen, settle=1.5)
                screen = self.grab()
                if not self.results_bar_live(screen):
                    break
            self.finish()
        self.log("Loop finished - Redeploy")
        self.tap_template("results_redeploy", screen, settle=2.0)
        self.progress()

    def handle_ok_button(self, screen):
        self.tap_template("ok_button", screen)

    def handle_use_pot_button(self, screen):
        self.use_potion(screen)

    def handle_crystal_dialog(self, screen):
        self.use_crystals(screen)

    def handle_continue_box(self, screen):
        self.failures += 1
        self.count("failures")
        self.record("failure", "Party wiped - restarting the quest")
        self.log("Quest failed (Continue?) - cancelling and restarting the quest")
        self.notify(f"{self.NAME}: a run failed (party wiped). Restarting the quest.", ping=False)
        self.tap_template("cancel_btn", screen, settle=1.5)
        m = self.wait_for(["restart_btn"], 8)
        if m:
            self.tap_match(m, settle=2)
        self.party_done = False
        self.in_loop = False
        if self.failures >= 5 and self.failures > self.session_runs:
            self.notify(f"{self.NAME}: {self.failures} failures - your team may not clear this quest. Stopped.")
            raise Finished("too many failures")
