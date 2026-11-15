"""Check gsc_app/calc.py against the live site.

The site's own calculator is run in a browser tab on random teams (the JS in
tools/calc_oracle.js); it answers with a short fingerprint per team.  This file builds the
same random teams (same random numbers, same order), runs the Python port and compares
fingerprints.

    py -m gsc_app.calc_check SEED START "<fingerprints from the browser>"
    py -m gsc_app.calc_check SEED N          # show scenario N in full (to debug a mismatch)
"""
from __future__ import annotations

import sys
from pathlib import Path

from . import calc

KINDS = ["skill", "arts", "trueArts", "superArts", "crossArts", "phantomBullet", "originBullet",
         "protagonize", "superEquip"]
ELS = ["Fire", "Water", "Earth", "Light", "Dark"]
RACES = ["Human", "Demon", "God", "Spirit", "Machine", "Dragon", "Beast", "Giant"]
TK = ["atk", "atkFlat", "dmg", "critDmg", "res", "defDown", "ignoreDef", "criRate",
      "superCriRate", "multAdd", "multFactor"]


class Rng:
    def __init__(self, seed: int):
        self.s = seed & 0xFFFFFFFF

    def rnd(self) -> float:
        self.s = (self.s * 1664525 + 1013904223) & 0xFFFFFFFF
        return self.s / 4294967296

    def ri(self, n: int) -> int:
        return int(self.rnd() * n)

    def pick(self, a):
        return a[self.ri(len(a))]


def fx(x) -> str:
    return f"{float(x):.6f}"


def canon(r: dict) -> str:
    parts = [fx(r["result"]["final"]), fx(r["expected"]), str(r["result"]["dealt"]),
             str(r["result"]["shown"]), fx(r["rates"]["criRate"]), fx(r["rates"]["superCriRate"]),
             r["hitType"], *[fx(r["terms"][k]) for k in TK]]
    parts += [f"{k}={v}" for k, v in sorted(r["status"].items(), key=lambda kv: kv[0])]
    parts.append("true" if r["negated"] else "false")
    return "|".join(parts)


def fnv(s: str) -> int:
    h = 2166136261
    for ch in s:
        h ^= ord(ch)
        h = (h * 16777619) & 0xFFFFFFFF
    return h


def scenarios(data: calc.CalcData, seed: int, upto: int):
    """Yield (n, scenario) for n in 0..upto-1, advancing the random numbers like the JS does."""
    g = Rng(seed)
    rnd, ri, pick = g.rnd, g.ri, g.pick
    eqs = list(data.equips.values())   # same order as the site's calc-equips.json
    units = data.unit_list
    usable = [u for u in units if any((u.get("hits") or {}).get(k) for k in KINDS)]
    for n in range(upto):
        size = 1 + ri(4)
        pos = [0, 1, 2, 3]
        for i in range(3, 0, -1):
            j = ri(i + 1)
            pos[i], pos[j] = pos[j], pos[i]
        pos = pos[:size]
        specs = [None, None, None, None]
        for i in pos:
            u = pick(usable)
            active = {}
            for m in u.get("moves") or []:
                if rnd() < 0.5:
                    active[m] = True
            stacks = {}
            for e in calc.J(u)["list"]:
                if rnd() < 0.6:
                    stacks[e["id"]] = 1 + ri(e["max"])
            dream = pick(u["dream"]) if (u.get("dream") and rnd() < 0.5) else None
            equips = []
            for sl in u.get("slots") or []:
                if rnd() < 0.35:
                    equips.append(None)
                    continue
                c = [e for e in eqs if e["type"] in sl["types"] and e["star"] <= sl["star"]]
                if not c:
                    equips.append(None)
                    continue
                e = pick(c)
                row = {"id": e["id"]}
                if rnd() < 0.3:
                    row["on"] = False
                if any(f.get("target") == "target" for f in e["effects"]) and rnd() < 0.6:
                    row["to"] = pick(pos)
                equips.append(row)
            specs[i] = {"id": u["id"], "active": active, "stacks": stacks, "dream": dream,
                        "equips": equips}
        if rnd() < 0.6:
            specs[pick(pos)]["leader"] = True
        att = pick(pos)
        au = data.units[specs[att]["id"]]
        dream = specs[att]["dream"]
        roll = rnd()
        aeq = [e for e in (specs[att]["equips"] or []) if e and data.equips[e["id"]].get("hit")]
        if roll < 0.15 and aeq:
            e = pick(aeq)
            q = data.equips[e["id"]]
            el = au["element"] if q["hit"]["element"] == "user" else q["hit"]["element"]
            hit = {"kind": "equip", "equipId": q["id"], "multiplier": q["hit"]["multiplier"],
                   "element": el or None, "dmgType": q["hit"]["dmgType"]}
        elif roll < 0.3:
            first = next(iter((au.get("hits") or {}).values()), None)
            dt = (first[0].get("dmgType") if first else None) or "PHY"
            hit = {"kind": "normal", "equipId": None, "multiplier": 100,
                   "element": au["element"], "dmgType": dt}
        else:
            kinds = [k for k in KINDS if (au.get("hits") or {}).get(k)]
            kind = pick(kinds)
            ov = (au.get("dreamHits") or {}).get(dream) if dream else None
            lst = calc.apply_hit_overrides(kind, au["hits"][kind], ov)
            h = pick(lst)
            hit = {"kind": kind, "equipId": None, "multiplier": h["multiplier"],
                   "element": h.get("element") or None, "dmgType": h["dmgType"]}
        if rnd() < 0.6:
            e = pick(data.enemies)
            half = rnd() < 0.5
            if half:
                st = list(e.get("statusOn") or [])
            else:
                st = [k for k in (e.get("while") or {}) if rnd() < 0.5]
            res = 0 if rnd() < 0.5 else ri(60) - 20
            enemy = {"id": e["id"], "element": e["element"], "race": e["race"],
                     "def": e.get("def") or 0, "res": res, "broken": rnd() < 0.3, "status": st,
                     "resBy": e.get("resBy"), "negates": e.get("negates"),
                     "while": e.get("while"), "cri": e.get("cri")}
        else:
            el = "" if rnd() < 0.2 else pick(ELS)
            rc = "" if rnd() < 0.2 else pick(RACES)
            enemy = {"id": "", "element": el, "race": rc, "def": ri(4000), "res": ri(80) - 30,
                     "broken": rnd() < 0.3, "status": []}
        atk = 1000 + ri(9000)
        extra = {"atk": ri(80) if rnd() < 0.4 else 0, "dmg": ri(100) if rnd() < 0.4 else 0,
                 "critDmg": ri(80) if rnd() < 0.3 else 0, "res": ri(40) if rnd() < 0.3 else 0,
                 "ignoreDef": ri(60) if rnd() < 0.3 else 0,
                 "criRate": ri(120) if rnd() < 0.4 else 0}
        crit = pick(["auto", "auto", "none", "crit", "super"])
        crest = None
        crest_spec = None
        if rnd() < 0.5:
            c = pick(data.crest_list)
            li = ri(len(c["lv"]))
            crest_spec = {"id": c["id"], "lv": li}
            crest = data.crest_fx(c["id"], li)
        team = data.team(specs)
        enemy_in = {k: v for k, v in enemy.items() if k != "id"}
        enemy_in.setdefault("status", [])

        def call(ov, team=team, att=att, hit=hit, enemy_in=enemy_in, atk=atk, extra=extra,
                 crit=crit, crest=crest):
            return calc.calculate(team, att, hit, enemy_in, atk, extra, crit, ov, crest)

        r = call({})
        ovr = {}
        if rnd() < 0.4 and r["mods"]:
            for _ in range(3):
                k_ = pick(r["mods"])["key"]   # JS evaluates the key before the value
                ovr[k_] = rnd() < 0.5
            r = call(ovr)
        yield n, {"specs": specs, "att": att, "hit": hit, "enemy": enemy, "atkBase": atk,
                  "extra": extra, "crit": crit, "crest": crest_spec, "ov": ovr}, r, team


def main(argv):
    seed, a = int(argv[1]), int(argv[2])
    data = calc.CalcData(Path(__file__).resolve().parents[1] / "data" / "gscompanion")
    if len(argv) >= 4:   # compare against the browser's fingerprints
        want = {}
        for tok in argv[3].split():
            n, h, fin = tok.split(":", 2) if tok.count(":") >= 2 else (tok.split(":")[0], "", "")
            want[int(n)] = (h, fin)
        bad = []
        total = 0
        for n, _spec, r, _team in scenarios(data, seed, a + len(want)):
            if n < a:
                continue
            total += 1
            h = format(fnv(canon(r)), "x")
            if want.get(n, ("", ""))[0] != h:
                bad.append((n, want.get(n), h, f"{r['result']['final']:.3f}"))
        print(f"{total - len(bad)}/{total} match")
        for b in bad[:20]:
            print("MISMATCH", b)
    else:
        for n, spec, r, _team in scenarios(data, seed, a + 1):
            if n == a:
                import json
                print(json.dumps(spec, default=str)[:3000])
                print(canon(r))


if __name__ == "__main__":
    main(sys.argv)


def digest(data, seed: int, count: int) -> str:
    """One fingerprint for `count` teams: matches the browser's __digest(seed, count)."""
    toks = []
    for n, _spec, r, _team in scenarios(data, seed, count):
        toks.append(f"{n}:{fnv(canon(r)):x}")
    return format(fnv(" ".join(toks)), "x")


def aps_digest(data, seed: int, count: int) -> str:
    """Same teams, but the arts gauge per second (browser: __digest(seed, count, 'aps'))."""
    toks = []
    for n, _spec, _r, team in scenarios(data, seed, count):
        g = calc.arts_gen(team)
        parts = [fx(g["team"])] + [f"{k}={fx(g['units'][k])}:{'null' if g['hp'][k] is None else g['hp'][k]}"
                                    for k in sorted(g["units"])]
        toks.append(f"{n}:{fnv('|'.join(parts)):x}")
    return format(fnv(" ".join(toks)), "x")
