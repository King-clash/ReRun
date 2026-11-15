"""The team + damage setup behind the Team & Damage page: what is in each slot, who attacks
with what, the enemy, the crest, and every edit you can make (add / move / remove a unit,
leader, move toggles, stacks, dream, equips, hit choice ...).  It mirrors the state and rules
of gscompanion.com's calculator, so the link it makes opens the exact same setup there and
a link from the site loads here.  No windows in here: the page just calls these methods.
"""
from __future__ import annotations

import base64
import copy
import json
import re
import zlib

from . import calc
from .calc import CalcData

KIND_ORDER = ["skill", "arts", "trueArts", "superArts", "crossArts", "phantomBullet",
              "originBullet", "protagonize", "superEquip", "normal"]
MOVE_SHORT = {"skill": "S", "arts": "NA", "trueArts": "TA", "superArts": "SA", "crossArts": "CA",
              "phantomBullet": "PB", "originBullet": "OB", "protagonize": "PR",
              "superEquip": "SE"}
CRITS = ["auto", "none", "crit", "super"]
SLOTS = 4
# the site's preset dictionary for share links (it makes links short)
_DICT = ('{"slots":[{"id":1,"active":{"skill":true,"arts":true,"trueArts":true,"superArts":'
         'true,"crossArts":true,"phantomBullet":true,"originBullet":true,"protagonize":true,'
         '"superEquip":true},"equips":[{"id":1,"on":false},null],"stacks":{"0":2},"leader":true}'
         ',null],"saved":"","atk":0,"hit":{"kind":"arts","idx":0},"mult":0,"hitEl":"","hitType":'
         '"PHY","base":{"unit":0,"tasmon":0,"equip":0,"crest":0},"enemy":{"id":"","element":"",'
         '"race":"","def":0,"res":0,"broken":false},"extra":{"atk":0,"dmg":0,"critDmg":0,"res":0,'
         '"ignoreDef":0,"criRate":0},"crit":"auto","ov":{}}').encode("utf-8")
SITE = "https://gscompanion.com"


def encode_state(state: dict) -> str:
    """The site's share-link code ('~' + deflate with its dictionary, base64url)."""
    c = zlib.compressobj(9, zlib.DEFLATED, -15, zdict=_DICT)
    raw = c.compress(json.dumps(state, separators=(",", ":"), ensure_ascii=False)
                     .encode("utf-8")) + c.flush()
    return "~" + base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_state(code: str) -> dict | None:
    """The state inside a share-link code (or a whole link); None when it isn't one."""
    code = code.strip()
    if "#" in code:
        code = code.split("#", 1)[1]
    m = re.search(r"~[A-Za-z0-9_-]+", code)
    if not m:
        return None
    raw = m.group(0)[1:]
    try:
        data = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
        d = zlib.decompressobj(-15, zdict=_DICT)
        return json.loads((d.decompress(data) + d.flush()).decode("utf-8"))
    except (ValueError, zlib.error):
        return None


def fresh_state() -> dict:   # j()
    return {"slots": [None] * SLOTS, "atk": 0, "hit": None, "mult": 0, "hitEl": "",
            "hitType": "PHY", "base": {"unit": 0, "tasmon": 0, "equip": 0, "crest": 0},
            "crest": {"id": 0, "lv": 0},
            "enemy": {"id": "", "element": "", "race": "", "def": 0, "res": 0,
                      "broken": False, "status": []},
            "extra": {"atk": 0, "dmg": 0, "critDmg": 0, "res": 0, "ignoreDef": 0, "criRate": 0},
            "crit": "auto", "ov": {}, "saved": ""}


def _fits(equip: dict, slot: dict | None) -> bool:   # save-team s()
    return bool(slot) and equip["type"] in slot["types"] and equip["star"] <= slot["star"]


class CalcModel:
    def __init__(self, data: CalcData):
        self.data = data
        self.s = fresh_state()

    # ------------------------------------------------------------------ reading the setup
    def unit(self, i: int | None = None):
        i = self.s["atk"] if i is None else i
        slot = self.s["slots"][i] if 0 <= i < SLOTS else None
        return self.data.units.get(slot["id"]) if slot else None

    def equips_of(self, i: int) -> list[dict]:   # p(slot)
        slot = self.s["slots"][i]
        out = []
        for e in (slot or {}).get("equips") or []:
            if e and e.get("id") in self.data.equips:
                row = {"equip": self.data.equips[e["id"]], "on": e.get("on") is not False}
                if isinstance(e.get("to"), int) and not isinstance(e.get("to"), bool):
                    row["to"] = e["to"]
                out.append(row)
        return out

    def leader(self) -> int:   # F()
        for i, e in enumerate(self.s["slots"]):
            if e and e.get("leader"):
                return i
        return 0

    def equip_atk(self, i: int) -> int:   # P()
        return sum(r["equip"].get("atk") or 0 for r in self.equips_of(i))

    def team(self) -> list:   # he()
        out = []
        for i, e in enumerate(self.s["slots"]):
            if not e or e["id"] not in self.data.units:
                out.append(None)
                continue
            out.append({"unit": self.data.units[e["id"]], "active": e.get("active") or {},
                        "stacks": e.get("stacks") or {}, "leader": bool(e.get("leader")),
                        "dream": e.get("dream"), "equips": self.equips_of(i)})
        return out

    # ------------------------------------------------------------------ hits
    def hits(self) -> list[dict]:   # I(unit)
        u = self.unit()
        if not u:
            return []
        slot = self.s["slots"][self.s["atk"]]
        out = []
        for kind in KIND_ORDER:
            if kind == "normal":
                for r in self.equips_of(self.s["atk"]):
                    q = r["equip"]
                    if q.get("hit"):
                        el = u["element"] if q["hit"]["element"] == "user" else q["hit"]["element"]
                        out.append({"kind": "equip", "idx": q["id"], "name": q["name"],
                                    "multiplier": q["hit"]["multiplier"], "element": el,
                                    "dmgType": q["hit"]["dmgType"], "context": q.get("skill")})
                first = next(iter((u.get("hits") or {}).values()), None)
                dt = (first[0].get("dmgType") if first else None) or "PHY"
                out.append({"kind": "normal", "idx": 0, "multiplier": 100,
                            "element": u["element"], "dmgType": dt, "context": ""})
            else:
                ov = ((u.get("dreamHits") or {}).get(slot.get("dream"))
                      if slot.get("dream") else None)
                for i, h in enumerate(calc.apply_hit_overrides(
                        kind, (u.get("hits") or {}).get(kind) or [], ov)):
                    out.append({"kind": kind, "idx": i, **h})
        return out

    @staticmethod
    def custom_equip_hit(u: dict) -> dict:   # L()
        return {"kind": "equip", "idx": 0, "multiplier": 10000, "element": u["element"],
                "dmgType": "PHY", "context": ""}

    def find_hit(self, kind: str, idx: int):   # R()
        u = self.unit()
        if not u:
            return None
        if kind == "equip" and idx == 0:
            return self.custom_equip_hit(u)
        return next((h for h in self.hits() if h["kind"] == kind and h["idx"] == idx), None)

    def best_hit(self):   # B()
        hs = self.hits()
        if not hs:
            return None
        pool = [h for h in hs if h["kind"] not in ("skill", "trueWeapon", "equip", "normal")]
        pool = pool or hs
        best = pool[0]
        for h in pool[1:]:
            if h["multiplier"] > best["multiplier"]:
                best = h
        return best

    def hit_label(self, h: dict) -> str:   # z()
        if h["kind"] == "equip":
            if h.get("name"):
                return h["name"]
            eq = self.data.equips.get(h["idx"])
            return (eq or {}).get("name") or "Custom equip"
        n = calc.HITKIND.get(h["kind"], h["kind"])
        return f"{n} · {h['idx'] + 1}" if h["idx"] else n

    def pick_hit(self, h: dict | None):   # V()
        if not h:
            return
        self.s["hit"] = {"kind": h["kind"], "idx": h["idx"]}
        self.s["mult"] = h["multiplier"]
        self.s["hitEl"] = h.get("element") or ""
        self.s["hitType"] = h["dmgType"]

    def select_hit(self, kind: str, idx: int):
        self.pick_hit(self.find_hit(kind, idx))

    # ------------------------------------------------------------------ edits
    def set_attacker(self, i: int):   # H()
        self.s["atk"] = i
        u = self.unit()
        if not u:
            self.s["hit"] = None
            return
        self.s["base"]["unit"] = u["atk"]
        self.s["base"]["tasmon"] = u["tasmon"]
        if self.equips_of(i):
            self.s["base"]["equip"] = self.equip_atk(i)
        self.pick_hit(self.best_hit())

    def add_unit(self, i: int, unit_id: int):   # De()
        u = self.data.units.get(unit_id)
        if not u or not 0 <= i < SLOTS:
            return
        active = {k: True for k in ("arts", "trueArts", "superArts") if k in (u.get("moves") or [])}
        self.s["slots"][i] = {"id": u["id"], "active": active}
        if i == self.s["atk"] or not self.unit():
            self.set_attacker(i)

    def remove_unit(self, i: int):
        was = i == self.s["atk"]
        self.s["slots"][i] = None
        if was:
            first = next((k for k, e in enumerate(self.s["slots"]) if e), 0)
            self.set_attacker(max(0, first))

    def set_leader(self, i: int):
        if i == self.leader():
            return
        for e in self.s["slots"]:
            if e:
                e.pop("leader", None)
        if i > 0 and self.s["slots"][i]:
            self.s["slots"][i]["leader"] = True

    def move_unit(self, i: int, d: int):   # ve()
        j = i + d
        if not (0 <= j < SLOTS):
            return
        sl = self.s["slots"]
        lead = sl[self.leader()]
        sl[i], sl[j] = sl[j], sl[i]
        for e in sl:
            if e:
                e.pop("leader", None)
        r = next((k for k, e in enumerate(sl) if e is lead), -1)
        if lead and r > 0:
            sl[r]["leader"] = True
        if self.s["atk"] == i:
            self.s["atk"] = j
        elif self.s["atk"] == j:
            self.s["atk"] = i

    def toggle_move(self, i: int, kind: str):
        a = self.s["slots"][i].setdefault("active", {})
        a[kind] = not a.get(kind)

    def set_stack(self, i: int, stack_id: str, n: int):
        self.s["slots"][i].setdefault("stacks", {})[stack_id] = n

    def set_dream(self, i: int, dream: str | None):
        slot = self.s["slots"][i]
        u = self.unit(i)
        if dream and dream in (u.get("dream") or []):
            slot["dream"] = dream
        else:
            slot.pop("dream", None)
        if i == self.s["atk"] and self.s["hit"]:
            h = self.find_hit(self.s["hit"]["kind"], self.s["hit"]["idx"])
            if h:
                self.pick_hit(h)

    def can_equip(self, i: int, k: int, equip_id: int) -> bool:
        u = self.unit(i)
        eq = self.data.equips.get(equip_id)
        return bool(u and eq and k < len(u.get("slots") or []) and _fits(eq, u["slots"][k]))

    def set_equip(self, i: int, k: int, equip_id: int):   # Z() pick
        u = self.unit(i)
        slot = self.s["slots"][i]
        cur = slot.get("equips") or []
        slot["equips"] = [cur[t] if t < len(cur) else None for t in range(len(u["slots"]))]
        slot["equips"][k] = {"id": equip_id}
        self._equips_changed(i)

    def remove_equip(self, i: int, k: int):
        eqs = self.s["slots"][i].get("equips")
        if eqs and k < len(eqs):
            eqs[k] = None
        self._equips_changed(i)

    def toggle_equip(self, i: int, k: int):
        e = self.s["slots"][i]["equips"][k]
        if e.get("on") is False:
            e.pop("on", None)
        else:
            e["on"] = False

    def set_equip_target(self, i: int, k: int, to: int):
        e = self.s["slots"][i]["equips"][k]
        if to == i:
            e.pop("to", None)
        else:
            e["to"] = to

    def _equips_changed(self, i: int):   # X()
        slot = self.s["slots"][i]
        if slot.get("equips") is not None and not any(slot["equips"]):
            slot.pop("equips", None)
        if i == self.s["atk"]:
            self.s["base"]["equip"] = self.equip_atk(i)
        h = self.s["hit"]
        if (i == self.s["atk"] and h and h["kind"] == "equip" and h["idx"]
                and not any(r["equip"]["id"] == h["idx"] for r in self.equips_of(i))):
            self.pick_hit(self.best_hit())

    def set_enemy(self, enemy_id: str):   # Ce()
        e = self.data.enemy_by_id.get(enemy_id)
        en = self.s["enemy"]
        en["id"] = enemy_id if e else ""
        if e:
            en["element"], en["race"], en["def"] = e["element"], e["race"], e.get("def") or 0
        en["status"] = list(e.get("statusOn") or []) if e else []

    def clear_enemy(self):
        self.s["enemy"] = fresh_state()["enemy"]

    def toggle_status(self, status: str, on: bool):
        st = set(self.s["enemy"].get("status") or [])
        (st.add if on else st.discard)(status)
        self.s["enemy"]["status"] = sorted(st, key=lambda v: v)

    def set_crest(self, crest_id: int | None, lv_name: str | None = None):   # ye()
        c = self.data.crests.get(int(crest_id)) if crest_id else None
        if not c:
            self.s["crest"] = {"id": 0, "lv": 0}
            self.s["base"]["crest"] = 0
            return
        idx = next((i for i, lv in enumerate(c["lv"]) if lv["n"] == lv_name), -1)
        idx = idx if idx >= 0 else len(c["lv"]) - 1
        self.s["crest"] = {"id": c["id"], "lv": idx}
        self.s["base"]["crest"] = c["lv"][idx]["atk"]

    def set_crest_level(self, idx: int):
        c = self.data.crests.get(self.s["crest"]["id"])
        if c:
            self.s["crest"]["lv"] = idx
            self.s["base"]["crest"] = c["lv"][idx]["atk"]

    def set_override(self, key: str, on: bool):
        self.s["ov"][key] = bool(on)

    # ------------------------------------------------------------------ results
    def enemy_for_calc(self) -> dict:   # Se()
        en = dict(self.s["enemy"])
        e = self.data.enemy_by_id.get(en.get("id") or "")
        if e:
            en.update({"resBy": e.get("resBy"), "negates": e.get("negates"),
                       "while": e.get("while"), "cri": e.get("cri")})
        return en

    def atk_base(self) -> float:
        b = self.s["base"]
        return b["unit"] + b["tasmon"] + b["equip"] + b["crest"]

    def hit_for_calc(self) -> dict | None:   # W()
        h = self.s["hit"]
        if not h:
            return None
        return {"kind": h["kind"], "equipId": h["idx"] if h["kind"] == "equip" and h["idx"]
                else None, "multiplier": self.s["mult"], "element": self.s["hitEl"] or None,
                "dmgType": self.s["hitType"]}

    def crest_for_calc(self):   # be()
        c = self.s["crest"]
        return self.data.crest_fx(c["id"], c["lv"]) if c["id"] else None

    def calc_hit(self, hit: dict, overrides=None):
        return calc.calculate(self.team(), self.s["atk"], hit, self.enemy_for_calc(),
                              self.atk_base(), self.s["extra"], self.s["crit"],
                              self.s["ov"] if overrides is None else overrides,
                              self.crest_for_calc())

    def result(self) -> dict | None:   # G(W())
        h = self.hit_for_calc()
        if not self.unit() or not h:
            return None
        return self.calc_hit(h)

    def all_moves(self) -> list[dict]:   # Re(): every hit's damage for the table
        out = []
        for h in self.hits():
            r = self.calc_hit({"kind": h["kind"], "equipId": h["idx"] if h["kind"] == "equip"
                               and h["idx"] else None, "multiplier": h["multiplier"],
                               "element": h.get("element"), "dmgType": h["dmgType"]})
            out.append({"hit": h, "shown": r["result"]["shown"], "type": r["hitType"]})
        return out

    def team_hp(self) -> list:
        return calc.we(self.team())

    # ------------------------------------------------------------------ links / saving
    def to_link(self) -> str:
        return f"{SITE}/damage-calc/#{encode_state(self.s)}"

    def builder_link(self) -> str:
        return f"{SITE}/team-builder/#{encode_state({'slots': self.s['slots']})}"

    def state_copy(self) -> dict:
        return copy.deepcopy(self.s)

    def load(self, e: dict) -> None:   # Be()
        d = self.data
        s = fresh_state()
        self.s = s
        if isinstance(e.get("slots"), list):
            slots = []
            for t in range(SLOTS):
                n = e["slots"][t] if t < len(e["slots"]) else None
                if not n or n.get("id") not in d.units:
                    slots.append(None)
                    continue
                u = d.units[n["id"]]
                row = {"id": n["id"], "active": n.get("active") or {}}
                if n.get("stacks"):
                    row["stacks"] = n["stacks"]
                if n.get("leader"):
                    row["leader"] = True
                if n.get("dream") in (u.get("dream") or []):
                    row["dream"] = n["dream"]
                row.update(self._norm_equips(n.get("equips"), u))
                slots.append(row)
            s["slots"] = slots
        for k in ("base", "enemy", "extra"):
            if isinstance(e.get(k), dict):
                s[k].update(e[k])
        en = s["enemy"]
        if en.get("id") and en["id"] not in d.enemy_by_id:
            en["id"] = ""
        crest = e.get("crest") if isinstance(e.get("crest"), dict) else {}
        if crest.get("id") in d.crests:
            c = d.crests[crest["id"]]
            try:
                lv = int(crest.get("lv") or 0)
            except (TypeError, ValueError):
                lv = 0
            s["crest"] = {"id": c["id"], "lv": min(max(0, lv), len(c["lv"]) - 1)}
            s["base"]["crest"] = c["lv"][s["crest"]["lv"]]["atk"]
        elif s["base"].get("crest", 0) > 0:
            for c in d.crests.values():
                idx = next((i for i, lv in enumerate(c["lv"]) if lv["atk"] == s["base"]["crest"]),
                           -1)
                if idx >= 0:
                    s["crest"] = {"id": c["id"], "lv": idx}
                    break
        for k in ("crit", "ov", "mult", "hitEl", "hitType"):
            if e.get(k) is not None:
                s[k] = e[k]
        if isinstance(e.get("saved"), str):
            s["saved"] = e["saved"]
        first = max(0, next((i for i, x in enumerate(s["slots"]) if x), -1))
        atk = e.get("atk")
        if not (isinstance(atk, int) and not isinstance(atk, bool) and 0 <= atk < SLOTS
                and s["slots"][atk]):
            self.set_attacker(first)
            return
        s["atk"] = atk
        h = e.get("hit")
        r = self.find_hit(h["kind"], h["idx"]) if isinstance(h, dict) else None
        if r and e.get("mult") is not None:
            s["hit"] = h
        else:
            self.pick_hit(r or self.best_hit())
        if not e.get("base"):
            u = self.unit()
            s["base"]["unit"], s["base"]["tasmon"] = u["atk"], u["tasmon"]

    def _norm_equips(self, eqs, unit) -> dict:   # save-team d()
        n = [None] * len(unit.get("slots") or [])
        for r, e in enumerate(eqs if isinstance(eqs, list) else []):
            q = self.data.equips.get((e or {}).get("id"))
            if not q:
                continue
            o = r if (r < len(n) and not n[r] and _fits(q, unit["slots"][r])) else next(
                (k for k, x in enumerate(n) if not x and _fits(q, unit["slots"][k])), -1)
            if o >= 0:
                row = {"id": e["id"]}
                if e.get("on") is False:
                    row["on"] = False
                if isinstance(e.get("to"), int) and not isinstance(e.get("to"), bool) \
                        and 0 <= e["to"] < 4:
                    row["to"] = e["to"]
                n[o] = row
        return {"equips": n} if any(n) else {}

    def load_link(self, link: str) -> bool:
        st = decode_state(link)
        if not isinstance(st, dict):
            return False
        self.load(st)
        return True
