"""GS Companion names take priority over names read from the game (clear matches only)."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rerun.compendium import Compendium  # noqa: E402
from rerun.gsc_data import GSCData  # noqa: E402
from rerun.units import UnitRoster  # noqa: E402

UNITS = [("Clyde", "Fire", "Human"), ("Priscilla", "Fire", "Human"), ("Valentines Priscilla", "Fire", "Human"),
         ("Freed", "Light", "God"), ("Emperor Isliid", "Light", "Human"),
         ("Rimuru (Slime-form)", "Water", "Demon"), ("Rimuru (Human form)", "Water", "Demon"),
         ("Platina", "Light", "God"), ("Godspeed Crusader Platina", "Light", "God"),
         ("Nies", "Water", "God"), ("Kane (Earth)", "Earth", "Human"), ("Kane (Dark)", "Dark", "Human"),
         ("Weaver", "Water", "Spirit")]


def gsc(d: str) -> GSCData:
    g = Path(d) / "data" / "gscompanion"
    g.mkdir(parents=True)
    (g / "units.json").write_text(json.dumps({"units": [
        {"name": n, "element": e, "tag": "AWK"} for n, e, _ in UNITS]}), encoding="utf-8")
    (g / "unit_details.json").write_text(json.dumps({"units": {
        n: {"name": n, "race": r, "aka": [n]} for n, _, r in UNITS}}), encoding="utf-8")
    (g / "crests.json").write_text(json.dumps({"crests": []}), encoding="utf-8")
    return GSCData(d)


def ob(name, el, race="Human", clears=1):
    return {"name": name, "name_conf": 90, "fields": {
        "element": {"value": el, "confidence": 90}, "race": {"value": race, "confidence": 90},
        "quest_clears": {"value": clears, "confidence": 90}}}


def test_reference_name_rules():
    with tempfile.TemporaryDirectory() as d:
        g = gsc(d)
        assert g.reference_name("Clyde, the Crimson Sword God", "Fire", "Human") == "Clyde"
        assert g.reference_name("Awoken Priscilla", "Fire", "Human") == "Priscilla"
        assert g.reference_name("Emperor of Gods Freed", "Light", "God") == "Freed"
        assert g.reference_name("IDivine ConquronGediNies SF", "Water", "God") == "Nies"
        assert g.reference_name("Godspeed Grusader Platina", "Light", "God") == "Godspeed Crusader Platina"
        assert g.reference_name("Kane", "Earth", "Human") == "Kane (Earth)"       # element decides
        assert g.reference_name("Rimuru", "Water", "Demon") is None              # two equal matches
        assert g.reference_name("wee", "Water", None) is None                    # junk stays as read
        assert g.reference_name("Troll", "Earth", "Giant") is None               # not on the site


def test_adopt_renames_keeps_manual_and_aliases_and_targets():
    with tempfile.TemporaryDirectory() as d:
        g = gsc(d)
        r = UnitRoster(d)
        r.apply_scan([ob("Clyde, the Crimson Sword God", "Fire", clears=7),
                      ob("Awoken Priscilla", "Fire")], "units_list")
        r.correct_name("Awoken Priscilla", "My Priscilla")           # you typed this: kept
        c = Compendium(r)
        c.set_target("Clyde, the Crimson Sword God", 50)
        r.rename_listeners.append(c.rename)
        done = r.adopt_reference_names(g.reference_name)
        assert done == [("Clyde, the Crimson Sword God", "Clyde")]
        assert "Clyde" in r.units and r.units["Clyde"]["name_status"] == "reference"
        assert r.units["Clyde"]["read_as"] == "Clyde, the Crimson Sword God"
        assert r.value(r.units["Clyde"], "quest_clears") == 7
        assert "My Priscilla" in r.units
        assert r.aliases["Clyde, the Crimson Sword God"] == "Clyde"
        assert c.target_of("Clyde") == (50, "unit")
        log = (Path(d) / "units" / "renames.jsonl").read_text(encoding="utf-8")
        assert '"to": "Clyde"' in log
        assert r.adopt_reference_names(g.reference_name) == []    # repeatable
        # history follows the rename: the next scan's change is counted on "Clyde"
        r.apply_scan([ob("Clyde, the Crimson Sword God", "Fire", clears=9)], "units_list")
        assert r.value(r.units["Clyde"], "quest_clears") == 9 and len(r.units) == 2


def test_new_reading_filed_under_reference_name():
    with tempfile.TemporaryDirectory() as d:
        g = gsc(d)
        r = UnitRoster(d)
        r.reference = g.reference_name
        s = r.apply_scan([ob("Clyde,the Crimson Swrd God", "Fire")], "units_list")
        assert list(r.units) == ["Clyde"] and s["new"] == ["Clyde"]
        assert r.units["Clyde"]["name_status"] == "reference"
        r.apply_scan([ob("Clyde the Crimson Sword God", "Fire", clears=4)], "units_list")
        assert list(r.units) == ["Clyde"] and r.value(r.units["Clyde"], "quest_clears") == 4
        r.apply_scan([ob("Troll", "Earth", "Giant")], "units_list")    # no reference: as read
        assert "Troll" in r.units


def test_race_and_element_from_reference():
    with tempfile.TemporaryDirectory() as d:
        g = gsc(d)
        r = UnitRoster(d)
        r.apply_scan([ob("Awoken Priscilla", "Fire", "(men"),
                      {"name": "IDivine ConquronGediNies SF", "name_conf": 90, "fields": {
                          "element": {"value": "Water", "confidence": 40}}},   # uncertain element
                      ob("Weaver", "Fire", "Spirit")], "units_list")          # same name, other element
        r.set_field("Weaver", "race", "Ghost")                                  # typed by you
        r.reference_facts = g.unit_facts
        r.adopt_reference_names(g.reference_name)
        p = r.units["Priscilla"]["fields"]
        assert p["race"]["value"] == "Human" and p["race"]["status"] == "reference" and p["race"]["read"] == "(men"
        n = r.units["Nies"]["fields"]
        assert n["element"]["value"] == "Water" and n["element"]["status"] == "reference"
        assert n["race"]["value"] == "God"
        w = r.units["Weaver"]["fields"]
        assert w["element"]["value"] == "Fire" and w["race"]["value"] == "Ghost"   # left alone
        # a later scan's misread race does not replace the reference one
        r.apply_scan([ob("Awoken Priscilla", "Fire", "Hman")], "units_list")
        assert r.units["Priscilla"]["fields"]["race"]["value"] == "Human"


def test_clash_is_left_alone():
    with tempfile.TemporaryDirectory() as d:
        g = gsc(d)
        r = UnitRoster(d)
        r.apply_scan([ob("Clyde", "Fire"), ob("Clyde, the Crimson Sword God", "Fire")], "units_list")
        assert r.adopt_reference_names(g.reference_name) == []
        assert set(r.units) == {"Clyde", "Clyde, the Crimson Sword God"}


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
