"""Damage calculator rules, ported by hand from gscompanion.com's calculator (Python, no
JavaScript is run).  The function names in comments (f, p, x, L, K, G, Ge, Je, Xe ...) are
the site's own short names, so the two can be compared line by line.

    calculate(team, attacker, hit, enemy, atk_base, extra, crit, overrides, crest) -> dict

team      list of 4 slots, each None or
          {"unit": <calc unit>, "active": {"arts": True}, "stacks": {id: n}, "leader": bool,
           "dream": "Water" | None, "equips": [{"equip": <calc equip>, "on": True, "to": None}]}
attacker  index of the attacking slot
hit       {"kind", "equipId", "multiplier", "element", "dmgType"}
enemy     {"element", "race", "def", "res", "broken", "status", "resBy", "negates", "while",
           "cri"}
The numbers are checked against the live site on many random teams (gsc_app/test_calc.py)."""
from __future__ import annotations

import math
import re

ELEMENTS = ["Fire", "Water", "Earth", "Light", "Dark"]
RACES = ["Human", "Demon", "God", "Spirit", "Machine", "Dragon", "Beast", "Giant"]
_R = "|".join(ELEMENTS)
_I = "|".join(RACES)
I_ = re.IGNORECASE


class Obj(dict):
    """An effect row. Compared and hashed by identity, like the JS objects they mirror."""
    __hash__ = object.__hash__

    def __eq__(self, other):
        return self is other

    def __ne__(self, other):
        return self is not other


def js_round(x: float) -> int:
    return math.floor(x + 0.5)


def js_str(v) -> str:
    """JS String(v) for the values that appear in the data."""
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float) and v == int(v) and abs(v) < 1e21:
        return str(int(v))
    return str(v)


def nz(v):
    """JS `v || 0`."""
    return v if v else 0


def cap1(s: str) -> str:  # JS: charAt(0).toUpperCase() + slice(1)
    return s[:1].upper() + s[1:]


def Q(s: str) -> str:  # JS: charAt(0).toUpperCase() + slice(1).toLowerCase()
    return s[:1].upper() + s[1:].lower()


I = Q

# --------------------------------------------------------------------------- text helpers
_A = {
    "atk_up": re.compile(r"ATK", I_), "stats_up": re.compile(r"stats", I_),
    "cri_rate_up": re.compile(r"(?<!super\s)CRI(?:T|tical)?\s*rate", I_),
    "super_cri_rate_up": re.compile(r"super\s+CRI", I_),
    "cri_dmg_up": re.compile(r"CRI(?:T|tical)?\s*DMG", I_),
    "arts_dmg_up": re.compile(r"arts\W*\s*DMG", I_),
    "phys_dmg_up": re.compile(r"PHY|physical", I_), "mag_dmg_up": re.compile(r"MAG|magic", I_),
    "dmg_res_down": re.compile(r"RES", I_), "element_res_down": re.compile(r"RES", I_),
    "phys_res_down": re.compile(r"RES", I_), "mag_res_down": re.compile(r"RES", I_),
    "def_down": re.compile(r"DEF", I_),
}
_O = re.compile(r"\s\+\s|;|\.(?=\s|\Z)|\n")
_S = r"\s(?:and|&)\s(?!(?:%s|%s)\b)" % (_R, _I)
_C = re.compile(r",\s|" + _S, I_)
_L = re.compile(r",\s|" + _S + r"|\s\+\s|;|\.(?=\s|\Z)|\n", I_)
_U = re.compile(r"\b(?:increase|increases|reduce|reduces|decrease|decreases|gain|gains|grant|"
                r"grants|lower|lowers)\b", I_)


def _d(text: str, rx) -> int:
    """End index of the last match of rx in text (0 when none)."""
    n = 0
    for m in rx.finditer(text):
        n = m.start() + len(m.group(0))
    return n


def f(e: dict, t: int = 0) -> dict:
    """The part of an effect's text that talks about its value (scope) and what precedes it."""
    n = e.get("text") or ""
    r = js_str(e.get("value")).replace(".", r"\.")
    idx = [m.start() for m in re.finditer(r"(?<![\d.])" + r + "%", n)]
    if not idx:
        return {"scope": n, "pre": n}
    s = _A.get(e.get("type"))

    def f_(i):
        return _d(n[:i], _O)

    def p_(i):
        tt = f_(i)
        return tt + _d(n[tt:i], _C)

    if s and len(idx) > 1:
        hit = [i for i in idx if s.search(n[p_(i):i])]
        if hit:
            idx = hit
    m = idx[min(t, len(idx) - 1)]
    h = f_(m)
    g = p_(m)
    mm = _L.search(n[m:])
    v = n[g:(m + mm.start()) if mm else len(n)]
    ym = _U.search(n[h:])
    y = ym.start() if ym else -1
    scope = (n[h:min(h + y, g) if y >= 0 else g] + " " + v).strip()
    return {"scope": scope, "pre": n[g:m]}


def p(effects, cb):
    """forEach with the occurrence number of identical (text|type|value) effects."""
    seen: dict[str, int] = {}
    for r, e in enumerate(effects or []):
        k = f"{js_str(e.get('text'))}|{js_str(e.get('type'))}|{js_str(e.get('value'))}"
        a = seen.get(k, 0)
        seen[k] = a + 1
        cb(e, r, a)


DEBUFF = {"dmg_res_down", "phys_res_down", "mag_res_down", "element_res_down", "def_down",
          "atk_down", "cri_res_down", "break_res_down", "evasion_down", "accuracy_down",
          "action_speed_down", "inflict_ailment", "ailment_res_down", "arts_gauge_down",
          "enemy_dmg_down", "healing_taken_down", "break_bar_down"}   # m
SELFDOWN = {"self_dmg", "self_down"}                                    # h
INSTANT = {"arts_instant", "arts_quest_start", "heal_instant", "shorten_ct", "cleanse",
           "revive", "summon", "gauge_up", "gauge_down"}                # g

LABEL = {   # _
    "dmg_up": "DMG UP", "atk_up": "ATK UP", "def_up": "DEF UP", "hp_up": "HP UP",
    "stats_up": "Stats UP", "dmg_up_vs_broken": "DMG vs Broken",
    "dmg_up_conditional": "Conditional DMG UP", "phys_dmg_up": "PHY DMG UP",
    "mag_dmg_up": "MAG DMG UP", "arts_dmg_up": "Arts DMG UP",
    "super_arts_dmg_up": "Super Arts DMG UP", "equip_dmg_up": "Equip DMG UP",
    "cri_rate_up": "CRI Rate UP", "cri_dmg_up": "CRI DMG UP",
    "super_cri_rate_up": "Super CRI Rate UP", "species_killer": "Species Killer",
    "element_killer": "Element Killer", "ignore_def": "Ignore DEF",
    "break_power_up": "Break PWR UP", "max_hp_up": "Max HP UP",
    "dmg_res_down": "DMG RES DOWN", "phys_res_down": "PHY RES DOWN",
    "mag_res_down": "MAG RES DOWN", "element_res_down": "Elem RES DOWN",
    "def_down": "DEF DOWN", "atk_down": "ATK DOWN", "cri_res_down": "CRI RES DOWN",
    "break_res_down": "Break RES DOWN", "evasion_down": "Evasion DOWN",
    "accuracy_down": "Accuracy DOWN", "action_speed_down": "Action Speed DOWN",
    "inflict_ailment": "Inflict Ailment", "ailment_res_down": "Status RES DOWN",
    "arts_gauge_down": "Enemy Arts DOWN", "enemy_dmg_down": "Enemy DMG DOWN",
    "dmg_taken_down": "DMG RES UP", "phys_dmg_down": "PHY RES UP", "mag_dmg_down": "MAG RES UP",
    "element_res_up": "Elem RES UP", "barrier": "Barrier", "taunt": "Taunt",
    "reflect_dmg": "Reflect DMG", "cri_res_up": "CRI RES UP", "evasion_up": "Evasion UP",
    "accuracy_up": "Accuracy UP", "ailment_res_up": "Status RES UP", "cleanse": "Cleanse",
    "arts_regen": "Arts Gen", "arts_instant": "Instant Arts", "arts_quest_start": "Arts at Start",
    "be_output_up": "BE Output UP", "heal_instant": "Heal", "heal_regen": "Heal/s",
    "heal_rate_up": "Heal Rate UP", "healing_taken_up": "Healing Taken UP",
    "lifesteal": "Lifesteal", "revive": "Revive", "skill_ct_up": "Skill CT UP",
    "equip_ct_up": "Equip CT UP", "shorten_ct": "Shorten CT", "self_dmg": "Self DMG",
    "hellfire_res": "Hellfire RES", "multiplier_up": "Multiplier UP",
    "skill_dmg_up": "Skill DMG UP", "normal_attack_dmg_up": "Normal Attack DMG UP",
    "self_down": "Self Debuff", "healing_taken_down": "Healing Taken DOWN",
    "debuff_res_up": "Debuff RES UP", "break_bar_down": "Break Bar DOWN",
    "gauge_up": "Gauge UP", "gauge_down": "Gauge DOWN", "enter_mode": "Enter Mode",
    "duration_up": "Duration UP", "arts_floor": "Arts Floor", "knockback_res": "Knockback RES",
    "invulnerable": "Invulnerable", "survive_lethal": "Survive at 1 HP", "summon": "Summon",
    "arts_gen_up": "Arts Gen UP", "exp_up": "EXP UP", "gren_up": "Gren UP",
    "ailment_dmg_up": "Ailment DMG UP",
}
V_CRI = "CRI Rate UP + CRI RES DOWN"                                    # v

HITKIND = {   # O / Z
    "normal": "Normal Attack", "skill": "Skill", "arts": "Arts", "trueArts": "True Arts",
    "superArts": "Super Arts", "crossArts": "Cross Arts", "phantomBullet": "Phantom Bullet",
    "originBullet": "Origin Bullet", "protagonize": "Protagonize", "superEquip": "Super Equip",
    "trueWeapon": "True Weapon", "equip": "Equip",
}
SRC_O = {"skill": "Skill", "arts": "Arts", "trueArts": "True Arts", "superArts": "Super Arts",
         "crossArts": "Cross Arts", "originBullet": "Origin Bullet",
         "phantomBullet": "Phantom Bullet"}


def title(e: str) -> str:   # y
    return re.sub(r"\b\w", lambda m: m.group(0).upper(), e.replace("_", " "))


def b(e: str) -> str:
    """Readable label of a condition."""
    if not e:
        return ""
    if e == "not:is_leader":
        return "not Leader"
    if "+" in e:
        return ", ".join(b(x) for x in e.split("+"))
    if e.startswith("not:"):
        return f"unless {b(e[4:])}"
    t, *n = e.split(":")
    r = ":".join(n)
    i = {
        "boss_broken": "enemy in Break", "boss_not_broken": "enemy not in Break",
        "is_leader": "is Leader", "hp_full": "own HP full", "low_hp": "own HP low",
        "vs_low_hp": "enemy HP low", "high_hp": "own HP high", "vs_high_hp": "enemy HP high",
        "next_use": "next use only", "daily_element": "today's element",
        "elemental_advantage": "elemental advantage", "vs_giant_boss": "vs Giant Boss",
        "vs_raid_boss": "vs Raid Boss", "vs_boss": "vs bosses",
        "vs_non_boss": "vs non-Boss enemies", "near_death": "near death",
        "on_lethal_damage": "on lethal DMG", "no_status_ailment": "no status ailments",
        "on_crit": "on crit", "quest_start": "quest start", "when_hit": "when hit",
        "has_barrier": "under a Barrier", "enemy_casting": "while the enemy uses Arts",
        "ally_taunting": "while an ally redirects DMG", "sp_art": "with SP Art",
        "counterattack": "Counterattack only", "conditional": "conditional",
        "equip_set": "with the full equip set",
    }
    if e in i:
        return i[e]
    if t == "ally_hp":
        try:
            return f"{int(float(r)):,}+ HP"
        except ValueError:
            return r
    if t == "hp_range":
        a, c = (r.split(":") + [""])[:2]
        return f"own HP {a}–{c}%"
    if t == "holder":
        a, c = (r.split(":") + [""])[:2]
        return "on its own unit" if a == "unit" else f"if held by a {c.replace('/', ' or ')} unit"
    if t == "after_move":
        return f"right after {HITKIND.get(r, r)}"
    if t == "ally_hp_above":
        return f"allies above {r}% HP"
    if t == "ally_hp_below":
        return f"allies below {r}% HP"
    if t == "hp_above":
        return f"own HP ≥{r}%"
    if t == "hp_below":
        return f"own HP <{r}%"
    if t == "vs_hp_below":
        return f"enemy ≤{r}% HP"
    if t == "vs_hp_above":
        return f"enemy ≥{r}% HP"
    if t == "first_uses":
        return "first use" if r == "1" else f"first {r} uses"
    if t == "nth_use":
        return f"use {r} only"
    if t == "from_use":
        return f"from use {r} on"
    if t == "arts_below":
        return f"own Arts <{r}"
    if t == "arts_min":
        return f"Arts ≥{r} when used"
    if t == "arts_max":
        return f"Arts ≤{r} when used"
    if t == "own_element":
        return f"if own element is {r}"
    if t == "with_race":
        return f"with a {r} in party"
    if t == "in_area":
        return f"in {r} area"
    if t == "quest_window":
        return f"first {r}s of the quest"
    if t in ("vs_race", "vs_element"):
        return f"vs {r}"
    if t == "hit":
        return f"{r} hits only"
    if t == "vs_ailment":
        return "enemy has an ailment" if r == "any" else f"enemy has {r}"
    if t == "vs_bleed":
        return "enemy Bleeding" if r == "1" else f"enemy Bleed Lv{r}+"
    if t == "on_inflict":
        return f"if it inflicts {r}"
    if t == "self_ailment":
        return f"while own {r}"
    if t == "in_mode":
        return f"in {title(r)}"
    if t == "with_unit":
        return f"with {r} in party"
    if t == "mode_slot":
        return f"position {r}"
    if t == "summon_present":
        return f"while a {r} is present"
    if t == "counter":
        a, *rest = n
        if a == "full":
            return f"{':'.join(rest)} full"
        if a == "max":
            return f"{':'.join(rest)} at max"
        return f"at {a} {':'.join(rest)}"
    return e.replace("_", " ")


# --------------------------------------------------------------------------- conditions
def S(e: dict) -> bool:
    return any(x.get("type") == "taunt" for x in (e.get("effects") or []))


def x(e, t, n, r=0):
    """Condition truth for a unit in slot n: True / False / None (unknown)."""
    if not e:
        return None
    if "+" in e:
        i = [x(c, t, n, r) for c in e.split("+")]
        if any(v is False for v in i):
            return False
        return True if all(v is True for v in i) else None
    if e.startswith("not:"):
        i = x(e[4:], t, n, r)
        return None if i is None else (not i)
    if e == "is_leader":
        return n == r
    if e.startswith("with_unit:"):
        want = e[10:].lower()

        def nm(s):
            return re.sub(r"\s*\([^)]*\)$", "", s.lower())

        return any(u and idx != n and (nm(u["name"]) == want or any(
            a.lower() == want for a in (u.get("aliases") or []))) for idx, u in enumerate(t))
    if e.startswith("with_race:"):
        return any(u and idx != n and u.get("race") == e[10:] for idx, u in enumerate(t))
    if e.startswith("mode_slot:"):
        try:
            k = float(e[10:]) - 1
        except ValueError:
            k = float("nan")
        if n == k:
            return True
        return None if n == 3 else False
    if e == "ally_taunting":
        return None if any(u and idx != n and S(u) for idx, u in enumerate(t)) else False
    return None


_C_ = f"{_R}|{_I}|Female|Male"
_W = re.compile(
    r"\bif\s+(?:the\s+)?(?:user|equipper)\s+is\s+(not\s+)?(?:an?\s+)?((?:%s)(?:\s*(?:,|or|and|&)"
    r"\s*(?:%s))*)|\bif\s+(%s)(?:\s+(?:unit|elemental|type))?\s*," % (_C_, _C_, _C_), I_)


def T(e: str):
    t = _W.search(e)
    if not t:
        return None
    return {"not": bool(t.group(1)),
            "list": [I(s) for s in re.split(r"\s*(?:,|or|and|&)\s*", t.group(2) or t.group(3),
                                           flags=I_) if s]}


def E(e, t, n):
    if not n:
        return None
    m = re.search(r"\bwhen equipped by ([^,.]+?)\s*(?:,|\.|$)", e.get("text") or "", I_)
    r = m.group(1) if m else None
    if r:
        low = r.lower()
        names = [n.get("name"), n.get("fullName"), *(n.get("aliases") or [])]
        return {"met": any(s and s.lower() == low for s in names), "label": f"on {r}"}
    i = T(t) or T(e.get("text") or "")
    if i:
        has = any(n.get("element") == v or n.get("race") == v or n.get("gender") == v
                  for v in i["list"])
        return {"met": has != i["not"], "label": f"user is {'not ' if i['not'] else ''}"
                                                 f"{'/'.join(i['list'])}"}
    return None


def D(e: str, t) -> bool:
    """holder:* condition against the unit holding the equip."""
    if e.startswith("not:"):
        return not D(e[4:], t)
    parts = e.split(":")
    n = parts[1] if len(parts) > 1 else None
    r = parts[2] if len(parts) > 2 else None
    if not t or not r:
        return False
    i = r.split("/")
    if n == "element":
        return t.get("element") in i
    if n == "race":
        return t.get("race") in i
    if n == "unit":
        return any(str(t.get("base")) == v for v in i)
    return n == "gender" and t.get("gender") in i


KILLERS = {"species_killer", "element_killer", "element_res_down", "element_res_up"}   # k


def A(e: dict) -> str:
    m = re.search(r"(?:element|race|ailment):([\w/]+)", e.get("note") or "")
    if m:
        return re.sub(r"(^|/)\w", lambda mm: mm.group(0).upper(), m.group(1))
    if e.get("type") not in KILLERS:
        return ""
    n = re.search(r"\b(Fire|Water|Earth|Light|Dark|Human|Demon|God|Spirit|Machine|Dragon|"
                  r"Beast|Giant)\b", e.get("text") or "")
    return n.group(1) if n else ""


def j(e: dict) -> str:
    mv = e.get("moves")
    if not mv:
        return ""
    return "Arts" if len(mv) >= 7 else "/".join(HITKIND.get(m, m) for m in mv)


def M(e: dict) -> str:
    t = e.get("type")
    if t == "multiplier_up":
        return HITKIND.get(e.get("move"), "") or ""
    if t in ("gauge_up", "gauge_down", "enter_mode"):
        return re.sub(r"^\w+:", "", e.get("note") or "")
    return " · ".join(v for v in (A(e), j(e)) if v)


def N(e: dict) -> str:
    t = e.get("target") or "self"
    if t in ("self", "enemies"):
        return "self"
    if t == "allies":
        return "team"
    if t == "target":
        return "team" if e.get("toSlot") is None else f"slot:{e['toSlot']}"
    return t


def ee(e: dict) -> str:
    if e.get("condition") == "conditional":
        return f"conditional:{e.get('text') or ''}"
    return e.get("condition") or ""


def P(e: dict) -> str:
    t = f":{e.get('valueKind')}" if e.get("type") == "multiplier_up" else (
        ":flat" if e.get("valueKind") == "flat" else "")
    n = f"{e.get('type')}:{M(e)}{t}"
    r = f"|eq:{e['equipId']}" if e.get("equipId") and e.get("type") != "dmg_res_down" else ""
    return (n if e.get("type") in DEBUFF else f"{n}|{N(e)}|{ee(e)}") + r


ALL_APPLY = {"EX1", "EX3", "Passive"}   # F


def te(e):
    return {"allApply": e in ALL_APPLY, "perUnit": e == "EX2"}


SIDES = {"right", "left", "sides"}   # ne


def L(e, t, n, r, i=0):
    """Does effect e (cast by slot t) reach the unit in slot n?"""
    a = e.get("target") or "self"
    for ex in e.get("except") or []:
        if ex == "leader":
            if n == i:
                return False
            continue
        k, v = (ex.split(":") + [""])[:2]
        if ((r.get("race") if k == "race" else r.get("element")) == v):
            return False
    if a in ("self", "enemies"):
        return t == n
    if a == "target":
        to = e.get("toSlot")
        to = t if to is None else to
        return n == to and (not e.get("targetIf") or L({"target": e["targetIf"]}, t, n, r, i))
    if a == "allies":
        return t != n or (not e.get("exceptSelf") and not re.search(
            r"\(?except\s+(?:own\s*)?self\)?|other allies", e.get("text") or "", I_))
    if a == "leader":
        return n == i
    if a == "right":
        return n == t + 1
    if a == "left":
        return n == t - 1
    if a == "sides":
        return abs(n - t) == 1
    if a == "taunter":
        return n != t and S(r)
    o, _, s = a.partition(":")
    if o == "group":
        return bool(re.search(r"\b%s\b" % s, r.get("name") or "", I_))
    if o == "unit":
        return any(str(r.get("base")) == v for v in s.split("/"))
    if o == "gender":
        return r.get("gender") == s
    if o not in ("element", "race"):
        return False
    return (r.get("race") if o == "race" else r.get("element")) in s.split("/")


# --------------------------------------------------------------------------- stacking
def B(e) -> float:
    return min(e["value"], e["cap"]) if e.get("cap") else e["value"]


def V(e) -> float:
    s = 0
    for t in e:
        s += B(t)
    return s


def H(e):
    s = e.get("slot")
    if s is None:
        s = e.get("unitIdx")
    return "" if s is None else s


def U(e, t):
    n: dict = {}
    for r in e:
        k = t(r)
        n.setdefault(k, []).append(r)
    return n


def W(e) -> str:
    eq = e.get("equipId")
    dr = e.get("dream")
    return f"{H(e)}|{e.get('source')}|{'' if eq is None else eq}|{'' if dr is None else dr}"


def G(e) -> set:
    """Effects that lose to a stronger effect of the same stack group."""
    t: set = set()
    n = U([v for v in e if (v.get("stackGroup") or 0) > 0 and v.get("value") is not None],
          lambda v: f"{v['stackGroup']}|{'p' if v.get('stackPassive') else ''}")
    for grp in n.values():
        groups = list(U(grp, W).values())
        if len(groups) < 2:
            continue

        def order(g):
            return max((v.get("stackOrder") or 0) for v in g)

        best = groups[0]
        for g in groups:
            if g is groups[0]:
                # reduce starts with the first element as accumulator; compare from the 2nd
                continue
            if order(g) > order(best) or (order(g) == order(best) and V(g) > V(best)):
                best = g
        for g in groups:
            if g is not best:
                for v in g:
                    t.add(v)
    return t


VE = {"passive", "trueWeapon", "dream"}   # ve


def K(e, strongestOnly=False, allApply=False, perUnit=False, lost=None):
    """Which of a group of effects count, and their total."""
    a = [v for v in e if v.get("value") is not None and v.get("stackGroup") is not None]
    o = [v for v in a if not (lost and v in lost)]
    s = [v for v in e if v.get("value") is not None and v.get("stackGroup") is None]
    c = [] if strongestOnly else [v for v in s if allApply or v.get("permanent")
                                  or v.get("stackable")]
    l: list = []

    def key(v):
        return f"{v.get('source')}|{v.get('text')}" if v.get("source") in VE else id(v)

    for k, t in U(c, key).items():
        n = list(U(t, H).values())
        if isinstance(k, str):
            best = n[0]
            for g in n[1:]:
                if V(g) > V(best):
                    best = g
            l.extend(best)
        else:
            l.extend(t)
    cset = set(c)
    u = [v for v in s if v not in cset]

    def d(v):
        tg = v.get("target") or ""
        return tg if re.match(r"^(?:element|race):|^leader$", tg) else "*"

    f_ = []
    for grp in U(u, lambda v: f"{H(v)}|{v.get('source')}").values():
        pick = []
        for sub in U([v for v in grp if not v.get("additional")], d).values():
            best = sub[0]
            for v in sub[1:]:
                if B(v) > B(best):
                    best = v
            pick.append(best)
        f_.append(pick + [v for v in grp if v.get("additional")])

    def pk(lists):
        if not lists:
            return []
        best = lists[0]
        for li in lists[1:]:
            if V(li) > V(best):
                best = li
        return best

    if perUnit:
        m = []
        for grp in U(f_, lambda li: H(li[0])).values():
            m.extend(pk(grp))
    else:
        m = pk(f_)
    h = [*l, *m, *o]
    g = max([0, *[v.get("cap") or 0 for v in e]]) or None
    return {
        "value": None if e[0].get("value") is None else V(h),
        "valueKind": next((v.get("valueKind") for v in e if v.get("valueKind")), None),
        "cap": g,
        "capped": any(v.get("cap") and v["value"] > v["cap"] for v in h),
        "strongestOnly": (len(f_) > 1 and not perUnit) or len(o) < len(a),
        "hasNoVal": any(v.get("value") is None for v in e),
        "list": e, "applied": set(h),
    }


_SE = re.compile(r"\(stack(?:s|able)\)|\bstackable\b|\bmax\.?\s*\d+\s*stacks\b|"
                 r"\bfor each (?:stack|count)\b|\bfor each\b[^,.]*\bcount\b", I_)
_CE = re.compile(r"\b(?:each|every) time\b|\bfor each\b(?!\s+(?:\w+\s+)?(?:ally|allies|units?|"
                 r"enemy hit|enemies hit)\b)", I_)
LE = {"arts_instant", "arts_quest_start", "heal_instant", "shorten_ct", "cleanse", "revive",
      "summon", "gauge_up", "gauge_down", "inflict_ailment", "exp_up", "gren_up", "self_dmg",
      "enter_mode", "barrier"}
UE = {"count", "stat", "hp", "max"}
DE = {"skill": "Skill", "arts": "Arts", "trueArts": "True Arts", "superArts": "Super Arts",
      "crossArts": "Cross Arts", "phantomBullet": "Phantom Bullet",
      "originBullet": "Origin Bullet", "passive": "Passive", "trueWeapon": "True Weapon",
      "superEquip": "Super Equip", "dream": "Dream Awakening"}


def _scale(e: dict, k):
    sc = e.get("scale")
    return sc.get(k) if isinstance(sc, dict) else None


def pe(e: dict, t: str) -> bool:
    if e.get("value") is None or e.get("type") in LE or _scale(e, "by") in UE:
        return False
    if _scale(e, "by") == "stack" or e.get("stackable") or e.get("maxStacks") or _SE.search(t):
        return True
    return bool(_CE.search(t)) and (bool(re.search(r"\bpermanently\b|\badditional", t, I_))
                                    or (bool(e.get("cap")) and e["cap"] >= e["value"]))


def me(e: dict, t: str):
    if e.get("maxStacks"):
        return e["maxStacks"]
    n = re.search(r"\bmax\.?\s*(\d+)\s*stacks\b|\bup to (\d+) stacks\b", t, I_)
    if n:
        return float(n.group(1) or n.group(2))
    if re.search(r"\bstacks? of bleed\b", t, I_):
        return 3
    r = None
    if e.get("valueKind") == "pct":
        mm = re.search(r"\b(?:up to|maximum of) (\d+(?:\.\d+)?)%", t, I_)
        r = float(mm.group(1)) if mm else None
    i = e.get("cap") or r or None
    if not i:
        return None
    if i >= e["value"]:
        return max(1, math.floor((i - nz(e.get("base"))) / e["value"]))
    return i


def _he(e: str) -> str:
    return re.sub(r"\b\w", lambda m: m.group(0).upper(), e)


def _ge(e: str) -> str:
    s = e.strip()
    s = re.sub(r"\s+on (?:that )?enemy\b.*$", " on enemy", s, flags=I_)
    s = re.sub(r"\s+(?:throughout (?:the )?battle|from current .+)$", "", s, flags=I_)
    return cap1(s)


def _e(e: dict, t: str) -> str:
    if _scale(e, "by") == "stack":
        of = e["scale"]["of"]
        if of == "hit":
            return "Hits"
        m = re.match(r"^times (?:this |own )?(true arts|super arts|cross arts|arts?|skill)\b",
                     of, I_)
        if m:
            return _he(re.sub(r"^art$", "arts", m.group(1), flags=I_)) + " uses"
        return _ge(of)
    n = re.search(r"\b(?:each|every) time\s+(?:this\s+|own\s+)?(true arts|super arts|cross "
                  r"arts|arts|skill)\b", t, I_)
    if n:
        return _he(n.group(1)) + " uses"
    r = re.search(r"\bfor each (stack of )?(.+?)(?:,|\s+(?:enemy has|increase|reduce)\b|\s*\(|$)",
                  t, I_)
    if r:
        return _ge(r.group(2)) + (" stacks" if r.group(1) else "")
    return f"{DE.get(e.get('source'), 'Buff')} stacks"


_J_CACHE: dict = {}


def J(unit):
    """Stackable effects of a unit: {'list': [...], 'of': {effect index: stack info}}."""
    if not unit:
        return {"list": [], "of": {}}
    k = id(unit)
    if k in _J_CACHE and _J_CACHE[k][0] is unit:
        return _J_CACHE[k][1]
    lst: list = []
    keyed: dict = {}
    of: dict = {}

    def cb(e, i, a):
        o = f(e, a)["scope"]
        if not pe(e, o):
            return
        if _scale(e, "by") == "stack":
            s = f"c:{e['scale']['of'].lower()}"
        elif e.get("source") in ("passive", "dream"):
            s = f"p:{e.get('text')}"
        else:
            s = f"s:{e.get('source')}{(':' + e['dream']) if e.get('dream') else ''}"
        c = keyed.get(s)
        if c is None:
            c = {"id": str(i), "label": _e(e, o), "source": e.get("source"), "max": None,
                 "idx": []}
            if e.get("dream"):
                c["dream"] = e["dream"]
            keyed[s] = c
            lst.append(c)
        lv = me(e, o)
        if lv is not None:
            c["max"] = lv if c["max"] is None else min(c["max"], lv)
        c["idx"].append(i)
        of[i] = c

    p(unit.get("effects"), cb)
    for c in lst:
        c["capped"] = c["max"] is not None
        if c["max"] is None:
            c["max"] = 10
    res = {"list": lst, "of": of}
    _J_CACHE[k] = (unit, res)
    return res


def Y(slot, t) -> int:
    st = (slot or {}).get("stacks") or {}
    try:
        v = float(st.get(t["id"]))
    except (TypeError, ValueError):
        v = 0
    n = js_round(v) if v == v and v else 1
    return max(1, min(t["max"], n or 1))


def ye(e: dict, t: dict):
    """Is this unit effect switched on for this slot? (Passive-type always, others by toggle.)"""
    if (e.get("dream") and t.get("dream") != e["dream"]) or (
            e.get("notDream") and t.get("dream") == e["notDream"]) or (
            e.get("source") not in VE and not (t.get("active") or {}).get(e.get("source"))):
        return None
    n = re.match(r"^in_mode:(\w+)_dream_path$", e.get("condition") or "")
    if not n:
        return e
    if (t.get("dream") or "").lower() != n.group(1):
        return None
    i = {k: v for k, v in e.items() if k != "condition"}
    return i


def X(team) -> int:
    for i, e in enumerate(team):
        if e and e.get("unit") and e.get("leader"):
            return i
    return 0


def z(e, t, n):
    """How many of something the party has ('scale' effects)."""
    if not e or e.get("by") != "count":
        return None
    r = [(u, i) for i, u in enumerate(t) if u and not (e.get("self") == "exclude" and i == n)]
    of = e.get("of")
    if of == "allies":
        return len(r)
    if of == "unique_races":
        return len({u.get("race") for u, _ in r if u.get("race")})
    if of == "unique_elements":
        skip = e.get("skip") or []
        return len({u.get("element") for u, _ in r if u.get("element") not in skip})
    items = [s.split(":") for s in ([of] if isinstance(of, str) else (of or []))]
    cnt = 0
    for u, _ in r:
        for kk, vv in [(it[0], it[1] if len(it) > 1 else None) for it in items]:
            val = u.get("race") if kk == "race" else u.get("gender") if kk == "gender" \
                else u.get("element")
            if val == vv:
                cnt += 1
                break
    return cnt


# --------------------------------------------------------------------------- team stats (HP)
def re_(e):
    if not e or not e.get("stats"):
        return None
    return nz(e["stats"].get("hp")) + nz(e["stats"].get("hpPlus"))


def ie(e):
    m = re.match(r"^(not:)?ally_hp:(\d+)$", e.get("condition") or "")
    return {"n": int(m.group(2)), "not": bool(m.group(1))} if m else None


def ae(e, t):
    return (not e) or t is None or ((t >= e["n"]) != e["not"])


def oe(effects, units, reach):
    """HP of each slot after HP UP effects."""
    out = []
    for r, unit in enumerate(units):
        i = re_(unit)
        if i is None:
            out.append(None)
            continue
        a = 0
        o = 0
        lost = G([e for e in effects if r in reach(e)])
        c = [e for e in effects if e.get("type") in ("max_hp_up", "hp_up", "stats_up")
             and e.get("value") is not None and not e.get("equipId") and not ie(e)
             and r in reach(e)]
        for grp in U(c, P).values():
            if grp[0].get("valueKind") == "flat":
                o += K(grp, lost=lost)["value"]
            else:
                a += K(grp, lost=lost)["value"]
        out.append(js_round(i * (1 + a / 100) + o))
    return out


def _equip_rows(t_, i_units, o, a_leader):
    return t_.get("equips") or []


def be(team, include_conditional=True):
    """All effects of the team with their conditions checked (used for HP)."""
    r: list = []
    units = [e.get("unit") if e else None for e in team]
    a = X(team)
    for o, slot in enumerate(team):
        if not slot or not slot.get("unit"):
            continue
        unit = slot["unit"]
        s = J(unit)["of"]
        for c, l in enumerate(unit.get("effects") or []):
            u = ye(l, slot)
            if not u:
                continue
            d = x(u.get("condition"), units, o, a)
            if d is False or (not include_conditional and u.get("condition") and d is not True):
                continue
            fx = s.get(c)
            pp = z(u.get("scale"), units, o)
            if pp is None:
                pp = Y(slot, fx) if fx else 1
            m = u.get("value") if u.get("value") is None else nz(u.get("base")) + u["value"] * pp
            h = u["cap"] if (u.get("cap") and u.get("value") is not None
                             and u["cap"] >= u["value"]) else None
            row = Obj(u)
            row.update({"value": m, "cap": h, "unit": unit["name"], "unitId": unit["id"],
                        "slot": o})
            if fx:
                row["stacks"] = pp
            r.append(row)
        for eq in slot.get("equips") or []:
            equip, on, to = eq["equip"], eq.get("on", True), eq.get("to")
            u_idx = to if isinstance(to, int) and not isinstance(to, bool) and 0 <= to < 4 \
                and units[to] else o

            def cb(l, d, pp_, equip=equip, on=on, u_idx=u_idx, slot=slot, unit=unit, o=o):
                if l.get("source") != "passive" and not on:
                    return
                cond = l.get("condition")
                if cond and "holder:" in cond:
                    parts = cond.split("+")

                    def is_h(v):
                        return bool(re.match(r"^(?:not:)?holder:", v))

                    if not all(D(v, unit) for v in parts if is_h(v)):
                        return
                    cond = "+".join(v for v in parts if not is_h(v)) or None
                if cond == "conditional":
                    ev = E(l, f(l, pp_)["scope"], unit)
                    if ev and not ev["met"]:
                        return
                    if ev:
                        cond = None
                hh = x(cond, units, o, a)
                if hh is False or (not include_conditional and cond and hh is not True):
                    return
                g = z(l.get("scale"), units, o)
                g = 1 if g is None else g
                _v = l.get("value") if l.get("value") is None else nz(l.get("base")) + l["value"] * g
                cp = l["cap"] if (l.get("cap") and l.get("value") is not None
                                  and l["cap"] >= l["value"]) else None
                row = Obj(l)
                row.update({"condition": cond, "value": _v, "cap": cp, "source": "equip",
                            "equip": equip["name"], "equipId": equip["id"], "unit": unit["name"],
                            "unitId": unit["id"], "slot": o})
                if l.get("type") == "arts_regen":
                    row["agType"] = f"Equip:{equip['id']}"
                if l.get("target") == "target":
                    row["toSlot"] = u_idx
                    row["toUnit"] = units[u_idx]["name"]
                r.append(row)

            p(equip.get("effects") or [], cb)
    xe(r)
    out = []
    for e in r:
        c = e.get("condition") or ""
        if c.startswith("not:") and not ie(e) and any(
                t.get("slot") == e.get("slot") and t.get("source") == e.get("source")
                and t.get("equipId") == e.get("equipId") and t.get("type") == e.get("type")
                and t.get("condition") == c[4:] for t in r):
            continue
        out.append(e)
    return out


def xe(effects):
    def beats(e, t):
        return (e is not t and e.get("slot") == t.get("slot") and e.get("source") == t.get("source")
                and e.get("equipId") == t.get("equipId") and e.get("dream") == t.get("dream")
                and e.get("type") == t.get("type") and e.get("value") is not None
                and e["value"] > t["value"])

    for n in effects:
        if n.get("value") is None:
            continue
        if len(n.get("except") or []) == 1 and n.get("target") == "allies":
            r = n["except"][0]
            i = next((e for e in effects if beats(e, n) and e.get("target") == r
                      and (e.get("condition") or "") == (n.get("condition") or "")
                      and not e.get("except")), None)
            if not i:
                continue
            n.pop("except", None)
            i["value"] -= n["value"]
            i["additional"] = True
        elif re.match(r"^not:ally_hp:\d+$", n.get("condition") or ""):
            r = next((e for e in effects if beats(e, n) and e.get("target") == n.get("target")
                      and e.get("condition") == n["condition"][4:]), None)
            if not r:
                continue
            n.pop("condition", None)
            r["value"] -= n["value"]
            r["additional"] = True


def Se(e) -> bool:
    return e.get("type") not in DEBUFF and e.get("type") not in SELFDOWN


def Ce(units):
    return [i for i, u in enumerate(units) if u]


def we(team):
    units = [e.get("unit") if e else None for e in team]
    n = Ce(units)
    r = [e for e in be(team) if Se(e)]
    i = X(team)
    return oe(r, units, lambda e: [k for k in n if L(e, e["slot"], k, units[k], i)])


# --------------------------------------------------------------------------- damage terms
TERM = {   # Pe: term, when(hit, enemy, param), need
    "atk_up": ("atk", None, None), "stats_up": ("atk", None, None),
    "dmg_up": ("dmg", None, None), "dmg_up_conditional": ("dmg", None, None),
    "phys_dmg_up": ("dmg", lambda h, en, w: h["dmgType"] == "PHY", "PHY hits"),
    "mag_dmg_up": ("dmg", lambda h, en, w: h["dmgType"] == "MAG", "MAG hits"),
    "arts_dmg_up": ("dmg", lambda h, en, w: h["kind"] in ARTS_KINDS, "Arts-type hits"),
    "super_arts_dmg_up": ("dmg", lambda h, en, w: h["kind"] == "superArts", "Super Arts"),
    "equip_dmg_up": ("dmg", lambda h, en, w: h["kind"] in EQUIP_KINDS, "equip hits"),
    "skill_dmg_up": ("dmg", lambda h, en, w: h["kind"] == "skill", "Skill hits"),
    "normal_attack_dmg_up": ("dmg", lambda h, en, w: h["kind"] == "normal", "normal attacks"),
    "multiplier_up": ("mult", None, None),
    "species_killer": ("dmg", lambda h, en, w: bool(w) and en.get("race") == w,
                       lambda w: f"vs {w or '?'} enemies"),
    "element_killer": ("dmg", lambda h, en, w: bool(w) and en.get("element") == w,
                       lambda w: f"vs {w or '?'} enemies"),
    "dmg_up_vs_broken": ("dmg", lambda h, en, w: bool(en.get("broken")), "enemy in Break"),
    "cri_dmg_up": ("critDmg", None, None), "cri_rate_up": ("criRate", None, None),
    "cri_res_down": ("criRate", None, None), "super_cri_rate_up": ("superCriRate", None, None),
    "ignore_def": ("ignoreDef", None, None),
    "dmg_res_down": ("res", None, None),
    "element_res_down": ("res", lambda h, en, w: bool(w) and w == h.get("element"),
                         lambda w: f"{w or '?'} hits"),
    "phys_res_down": ("res", lambda h, en, w: h["dmgType"] == "PHY", "PHY hits"),
    "mag_res_down": ("res", lambda h, en, w: h["dmgType"] == "MAG", "MAG hits"),
    "def_down": ("defDown", None, None),
}
STRONGEST_ONLY = {"dmg_res_down"}
DEBUFF_TERM = {"cri_res_down", "dmg_res_down", "element_res_down", "phys_res_down",
               "mag_res_down", "def_down"}
ARTS_KINDS = {"arts", "trueArts", "superArts", "crossArts", "phantomBullet", "originBullet",
              "protagonize"}
EQUIP_KINDS = {"trueWeapon", "superEquip", "equip"}
FE = {"dmg_up", "phys_dmg_up", "mag_dmg_up", "arts_dmg_up", "cri_dmg_up"}
CHAIN = {"Fire": "Earth", "Earth": "Water", "Water": "Fire", "Light": "Dark", "Dark": "Light"}  # je
DE_ = 1.25
OE_ = 1.25


def Me(e, t) -> float:
    """Element advantage."""
    if not e or not t:
        return 1
    if CHAIN.get(e) == t:
        return 1.2
    if CHAIN.get(t) == e:
        return 0.8
    return 1


def Ie(e: dict, t: str, n: str) -> str:
    """The element / race an effect names (its 'param')."""
    def a(rx):
        ms = list(re.finditer(rx, t, I_))
        return ms[-1].group(1) if ms else None

    def o(rx):
        m = re.search(r"(?:element|race):(\w+)", e.get("note") or "")
        v = (m.group(1) if m else None) or a(rx)
        if not v:
            mm = re.search(rx, n, I_)
            v = mm.group(1) if mm else ""
        return Q(v or "")

    ty = e.get("type")
    if ty == "species_killer":
        return o(r"\b(%s)s?\b" % _I)
    if ty == "element_killer":
        return o(r"\b(%s)\b" % _R)
    if ty == "element_res_down":
        return o(r"\b(%s)\s+RES\b" % _R)
    if ty in FE:
        return Q(a(r"\b(%s)\s+(?:CRI(?:tical)?\s+)?DMG\b(?!\s*\()" % _R) or "")
    return ""


def Le(e, t, n, r, i) -> bool:
    if e.get("type") in DEBUFF_TERM:
        return (e.get("target") or "self") == "enemies"
    return L(e, t, n, r, i)


RE_ = {"true arts": "trueArts", "super arts": "superArts", "cross arts": "crossArts",
       "arts": "arts", "skill": "skill"}
_ZE = re.compile(r"\b(?:this|current)\s+(true arts|super arts|cross arts|arts|skill)\b(?!\s+"
                 r"(?:is|has|was|are|inflicts|hits|deals)\b)|\b(?:for (?:the )?duration of|"
                 r"during)\s+(?:own\s+|this\s+)?(true arts|super arts|cross arts|arts)\b"
                 r"(?!\s+(?:DMG|CT))|\bof\s+(?:own\s+)?next\s+(true arts|super arts|cross arts"
                 r"|arts|skill)\b", I_)
_BE = re.compile(r"\bnext\s+(true arts|super arts|cross arts|origin bullet|phantom bullet|arts|"
                 r"skill)\b", I_)
VE_ = {**RE_, "origin bullet": "originBullet", "phantom bullet": "phantomBullet"}


def He(e: str, t: dict):
    """Moves an effect is tied to, from its wording ('next Arts', 'this Skill' ...)."""
    n = _ZE.search(e)
    if n:
        return [RE_[(n.group(1) or n.group(2) or n.group(3)).lower()]]
    if (t.get("target") or "self") != "self":
        return None
    parts = re.split(r"\s\+\s|\.\s+(?=[A-Z])", t.get("text") or "")
    val = f"{js_str(t.get('value'))}%"
    r = next((s for s in parts if val in s), e)
    idx = r.find(val)
    cut = r[:max(0, idx) or len(r)]
    i = [VE_[m.group(1).lower()] for m in _BE.finditer(cut)]
    return i or None


def cond_state(e, t, n, a, o, s, c, l, u):   # $
    """State of an effect's condition: met / unmet / unknown / assumed / none, with a label."""
    d = e.get("condition") or ""
    if "+" in d:
        rs = [cond_state({**e, "condition": r}, t, n, a, o, s, c, l, u) for r in d.split("+")]
        i = ", ".join(x_["label"] for x_ in rs if x_["label"])

        def has(st):
            return any(x_["state"] == st for x_ in rs)

        return {"state": "unmet" if has("unmet") else "unknown" if has("unknown")
                else "assumed" if has("assumed") else "met", "label": i}
    if d.startswith("not:"):
        r = cond_state({**e, "condition": d[4:]}, t, n, a, o, s, c, l, u)
        flip = {"met": "unmet", "unmet": "met", "assumed": "unknown", "unknown": "assumed"}
        return {"state": flip.get(r["state"], "none"), "label": f"unless {r['label']}"}
    if d == "boss_broken":
        return {"state": "met" if n.get("broken") else "unmet", "label": "enemy in Break"}
    if d == "boss_not_broken":
        return {"state": "unmet" if n.get("broken") else "met", "label": "enemy not in Break"}
    fv = x(d, c, a, u)
    if fv is not None:
        return {"state": "met" if fv else "unmet", "label": b(d)}
    if d.startswith("ally_hp:"):
        return {"state": "assumed" if l is None else ("met" if l >= float(d[8:]) else "unmet"),
                "label": b(d)}
    if d == "hp_full":
        return {"state": "assumed", "label": "own HP full"}
    if d.startswith("first_uses:"):
        k = int(d[11:])
        return {"state": "assumed", "label": "first use" if k == 1 else f"first {k} uses"}
    if d == "next_use":
        return {"state": "assumed", "label": "next use only"}
    if d.startswith("quest_window:"):
        return {"state": "assumed", "label": f"first {d[13:]}s of the quest"}
    if d == "daily_element":
        return {"state": "unknown", "label": "today's element"}
    if d in ("low_hp", "near_death") or d.startswith("hp_below:") or d.startswith("ally_hp_below:"):
        return {"state": "unknown", "label": b(d)}
    if d == "vs_low_hp":
        return {"state": "unknown", "label": "enemy HP low"}
    if d in ("vs_non_boss", "counterattack"):
        return {"state": "unknown", "label": b(d)}
    if d == "vs_boss":
        return {"state": "met", "label": b(d)}
    if d.startswith("vs_race:"):
        k = d[8:].split("/")
        if n.get("race"):
            return {"state": "met" if n["race"] in k else "unmet", "label": f"vs {'/'.join(k)}"}
        return {"state": "unknown", "label": f"vs {'/'.join(k)}"}
    if d.startswith("vs_element:"):
        return {"state": "met" if n.get("element") == d[11:] else "unmet",
                "label": f"vs {d[11:]}"}
    if d.startswith("hit:"):
        if s and s.get("dmgType"):
            return {"state": "met" if s["dmgType"] == d[4:] else "unmet", "label": b(d)}
        return {"state": "unknown", "label": b(d)}
    if d == "elemental_advantage":
        if not n.get("element") or not (s or {}).get("element"):
            return {"state": "unknown", "label": "elemental advantage"}
        return {"state": "met" if Me(s["element"], n["element"]) > 1 else "unmet",
                "label": "elemental advantage"}
    pl = {"vs_giant_boss": "vs Giant Boss", "vs_raid_boss": "vs Raid Boss",
          "on_lethal_damage": "on lethal DMG", "enemy_casting": "while the enemy uses Arts"}
    if d in pl:
        return {"state": "unknown", "label": pl[d]}
    if d.startswith("vs_hp_below:"):
        return {"state": "unknown", "label": f"enemy ≤{d[12:]}% HP"}
    if d.startswith("vs_hp_above:"):
        return {"state": "unknown", "label": f"enemy ≥{d[12:]}% HP"}
    if d.startswith("vs_ailment:"):
        return {"state": "unknown", "label": "enemy has an ailment" if d.endswith(":any")
                else f"enemy has {d[11:]}"}
    if d.startswith("vs_bleed:"):
        return {"state": "unknown", "label": b(d)}
    if d == "conditional":
        ev = E(e, t, c[a])
        if ev:
            return {"state": "met" if ev["met"] else "unmet", "label": ev["label"]}
    if d:
        return {"state": "assumed", "label": b(d)}
    if re.search(r"\b(?:own\s*self|this unit|self) is (?:the )?leader\b", t, I_):
        return {"state": "met" if a == u else "unmet", "label": "source is Leader"}
    if re.search(r"\bnot\s+(?:in\s+)?(?:break|broken)\b", t, I_):
        return {"state": "unmet" if n.get("broken") else "met", "label": "enemy not in Break"}
    if re.search(r"\b(?:in|during)\s+break\b|\bbroken\b", t, I_):
        return {"state": "met" if n.get("broken") else "unmet", "label": "enemy in Break"}
    if not o:
        m = re.search(r"(?:against|to)\s+((?:%s)(?:\s*(?:,|and|or|&)\s*(?:%s))*)\s+(?:enem|boss)"
                      % (_R, _R), t, I_)
        if m:
            k = [Q(v) for v in re.split(r"\s*(?:,|and|or|&)\s*", m.group(1), flags=I_)]
            return {"state": "met" if n.get("element") in k else "unmet",
                    "label": f"vs {'/'.join(k)}"}
        m = re.search(r"(?:against|to)\s+(%s)s?\b" % _I, t, I_)
        if m:
            return {"state": "met" if n.get("race") == Q(m.group(1)) else "unmet",
                    "label": f"vs {Q(m.group(1))}"}
    if re.search(r"(?:burn|poison|blind|paraly|freez|frozen|bleed|curse|disease|faint|status "
                 r"ailment)\w*\s+enem|enem\w*\s+with\s+(?:status|bleed|burn|poison)|enem\w*\s+"
                 r"(?:under|below|above)\s+\d+%|(?:less than|under|below)\s+\d+%\s+HP", t, I_):
        return {"state": "unknown", "label": "enemy state"}
    if re.search(r"\b(?:if|when|whenever|while|after)\b", t, I_):
        return {"state": "assumed", "label": "conditional"}
    return {"state": "none", "label": ""}


_UE_ = re.compile(r"(?:#\s*of|for each)\s+(%s|%s)s?\s+(?:allies|ally|in)\b" % (_R, _I), I_)


def We(e, t, n, r):
    if e.get("scale"):
        return z(e["scale"], [s.get("unit") if s else None for s in n], r)
    i = _UE_.search(t)
    if not i:
        return None
    a = Q(i.group(1))
    o = bool(re.search(r"excluding self|except self", e.get("text") or "", I_))
    return len([1 for k, s in enumerate(n) if s and s.get("unit") and (
        s["unit"].get("element") == a or s["unit"].get("race") == a) and not (o and k == r)])


def Ke(e, t):
    if not t or _scale(e, "by") != "stat":
        return None
    n = re.match(r"^(\d+(?:\.\d+)?)%?\s*×\s*own ATK(/100)?$", e.get("formula") or "")
    if not n:
        return None
    return js_round(float(n.group(1)) * t / (100 if n.group(2) else 1) * 10) / 10


def Ge(team, attackerIdx, hit, enemy, atkBase=0, crest=None):
    """Every effect that could matter for this hit, each with its condition state."""
    o = (team[attackerIdx] or {}).get("unit")
    if not o:
        return []
    s: list = []
    c = we(team)[attackerIdx]
    l = X(team)
    u = [e.get("unit") if e else None for e in team]

    def d(a, dd, slot, srcIdx, key, source, g=None, equip=None, crest_name=None):
        ty = a.get("type")
        x_ = TERM.get(ty)
        if not x_ or a.get("value") is None or not Le(a, srcIdx, attackerIdx, o, l):
            return
        term0, when, need = x_
        sc = f(a, dd)
        S_, C_ = sc["scope"], sc["pre"]
        w = Ie(a, C_, S_)
        T_ = ty in ("species_killer", "element_killer")
        E_ = True
        D_ = ""
        mv = a.get("moves")
        O_ = None if (mv or re.search(r"(?:^|\+)on_inflict:", a.get("condition") or "")) \
            else He(S_, a)
        if mv and hit["kind"] not in mv:
            E_, D_ = False, "only " + " / ".join(HITKIND.get(m, m) for m in mv) + " hits"
        elif O_ and not (srcIdx == attackerIdx and hit["kind"] in O_):
            E_, D_ = False, "only on own " + " / ".join(HITKIND[m] for m in O_)
        elif when and not when(hit, enemy, w):
            E_ = False
            D_ = "only " + (need(w) if callable(need) else need)
        elif w and ty in FE and w != hit.get("element"):
            E_, D_ = False, f"only {w} hits"
        if ty == "multiplier_up" and (srcIdx != attackerIdx or a.get("move") != hit["kind"]):
            E_, D_ = False, f"only on own {HITKIND.get(a.get('move'), a.get('move'))}"
        if ty == "multiplier_up":
            k = "multFactor" if a.get("valueKind") == "factor" else "multAdd"
        elif ty == "atk_up" and a.get("valueKind") == "flat":
            k = "atkFlat"
        else:
            k = term0
        A_ = None if _scale(a, "by") in ("stat", "hp", "max") else We(a, S_, team, srcIdx)
        j_ = Ke(a, atkBase) if srcIdx == attackerIdx else None
        M_ = g if A_ is None else None
        P_ = a["cap"] if a.get("cap") and a["cap"] >= a["value"] else None
        strongest = ty in STRONGEST_ONLY
        F_ = f"|eq:{equip['id']}" if equip and not strongest else ""
        debuff = ty in DEBUFF_TERM
        row = Obj({
            "key": key, "term": k, "type": ty, "param": w,
            "group": (f"{k}|{ty}|{w}" if debuff else f"{k}|{ty}|{w}|{N(a)}|{ee(a)}") + F_,
            "condition": a.get("condition"),
            "label": f"{HITKIND.get(a.get('move')) or 'Move'} multiplier"
            if ty == "multiplier_up" else LABEL.get(ty, ty) + (f" ({w})" if w else ""),
            "value": j_ if j_ is not None else a["value"], "base": nz(a.get("base")),
            "formula": a.get("formula") or "", "cap": P_, "permanent": bool(a.get("permanent")),
            "stackable": bool(a.get("stackable")), "additional": bool(a.get("additional")),
            "capRaw": a.get("cap"),
            "capPlus": bool(re.search(r"MAX:?\s*\+", a.get("text") or "", I_)),
            "strongestOnly": strongest, "debuff": debuff, "count": A_,
            "stack": ({"id": M_["id"], "label": M_["label"], "max": M_["max"],
                       "capped": M_["capped"], "n": Y(slot, M_)} if M_ else None),
            "unit": slot["unit"]["name"], "unitIdx": srcIdx, "source": source,
            "equip": equip["name"] if equip else None, "crest": crest_name,
            "target": a.get("target"), "text": a.get("text"), "scope": S_,
        })
        if a.get("stackGroup") is not None:
            row["stackGroup"] = a["stackGroup"]
            row["stackOrder"] = a.get("stackOrder") or 0
            if a.get("stackPassive"):
                row["stackPassive"] = True
            if equip:
                row["equipId"] = equip["id"]
            if a.get("dream"):
                row["dream"] = a["dream"]
        row["cond"] = cond_state(a, S_, enemy, srcIdx, T_, hit, u, c, l)
        row["relevant"] = E_
        row["reason"] = D_
        s.append(row)

    for r, slot in enumerate(team):
        if not slot or not slot.get("unit"):
            continue
        unit = slot["unit"]
        i_of = J(unit)["of"]
        act = dict(slot.get("active") or {})
        if r == attackerIdx:
            act[hit["kind"]] = True
        a_slot = {**slot, "active": act}

        def cb1(t, n, occ, slot=slot, r=r, unit=unit, i_of=i_of, a_slot=a_slot):
            sx = ye(t, a_slot)
            if sx:
                d(sx, occ, slot, r, f"{unit['id']}:{n}", sx.get("source"), g=i_of.get(n))

        p(unit.get("effects"), cb1)
        for eq in slot.get("equips") or []:
            equip, on, to = eq["equip"], eq.get("on", True), eq.get("to")
            sI = r == attackerIdx and hit["kind"] == "equip" and hit.get("equipId") == equip["id"]
            cI = to if isinstance(to, int) and not isinstance(to, bool) and u[to] else r

            def cb2(t, n, occ, slot=slot, r=r, unit=unit, equip=equip, on=on, sI=sI, cI=cI):
                if t.get("source") != "passive" and not on and not sI:
                    return
                lrow = {**t, "toSlot": cI} if t.get("target") == "target" else t
                cond = t.get("condition")
                if cond and "holder:" in cond:
                    parts = cond.split("+")

                    def is_h(v):
                        return bool(re.match(r"^(?:not:)?holder:", v))

                    if not all(D(v, unit) for v in parts if is_h(v)):
                        return
                    rest = "+".join(v for v in parts if not is_h(v))
                    lrow = {**lrow, "condition": rest or None}
                    if not rest:
                        lrow.pop("condition", None)
                d(lrow, occ, slot, r, f"{unit['id']}:e{equip['id']}:{n}", "equip", equip=equip)

            p(equip.get("effects"), cb2)
    if crest and crest.get("effects"):
        def cb3(n, r, occ):
            d(n, occ, team[attackerIdx], attackerIdx, f"crest:{r}", "crest",
              crest_name=crest.get("name"))
        p(crest["effects"], cb3)
    return s


def qe(e, t=None) -> bool:
    t = t or {}
    if not e["relevant"]:
        return False
    if e["key"] in t:
        return bool(t[e["key"]])
    return e["cond"]["state"] not in ("unmet", "unknown")


def Je(effects, overrides=None):
    """Which effects apply, and the total of each term."""
    overrides = overrides or {}
    n: dict = {}
    r: dict = {}
    i: dict = {}
    a: list = []
    for o in effects:
        if not qe(o, overrides):
            r[o["key"]] = "off" if o["relevant"] else "na"
            continue
        cnt = o["count"]
        if cnt is None:
            cnt = (o["stack"] or {}).get("n") if o["stack"] else None
        if cnt is None:
            cnt = 1
        i[o["key"]] = nz(o["base"]) + o["value"] * cnt
        if o["term"] in ("multAdd", "multFactor"):
            r[o["key"]] = "applied"
            row = Obj(o)
            row["value"] = i[o["key"]]
            a.append(row)
            continue
        row = Obj(o)
        row["value"] = i[o["key"]]
        n.setdefault(o["group"], []).append(row)
    flat = [v for grp in n.values() for v in grp]
    s = G([v for v in flat if not v["debuff"]]) | G([v for v in flat if v["debuff"]])
    c = {"atk": 0, "atkFlat": 0, "dmg": 0, "critDmg": 0, "res": 0, "defDown": 0, "ignoreDef": 0,
         "criRate": 0, "superCriRate": 0, "multAdd": 0, "multFactor": 1}
    groups = []
    for e, t in n.items():
        k = K(t, strongestOnly=t[0]["strongestOnly"], lost=s)
        c[t[0]["term"]] += k["value"]
        for v in t:
            r[v["key"]] = "applied" if v in k["applied"] else "overridden"
        groups.append({"key": e, "term": t[0]["term"], "label": t[0]["label"],
                       "value": k["value"], "capped": k["capped"], "cap": k["cap"]})
    return {"terms": c, "status": r, "effValue": i, "groups": groups, "mult": a}


def Ye(e, t=None):
    n = 0
    r = 1
    for i in t or []:
        if i["term"] == "multFactor":
            r *= i["value"]
            continue
        v = i["value"]
        if i.get("capRaw"):
            v = min(v, i["capRaw"] if (i.get("capPlus") or i["capRaw"] <= e)
                    else i["capRaw"] - e)
        n += v
    return {"multiplier": (e + n) * r, "add": n, "factor": r}


def Xe(atkBase, multiplier, atkUp=0, elem=1, broken=False, crit="none", dmgUp=0, critDmgUp=0,
       resDown=0, enemyRes=0, enemyDef=0, defDown=0, ignoreDef=0, negated=False):
    """The damage formula."""
    m = math.floor(max(0, atkBase * (1 + atkUp / 100)) + 1e-9)
    h = 700 * m / (m + 3500) if m > 0 else 0
    g = crit in ("crit", "super")
    _ = 3 if crit == "super" else (DE_ if g else 1)
    v = OE_ if broken else 1
    y = 1 + (dmgUp + (critDmgUp if g else 0)) / 100
    bb = max(0, 1 + (resDown - enemyRes) / 100)

    def xx(e):
        return min(100, max(0, e)) / 100

    Sx = math.trunc(max(0, enemyDef) * (1 - xx(defDown)))
    Cx = max(0, math.trunc(math.trunc(Sx - 1) * (1 - xx(ignoreDef))))
    w = 1 if (g or Cx < 1) else 1 - Cx / (Cx + 5000)
    Tt = 0 if negated else h * elem * v * _ * y * bb * (multiplier / 100)
    Ee = 1 if (not negated and multiplier > 0 and Tt * w <= 0) else Tt * w
    return {"atk": m, "atkCurve": h, "elem": elem, "breakF": v, "critF": _, "dmgF": y,
            "resF": bb, "effDef": Cx, "mitigation": w, "trueDmg": Tt, "final": Ee,
            "dealt": math.floor(Ee + 1e-6), "shown": max(0, math.ceil(Ee - 1e-6))}


def Ze(e: dict, t, n):
    r = min(1, max(0, t) / 100)
    i = min(1, max(0, n) / 100)

    def a(c):
        return Xe(**{**e, "crit": c})["final"]

    return (1 - r) * a("none") + r * (1 - i) * a("crit") + r * i * a("super")


def Qe(e, t) -> str:
    if e >= 100:
        return "super" if t >= 100 else "crit"
    return "none"


def hit_res(e: dict, t: dict) -> dict:   # $e
    n = dict((e or {}).get("resBy") or {})
    for st in (e or {}).get("status") or []:
        for k, v in (((e or {}).get("while") or {}).get(st) or {}).items():
            n[k] = nz(n.get(k)) + v
    neg = next((x_ for x_ in ((e or {}).get("negates") or [])
                if x_.get("key") in (t.get("element"), t.get("dmgType"))), None)
    return {"res": nz(n.get("all")) + nz(n.get(t.get("element"))) + nz(n.get(t.get("dmgType"))),
            "negated": neg}


def calculate(team, attackerIdx, hit, enemy, atkBase, extra=None, crit="auto", overrides=None,
              crest=None) -> dict:
    """et: the whole calculation."""
    extra = extra or {}
    mods = Ge(team, attackerIdx, hit, enemy, atkBase, crest)
    u = Je(mods, overrides)
    d = u["terms"]
    fm = Ye(hit["multiplier"], u["mult"])
    d["multAdd"] = fm["add"]
    d["multFactor"] = fm["factor"]
    rates = {"criRate": d["criRate"] + nz(extra.get("criRate")) + nz(enemy.get("cri")),
             "superCriRate": d["superCriRate"] + nz(extra.get("superCriRate"))}
    m = Qe(rates["criRate"], rates["superCriRate"]) if crit == "auto" else crit
    h = hit_res(enemy, hit)
    g = {"atkBase": atkBase + d["atkFlat"], "multiplier": fm["multiplier"],
         "broken": bool(enemy.get("broken")), "crit": m,
         "elem": Me(hit.get("element"), enemy.get("element")),
         "atkUp": d["atk"] + nz(extra.get("atk")), "dmgUp": d["dmg"] + nz(extra.get("dmg")),
         "critDmgUp": d["critDmg"] + nz(extra.get("critDmg")),
         "resDown": d["res"] + nz(extra.get("res")),
         "enemyRes": nz(enemy.get("res")) + h["res"], "enemyDef": nz(enemy.get("def")),
         "defDown": d["defDown"], "ignoreDef": d["ignoreDef"] + nz(extra.get("ignoreDef")),
         "negated": bool(h["negated"])}
    inp = dict(g)
    return {"mods": mods, **u, "rates": rates, "hitType": m, "input": inp,
            "baseMultiplier": hit["multiplier"], "negated": h["negated"],
            "result": Xe(**g), "expected": Ze(g, rates["criRate"], rates["superCriRate"])}


def apply_hit_overrides(kind, hits, overrides=None):   # Ne
    out = []
    for t in hits:
        r = next((n for n in (overrides or []) if n.get("kind") == kind and (
            n.get("from") is None or n.get("from") == t["multiplier"])), None)
        if r:
            row = {**t, "multiplier": r["to"]}
            if t.get("formula") and r.get("from") is not None:
                row["formula"] = t["formula"].replace(js_str(r["from"]), js_str(r["to"]))
            out.append(row)
        else:
            out.append(t)
    return out


# --------------------------------------------------------------------------- data + team building
import json  # noqa: E402
from pathlib import Path  # noqa: E402


class CalcData:
    """data/gscompanion/calc_*.json, joined the way the site's page does."""

    def __init__(self, folder: Path):
        d = Path(folder)

        def load(name, key):
            try:
                return json.loads((d / name).read_text(encoding="utf-8")).get(key, [])
            except (OSError, ValueError):
                return []

        # each unit's kit text (skill, arts, true arts, super arts, passives), from the Team Builder data
        self.kits = {u["id"]: u.get("kit") or [] for u in load("team_units.json", "units")}
        self.unit_list = load("calc_units.json", "units")
        self.units = {u["id"]: u for u in self.unit_list}
        self.enemies = load("calc_enemies.json", "enemies")
        self.enemy_by_id = {e["id"]: e for e in self.enemies}
        self.crest_list = load("calc_crests.json", "crests")
        self.crests = {c["id"]: c for c in self.crest_list}
        self.equips: dict = {}
        for t in load("calc_equips.json", "equips"):
            tx = t.get("tx") or []
            self.equips[t["id"]] = {**t, "effects": [
                {**e, "text": tx[e["text"]] if isinstance(e.get("text"), int)
                 and e["text"] < len(tx) else e.get("text")} for e in t.get("effects") or []]}

    @property
    def available(self) -> bool:
        return bool(self.units and self.equips)

    def slot(self, spec: dict | None):
        """A team slot from its saved form: {id, active, stacks, leader, dream, equips}."""
        if not spec:
            return None
        unit = self.units.get(spec["id"])
        if not unit:
            return None
        eq = []
        for e in spec.get("equips") or []:
            if e and e.get("id") in self.equips:
                row = {"equip": self.equips[e["id"]], "on": e.get("on") is not False}
                if isinstance(e.get("to"), int) and not isinstance(e.get("to"), bool):
                    row["to"] = e["to"]
                eq.append(row)
        return {"unit": unit, "active": dict(spec.get("active") or {}),
                "stacks": dict(spec.get("stacks") or {}), "leader": bool(spec.get("leader")),
                "dream": spec.get("dream"), "equips": eq}

    def team(self, specs: list) -> list:
        return [self.slot(s) for s in specs]

    def crest_fx(self, crest_id, lv_idx):
        c = self.crests.get(crest_id)
        if not c:
            return None
        lv = c["lv"][lv_idx] if 0 <= lv_idx < len(c["lv"]) else None
        if not lv or not lv.get("fx"):
            return None
        txt = (lv.get("text") or "").replace("\n", " / ")
        return {"name": c["name"], "effects": [{**e, "text": txt} for e in lv["fx"]]}


def unit_hits(unit: dict, dream=None) -> dict:
    """The moves a unit can attack with, [(kind, index, hit)], dream overrides applied."""
    out = []
    ov = (unit.get("dreamHits") or {}).get(dream) if dream else None
    for kind in ("skill", "arts", "trueArts", "superArts", "crossArts", "phantomBullet",
                 "originBullet", "protagonize", "superEquip"):
        for i, h in enumerate(apply_hit_overrides(kind, (unit.get("hits") or {}).get(kind) or [],
                                                  ov)):
            out.append({"kind": kind, "idx": i, **h})
    return out


# --------------------------------------------------------------------------- arts gauge
def arts_gen(team) -> dict:
    """Arts gauge per second for each slot (and for the whole team), from the team's
    "Arts Gen" effects: the part of the site's team analysis that counts the gauge.
    -> {"team": per second for effects that reach everyone, "units": {slot: per second}}"""
    units = [e.get("unit") if e else None for e in team]
    idx = Ce(units)
    rows = [e for e in be(team) if Se(e)]
    lead = X(team)
    reach = {e: [k for k in idx if L(e, e["slot"], k, units[k], lead)] for e in rows}
    hp = oe(rows, units, lambda e: reach[e])
    reach2 = {e: [k for k in reach[e] if ae(ie(e), hp[k])] for e in rows}
    everyone = set()
    for e in rows:
        if e.get("target") in ("self", "leader", "target") or e.get("target") in SIDES or not idx:
            continue
        mine = reach2[e]
        outside = e.get("target") == "allies" and e["slot"] not in reach[e]
        if all(k in mine or (outside and k == e["slot"]) for k in idx):
            everyone.add(e)
    lost_team = G([e for e in rows if e in everyone])
    lost_by = {k: G([e for e in rows if k in reach2[e]]) for k in idx}
    regen = [e for e in rows if e.get("type") == "arts_regen" and e.get("value") is not None]

    def total(effs, lost):
        n = 0
        for ag, grp in U(effs, lambda e: e.get("agType") or "?").items():
            n += K(grp, lost=lost, **te(ag))["value"]
        return js_round(n * 10) / 10

    return {"team": total([e for e in regen if e in everyone], lost_team),
            "units": {k: total([e for e in regen if k in reach2[e]], lost_by[k]) for k in idx},
            "hp": {k: hp[k] for k in idx}}
