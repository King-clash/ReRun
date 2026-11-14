"""Compendium Counter - ReStart's compendium scan.

On the Units compendium grid Rerun opens each card, reads the unit's name
and its quest clear count with OCR, goes back, and scrolls on until the end
of the list. Units you don't own have no clear count and are skipped. The
result is saved to compendium_report.csv (and shown in History)."""
from __future__ import annotations

import csv
import re
import time
from pathlib import Path

import numpy as np

from .base import BaseScript, Done, Finished, Setting, T

_NUM = re.compile(r"\d[\d,]*")


class CompendiumCounterScript(BaseScript):
    ID = "compendium_counter"
    NAME = "Compendium Counter"
    BETA = True
    DESCRIPTION = "Scans the Units compendium and reports each unit's quest clear count."
    INSTRUCTIONS = """COMPENDIUM COUNTER (BETA - not yet run on your game; uses text reading)
Opens every unit in the Units compendium, reads its name and quest clear
count, and writes them to compendium_report.csv in the Rerun folder.

SETUP
1. Open the Units compendium in-game (the grid of unit cards).
2. Press Start. Units you don't own are skipped - their page has no count.
"""
    SETTINGS = [Setting("max_units", "Stop after this many units (0 = all)", "int", 0)]
    TEMPLATES = [
        T("compendium_grid_header", "'Units' title of the compendium grid."),
        T("compendium_card_lv", "The 'Lv' corner of a unit card on the grid."),
        T("compendium_card_lv_rainbow", "The rainbow 'Lv' corner (higher rarity).", optional=True),
        T("compendium_detail_marker", "The 'Achievements' tab of a unit's page."),
    ]
    STATES = [
        ("detail", ["compendium_detail_marker"]),
        ("grid", ["compendium_grid_header"]),
    ]
    MAX_SCROLLS = 80

    def on_start(self) -> None:
        if self.ocr is None:
            self.notify("Compendium Counter needs the text reader (it comes with ReStart). Stopped.")
            raise Done("no text reader")
        self.rows: dict[str, int] = {}
        self.done_cards: set[tuple[int, int]] = set()  # card spots already opened on this view
        self.opened: tuple[int, int] | None = None
        self.scrolls = 0
        self.limit = int(self.cfg.get("max_units") or 0)
        self.view_sig: bytes | None = None

    def report(self, why: str) -> None:
        path = Path(self.ctx.data_dir or ".") / "compendium_report.csv"
        if self.rows:
            with path.open("w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["unit", "quest clears"])
                for name, n in sorted(self.rows.items(), key=lambda r: -r[1]):
                    w.writerow([name, n])
            msg = f"Compendium Counter: {len(self.rows)} unit(s) counted - saved to {path.name}. {why}"
        else:
            msg = f"Compendium Counter: nothing found - keeping the previous report. {why}"
        self.record("compendium", msg)
        self.notify(msg, screenshot=False, ping=False)
        raise Done(msg)

    # ---------------------------------------------------------------- grid
    def cards(self, screen) -> list[tuple[int, int]]:
        found = self.ctx.vision.find_all(screen, "compendium_card_lv")
        if self.has_template("compendium_card_lv_rainbow"):
            found += self.ctx.vision.find_all(screen, "compendium_card_lv_rainbow")
        # The 'Lv' tag sits on the card's lower-left; tap the card body above it.
        return sorted({(m.center[0] + 30, m.center[1] - 40) for m in found}, key=lambda p: (p[1], p[0]))

    def handle_grid(self, screen):
        if self.limit and len(self.rows) >= self.limit:
            self.report("Unit limit reached.")
        sig = np.asarray(screen[300:1100:40, ::40]).tobytes()
        if sig != self.view_sig:
            self.view_sig, self.done_cards = sig, set()
        todo = [c for c in self.cards(screen) if c not in self.done_cards]
        if todo:
            self.opened = todo[0]
            self.done_cards.add(todo[0])
            self.tap(*todo[0], settle=1.5)
            return
        # every card on this view done: scroll; if nothing moves, the list has ended
        self.scrolls += 1
        if self.scrolls > self.MAX_SCROLLS:
            self.report("Scroll limit reached.")
        before = screen
        self.ctx.device.swipe(360, 1000, 360, 560, 600)
        self.sleep(1.2)
        after = self.grab()
        if np.abs(after[300:1100].astype(int) - before[300:1100].astype(int)).mean() < 2:
            self.report("Reached the end of the list.")
        self.log("Scrolled")

    # ---------------------------------------------------------------- unit page
    def read_unit(self, screen) -> tuple[str | None, int | None]:
        words = self.ocr.screen_words(screen, min_conf=55)
        # Clear count: the number right after a word starting with "clear".
        count = None
        for i, w in enumerate(words):
            if w.text.lower().startswith("clear"):
                for nxt in words[i + 1:i + 4]:
                    if abs(nxt.y - w.y) < 20 and _NUM.fullmatch(nxt.text):
                        count = int(nxt.text.replace(",", ""))
                        break
            if count is not None:
                break
        # Name: the longest line of words in the top part of the page.
        lines: dict[int, list] = {}
        for w in words:
            if 150 < w.y < 420 and not _NUM.fullmatch(w.text):
                lines.setdefault(w.y // 18, []).append(w)
        name = None
        if lines:
            best = max(lines.values(), key=lambda ws: sum(len(x.text) for x in ws))
            name = " ".join(x.text for x in sorted(best, key=lambda x: x.x))
        return name, count

    def handle_detail(self, screen):
        name, count = self.read_unit(screen)
        if count is None:
            self.log(f"No quest count on that page ({name or 'unnamed'}) - skipped.")
        elif name in self.rows:
            self.log(f"{name} already counted (seen again after scrolling)")
        elif name:
            self.rows[name] = count
            self.count("units")
            self.log(f"{name}: {count} clears")
            self.progress()
        self.ctx.device.back()
        self.sleep(1.2)

    def handle_unknown(self, screen):
        # A card that opened neither its page nor stayed on the grid.
        if self.opened and self._unknown_since and time.monotonic() - self._unknown_since > 15:
            self.notify("Compendium Counter: a card opened neither its page nor the grid - stopped.")
            raise Finished("unexpected screen")


__all__ = ["CompendiumCounterScript"]
