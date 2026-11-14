"""What the GS Companion app remembers, and which units are "yours".

Settings: one small JSON file (window, last view, filters, text size, starred units,
farm plan, compared crests). Written atomically; a broken or missing file just means
defaults. Rerun's unit scan (<rerun>/units/roster.json, built by the Compendium
Counter) is only ever read, never written.
"""
from __future__ import annotations

import json
from pathlib import Path

DEFAULTS = {
    "view": "Palace", "size": "Medium", "sash": None, "geometry": None,
    "diff": "All difficulties", "kind": "All kinds", "element": "All elements",
    "unit_filter": "All units", "starred": [], "plan": [], "compare": [], "rerun_dir": None,
}


class Settings:
    def __init__(self, path: Path | None):
        self.path = path
        self.data = dict(DEFAULTS)
        if path:
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    self.data.update({k: v for k, v in loaded.items() if k in DEFAULTS})
            except (OSError, ValueError):
                pass

    def __getitem__(self, key):
        return self.data[key]

    def __setitem__(self, key, value):
        self.data[key] = value

    def save(self) -> bool:
        if not self.path:
            return False
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, indent=1, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self.path)
            return True
        except OSError:
            return False


class MyUnits:
    """Starred units (saved in Settings) plus units found in Rerun's unit scan."""

    def __init__(self, settings: Settings, gsc, rerun_dir: Path | None):
        self.s, self.gsc = settings, gsc
        self.default_dir = rerun_dir
        self._scan: set[str] = set()
        self._scan_key = None

    # --- Rerun scan ---------------------------------------------------------------
    @property
    def rerun_dir(self) -> Path | None:
        d = self.s["rerun_dir"]
        return Path(d) if d else self.default_dir

    @property
    def roster_path(self) -> Path | None:
        return self.rerun_dir / "units" / "roster.json" if self.rerun_dir else None

    def scanned(self) -> set[str]:
        """Names (GS Companion spelling) of units in Rerun's scan; re-read when it changes."""
        p = self.roster_path
        try:
            key = (str(p), p.stat().st_mtime) if p else None
        except OSError:
            key = None
        if key != self._scan_key:
            self._scan_key, self._scan = key, set()
            if key:
                try:
                    roster = json.loads(p.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    roster = {}
                for name, rec in (roster.items() if isinstance(roster, dict) else []):
                    el = ((rec or {}).get("fields", {}).get("element") or {}).get("value")
                    u = (self.gsc.match_unit(f"{name} ({el})") if el else None) \
                        or self.gsc.match_unit(name)
                    if u:
                        self._scan.add(u["name"])
        return self._scan

    def scan_status(self) -> str:
        p = self.roster_path
        if not p or not p.exists():
            return "No Rerun scan found"
        return f"Rerun scan: {len(self.scanned())} units"

    # --- stars --------------------------------------------------------------------
    @property
    def starred(self) -> set[str]:
        return set(self.s["starred"])

    def is_starred(self, name: str) -> bool:
        return name in self.s["starred"]

    def toggle_star(self, name: str) -> bool:
        stars = list(self.s["starred"])
        if name in stars:
            stars.remove(name)
        else:
            stars.append(name)
        self.s["starred"] = stars
        self.s.save()
        return name in stars

    # --- combined -----------------------------------------------------------------
    def all(self) -> set[str]:
        return self.starred | self.scanned()

    def mark(self, name: str) -> str:
        """Short marker for lists: ★ starred, ✓ only in Rerun's scan."""
        if name in self.s["starred"]:
            return "★"
        return "✓" if name in self.scanned() else ""
