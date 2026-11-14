"""Reading the Units list grid and a unit's page (real 720x1280 captures, 2026-11-14).

Units list (header 'Units', template compendium_grid_header): a fixed 5-column
grid. Cards carry no readable text - portrait, element icon, star badge, 'Lv'
badge without a number - so names come from each unit's page.

Unit page (template compendium_detail_marker = 'Achievements'): element icon +
name on one line (white text over artwork), race on the right, and
'Quest cleared: N' at the bottom. The page shows no level.
Calibrated on tests/fixtures/units_grid_*.png and unit_profile_ira.png.
"""
from __future__ import annotations

import re
from collections import Counter

import cv2
import numpy as np

from .ocr import BORDER

# --------------------------------------------------------------------------- grid
GRID_COLS = [64, 199, 335, 470, 605]   # x of each card's 'Lv' badge
ROW_PITCH = 121.8                       # px between card rows
GRID_TOP, GRID_BOTTOM = 330, 1070       # badge rows outside this are cut off by the frame
CARD_MIN_SCORE = 0.72                   # cards 0.79+, empty cells <= 0.27 on the fixtures
TAP_OFFSET = (30, -40)                  # badge -> card body


def _cell_score(gray: np.ndarray, tmpl_gray: list[np.ndarray], x: int, y: int) -> float:
    best = 0.0
    for t in tmpl_gray:
        th, tw = t.shape[:2]
        x0, y0 = x - tw // 2 - 8, y - th // 2 - 8
        win = gray[max(0, y0):y0 + th + 16, max(0, x0):x0 + tw + 16]
        if win.shape[0] >= th and win.shape[1] >= tw:
            best = max(best, float(cv2.minMaxLoc(cv2.matchTemplate(win, t, cv2.TM_CCOEFF_NORMED))[1]))
    return best


def grid_cards(screen: np.ndarray, vision) -> list[tuple[int, int]]:
    """Tap points of every card on the visible grid, top-left to bottom-right.
    Rows are anchored on confident 'Lv' badge matches, then every column of
    each row is checked on its own (template matching alone missed ~25%)."""
    names = [n for n in ("compendium_card_lv", "compendium_card_lv_rainbow") if vision.store.has(n)]
    anchors = sorted(m.center[1] for n in names for m in vision.find_all(screen, n)
                     if GRID_TOP <= m.center[1] <= GRID_BOTTOM)
    if not anchors:
        return []
    base = anchors[0]
    ys = set()
    k = -int((base - GRID_TOP) // ROW_PITCH)
    while True:
        y = round(base + k * ROW_PITCH)
        if y > GRID_BOTTOM:
            break
        if y >= GRID_TOP:
            ys.add(y)
        k += 1
    gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
    tg = [cv2.cvtColor(vision.store.get(n), cv2.COLOR_BGR2GRAY) for n in names]
    out = []
    for y in sorted(ys):
        for x in GRID_COLS:
            if _cell_score(gray, tg, x, y) >= CARD_MIN_SCORE:
                out.append((x + TAP_OFFSET[0], y + TAP_OFFSET[1]))
    return out


# --------------------------------------------------------------------------- unit page
NAME_BOX = (100, 698, 370, 46)      # x, y, w, h  (element icon sits just left of it)
ICON_BOX = (64, 703, 32, 32)
RACE_BOX = (500, 700, 125, 40)
CLEARED_BOX = (420, 1100, 280, 46)
# OpenCV hue (0-180) of the element icon. Seen on real captures: fire 8, light 21,
# dark 131-133. Water / earth are expected ranges not yet seen on this account.
ELEMENTS = [("Fire", 0, 14, True), ("Light", 15, 32, True), ("Earth", 33, 85, False),
            ("Water", 86, 125, False), ("Dark", 126, 165, True), ("Fire", 166, 180, True)]
_CLEARED = re.compile(r"cleared\s*[:;.]?\s*([\d,]+)", re.I)


def white_text(img: np.ndarray, smax: int, vmin: int, scale: float = 3.0) -> np.ndarray:
    """Keep only near-white, unsaturated strokes: the game's white text over artwork."""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    m = cv2.inRange(hsv, (0, 0, vmin), (180, smax, 255))
    m = cv2.resize(m, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    return cv2.copyMakeBorder(255 - m, BORDER, BORDER, BORDER, BORDER, cv2.BORDER_CONSTANT, value=255)


def read_name(ocr, screen: np.ndarray) -> tuple[str, float, int]:
    """(name, mean confidence of the winning reading, votes out of 3).
    Three white-text thresholds vote; the name only counts as read when they agree."""
    x, y, w, h = NAME_BOX
    crop = screen[y:y + h, x:x + w]
    reads = []
    for vmin in (170, 200, 225):
        words = ocr._words(white_text(crop, 40, vmin), 7, None)
        words = [wd for wd in words if re.search(r"[A-Za-z]", wd.text)]
        if words:
            text = re.sub(r"[^\w' .&:()-]", "", " ".join(wd.text for wd in words)).strip()
            reads.append((text, sum(wd.conf for wd in words) / len(words)))
    if not reads:
        return "", 0.0, 0
    text, votes = Counter(t for t, _ in reads).most_common(1)[0]
    conf = max(c for t, c in reads if t == text)
    if votes == 1:
        text, conf = max(reads, key=lambda r: r[1])
        conf = min(conf, 55.0)  # no agreement: keep it, but as uncertain
    return text, round(conf, 1), votes


def read_element(screen: np.ndarray) -> tuple[str | None, float]:
    x, y, w, h = ICON_BOX
    hsv = cv2.cvtColor(screen[y:y + h, x:x + w], cv2.COLOR_BGR2HSV).reshape(-1, 3)
    px = hsv[(hsv[:, 1] > 80) & (hsv[:, 2] > 80)]
    if len(px) < 120:
        return None, 0.0
    hue = float(np.median(px[:, 0]))
    for name, lo, hi, seen in ELEMENTS:
        if lo <= hue <= hi:
            return name, (90.0 if seen else 50.0)  # unseen colours stay 'uncertain'
    return None, 0.0


def read_profile(ocr, screen: np.ndarray) -> dict:
    """One observation for UnitRoster.apply_scan."""
    name, name_conf, votes = read_name(ocr, screen)
    element, el_conf = read_element(screen)
    race = ocr.read_region(screen, *RACE_BOX)
    race_text = re.sub(r"[^A-Za-z -]", "", race.text).strip()
    cl = ocr.read_region(screen, *CLEARED_BOX)
    m = _CLEARED.search(cl.text or "")
    clears = int(m.group(1).replace(",", "")) if m else None
    fields = {
        "element": {"value": element, "confidence": el_conf},
        "race": {"value": race_text or None, "confidence": race.confidence},
        "quest_clears": {"value": clears, "confidence": cl.confidence if m else 0},
    }
    return {"name": name, "name_conf": name_conf, "name_votes": votes, "fields": fields}
