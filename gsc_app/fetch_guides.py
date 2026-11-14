"""Download the Crest Palace stage guides from GS Companion, for the app to show offline.

    py gsc_app/fetch_guides.py            (only stages not saved yet)
    py gsc_app/fetch_guides.py --refresh  (fetch every stage page again)

For each stage in data/gscompanion/crest_palace.json it fetches the stage's own page
(gscompanion.com/stages/<slug>/), keeps the page in data/gscompanion/raw/stages/<slug>.html
and writes everything it understood to data/gscompanion/stage_guides.json:
  summary (strategy), boss facts, every wave (gimmicks, notes, enemies), recommended units
  by role ("Also fits" too), example teams with their notes, and the guide it credits.
Then it saves the pictures those guides use (unit thumbnails, enemy faces, crest drops) the
same way fetch_images.py does. One request at a time with a pause between them.
The guides are the site's / the GSGL advisor team's: they stay in data/ (git-ignored).
"""
from __future__ import annotations

import html
import json
import re
import sys
import time
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_images  # noqa: E402  (same folder: reuse its safe image saving)

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "gscompanion"
RAW = DATA / "raw" / "stages"
OUT = DATA / "stage_guides.json"
SITE = "https://gscompanion.com"
PAUSE_S = 0.6
MAX_BYTES = 3_000_000
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) page-cache/1.0"}
SLUG_RE = re.compile(r"^[a-z0-9-]+$")
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
        "source", "track", "wbr"}


# --- a tiny DOM, enough to read the site's server-rendered pages -----------------------
class Node:
    def __init__(self, tag: str, attrs: dict, parent: "Node | None"):
        self.tag, self.attrs, self.parent = tag, attrs, parent
        self.kids: list["Node | str"] = []

    @property
    def classes(self) -> set[str]:
        return set((self.attrs.get("class") or "").split())

    def text(self) -> str:
        out = []
        for k in self.kids:
            out.append(k if isinstance(k, str) else k.text())
        return "".join(out)

    def clean(self) -> str:
        return re.sub(r"\s+", " ", self.text()).strip()

    def all(self, tag: str | None = None, cls: str | None = None):
        for k in self.kids:
            if isinstance(k, Node):
                if (tag is None or k.tag == tag) and (cls is None or cls in k.classes):
                    yield k
                yield from k.all(tag, cls)

    def first(self, tag: str | None = None, cls: str | None = None) -> "Node | None":
        return next(self.all(tag, cls), None)

    def children(self, tag: str | None = None, cls: str | None = None) -> list["Node"]:
        return [k for k in self.kids if isinstance(k, Node)
                and (tag is None or k.tag == tag) and (cls is None or cls in k.classes)]


class Tree(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("root", {}, None)
        self.cur = self.root

    def handle_starttag(self, tag, attrs):
        node = Node(tag, {k: v or "" for k, v in attrs}, self.cur)
        self.cur.kids.append(node)
        if tag not in VOID:
            self.cur = node

    def handle_startendtag(self, tag, attrs):
        self.cur.kids.append(Node(tag, {k: v or "" for k, v in attrs}, self.cur))

    def handle_endtag(self, tag):
        n = self.cur
        while n is not None and n.tag != tag:
            n = n.parent
        if n is not None and n.parent is not None:
            self.cur = n.parent

    def handle_data(self, data):
        self.cur.kids.append(data)


def parse_html(text: str) -> Node:
    t = Tree()
    t.feed(text)
    t.close()
    return t.root


# --- reading one stage page -------------------------------------------------------------
def img_src(node: Node | None) -> str:
    img = node.first("img") if node is not None else None
    src = img.attrs.get("src", "") if img is not None else ""
    return src if src.startswith("/images/") else ""


def face(a: Node) -> dict:
    """<a class="face el-Water" href="/units/beta/" title="Beta"><img ...><span>Beta</span></a>"""
    href = a.attrs.get("href", "")
    m = re.match(r"^/units/([a-z0-9-]+)/?$", href)
    el = next((c[3:] for c in a.classes if c.startswith("el-")), "")
    return {"name": a.attrs.get("title") or a.clean(), "slug": m.group(1) if m else "",
            "element": el, "image": img_src(a)}


def section(root: Node, heading: str) -> Node | None:
    for sec in root.all("section"):
        h2 = sec.first("h2")
        if h2 is not None and h2.clean().lower() == heading.lower():
            return sec
    return None


def read_wave(w: Node) -> dict:
    top = w.first("div", "wave-top")
    name = top.first("div", "wave-name") if top is not None else None
    label = name.first("span", "wl").clean() if name is not None and name.first("span", "wl") else ""
    title = name.first("b").clean() if name is not None and name.first("b") else ""
    muted = [s.clean() for s in name.children("span", "muted")] if name is not None else []
    body = w.first("div", "wave-body")
    chips, notes, enemies = [], [], []
    if body is not None:
        chipbox = body.children("div", "chips")
        for box in chipbox:
            for c in box.children("span", "chip"):
                tone = next((x[5:] for x in c.classes if x.startswith("tone-")), "")
                chips.append({"text": c.clean(), "tone": tone})
        notes = [p.clean() for p in body.children("p") if p.clean()]
        for foe in body.all("div", "foe"):
            fn = foe.first("span", "fn")
            if fn is None:
                continue
            first = fn.first("span")
            nm = first.first("b").clean() if first is not None and first.first("b") else ""
            count = ""
            if first is not None:
                rest = first.clean()[len(nm):].strip()
                count = rest.replace("×", "x").strip()
            info = fn.first("small").clean() if fn.first("small") else ""
            stats = {s.attrs.get("data-l", ""): s.clean()
                     for s in fn.all("span") if s.attrs.get("data-l")}
            res = [c.clean() for c in fn.all("span", "chip")]
            enemies.append({"name": nm, "count": count, "info": info, "stats": stats,
                            "traits": res, "image": img_src(foe.first("span", "eface"))})
    return {"label": label, "name": title, "details": [m for m in muted if m],
            "chips": chips, "notes": notes, "enemies": enemies,
            "image": img_src(top.first("span", "eface")) if top is not None else ""}


def read_stage(text: str, stage: dict) -> dict:
    root = parse_html(text)
    main = root.first("main") or root
    head = main.first("header", "st-head")
    sub = head.first("p", "sub").clean() if head is not None and head.first("p", "sub") else ""
    facts = {}
    if head is not None and head.first("dl", "facts") is not None:
        dl = head.first("dl", "facts")
        dts, dds = dl.children("dt"), dl.children("dd")
        facts = {a.clean(): b.clean() for a, b in zip(dts, dds)}
    tags = [c.clean() for c in head.first("div", "chips").children("span", "chip")] \
        if head is not None and head.first("div", "chips") is not None else []
    drops = head.first("img", "st-drops") if head is not None else None
    summary = main.first("p", "summary")

    waves_sec = section(main, "Waves")
    waves = [read_wave(w) for w in waves_sec.children("div", "wave")] if waves_sec else []

    roles = []
    rec = section(main, "Recommended units")
    if rec is not None:
        for g in rec.all("div", "pick-group"):
            h3 = g.first("h3")
            top = g.children("div", "faces")
            also = g.first("details", "also")
            roles.append({
                "role": h3.clean() if h3 is not None else g.attrs.get("data-role", ""),
                "picks": [face(a) for box in top for a in box.children("a", "face")],
                "also": [face(a) for a in also.all("a", "face")] if also is not None else [],
            })

    teams = []
    ex = section(main, "Example teams")
    if ex is not None:
        for t in ex.children("div", "team"):
            box = t.first("div", "faces")
            note = t.children("p", "fine")
            builder = next((a.attrs.get("href", "") for a in t.all("a")
                            if a.attrs.get("href", "").startswith("/team-builder/")), "")
            teams.append({"units": [face(a) for a in box.children("a", "face")] if box else [],
                          "note": note[0].clean() if note else "",
                          "team_builder": SITE + builder if builder else ""})

    src = main.first("p", "sources")
    source = {}
    if src is not None:
        a = src.first("a")
        source = {"text": src.clean(), "url": a.attrs.get("href", "") if a is not None else ""}

    return {
        "name": stage["name"], "difficulty": stage["difficulty"], "slug": stage["slug"],
        "url": stage["url"], "boss": stage.get("boss", ""), "subtitle": sub, "tags": tags,
        "facts": facts, "summary": summary.clean() if summary is not None else "",
        "drops_image": drops.attrs.get("src", "") if drops is not None else "",
        "drops_text": drops.attrs.get("alt", "") if drops is not None else "",
        "waves": waves, "roles": roles, "teams": teams, "source": source,
    }


# --- fetching ---------------------------------------------------------------------------
def fetch_page(url: str) -> str:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("too large")
    return data.decode("utf-8", errors="replace")


def guide_images(guides: list[dict]) -> list[str]:
    srcs: set[str] = set()
    for g in guides:
        srcs.add(g.get("drops_image", ""))
        for w in g["waves"]:
            srcs.add(w["image"])
            srcs.update(e["image"] for e in w["enemies"])
        for r in g["roles"]:
            srcs.update(u["image"] for u in r["picks"] + r["also"])
        for t in g["teams"]:
            srcs.update(u["image"] for u in t["units"])
    return sorted(SITE + s for s in srcs if s.startswith("/images/") and ".." not in s)


def main(argv: list[str]) -> int:
    refresh = "--refresh" in argv
    stages = json.loads((DATA / "crest_palace.json").read_text(encoding="utf-8"))["stages"]
    RAW.mkdir(parents=True, exist_ok=True)
    failed = []
    todo = [s for s in stages if refresh or not (RAW / f"{s['slug']}.html").exists()]
    print(f"{len(stages)} stages, {len(todo)} to fetch")
    for s in todo:
        if not SLUG_RE.match(s["slug"]):
            failed.append((s["slug"], "odd slug"))
            continue
        try:
            page = fetch_page(f"{SITE}/stages/{s['slug']}/")
            tmp = RAW / f"{s['slug']}.html.part"
            tmp.write_text(page, encoding="utf-8")
            tmp.replace(RAW / f"{s['slug']}.html")
            print(f"  saved {s['name']} [{s['difficulty']}]", flush=True)
        except Exception as e:  # noqa: BLE001 - report and carry on
            failed.append((s["slug"], str(e)))
        time.sleep(PAUSE_S)

    guides = []
    for s in stages:
        p = RAW / f"{s['slug']}.html"
        if not p.exists():
            continue
        g = read_stage(p.read_text(encoding="utf-8"), s)
        if not g["summary"] and not g["roles"]:
            failed.append((s["slug"], "page had no guide"))
            continue
        guides.append(g)
    doc = {"source": f"{SITE}/stages/crest-palace/", "built": time.strftime("%Y-%m-%d"),
           "note": "Stage guides from GS Companion (based on the GSGL Official Discord Advisor "
                   "Team's guides). Local reference only.",
           "stages": guides}
    tmp = OUT.with_suffix(".json.part")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(OUT)
    print(f"{len(guides)} guides written to {OUT}")

    urls = [u for u in guide_images(guides) if not fetch_images.local_path(u).exists()]
    print(f"{len(urls)} new pictures to fetch")
    for i, url in enumerate(urls, 1):
        try:
            data = fetch_images.fetch(url)
            p = fetch_images.local_path(url)
            p.parent.mkdir(parents=True, exist_ok=True)
            part = p.with_suffix(p.suffix + ".part")
            part.write_bytes(data)
            part.replace(p)
        except Exception as e:  # noqa: BLE001
            failed.append((url, str(e)))
        if i % 50 == 0 or i == len(urls):
            print(f"  {i}/{len(urls)}", flush=True)
        time.sleep(fetch_images.PAUSE_S)

    for what, err in failed:
        print(f"FAILED {what}: {err}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
