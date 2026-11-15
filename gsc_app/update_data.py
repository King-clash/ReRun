"""Refresh the GS Companion data from gscompanion.com (also used by the app's "Update data").

    py gsc_app/update_data.py                 lists + stage guides + new unit details + pictures
    py gsc_app/update_data.py --all-units     ...and fetch every unit's page again
    py gsc_app/update_data.py --only guides   just one part: lists, guides, units, pictures

Writes into data/gscompanion/ (or --out DIR):
  crest_palace.json, crests.json, crest_recommendations.json, units.json   (the list pages)
  stage_guides.json   strategy, waves, recommended units and teams per Crest Palace stage
  unit_details.json   each unit's kit, effects, stats, equip slots, true weapon and tags
  images/             pictures the above use (unit thumbnails, banners, icons, enemies)

Polite by design: one request at a time with a pause between them, a plain browser
User-Agent, files already saved are not fetched again (pictures, unit pages), and nothing
is overwritten unless the new page parsed sensibly. Every file is written atomically.
The data is the site's / the GSGL advisor team's: it stays in data/ (git-ignored)."""
from __future__ import annotations

import io
import json
import re
import sys
import threading
import time
import urllib.request
from datetime import date
from pathlib import Path
from typing import Callable

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gsc_app import scrape  # noqa: E402

SITE = scrape.SITE
PAUSE_S = 0.5
MAX_PAGE = 4_000_000
MAX_IMAGE = 3_000_000
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) gsc-companion/1.0"}
PARTS = ("lists", "guides", "bosses", "equips", "calc", "units", "pictures")
CATALOG = Path(__file__).with_name("stage_catalog.json")
META_NOTE = "Fan-site reference data; the game itself is the authority."


class Cancelled(Exception):
    pass


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    tmp.replace(path)


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


class Updater:
    """progress(text, done, total) is called from the worker thread; stop with cancel()."""

    def __init__(self, out: Path, progress: Callable[[str, int, int], None] | None = None,
                 all_units: bool = False, parts: tuple[str, ...] = PARTS):
        self.out = Path(out)
        self.progress = progress or (lambda t, d, n: None)
        self.all_units = all_units
        self.parts = parts
        self._stop = threading.Event()
        self.failed: list[tuple[str, str]] = []
        self.summary: list[str] = []
        self._last = 0.0

    def cancel(self):
        self._stop.set()

    # --- network ------------------------------------------------------------------------
    def _get(self, url: str, limit: int) -> bytes:
        if self._stop.is_set():
            raise Cancelled()
        wait = PAUSE_S - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        req = urllib.request.Request(url, headers=HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = r.read(limit + 1)
        finally:
            self._last = time.monotonic()
        if len(data) > limit:
            raise ValueError("too large")
        return data

    def page(self, path: str) -> str:
        return self._get(SITE + path, MAX_PAGE).decode("utf-8", errors="replace")

    # --- parts --------------------------------------------------------------------------
    def run(self) -> bool:
        """True when everything worked (cancelled or failed parts -> False)."""
        steps = [("lists", self.lists), ("guides", self.guides), ("bosses", self.bosses),
                 ("equips", self.equips), ("calc", self.calc),
                 ("units", self.units),
                 ("pictures", self.pictures)]
        try:
            for name, fn in steps:
                if name in self.parts:
                    fn()
        except Cancelled:
            self.summary.append("Stopped early; what was saved so far is kept.")
            return False
        return not self.failed

    def lists(self):
        self.progress("Crest Palace, crests and units lists", 0, 3)
        palace = scrape.parse_palace(self.page("/stages/crest-palace/"))
        self.progress("Crest Palace, crests and units lists", 1, 3)
        notes: dict[str, list[str]] = {}
        crests, recs = scrape.parse_crests(self.page("/crests/"), notes)
        self.progress("Crest Palace, crests and units lists", 2, 3)
        units = scrape.parse_units(self.page("/units/"))
        self.progress("Crest Palace, crests and units lists", 3, 3)
        # Sanity: never replace good data with a half-parsed page.
        if len(palace) < 10 or len(crests) < 50 or len(units) < 200 or len(recs) < 100:
            self.failed.append(("lists", f"pages looked wrong ({len(palace)} stages, "
                                         f"{len(crests)} crests, {len(units)} units)"))
            return
        scrape.link_stage_crests(palace, crests)
        meta = {"source": SITE, "built": date.today().isoformat(), "note": META_NOTE}
        write_json(self.out / "crest_palace.json", {
            **meta, "reset_timezone": "America/Los_Angeles (per site)",
            "levels": scrape.LEVELS, "stages": palace})
        write_json(self.out / "crests.json", {**meta, "levels": scrape.LEVELS, "crests": crests})
        write_json(self.out / "crest_recommendations.json", {
            **meta, "source_doc": "CrestRec by the GSGL Official Discord Advisor Team",
            "units": recs, "notes": notes})
        write_json(self.out / "units.json", {**meta, "units": units})
        self.summary.append(f"{len(palace)} stages, {len(crests)} crests, {len(units)} units")

    def _stages(self) -> list[dict]:
        return read_json(self.out / "crest_palace.json", {}).get("stages", [])

    def guides(self):
        stages = self._stages()
        old = {g["slug"]: g for g in read_json(self.out / "stage_guides.json", {})
               .get("stages", [])}
        guides = []
        for i, s in enumerate(stages):
            self.progress(f"Stage guides: {s['name']}", i, len(stages))
            try:
                if not re.match(r"^[a-z0-9-]+$", s["slug"]):
                    raise ValueError("odd slug")
                g = scrape.parse_stage_guide(self.page(f"/stages/{s['slug']}/"), s)
                if not g["summary"] and not g["roles"]:
                    raise ValueError("page had no guide")
                guides.append(g)
            except Cancelled:
                raise
            except Exception as e:  # noqa: BLE001 - keep the old guide, report it
                self.failed.append((s["name"], str(e)))
                if s["slug"] in old:
                    guides.append(old[s["slug"]])
        self.progress("Stage guides", len(stages), len(stages))
        write_json(self.out / "stage_guides.json", {
            "source": f"{SITE}/stages/crest-palace/", "built": date.today().isoformat(),
            "note": "Stage guides from GS Companion (based on the GSGL Official Discord "
                    "Advisor Team's guides). Local reference only.",
            "stages": guides})
        self.summary.append(f"{len(guides)} stage guides")

    def bosses(self):
        """The guide for every Giant Boss, Story Challenge and Event quest in
        stage_catalog.json -> other_guides.json (same shape as stage_guides.json)."""
        stages = []
        for cat in read_json(CATALOG, {}).get("categories", []):
            for s in cat.get("stages", []):
                stages.append({"name": s["name"], "difficulty": "", "slug": s["slug"],
                               "boss": s.get("boss", ""),
                               "url": f"{SITE}/stages/{s['slug']}/"})
        path = self.out / "other_guides.json"
        old = {g["slug"]: g for g in read_json(path, {}).get("stages", [])}
        guides = []
        for i, s in enumerate(stages):
            self.progress(f"Boss and event guides: {s['name']}", i, len(stages))
            try:
                if not re.match(r"^[a-z0-9-]+$", s["slug"]):
                    raise ValueError("odd slug")
                g = scrape.parse_stage_guide(self.page(f"/stages/{s['slug']}/"), s)
                if not g["summary"] and not g["roles"] and not g["waves"]:
                    raise ValueError("page had no guide")
                guides.append(g)
            except Cancelled:
                raise
            except Exception as e:  # noqa: BLE001 - keep the old guide, report it
                self.failed.append((s["name"], str(e)))
                if s["slug"] in old:
                    guides.append(old[s["slug"]])
        self.progress("Boss and event guides", len(stages), len(stages))
        write_json(path, {
            "source": f"{SITE}/stages/", "built": date.today().isoformat(),
            "note": "Giant Boss, Story Challenge and Event guides from GS Companion. "
                    "Local reference only.",
            "stages": guides})
        self.summary.append(f"{len(guides)} boss and event guides")

    def equips(self):
        """Every equip (name, rarity, type, cooldown, skill, passives, where to get it) from
        the site's own list (/equips.json) -> equips.json."""
        self.progress("Equips", 0, 1)
        raw = json.loads(self.page("/equips.json"))
        keep = ("id", "name", "aka", "slug", "star", "type", "ct", "img", "loc", "secret",
                "skill", "passives")
        out = []
        for e in raw if isinstance(raw, list) else []:
            if not (isinstance(e, dict) and e.get("name")
                    and re.fullmatch(r"[a-z0-9-]+", str(e.get("slug", "")))):
                continue
            out.append({k: e[k] for k in keep if k in e})
        if len(out) < 500:  # never replace good data with a half-read page
            self.failed.append(("equips", f"list looked wrong ({len(out)} equips)"))
            return
        write_json(self.out / "equips.json", {
            "source": f"{SITE}/equips/", "built": date.today().isoformat(),
            "note": META_NOTE, "equips": out})
        self.progress("Equips", 1, 1)
        self.summary.append(f"{len(out)} equips")

    def calc(self):
        """The data the site's Team Builder and Damage Calc run on: every unit's structured
        effects (/units.json), the calculator's equips (/calc-equips.json) and the unit /
        enemy / crest lists embedded in the calculator page. -> team_*.json, calc_*.json"""
        steps = 4
        self.progress("Team and damage data", 0, steps)
        units = json.loads(self.page("/units.json"))
        self.progress("Team and damage data", 1, steps)
        equips = json.loads(self.page("/calc-equips.json"))
        self.progress("Team and damage data", 2, steps)
        html = self.page("/damage-calc/")
        self.progress("Team and damage data", 3, steps)
        blobs = {}
        for key in ("calc-data", "enemy-data", "crest-data"):
            m = re.search(r'<script[^>]*\bid="%s"[^>]*>(.*?)</script>' % key, html, re.S)
            blobs[key] = json.loads(m.group(1)) if m else None
        if (not isinstance(units, list) or len(units) < 200 or not isinstance(equips, list)
                or len(equips) < 500 or not all(isinstance(blobs[k], list) and blobs[k]
                                                for k in blobs)):
            self.failed.append(("calc", "the Team Builder / Damage Calc data looked wrong"))
            return
        meta = {"source": SITE, "built": date.today().isoformat(), "note": META_NOTE}
        write_json(self.out / "team_units.json", {**meta, "units": units})
        write_json(self.out / "calc_equips.json", {**meta, "equips": equips})
        write_json(self.out / "calc_units.json", {**meta, "units": blobs["calc-data"]})
        write_json(self.out / "calc_enemies.json", {**meta, "enemies": blobs["enemy-data"]})
        write_json(self.out / "calc_crests.json", {**meta, "crests": blobs["crest-data"]})
        self.progress("Team and damage data", steps, steps)
        self.summary.append(f"{len(units)} team units, {len(equips)} calc equips, "
                            f"{len(blobs['enemy-data'])} enemies, {len(blobs['crest-data'])} crests")

    def units(self):
        units = read_json(self.out / "units.json", {}).get("units", [])
        path = self.out / "unit_details.json"
        have = {} if self.all_units else read_json(path, {}).get("units", {})
        todo = [u for u in units if u["name"] not in have]
        keep = {u["name"] for u in units}
        details = {k: v for k, v in have.items() if k in keep}

        def save():
            write_json(path, {"source": f"{SITE}/units/", "built": date.today().isoformat(),
                              "note": META_NOTE, "units": details})
        try:
            for i, u in enumerate(todo):
                self.progress(f"Unit details: {u['name']}", i, len(todo))
                try:
                    if not re.match(r"^[a-z0-9-]+$", u["slug"]):
                        raise ValueError("odd slug")
                    d = scrape.parse_unit_page(self.page(f"/units/{u['slug']}/"), u)
                    if not d["moves"] and not d["tags"]:
                        raise ValueError("page had no kit")
                    details[u["name"]] = d
                except Cancelled:
                    raise
                except Exception as e:  # noqa: BLE001
                    self.failed.append((u["name"], str(e)))
                if i % 20 == 19:
                    save()
        finally:
            save()
        self.progress("Unit details", len(todo), len(todo))
        self.summary.append(f"{len(details)} unit details ({len(todo)} fetched)")

    def picture_paths(self) -> list[str]:
        """Every /images/... path the data files use."""
        out: set[str] = set()
        for u in read_json(self.out / "units.json", {}).get("units", []):
            if u.get("unit_id"):
                out.add(f"/images/unit_thumbnail_{u['unit_id']}.png")
        for s in self._stages():
            if s.get("stage_id"):
                out.add(f"/images/stages/banner_{s['stage_id']}.webp")
        for c in read_json(self.out / "crests.json", {}).get("crests", []):
            if c.get("icon", "").startswith(SITE + "/images/"):
                out.add(c["icon"][len(SITE):])
        for lv in scrape.LEVELS:
            out.add(f"/images/crests/{lv.lower().replace('+', 'p')}.png")
        # Giant Boss / Story / Event pictures (gsc_app/stage_catalog.json).
        for cat in read_json(Path(__file__).with_name("stage_catalog.json"), {}).get(
                "categories", []):
            for s in cat.get("stages", []):
                if s.get("image") and re.fullmatch(r"[A-Za-z0-9_./-]+\.(?:png|webp|jpg)",
                                                   s["image"]) and ".." not in s["image"]:
                    out.add(f"/images/{s['image']}")
        for e in read_json(self.out / "equips.json", {}).get("equips", []):
            if re.fullmatch(r"[A-Za-z0-9_]+", str(e.get("img", ""))):
                out.add(f"/images/{e['img']}.png")
        # Team & Damage: element, race and equip-type icons, the calculator's equips and
        # units, and its enemy icons.
        for n in ("fire", "water", "earth", "light", "dark"):
            out.add(f"/images/elem_{n}.png")
        for n in ("human", "demon", "god", "spirit", "machine", "dragon", "beast", "giant"):
            out.add(f"/images/race_{n}.png")
        for n in ("phys", "mag", "def", "heal", "supp"):
            out.add(f"/images/lbstone_{n}.png")
        for e in read_json(self.out / "calc_equips.json", {}).get("equips", []):
            if re.fullmatch(r"[A-Za-z0-9_]+", str(e.get("img", ""))):
                out.add(f"/images/{e['img']}.png")
        for u in read_json(self.out / "calc_units.json", {}).get("units", []):
            if re.fullmatch(r"[A-Za-z0-9_]+", str(u.get("thumb", ""))):
                out.add(f"/images/{u['thumb']}.png")
        for e in read_json(self.out / "calc_enemies.json", {}).get("enemies", []):
            ic = str(e.get("icon") or "")
            if re.fullmatch(r"/images/[A-Za-z0-9_./-]+\.(?:png|webp|jpg)", ic) and ".." not in ic:
                out.add(ic)
        text = "".join((self.out / f).read_text(encoding="utf-8")
                       for f in ("stage_guides.json", "other_guides.json")
                       if (self.out / f).exists())
        out.update(re.findall(r'"(/images/[A-Za-z0-9_./-]+\.(?:png|webp|jpg))"', text))
        return sorted(p for p in out if ".." not in p)

    def pictures(self):
        from PIL import Image
        root = (self.out / "images").resolve()
        todo = []
        for p in self.picture_paths():
            dest = (root / p[len("/images/"):]).resolve()
            if root in dest.parents and not dest.exists():
                todo.append((p, dest))
        for i, (p, dest) in enumerate(todo):
            self.progress("Pictures", i, len(todo))
            try:
                data = self._get(SITE + p, MAX_IMAGE)
                with Image.open(io.BytesIO(data)) as im:
                    im.verify()
                dest.parent.mkdir(parents=True, exist_ok=True)
                part = dest.with_suffix(dest.suffix + ".part")
                part.write_bytes(data)
                part.replace(dest)
            except Cancelled:
                raise
            except Exception as e:  # noqa: BLE001
                self.failed.append((p, str(e)))
        self.progress("Pictures", len(todo), len(todo))
        self.summary.append(f"{len(todo)} new pictures")


def main(argv: list[str]) -> int:
    out = Path(__file__).resolve().parents[1] / "data" / "gscompanion"
    parts = PARTS
    if "--out" in argv:
        out = Path(argv[argv.index("--out") + 1])
    if "--only" in argv:
        parts = tuple(argv[argv.index("--only") + 1].split(","))
    last = [""]

    def progress(text, done, total):
        part = text.split(":")[0]
        if part != last[0] or done == total or done % 25 == 0:
            print(f"{text}  {done}/{total}", flush=True)
            last[0] = part

    up = Updater(out, progress, all_units="--all-units" in argv, parts=parts)
    ok = up.run()
    for s in up.summary:
        print(s)
    for what, err in up.failed:
        print(f"FAILED {what}: {err}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
