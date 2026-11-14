"""Crest Palace farming with crest detection.

At the end of each Auto-Loop batch the game shows the Equip Crest screen:
your equipped crests sit in rows with blue checkboxes, and the new crest is
the row highlighted orange. The script ticks the existing rows (keeps them),
identifies the new crest's rarity from its icon, and then either

  * keeps it (wanted rarity): leaves the screen untouched, pings you on
    Discord with a screenshot, and stops, or
  * scraps it (everything else): Redeploy, which turns the unticked crest
    into fragments and starts the next loop with the same party.

A Crest Burst (5+) has its own full-screen overlay and always stops.
"""
from __future__ import annotations

import re
import time
from pathlib import Path

import cv2
import numpy as np

from .base import BASE_H, BASE_W, Finished, Setting, T, game_now
from .loop_farm import LOOP_SETTINGS, LOOP_TEMPLATES, LoopFarmScript

RARITY_ORDER = ["lv3", "lv3+", "lv4", "4+"]
ICON_TEMPLATES = {
    "lv3": "crest_icon_lv3",
    "lv3+": "crest_icon_lv3plus",
    "lv4": "crest_icon_lv4",
    "4+": "crest_icon_lv4plus",
}
KEEP_CHOICES = {
    "4+ and Burst only": "4+",
    "Lv4 and better": "lv4",
    "Lv3+ and better": "lv3+",
}
WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
_LV = re.compile(r"L\s*[vV]\s*\.?\s*([345])\s*(\+?)")


def text_rarity(text: str) -> str | None:
    """'Dark Resistance Lv3' -> 'lv3', 'Lv3+' -> 'lv3+', 'Lv4' -> 'lv4', 'Lv4+' -> '4+'."""
    m = _LV.search(text or "")
    if not m:
        return None
    level, plus = m.group(1), m.group(2)
    if level == "3":
        return "lv3+" if plus else "lv3"
    if level == "4":
        return "4+" if plus else "lv4"
    return None  # Lv5 rows don't appear here (Crest Burst has its own screen)


class CrestScript(LoopFarmScript):
    ID = "crest"
    NAME = "Crest"
    DESCRIPTION = "Farms a Crest Palace on Auto-Loop, scraps unwanted crests and stops on rare ones."
    INSTRUCTIONS = """CREST FARMING
Repeats a Crest Palace quest on Auto-Loop and handles the Equip Crest screen
after every batch.

SETUP
1. Go to the Crest Palace screen (or the quest list / party screen).
2. In Settings choose the run count, party, and which crests to keep.
3. Press Start.

CREST HANDLING
- Your equipped crests (blue boxes) are ticked so they are kept.
- The new crest (orange row) is identified by its rarity icon.
- Wanted rarity: the screen is left as is, you get a Discord ping with a
  screenshot, and the script stops so you can decide.
- Anything else is scrapped into fragments with Redeploy, and the next
  loop starts straight away.
- A Crest Burst (5+) always stops the script and pings you.
- An icon that can't be identified stops the script (safe default).

24/7 MODE
- Relaunches the game after a crash and logs back in at the 6 AM (UTC-6) reset.
- From Home it walks to Exploring > Crest Palace and opens the palace you
  captured (crest_palace_<day> for a weekday, else crest_palace_target).
"""
    SETTINGS = [
        *LOOP_SETTINGS,
        Setting("keep", "Crests to keep (stop + notify)", "choice", "4+ and Burst only",
                list(KEEP_CHOICES)),
        Setting("stop_on_unknown", "Stop if a crest can't be identified", "bool", True),
        Setting("verify_text", "Double-check the crest's level by reading its title", "bool", True,
                help="Reads 'Lv3', 'Lv4+'... from the crest's name. If it disagrees with the icon, "
                     "Rerun stops instead of scrapping. Needs the text reader (comes with ReStart)."),
        Setting("save_debug", "Save Equip Crest screenshots to debug_crest/", "bool", False),
    ]
    TEMPLATES = LOOP_TEMPLATES + [
        T("crest_icon_lv5plus", "'Crest Burst' title on the full-screen burst overlay (5+ crest)."),
        T("equip_crest_screen", "'Equip Crest' title at the top of the crest selection screen."),
        T("crest_checkbox", "An EMPTY blue checkbox on an equipped crest row (Equip Crest screen)."),
        T("crest_icon_lv3", "Rarity icon of a Lv3 crest, cropped from its row."),
        T("crest_icon_lv3plus", "Rarity icon of a Lv3+ crest."),
        T("crest_icon_lv4", "Rarity icon of a Lv4 crest."),
        T("crest_icon_lv4plus", "Rarity icon of a 4+ crest."),
        T("redeploy_button", "Green 'Redeploy' button on the Equip Crest screen."),
        T("select_crest_ok", "Orange OK at the bottom of the Equip Crest screen."),
        T("select_crest_ok2", "OK on the scrap confirmation that follows it."),
        T("crest_fragment", "'Crest Fragment' title of the fragments popup."),
        T("crest_fragment_ok", "OK on the Crest Fragment popup."),
        T("quest_list", "Header of a Crest Palace's quest list.", optional=True),
        T("quest_list_entry", "A quest row in that list to tap (e.g. the one you farm).", optional=True),
        T("exploring_button", "'Exploring' button on the Home screen (24/7 mode).", optional=True),
        T("crest_palace_icon", "Crest Palace entry on the Exploring screen (24/7 mode).", optional=True),
        T("crest_palace_icon2", "Same entry while a 'Campaign!' badge covers it.", optional=True),
        T("crest_palace_header", "Header of the Crest Palace screen (24/7 mode).", optional=True),
        T("crest_palace_target", "The palace tile to open from the Crest Palace screen (24/7 mode).",
          optional=True),
    ] + [T(f"crest_palace_{d}", f"Palace tile to open on {d.title()} (overrides crest_palace_target).",
           optional=True) for d in WEEKDAYS]

    STATES = [
        ("crest_burst", ["crest_icon_lv5plus"]),
        ("crest_fragment", ["crest_fragment"]),
        ("equip_crest_screen", ["equip_crest_screen"]),
        *LoopFarmScript.STATES[:-1],                      # loop flow, minus generic OK
        # After the loop states: the results bar's OK looks just like this one.
        ("select_crest_ok2", ["select_crest_ok2"]),
        ("crest_palace_screen", ["crest_palace_header"]),
        ("quest_list", ["quest_list"]),
        ("exploring_screen", ["crest_palace_icon", "crest_palace_icon2"]),
        ("home_screen", ["exploring_button"]),
        ("ok_button", ["ok_button"]),
    ]

    # Seen live: the 'Used L Potion' popup dimmed the Equip Crest screen to 65%
    # of its brightness and Crest judged the dimmed row (unidentifiable -> stop).
    # A dimmed Equip Crest screen means a popup is on top: handle that first.
    LIT_STATES = LoopFarmScript.LIT_STATES | {"equip_crest_screen"}
    LIT_RATIO = {"equip_crest_screen": 0.8}

    # Equip Crest screen colour/size, for the 720x1280 frame. Calibrate with save_debug.
    ORANGE_HSV_LOWER = (5, 120, 150)
    ORANGE_HSV_UPPER = (25, 255, 255)
    MIN_BOX_AREA = 6000
    ICON_THRESHOLD = 0.80
    BURST_THRESHOLD = 0.75

    def on_start(self) -> None:
        super().on_start()
        self.keep_from = KEEP_CHOICES.get(self.cfg["keep"], "4+")
        self.crest_handled_at = 0.0
        self.session_kept = 0
        self.crest_session = f"{self.ctx.instance}-{int(time.time())}"
        self.palace = None  # set when 24/7 mode opens a palace tile
        self.log(f"Keeping crests: {self.cfg['keep']}")

    # ------------------------------------------------------------ crest ledger
    def count_run(self) -> None:
        super().count_run()
        ledger = getattr(self.ctx, "crests", None)
        if ledger is not None:
            try:
                ledger.add_run(self.ctx.instance, self.session_tag(), self.ID)
            except Exception as e:  # noqa: BLE001 - statistics must never stop farming
                self.log(f"Could not record the run in crest statistics: {e}")

    def session_tag(self) -> str:
        if not getattr(self, "crest_session", None):
            self.crest_session = f"{self.ctx.instance}-{int(time.time())}"
        return self.crest_session

    def ledger_drop(self, rarity: str, action: str, confidence: str = "verified",
                    title: str | None = None) -> None:
        """Every crest seen goes to the append-only ledger (4+ / Burst / Lv4
        counted separately); notable ones keep a full screenshot."""
        ledger = getattr(self.ctx, "crests", None)
        if ledger is None:
            return
        try:
            ledger.add_drop(self.ctx.instance, self.session_tag(), rarity, action, self.ID,
                            image=self.screen_img, palace=getattr(self, "palace", None),
                            confidence=confidence, title=title)
        except Exception as e:  # noqa: BLE001 - statistics must never stop farming
            self.log(f"Could not record crest statistics: {e}")

    # ------------------------------------------------------------ detection
    def detect_state(self, screen: np.ndarray) -> str:
        # Burst overlay uses its own looser threshold (animated background).
        if self.find("crest_icon_lv5plus", screen, threshold=self.BURST_THRESHOLD):
            return "crest_burst"
        return super().detect_state(screen)

    def find_orange_box(self, screen: np.ndarray) -> tuple[int, int, int, int] | None:
        hsv = cv2.cvtColor(screen, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, np.array(self.ORANGE_HSV_LOWER), np.array(self.ORANGE_HSV_UPPER))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        scale = (screen.shape[1] * screen.shape[0]) / (BASE_W * BASE_H)
        rects = []
        for c in contours:
            x, y, w, h = cv2.boundingRect(c)
            if w * h >= self.MIN_BOX_AREA * scale and w > 2 * h:
                rects.append((x, y, w, h))
        if not rects:
            return None
        # The OK button is orange too; it's the smaller one at the bottom.
        # The new crest row is the widest orange rectangle.
        return max(rects, key=lambda r: r[2])

    def find_blue_boxes(self, screen: np.ndarray, above_y: int) -> list[tuple[int, int]]:
        tmpl = self.ctx.vision.store.get("crest_checkbox")
        res = cv2.matchTemplate(screen, tmpl, cv2.TM_CCOEFF_NORMED)
        ys, xs = np.where(res >= self.ctx.vision.store.threshold("crest_checkbox"))
        th, tw = tmpl.shape[:2]
        points: list[tuple[int, int]] = []
        for x, y in sorted(zip(xs, ys), key=lambda p: -res[p[1], p[0]]):
            cx, cy = int(x + tw // 2), int(y + th // 2)
            if cy >= above_y:
                continue
            if all(abs(cy - py) > th // 2 for _, py in points):
                points.append((cx, cy))
        return sorted(points, key=lambda p: p[1])

    def identify_crest(self, screen: np.ndarray, box) -> tuple[str | None, dict]:
        x, y, w, h = box
        pad = h // 2
        crop = screen[max(0, y - pad):y + h + pad, max(0, x - pad):x + w + pad]
        scores = {}
        for rarity, name in ICON_TEMPLATES.items():
            tmpl = self.ctx.vision.store.get(name)
            if crop.shape[0] < tmpl.shape[0] or crop.shape[1] < tmpl.shape[1]:
                scores[rarity] = 0.0
                continue
            _, best, _, _ = cv2.minMaxLoc(cv2.matchTemplate(crop, tmpl, cv2.TM_CCOEFF_NORMED))
            scores[rarity] = round(float(best), 3)
        rarity = max(scores, key=scores.get)
        if scores[rarity] < self.ICON_THRESHOLD:
            return None, scores
        # lv4 vs 4+ icons are close; only call it 4+ when it clearly wins.
        if rarity == "lv4" and scores["4+"] >= scores["lv4"] - 0.02:
            rarity = "4+"
        return rarity, scores

    # The crest's title ("Dark Resistance Lv3") sits on the row's first line,
    # right of the icon. Offsets are within the orange row (720x1280 frame).
    TITLE_BOX = (95, 22, 425, 46)  # x, y, w, h

    def read_crest_text(self, screen: np.ndarray, box) -> tuple[str | None, str]:
        """(rarity from the title text or None, the text read)."""
        x, y, _, _ = box
        tx, ty, tw, th = self.TITLE_BOX
        text = self.read_text(x + tx, y + ty, tw, th, screen=screen, min_conf=70) or ""
        return text_rarity(text), text

    @staticmethod
    def row_image(screen: np.ndarray, box) -> np.ndarray:
        """The new crest's row (with a little margin) for the History tab."""
        x, y, w, h = box
        m = h // 4
        return screen[max(0, y - m):y + h + m, max(0, x - m):x + w + m].copy()

    def wanted(self, rarity: str) -> bool:
        return RARITY_ORDER.index(rarity) >= RARITY_ORDER.index(self.keep_from)

    def save_debug(self, screen: np.ndarray, tag: str) -> None:
        if not self.cfg.get("save_debug"):
            return
        folder = Path(self.ctx.data_dir or ".") / "debug_crest"
        folder.mkdir(exist_ok=True)
        cv2.imwrite(str(folder / f"{time.strftime('%Y%m%d_%H%M%S')}_{tag}.png"), screen)

    # ------------------------------------------------------------ handlers
    def handle_crest_burst(self, screen):
        self.count("burst")
        self.log("CREST BURST (5+) detected - stopping")
        self.save_debug(screen, "burst")
        self.record("crest", "Crest Burst (5+) - kept, script stopped", screen, rarity="5+",
                    action="kept")
        self.ledger_drop("burst", "kept")
        self.notify(f"Crest Burst (5+) found on {self.ctx.instance}! Script stopped - check your emulator.")
        raise Finished("crest burst")

    def handle_equip_crest_screen(self, screen):
        if time.monotonic() - self.crest_handled_at < 5:
            return  # we already acted; wait for the screen to change
        self.in_loop = False
        self.save_debug(screen, "equip")
        box = self.find_orange_box(screen)
        for attempt in range(2):
            if box:
                break
            self.log(f"New crest row not visible - scrolling down (attempt {attempt + 1})")
            h, w = screen.shape[:2]
            self.ctx.device.swipe(w // 2, int(h * 0.65), w // 2, int(h * 0.35), 400)
            self.sleep(1)
            screen = self.grab()
            box = self.find_orange_box(screen)
        if not box:
            self.log("Could not find the new crest row")
            self.save_debug(screen, "no_orange")
            if self.cfg.get("stop_on_unknown", True):
                self.notify("Crest: couldn't find the new crest on the Equip Crest screen. Stopped so nothing is scrapped by mistake.")
                raise Finished("new crest row not found")
            self.scrap(screen)
            return

        rarity, scores = self.identify_crest(screen, box)
        self.log(f"Crest icon scores: {scores}")
        row = self.row_image(screen, box)
        text, confidence = None, "verified"
        if self.cfg.get("verify_text", True) and self.ocr is not None:
            said, text = self.read_crest_text(screen, box)
            self.log(f"Crest title reads: '{text}' -> {said or 'no level found'}")
            if rarity is None and said:
                self.log(f"Icon unclear - using the title's level ({said})")
                rarity = said
            elif rarity and said and said != rarity:
                # Two independent readings disagree: never scrap on a guess.
                self.count("mismatch")
                self.record("crest", f"Icon says {rarity}, title says {said} ('{text}') - "
                            "left on screen", row, rarity="?", action="stopped")
                self.ledger_drop("?", "stopped", "uncertain", title=text)
                self.notify(f"Crest: the icon looks like {rarity} but the title reads '{text}' "
                            f"({said}). Left it on screen and stopped so nothing is scrapped by mistake.")
                raise Finished("crest icon/title disagree")
        if rarity is None:
            self.count("unknown")
            if self.cfg.get("stop_on_unknown", True):
                self.record("crest", f"Unidentified crest - left on screen (scores {scores})", row,
                            rarity="?", action="stopped")
                self.ledger_drop("?", "stopped", "uncertain", title=text)
                self.notify(f"Crest: found a crest I couldn't identify (scores {scores}). Left it on screen and stopped.")
                raise Finished("unknown crest")
            rarity, confidence = "lv3", "assumed"
        self.count(f"crest_{rarity}")
        self.progress()

        if self.wanted(rarity):
            self.session_kept += 1
            self.count("kept")
            self.log(f"{rarity} CREST - keeping it and stopping")
            self.record("crest", f"{rarity} crest - kept, script stopped", row, rarity=rarity,
                        action="kept")
            self.ledger_drop(rarity, "kept", confidence, title=text)
            self.notify(f"{rarity} crest found on {self.ctx.instance}! Left on the Equip Crest screen for you.")
            raise Finished(f"{rarity} crest")

        self.record("crest", f"{rarity} crest - scrapped into fragments", row, rarity=rarity,
                    action="scrapped")
        self.ledger_drop(rarity, "scrapped", confidence, title=text)
        self.log(f"Crest identified as {rarity} - scrapping")
        # Tick the equipped crests so only the new one is converted.
        for (cx, cy) in self.find_blue_boxes(screen, box[1]):
            self.log(f"Ticking equipped crest at ({cx}, {cy})")
            self.tap(cx, cy, settle=0.4)
        self.count("scrapped")
        self.crest_handled_at = time.monotonic()
        self.scrap(self.grab())

    def scrap(self, screen) -> None:
        """Redeploy (scrap + next loop) when runs remain; otherwise OK + confirm."""
        if not self.target_reached():
            m = self.find("redeploy_button", screen)
            v = self.ctx.vision
            if m and v.brightness(screen, m) >= 0.75 * v.template_brightness("redeploy_button"):
                self.log("Redeploying")
                self.tap_match(m, settle=2.5)
                return
            self.log("Redeploy missing or greyed out - scrapping with OK")
        if self.tap_template("select_crest_ok", screen, settle=1.5):
            ok2 = self.wait_for(["select_crest_ok2"], 6)
            if ok2:
                self.tap_match(ok2, settle=1.5)
        if self.target_reached():
            self.finish()

    def handle_select_crest_ok2(self, screen):
        if self.find("results_redeploy", screen) or self.find("looping_button", screen):
            return  # that's the results bar's OK, not a scrap confirmation
        self.tap_template("select_crest_ok2", screen, settle=1.5)

    def handle_crest_fragment(self, screen):
        self.log("Crest Fragment popup - OK")
        self.tap_template("crest_fragment_ok", screen, settle=1.0)

    def handle_quest_list(self, screen):
        if self.target_reached():
            self.finish()
        if self.tap_template("quest_list_entry", screen, settle=2):
            self.log("Quest list - opening the quest")
            self.party_done = False

    def handle_home_screen(self, screen):
        if not self.cfg.get("mode_247"):
            return
        self.log("Home screen - entering Exploring")
        self.tap_template("exploring_button", screen, settle=3)

    def handle_exploring_screen(self, screen):
        if not self.cfg.get("mode_247"):
            return
        self.log("Exploring - entering Crest Palace")
        self.tap_template("crest_palace_icon", screen, settle=3) or \
            self.tap_template("crest_palace_icon2", screen, settle=3)

    def handle_crest_palace_screen(self, screen):
        if not self.cfg.get("mode_247"):
            return
        day = WEEKDAYS[game_now().weekday()]
        for name in (f"crest_palace_{day}", "crest_palace_target"):
            if self.tap_template(name, screen, settle=3):
                self.log(f"Opened palace ({name})")
                self.palace = name
                return
        self.notify("Crest: on the Crest Palace screen but no palace tile template matched today. Stopped.")
        raise Finished("palace not found")
