"""Team checking against a Crest Palace stage guide, and how ready "your units" are.

All of it is a rule-of-thumb reading of the guide, not a promise of a clear:
  - roles: does the team have a unit the guide lists for each role (picks or "also fits")?
  - warnings: stage hazards that punish a unit, read from the hazard names:
      "<Element> Killer"      units of that element
      "<Race> Killer"         units of that race (needs unit details)
      "<Element> DMG negated" units of that element
      "MAG/PHY DMG negated"   magic / physical attackers (needs unit details)
      "Taunt Killer"          units whose kit taunts (needs unit details)
      "HP auto-recovery killer" units that heal over time (needs unit details)
  - example teams: how much of each example team you have / have in this team."""
from __future__ import annotations

import re

ELEMENTS = ("Fire", "Water", "Earth", "Light", "Dark")
TEAM_SIZE = 4


def hazards(stage: dict, guide: dict | None) -> list[str]:
    out = list(stage.get("hazards", []))
    for w in (guide or {}).get("waves", []):
        for c in w.get("chips", []):
            if c.get("tone") == "bad":
                out.append(c["text"])
    return list(dict.fromkeys(out))


def _kit_text(d: dict | None) -> str:
    if not d:
        return ""
    bits = [m.get("text", "") for m in d.get("moves", [])]
    bits += [p.get("name", "") + " " + p.get("text", "") for p in d.get("passives", [])]
    bits += [e.get("effect", "") for e in d.get("effects", [])]
    bits += [c for v in d.get("tags", {}).values() for c in v]
    return " ".join(bits).lower()


def hazard_hits(hz: str, unit: dict, d: dict | None) -> str | None:
    """Why hazard `hz` is bad for this unit, or None."""
    h = hz.strip()
    m = re.match(r"^(\w+) Killer\b", h, re.I)
    if m:
        what = m.group(1).title()
        if what in ELEMENTS and unit.get("element") == what:
            return f"{what} unit vs {h}"
        if what == "Taunt" and d and re.search(r"\btaunt|provok", _kit_text(d)):
            return f"taunts vs {h}"
        if d and d.get("race") and d["race"].lower() == m.group(1).lower():
            return f"{d['race']} vs {h}"
    if re.match(r"^HP auto-recovery killer", h, re.I) and d:
        if any(e.get("effect") == "Heal/s" for e in d.get("effects", [])) or \
                re.search(r"auto-recovery|regenerat|hp recovery over time", _kit_text(d)):
            return "heals over time vs HP auto-recovery killer"
    m = re.match(r"^(\w+) DMG negated", h, re.I)
    if m:
        what = m.group(1)
        if what.title() in ELEMENTS and unit.get("element") == what.title():
            return f"{what.title()} damage is negated"
        att = (d or {}).get("details", {}).get("Attack", "")
        if what.upper() == "MAG" and att == "Magic":
            return "magic damage is negated"
        if what.upper() in ("PHY", "PHYS") and att == "Physical":
            return "physical damage is negated"
    return None


class TeamCheck:
    def __init__(self, gsc, guides, details: dict[str, dict]):
        self.gsc, self.guides, self.details = gsc, guides, details

    def roles(self, guide: dict) -> list[dict]:
        return guide.get("roles", []) if guide else []

    def check(self, team: list[str], stage: dict, my: set[str]) -> dict:
        g = self.guides.for_stage(stage)
        team_set = set(team)
        roles = []
        for r in self.roles(g):
            names = [u["name"] for u in r.get("picks", []) + r.get("also", [])]
            have = [n for n in names if n in team_set]
            options = [n for n in names if n in my and n not in team_set]
            roles.append({"role": r["role"], "covered": have, "yours": options,
                          "picks": [u["name"] for u in r.get("picks", [])]})
        warnings = []
        for name in team:
            u = self.gsc.match_unit(name) or {"name": name}
            d = self.details.get(name)
            for hz in hazards(stage, g):
                why = hazard_hits(hz, u, d)
                if why:
                    warnings.append((name, why))
        teams = []
        for i, t in enumerate((g or {}).get("teams", []), 1):
            names = [u["name"] for u in t.get("units", [])]
            teams.append({"n": i, "units": names, "note": t.get("note", ""),
                          "in_team": [n for n in names if n in team_set],
                          "owned": [n for n in names if n in my]})
        no_details = [n for n in team if n not in self.details]
        return {"guide": g, "roles": roles, "warnings": warnings, "teams": teams,
                "no_details": no_details}

    def readiness(self, stage: dict, my: set[str]) -> dict:
        """How well your units cover the guide: roles you can fill, full example teams."""
        g = self.guides.for_stage(stage)
        rs = self.roles(g)
        filled = [r["role"] for r in rs
                  if any(u["name"] in my for u in r.get("picks", []) + r.get("also", []))]
        full = [i for i, t in enumerate((g or {}).get("teams", []), 1)
                if t.get("units") and all(u["name"] in my for u in t["units"])]
        return {"filled": filled, "roles": len(rs), "full_teams": full, "guide": bool(g)}

    def suggest(self, stage: dict, my: set[str], keep: list[str] | None = None) -> list[str]:
        """A team from your units: an example team you fully own, else one unit per role
        (top picks first), avoiding units the stage hazards punish."""
        g = self.guides.for_stage(stage)
        if not g:
            return list(keep or [])[:TEAM_SIZE]
        bad = {n for n in my
               if any(hazard_hits(h, self.gsc.match_unit(n) or {}, self.details.get(n))
                      for h in hazards(stage, g))}
        for t in g.get("teams", []):
            names = [u["name"] for u in t.get("units", [])]
            if names and all(n in my for n in names):
                return names[:TEAM_SIZE]
        team = [n for n in (keep or []) if n in my][:TEAM_SIZE]
        for r in self.roles(g):
            if len(team) >= TEAM_SIZE:
                break
            names = [u["name"] for u in r.get("picks", []) + r.get("also", [])]
            if any(n in team for n in names):
                continue
            pick = next((n for n in names if n in my and n not in bad and n not in team), None)
            if pick:
                team.append(pick)
        return team
