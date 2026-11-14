"""Build ReRun's GS Companion reference data from scraped pages.

Input:  data/gscompanion/raw/*.md   (markdown of gscompanion.com pages)
Output: data/gscompanion/*.json     (loaded by rerun/gsc_data.py)

Refresh: re-scrape the pages below as markdown into raw/ (same file names), then
    python tools/gscompanion_build.py

    raw/crest_palace.md  https://gscompanion.com/stages/crest-palace/
    raw/crests.md        https://gscompanion.com/crests/
    raw/units.md         https://gscompanion.com/units/

On crest_palace.md, stages open on the scrape day read "Open today" instead of a
weekday; the first line comment `site's "today" = <Weekday>` tells the builder which day.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "gscompanion" / "raw"
OUT = ROOT / "data" / "gscompanion"
SITE = "https://gscompanion.com"
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
LEVELS = ["Lv1", "Lv1+", "Lv2", "Lv2+", "Lv3", "Lv3+", "Lv4", "Lv4+", "Lv5", "Lv5+"]


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def split_tags(s: str) -> list[str]:
    """'Taunt KillerEarth Killer' -> ['Taunt Killer', 'Earth Killer'] (tags are glued together)."""
    return [t.strip() for t in re.split(r"(?<=[a-z0-9)])(?=[A-Z])", s) if t.strip()]


# --- Crest Palace -----------------------------------------------------------------

def parse_crest_palace(md: str) -> list[dict]:
    m = re.search(r'today" = (\w+)', md)
    today = m.group(1) if m else None
    stages = []
    tile = re.compile(
        r"\[!\[\]\((?P<banner>[^)]+)\)\\\\\s*\\\\\s*(?P<head>.+?)\\\\\s*\\\\\s*(?P<name>.+?)"
        r"(?:\\\\\s*\\\\\s*(?P<tags>.+?))?\]\((?P<url>https://gscompanion\.com/stages/[^)]+)\)",
        re.S)
    for t in tile.finditer(md):
        head = t["head"].strip()
        hm = re.match(r"(.+?)(NOVA|Extreme|PRO)(.+)$", head)
        boss, diff, when = hm.group(1), hm.group(2), hm.group(3).strip()
        if when == "Open today":
            when = today
        days = DAYS[:] if when == "Always open" else [when]
        banner_id = re.search(r"banner_(\d+)", t["banner"])
        stages.append({
            "name": t["name"].strip(),
            "difficulty": diff.upper(),
            "boss": boss.strip(),
            "days": days,
            "hazards": split_tags(t["tags"]) if t["tags"] else [],
            "stage_id": banner_id.group(1) if banner_id else None,
            "slug": t["url"].rstrip("/").rsplit("/", 1)[1],
            "url": t["url"],
        })
    return stages


# --- Crests -----------------------------------------------------------------------

DROP_LINK = re.compile(r"\[(.+?) \\\[(\w+)\\\]\]\((https://gscompanion\.com/stages/([^)/]+)/?)\)")


def parse_crests(md: str) -> tuple[list[dict], dict[str, list[str]]]:
    lines = md.splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith("## Crests "))

    # Recommendations: unit block, then a numbered list of crest links.
    recs: dict[str, list[str]] = {}
    unit = None
    for l in lines[:start]:
        um = re.match(r"\[!\[\]\([^)]*\)\*\*(.+?)\*\*\]\(", l)
        if um:
            unit = um.group(1)
            recs[unit] = []
            continue
        cm = re.match(r"\d+\. \[(.+?)\]\(", l)
        if cm and unit:
            recs[unit].append(cm.group(1))

    crests: list[dict] = []
    kind, event, cur, last = "regular", None, None, None
    kinds = {"Crests": "regular", "Unique Crests": "unique", "Event Crests": "event"}
    for l in lines[start:]:
        s = l.strip()
        if s.startswith("## "):
            kind = kinds.get(re.sub(r"\s+\d+$", "", s[3:]), kind)
            event, cur = None, None
            continue
        if s.startswith("### "):
            event = s[4:].strip()
            if event == "Other events":
                event = None
            cur = None
            continue
        if not s or s.startswith(("**Yay", "Share thoughts", "No crests match")):
            continue
        hm = re.match(r"!\[\]\(([^)]+)\)(.+)$", s)
        if hm:  # crest header: icon + name
            cur = {"name": hm.group(2).strip(), "kind": kind, "event": event,
                   "icon": hm.group(1), "levels": {}, "effect": None, "drops": []}
            crests.append(cur)
            last = None
            continue
        if cur is None:
            continue
        lm = re.match(r"- !\[\]\([^)]+\)(?:\*\*(Lv\d\+?)\*\* )?(.*)$", s)
        if lm:
            lv, text = lm.group(1), lm.group(2).strip()
            if lv:
                cur["levels"][lv] = text
                last = ("lv", lv)
            else:
                cur["effect"] = text
                last = ("effect", None)
            continue
        if s.startswith(("Drops:", "Crest Palace:")):
            for dm in DROP_LINK.finditer(s):
                cur["drops"].append({"stage": dm.group(1), "difficulty": dm.group(2).upper(),
                                     "slug": dm.group(4)})
            continue
        if s.startswith("Event:"):
            cur["event"] = s.split(":", 1)[1].strip()
            continue
        # continuation of the previous effect line
        if last and last[0] == "lv":
            cur["levels"][last[1]] += "\n" + s
        elif last and last[0] == "effect":
            cur["effect"] += "\n" + s

    for c in crests:
        c["slug"] = slugify(c["name"])
        if not c["levels"]:
            c.pop("levels")
        if c["effect"] is None:
            c.pop("effect")
        if c["event"] is None:
            c.pop("event")
    return crests, recs


# --- Units ------------------------------------------------------------------------

def parse_units(md: str) -> list[dict]:
    units = []
    element = None
    link = re.compile(r'\[!\[(?P<alt>[^\]]*)\]\((?P<img>[^)]+)\)(?P<text>[^\]]*)\]'
                      r'\((?P<url>https://gscompanion\.com/units/[^ )]+) "(?P<name>[^"]+)"\)')
    for l in md.splitlines():
        hm = re.match(r"## (\w+) \d+$", l.strip())
        if hm:
            element = hm.group(1)
            continue
        for u in link.finditer(l):
            name = u["name"]
            tag = u["text"][len(name):].strip() if u["text"].startswith(name) else ""
            tid = re.search(r"unit_thumbnail_(\d+)", u["img"])
            units.append({"name": name, "element": element, "tag": tag or None,
                          "unit_id": tid.group(1) if tid else None,
                          "slug": u["url"].rstrip("/").rsplit("/", 1)[1], "url": u["url"]})
    return units


def main() -> int:
    read = lambda n: (RAW / n).read_text(encoding="utf-8")
    palace = parse_crest_palace(read("crest_palace.md"))
    crests, recs = parse_crests(read("crests.md"))
    units = parse_units(read("units.md"))

    # Cross-link: which crests drop at each palace stage.
    by_slug = {s["slug"]: s for s in palace}
    for s in palace:
        s["crests"] = []
    for c in crests:
        for d in c["drops"]:
            if d["slug"] in by_slug:
                by_slug[d["slug"]]["crests"].append(c["name"])

    meta = {"source": SITE, "built": date.today().isoformat(),
            "note": "Fan-site reference data; the game itself is the authority."}
    files = {
        "crest_palace.json": {**meta, "reset_timezone": "America/Los_Angeles (per site)",
                              "levels": LEVELS, "stages": palace},
        "crests.json": {**meta, "levels": LEVELS, "crests": crests},
        "crest_recommendations.json": {**meta,
                                       "source_doc": "CrestRec by the GSGL Official Discord Advisor Team",
                                       "units": recs},
        "units.json": {**meta, "units": units},
    }
    for name, data in files.items():
        (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"crest palace stages: {len(palace)}  crests: {len(crests)}  "
          f"recommendations: {len(recs)}  units: {len(units)}")
    unlinked = [d["stage"] for c in crests for d in c["drops"] if d["slug"] not in by_slug]
    if unlinked:
        print("drops at stages not in crest_palace.md:", sorted(set(unlinked)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
