"""Phase 3: Unit Roster store, learned name list, scan merging and comparisons."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rerun.units import UnitRoster  # noqa: E402


def ob(name, conf=90, **fields):
    return {"name": name, "name_conf": conf,
            "fields": {k: ({"value": v, "confidence": 90} if not isinstance(v, dict) else v)
                       for k, v in fields.items()}}


def test_first_scan_adds_units_as_new():
    with tempfile.TemporaryDirectory() as d:
        r = UnitRoster(d)
        s = r.apply_scan([ob("Celia", level=120, rarity="SS", element="Dark"),
                          ob("Fosradius", level=100)], "units_list")
        assert sorted(s["new"]) == ["Celia", "Fosradius"] and s["seen"] == 2
        again = UnitRoster(d)                     # persisted
        assert again.value(again.units["Celia"], "level") == 120
        assert again.units["Celia"]["fields"]["level"]["status"] == "ocr"


def test_incomplete_scan_keeps_existing_values():
    with tempfile.TemporaryDirectory() as d:
        r = UnitRoster(d)
        r.apply_scan([ob("Celia", level=120, element="Dark")], "units_list")
        s = r.apply_scan([ob("Celia", level={"value": None, "confidence": 0})], "units_list")
        assert r.value(r.units["Celia"], "level") == 120 and r.value(r.units["Celia"], "element") == "Dark"
        assert s["new"] == [] and s["changed"] == []


def test_misread_name_maps_onto_known_unit():
    with tempfile.TemporaryDirectory() as d:
        r = UnitRoster(d)
        r.apply_scan([ob("Fosradius", level=100)], "units_list")
        name, how, score = r.resolve_name("Fosradlus")
        assert (name, how) == ("Fosradius", "fuzzy"), (name, how, score)
        s = r.apply_scan([ob("Fosradlus", level=110)], "units_list")
        assert s["new"] == [] and r.value(r.units["Fosradius"], "level") == 110
        assert len(r.units) == 1


def test_manual_correction_is_learned_and_merges():
    with tempfile.TemporaryDirectory() as d:
        r = UnitRoster(d)
        r.apply_scan([ob("Ce1ia X", level=80)], "units_list")      # bad reading became a unit
        r.correct_name("Ce1ia X", "Celia")
        assert "Ce1ia X" not in r.units and r.value(r.units["Celia"], "level") == 80
        assert UnitRoster(d).resolve_name("Ce1ia X") == ("Celia", "alias", 1.0)
        s = UnitRoster(d).apply_scan([ob("Ce1ia X", level=81)], "units_list")
        assert s["new"] == []


def test_confident_reading_replaces_earlier_uncertain_spelling():
    """Live: the first scan stored 'Clyde the.Crimson sword G' (uncertain)."""
    with tempfile.TemporaryDirectory() as d:
        r = UnitRoster(d)
        r.apply_scan([ob("Clyde the.Crimson sword G", conf=55, quest_clears=0)], "units_list")
        assert r.units["Clyde the.Crimson sword G"]["name_status"] == "uncertain"
        s = r.apply_scan([ob("Clyde, the Crimson Sword God", conf=61, quest_clears=0)], "units_list")
        assert list(r.units) == ["Clyde, the Crimson Sword God"], list(r.units)
        assert s["new"] == [] and s["renamed"]
        assert UnitRoster(d).resolve_name("Clyde the.Crimson sword G")[0] == "Clyde, the Crimson Sword God"
        # a manual name is never replaced
        r.correct_name("Clyde, the Crimson Sword God", "Clyde")
        r.apply_scan([ob("Clyde, the Crimson Sword God", conf=90)], "units_list")
        assert "Clyde" in r.units


def test_ocr_never_overwrites_manual_or_verified():
    with tempfile.TemporaryDirectory() as d:
        r = UnitRoster(d)
        r.apply_scan([ob("Celia", level=120)], "units_list")
        r.set_field("Celia", "level", 130, "manual")
        s = r.apply_scan([ob("Celia", level=125)], "units_list")
        assert r.value(r.units["Celia"], "level") == 130 and s["kept"] == 1


def test_low_confidence_does_not_replace_confident_reading():
    with tempfile.TemporaryDirectory() as d:
        r = UnitRoster(d)
        r.apply_scan([ob("Celia", level=120)], "units_list")
        r.apply_scan([ob("Celia", level={"value": 12, "confidence": 30})], "units_list")
        assert r.value(r.units["Celia"], "level") == 120


def test_low_confidence_unknown_name_is_marked_uncertain():
    with tempfile.TemporaryDirectory() as d:
        r = UnitRoster(d)
        s = r.apply_scan([ob("Xq#z", conf=40)], "units_list")
        assert s["uncertain"] == ["Xq#z"] and r.units["Xq#z"]["name_status"] == "uncertain"


def test_scan_comparison_and_csv_and_filters():
    with tempfile.TemporaryDirectory() as d:
        r = UnitRoster(d)
        a = r.apply_scan([ob("Celia", level=100, rarity="SS"), ob("Rem", level=90)], "units_list")
        import time
        time.sleep(1.1)  # scan ids are per second
        b = r.apply_scan([ob("Celia", level=120, rarity="SS"), ob("Reinhard", level=1)], "units_list")
        diff = r.compare(a["scan"], b["scan"])
        assert diff["added"] == ["Reinhard"] and diff["not_seen"] == ["Rem"]
        assert ("Celia", "level", 100, 120) in diff["changed"]
        csv_text = r.to_csv()
        assert csv_text.splitlines()[0].startswith("name,element,race,quest_clears,level,rarity")
        assert "Celia,,,,120,SS" in csv_text
        assert [u["name"] for u in r.rows(search="re")] == ["Reinhard", "Rem"]
        assert [u["name"] for u in r.rows(sort="level", desc=True)][0] == "Celia"
        assert [u["name"] for u in r.rows(rarity="SS")] == ["Celia"]
        assert "3" in r.summary_text()
        # 'unread' = fields a scan can read (element/race/quest clears) or an uncertain name
        r.apply_scan([ob("Ira", element="Dark", race="Human", quest_clears=2549)], "units_list")
        assert "Ira" not in [u["name"] for u in r.rows(only_incomplete=True)]
        assert "Celia" in [u["name"] for u in r.rows(only_incomplete=True)]


# ------------------------------------------------------------------ real screens
FIX = ROOT / "tests" / "fixtures"


def _vision():
    from rerun.vision import TemplateStore, Vision
    store = TemplateStore(ROOT / "templates")
    ok = all(store.has(n) for n in ("compendium_grid_header", "compendium_card_lv",
                                    "compendium_detail_marker"))
    return Vision(store) if ok else None


def _ocr():
    try:
        from rerun.ocr import get_ocr
        return get_ocr("auto")
    except Exception:  # noqa: BLE001
        return None


def test_grid_finds_every_card_on_real_units_lists():
    import cv2
    from rerun.unit_screens import grid_cards
    v = _vision()
    if v is None:
        print("  (skipped: compendium templates not imported)")
        return
    # counted by hand on the captures: Fire page 6x5 = 30; Dark page 28 (a shadowed
    # card and an empty last cell are not cards)
    for fx, n in (("units_grid_fire.png", 30), ("units_grid_dark.png", 28), ("home.png", 0),
                  ("unit_profile_ira.png", 0)):
        got = grid_cards(cv2.imread(str(FIX / fx)), v)
        assert len(got) == n, (fx, len(got))


def test_unit_page_reader_on_real_capture():
    import cv2
    from rerun.unit_screens import read_profile
    ocr = _ocr()
    if ocr is None:
        print("  (skipped: no Tesseract)")
        return
    ob = read_profile(ocr, cv2.imread(str(FIX / "unit_profile_ira.png")))
    assert ob["name"] == "Ira Gamagoori" and ob["name_votes"] >= 2, ob
    f = ob["fields"]
    assert f["element"]["value"] == "Dark" and f["race"]["value"] == "Human", f
    assert f["quest_clears"]["value"] == 2549, f


def test_scan_script_fills_roster_from_real_screens():
    """Grid -> tap a card -> unit page -> Back, on real captures; stops at max_units=1."""
    import cv2
    from rerun.adb import FakeDevice
    from rerun.engine import Context
    from rerun.scripts.compendium_counter import CompendiumCounterScript
    from rerun.stats import Stats
    import tests.test_scripts as ts
    v, ocr = _vision(), _ocr()
    if v is None or ocr is None:
        print("  (skipped: templates or Tesseract missing)")
        return
    ts.fast()
    grid = cv2.imread(str(FIX / "units_grid_dark.png"))
    page = cv2.imread(str(FIX / "unit_profile_ira.png"))

    class Dev(FakeDevice):
        def __init__(self):
            super().__init__([grid])
            self.cur, self.taps, self.backs = grid, [], 0

        def screencap(self):
            return self.cur

        def tap(self, x, y):
            self.taps.append((x, y))
            self.cur = page

        def back(self):
            self.backs += 1
            self.cur = grid

    with tempfile.TemporaryDirectory() as d:
        notes = []
        ctx = Context(instance="t", device=Dev(), vision=v, stats=Stats(), routines={},
                      base_resolution=(720, 1280), log=lambda i, m: None,
                      notify=lambda i, m, image=None, ping=False: notes.append(m), data_dir=d,
                      units=UnitRoster(d))
        ctx.params["tesseract_path"] = "auto"
        s = CompendiumCounterScript(ctx, {"max_units": 1})
        result = ts.run(s)
        r = UnitRoster(d)
        assert result.startswith("finished: Compendium Counter"), result
        assert "Ira Gamagoori" in r.units, r.units
        u = r.units["Ira Gamagoori"]
        assert r.value(u, "quest_clears") == 2549 and r.value(u, "element") == "Dark"
        tx, ty = ctx.device.taps[0]                      # first card, top-left
        assert abs(tx - 94) <= 3 and abs(ty - 365) <= 3, ctx.device.taps
        assert ctx.device.backs == 1
        assert len(r.scans()) == 1 and (Path(d) / "compendium_report.csv").exists()
        assert any("1 new" in n for n in notes), notes


def test_long_name_over_flames_and_race_split():
    """Seen live: 'Clyde, the Crimson Sword God' ran into the race box and the flames
    behind it broke the reading."""
    import cv2
    from rerun.unit_screens import read_profile
    ocr = _ocr()
    if ocr is None:
        print("  (skipped: no Tesseract)")
        return
    ob = read_profile(ocr, cv2.imread(str(FIX / "unit_profile_clyde.png")))
    assert ob["name"] == "Clyde, the Crimson Sword God" and ob["name_votes"] >= 2, ob
    f = ob["fields"]
    assert (f["element"]["value"], f["race"]["value"], f["quest_clears"]["value"]) == ("Fire", "Human", 0), f


def test_animated_grid_does_not_reopen_the_same_card():
    """Seen live 2026-11-14 15:00: the Units screen animates, an exact pixel signature
    never matched, and the first card was reopened forever."""
    import cv2
    from rerun.adb import FakeDevice
    from rerun.engine import Context
    from rerun.scripts.compendium_counter import CompendiumCounterScript
    from rerun.stats import Stats
    import tests.test_scripts as ts
    v, ocr = _vision(), _ocr()
    if v is None or ocr is None:
        print("  (skipped: templates or Tesseract missing)")
        return
    ts.fast()
    frames = [cv2.imread(str(FIX / "units_grid_fire.png")), cv2.imread(str(FIX / "units_grid_fire_top.png"))]
    pages = [cv2.imread(str(FIX / "unit_profile_clyde.png")), cv2.imread(str(FIX / "unit_profile_ira.png"))]

    class Dev(FakeDevice):
        def __init__(self):
            super().__init__(frames)
            self.n, self.page, self.taps, self.hits = 0, None, [], {}

        def screencap(self):
            if self.page is not None:
                return self.page
            self.n += 1
            return frames[self.n % 2]          # same view, animated

        def tap(self, x, y):
            if (x, y) not in self.taps:
                self.taps.append((x, y))
            self.hits[(x, y)] = self.hits.get((x, y), 0) + 1
            if self.hits[(x, y)] > 3:  # the live bug: fail fast instead of looping
                raise AssertionError(f"card {(x, y)} reopened {self.hits[(x, y)]} times")
            self.page = pages[min(self.taps.index((x, y)), 1)]

        def back(self):
            self.page = None

    with tempfile.TemporaryDirectory() as d:
        ctx = Context(instance="t", device=Dev(), vision=v, stats=Stats(), routines={},
                      base_resolution=(720, 1280), log=lambda i, m: None,
                      notify=lambda i, m, image=None, ping=False: None, data_dir=d, units=UnitRoster(d))
        ctx.params["tesseract_path"] = "auto"
        result = ts.run(CompendiumCounterScript(ctx, {"max_units": 2}))
        r = UnitRoster(d)
    assert result.startswith("finished: Compendium Counter"), result
    assert len(ctx.device.taps) == 2, ctx.device.taps        # two different cards, once each
    assert set(r.units) == {"Clyde, the Crimson Sword God", "Ira Gamagoori"}, list(r.units)


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
