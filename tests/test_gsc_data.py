"""GS Companion reference data: build output and the GSCData lookups."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rerun.gsc_data import GSCData  # noqa: E402

gsc = GSCData(ROOT)


def test_data_present():
    assert gsc.available
    assert len(gsc.stages) == 18
    assert len(gsc.crests) >= 130
    assert len(gsc.units) >= 400
    assert len(gsc.recommendations) >= 400


def test_palace_schedule():
    fri = {s["name"] for s in gsc.palace_on("friday")}
    assert {"Shrine of Caliginosity", "Shrine of Adamantine", "Temple of Heavenly Light"} <= fri
    assert [s["name"] for s in gsc.palace_on("Sunday", "nova")] == ["Shrine of Sagacity"]
    # Always-open stage is there every day.
    for d in ("Monday", "Thursday", "Sunday"):
        assert any(s["name"] == "Temple of Heavenly Light" for s in gsc.palace_on(d))


def test_palace_today_uses_game_reset():
    # Sat 2026-11-14 05:00 UTC-6 is still Friday's game day (reset is 06:00 UTC-6).
    t = datetime(2026, 11, 14, 11, 0, tzinfo=timezone.utc).timestamp()
    assert any(s["name"] == "Shrine of Caliginosity" for s in gsc.palace_today(t))
    t = datetime(2026, 11, 14, 13, 0, tzinfo=timezone.utc).timestamp()
    assert any(s["name"] == "Shrine of Cursed Claw" for s in gsc.palace_today(t))


def test_crest_lookups():
    c = gsc.crest("atk up")
    assert c["levels"]["Lv4+"] == "ATK 810 UP"
    assert {s["name"] for s in gsc.stages_dropping("ATK UP")} == {
        "Shrine of Cinderplume", "Shrine of Crimson Sea", "Shrine of Discordia"}
    assert "Promise of Funeral God" in gsc.stage("Shrine of Oblivion")["crests"]


def test_match_crest_from_ocr():
    c, lv = gsc.match_crest("Arts gauge UP Lv4+")
    assert c["name"] == "Arts gauge UP" and lv == "Lv4+"
    c, lv = gsc.match_crest("Arts gauqe UP Lv. 3")  # OCR misread
    assert c["name"] == "Arts gauge UP" and lv == "Lv3"
    assert gsc.match_crest("zzzz")[0] is None


def test_units_and_recommendations():
    assert gsc.match_unit("Mira (Fire")["element"] == "Fire"
    assert gsc.recommended("Clyde") == ["ATK UP"]
    assert "Clyde" in gsc.units_wanting("ATK UP")


if __name__ == "__main__":
    if not gsc.available:
        # data/ is local-only (gitignored): run tools/gscompanion_build.py to create it.
        print("SKIP: no data/gscompanion/ on this machine")
        sys.exit(0)
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
