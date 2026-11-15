"""Crest Palace stage guides (data/gscompanion/stage_guides.json, made by fetch_guides.py):
strategy, waves, recommended units by role and example teams for each stage."""
from __future__ import annotations

import json
from pathlib import Path


class Guides:
    def __init__(self, folder: Path, filename: str = "stage_guides.json"):
        self.path = Path(folder) / filename
        self.by_slug: dict[str, dict] = {}
        self.built = ""
        try:
            doc = json.loads(self.path.read_text(encoding="utf-8"))
            self.built = str(doc.get("built", ""))
            for g in doc.get("stages", []):
                if isinstance(g, dict) and g.get("slug"):
                    self.by_slug[g["slug"]] = g
        except (OSError, ValueError):
            pass  # no guides yet: the app works without them
        self._units: dict[str, list[tuple[str, str]]] | None = None

    @property
    def available(self) -> bool:
        return bool(self.by_slug)

    def for_stage(self, stage: dict | None) -> dict | None:
        return self.by_slug.get((stage or {}).get("slug", ""))

    @staticmethod
    def recommended(g: dict) -> list[str]:
        """Every unit the guide names (role picks, 'also fits' and example teams), in order."""
        seen: dict[str, None] = {}
        for r in g.get("roles", []):
            for u in r.get("picks", []) + r.get("also", []):
                seen.setdefault(u["name"], None)
        for t in g.get("teams", []):
            for u in t.get("units", []):
                seen.setdefault(u["name"], None)
        return list(seen)

    def stages_for_unit(self, name: str) -> list[tuple[str, str]]:
        """[(stage slug, 'Mitigation' / 'Mitigation (also fits)' / 'Example team'), ...]"""
        if self._units is None:
            idx: dict[str, list[tuple[str, str]]] = {}
            for slug, g in self.by_slug.items():
                roles: dict[str, list[str]] = {}
                for r in g.get("roles", []):
                    for u in r.get("picks", []):
                        roles.setdefault(u["name"], []).append(r["role"])
                    for u in r.get("also", []):
                        roles.setdefault(u["name"], []).append(f"{r['role']} (also fits)")
                for t in g.get("teams", []):
                    for u in t.get("units", []):
                        if u["name"] not in roles:
                            roles.setdefault(u["name"], []).append("Example team")
                for unit, rs in roles.items():
                    idx.setdefault(unit, []).append((slug, ", ".join(dict.fromkeys(rs))))
            self._units = idx
        return self._units.get(name, [])
