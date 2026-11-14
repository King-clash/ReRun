"""Phase 4: Compendium targets, progress, change since the last scan, summaries."""
from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rerun.compendium import Compendium, bar  # noqa: E402
from rerun.history import History  # noqa: E402
from rerun.units import UnitRoster  # noqa: E402

DAY = 86400


def ob(name, clears, conf=90):
    return {"name": name, "name_conf": conf,
            "fields": {"quest_clears": {"value": clears, "confidence": 90},
                       "element": {"value": "Fire", "confidence": 90}}}


def backdate(r: UnitRoster, *ages_days):
    """Give the scans in scans.jsonl the given ages (oldest first)."""
    lines = r.scans_path.read_text(encoding="utf-8").splitlines()
    now = time.time()
    out = []
    for line, age in zip(lines, ages_days):
        s = json.loads(line)
        s["t"] = now - age * DAY
        out.append(json.dumps(s))
    r.scans_path.write_text("\n".join(out) + "\n", encoding="utf-8")


def setup(d):
    r = UnitRoster(d)
    r.apply_scan([ob("Celia", 40), ob("Fen", 95), ob("Ira", 0)], "units_list", complete=True)
    r.apply_scan([ob("Celia", 52), ob("Fen", 100), ob("Ira", 0)], "units_list", complete=True)
    backdate(r, 7, 0)
    return r, Compendium(r)


def test_targets_progress_and_remaining():
    with tempfile.TemporaryDirectory() as d:
        r, c = setup(d)
        c.set_global(100)
        c.set_target("Celia", 200)
        rows = {x["name"]: x for x in c.rows()}
        assert rows["Celia"]["target"] == 200 and rows["Celia"]["target_kind"] == "unit"
        assert rows["Celia"]["remaining"] == 148 and round(rows["Celia"]["pct"]) == 26
        assert rows["Fen"]["target_kind"] == "global" and rows["Fen"]["state"] == "done"
        assert rows["Ira"]["remaining"] == 100 and rows["Ira"]["state"] == "open"
        # persisted
        c2 = Compendium(UnitRoster(d))
        assert c2.target_of("Celia") == (200, "unit") and c2.target_of("Ira") == (100, "global")
        c2.set_target("Celia", None)                       # back to the global target
        assert c2.target_of("Celia") == (100, "global")


def test_change_since_previous_scan():
    with tempfile.TemporaryDirectory() as d:
        r, c = setup(d)
        rows = {x["name"]: x for x in c.rows()}
        assert rows["Celia"]["delta"] == 12
        assert c.change_text(rows["Celia"]).startswith("+12 since ")
        assert rows["Ira"]["delta"] == 0
        # every scan is kept
        assert len(r.scans()) == 2


def test_filters_near_and_at_target():
    with tempfile.TemporaryDirectory() as d:
        r, c = setup(d)
        assert c.rows(show="With a target") == []
        c.set_global(110)                                  # Fen 100/110 = 91 %
        assert [x["name"] for x in c.rows(show="Near target")] == ["Fen"]
        c.set_near(95)
        assert c.rows(show="Near target") == []
        c.set_target("Celia", 50)
        assert [x["name"] for x in c.rows(show="At target")] == ["Celia"]
        assert len(c.rows(show="With a target")) == 3


def test_sort_puts_units_without_value_last():
    with tempfile.TemporaryDirectory() as d:
        r, c = setup(d)
        c.set_target("Celia", 100)
        names = [x["name"] for x in c.rows(sort="pct", desc=True)]
        assert names[0] == "Celia"                         # only one with a percentage
        names = [x["name"] for x in c.rows(sort="clears", desc=True)]
        assert names == ["Fen", "Celia", "Ira"]


def test_corrected_name_keeps_history_and_target():
    with tempfile.TemporaryDirectory() as d:
        r = UnitRoster(d)
        r.apply_scan([ob("Cella", 10)], "units_list")
        r.apply_scan([ob("Cella", 15)], "units_list")
        backdate(r, 3, 0)
        c = Compendium(r)
        c.set_target("Cella", 50)
        r.correct_name("Cella", "Celia")
        c.rename("Cella", "Celia")
        row = c.rows()[0]
        assert row["name"] == "Celia" and row["delta"] == 5 and row["target"] == 50


def test_summary_last_full_scan_and_counts():
    with tempfile.TemporaryDirectory() as d:
        r, c = setup(d)
        r.apply_scan([ob("Celia", 53)], "units_list", complete=False)   # stopped early
        c.set_global(100)
        s = c.summary()
        assert s["units"] == 3 and s["done"] == 1 and s["near"] == 0
        assert s["last_complete"] is not None and not s["last_scan_complete"]
        assert "stopped early" in c.summary_text()


def test_legacy_scan_counts_as_full_when_history_says_end_of_list():
    with tempfile.TemporaryDirectory() as d:
        r = UnitRoster(d)
        r.apply_scan([ob("Celia", 1)], "units_list")                     # no flag (old build)
        h = History(Path(d) / "history")
        assert Compendium(r, h).last_complete_scan() is None
        h.add("Instance 1", "compendium_counter", "compendium",
              "Compendium Counter: 1 unit(s) counted. Reached the end of the list.")
        assert Compendium(r, h).last_complete_scan()["id"] == r.scans()[0]["id"]


def test_bar():
    assert bar(None) == ""
    assert bar(0).startswith("░" * 10) and bar(100).startswith("█" * 10)
    assert bar(55).endswith(" 55%")


if __name__ == "__main__":
    failed = 0
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as e:  # noqa: BLE001
            import traceback
            failed += 1
            print(f"FAIL {t.__name__}: {e!r}")
            traceback.print_exc()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
