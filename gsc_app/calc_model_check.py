"""Check the Team & Damage setup (calc_model.py) against the site's own calculator page.

Random setups are built with the model's own edit methods, turned into share links and opened
in the real page (the browser tab on gscompanion.com/damage-calc/); the page shows the damage
and rewrites the link with its view of the setup.  Both must agree with the model.

    py -m gsc_app.calc_model_check make SEED COUNT   -> JSON with the links to open
    py -m gsc_app.calc_model_check compare FILE "<browser answers>"
Browser side: tools/calc_model_check.js
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

from . import calc
from .calc_model import CalcModel, MOVE_SHORT

DATA = Path(__file__).resolve().parents[1] / "data" / "gscompanion"


def fnv(s: str) -> str:
    h = 2166136261
    for ch in s:
        h ^= ord(ch)
        h = (h * 16777619) & 0xFFFFFFFF
    return format(h, "x")


def canon(state) -> str:
    return json.dumps(state, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def random_model(data: calc.CalcData, rng: random.Random) -> CalcModel:
    m = CalcModel(data)
    usable = [u for u in data.unit_list if u.get("hits")]
    pos = rng.sample(range(4), rng.randint(1, 4))
    for i in pos:
        m.add_unit(i, rng.choice(usable)["id"])
    for i in pos:
        u = m.unit(i)
        for k in u.get("moves") or []:
            if k in MOVE_SHORT and rng.random() < 0.5:
                m.toggle_move(i, k)
        for st in calc.J(u)["list"]:
            if rng.random() < 0.5:
                m.set_stack(i, st["id"], rng.randint(1, st["max"]))
        if u.get("dream") and rng.random() < 0.4:
            m.set_dream(i, rng.choice(u["dream"]))
        for k, sl in enumerate(u.get("slots") or []):
            if rng.random() < 0.65:
                opts = [e for e in data.equips.values()
                        if e["type"] in sl["types"] and e["star"] <= sl["star"]]
                if opts:
                    m.set_equip(i, k, rng.choice(opts)["id"])
                    if rng.random() < 0.3:
                        m.toggle_equip(i, k)
                    if any(f.get("target") == "target" for f in
                           m.data.equips[m.s["slots"][i]["equips"][k]["id"]]["effects"]) \
                            and rng.random() < 0.6:
                        m.set_equip_target(i, k, rng.choice(pos))
    if rng.random() < 0.5:
        m.set_leader(rng.choice(pos))
    if rng.random() < 0.3:
        i = rng.choice(pos)
        m.move_unit(i, rng.choice([-1, 1]))
    atk = rng.choice([i for i, e in enumerate(m.s["slots"]) if e])
    m.set_attacker(atk)
    hs = m.hits()
    if hs and rng.random() < 0.8:
        h = rng.choice(hs)
        m.select_hit(h["kind"], h["idx"])
    if rng.random() < 0.15:
        m.select_hit("equip", 0)
        m.s["mult"] = rng.choice([5000, 12000, 30000])
    if rng.random() < 0.7:
        m.set_enemy(rng.choice(data.enemies)["id"])
        for st in (data.enemy_by_id[m.s["enemy"]["id"]].get("while") or {}):
            if rng.random() < 0.5:
                m.toggle_status(st, True)
    else:
        m.s["enemy"].update({"element": rng.choice(calc.ELEMENTS + [""]),
                             "race": rng.choice(calc.RACES + [""]),
                             "def": rng.randint(0, 4000), "res": rng.randint(-30, 50)})
    m.s["enemy"]["broken"] = rng.random() < 0.3
    if rng.random() < 0.5:
        c = rng.choice(data.crest_list)
        m.set_crest(c["id"], rng.choice(c["lv"])["n"])
    for k, hi in (("atk", 80), ("dmg", 100), ("critDmg", 80), ("res", 40), ("ignoreDef", 60),
                  ("criRate", 120)):
        if rng.random() < 0.3:
            m.s["extra"][k] = rng.randint(0, hi)
    m.s["crit"] = rng.choice(["auto", "auto", "none", "crit", "super"])
    r = m.result()
    if r and r["mods"] and rng.random() < 0.4:
        for _ in range(3):
            m.set_override(rng.choice(r["mods"])["key"], rng.random() < 0.5)
    return m


def expected(m: CalcModel) -> dict:
    r = m.result()
    mods = [x for x in r["mods"] if x["relevant"]]
    return {"shown": r["result"]["shown"], "nmods": len(mods),
            "napplied": sum(1 for x in mods if r["status"].get(x["key"]) == "applied")}


def make(seed: int, count: int, out: Path):
    data = calc.CalcData(DATA)
    rng = random.Random(seed)
    items = []
    for _ in range(count):
        m = random_model(data, rng)
        link = m.to_link()
        m2 = CalcModel(data)
        m2.load_link(link)   # what the page does with it
        items.append({"link": link, "exp": expected(m2), "state": fnv(canon(m2.s))})
    out.write_text(json.dumps(items), encoding="utf-8")
    print(json.dumps([i["link"].split("#", 1)[1] for i in items]))


def compare(path: Path, answers: str):
    items = json.loads(path.read_text(encoding="utf-8"))
    got = json.loads(answers)
    bad = 0
    for n, (it, g) in enumerate(zip(items, got)):
        shown = int(str(g[0]).replace(",", "")) if str(g[0]).replace(",", "").isdigit() else None
        ok = (shown == it["exp"]["shown"] and g[1] == it["exp"]["nmods"]
              and g[2] == it["exp"]["napplied"] and g[3] == it["state"])
        if not ok:
            bad += 1
            print("MISMATCH", n, "model", it["exp"], it["state"], "page", g)
    print(f"{len(items) - bad}/{len(items)} agree")


if __name__ == "__main__":
    if sys.argv[1] == "make":
        make(int(sys.argv[2]), int(sys.argv[3]),
             Path(sys.argv[4]) if len(sys.argv) > 4 else Path("calc_model_check.json"))
    else:
        compare(Path(sys.argv[2]), sys.argv[3])
