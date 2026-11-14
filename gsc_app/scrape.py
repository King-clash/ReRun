"""Read GS Companion's pages (server-rendered HTML) into the app's data files.

Each parse_* function takes a page's HTML and returns plain data in the same shape the
app already reads (the same shape tools/gscompanion_build.py makes from markdown):
  parse_palace      /stages/crest-palace/  -> crest_palace.json "stages"
  parse_crests      /crests/               -> crests.json "crests" + crest_recommendations
  parse_units       /units/                -> units.json "units"
  parse_stage_guide /stages/<slug>/        -> stage_guides.json, one stage
  parse_unit_page   /units/<slug>/         -> unit_details.json, one unit
Nothing here touches the network; update_data.py does the fetching."""
from __future__ import annotations

import re
from html.parser import HTMLParser

SITE = "https://gscompanion.com"
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
LEVELS = ["Lv1", "Lv1+", "Lv2", "Lv2+", "Lv3", "Lv3+", "Lv4", "Lv4+", "Lv5", "Lv5+"]
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
        "source", "track", "wbr"}


# --- a tiny DOM, enough for the site's pages --------------------------------------------
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
            if isinstance(k, str):
                out.append(k)
            elif k.tag == "br":
                out.append("\n")
            elif k.tag not in ("svg", "script", "style"):
                out.append(k.text())
        return "".join(out)

    def clean(self) -> str:
        return re.sub(r"\s+", " ", self.text()).strip()

    def lines(self) -> str:
        """Text with <br> kept as line breaks."""
        return "\n".join(re.sub(r"[ \t\r\f\v]+", " ", s).strip()
                         for s in self.text().split("\n") if s.strip())

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

    def ctext(self, tag: str | None = None, cls: str | None = None) -> str:
        n = self.first(tag, cls)
        return n.clean() if n is not None else ""


class _Tree(HTMLParser):
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
    t = _Tree()
    t.feed(text)
    t.close()
    return t.root


def main_of(text: str) -> Node:
    root = parse_html(text)
    return root.first("main") or root


def img_src(node: Node | None) -> str:
    img = node if node is not None and node.tag == "img" else (
        node.first("img") if node is not None else None)
    src = img.attrs.get("src", "") if img is not None else ""
    return src if src.startswith("/images/") else ""


def slug_of(href: str, kind: str) -> str:
    m = re.match(rf"^(?:{re.escape(SITE)})?/{kind}/([a-z0-9-]+)/?$", href)
    return m.group(1) if m else ""


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def section(root: Node, heading: str) -> Node | None:
    for sec in root.all("section"):
        h2 = sec.first("h2")
        if h2 is not None and h2.clean().lower() == heading.lower():
            return sec
    return None


# --- list pages -------------------------------------------------------------------------
def parse_palace(text: str) -> list[dict]:
    stages = []
    for a in main_of(text).all("a", "sc"):
        slug = slug_of(a.attrs.get("href", ""), "stages")
        if not slug:
            continue
        day = a.attrs.get("data-day", "")
        banner = re.search(r"banner_(\d+)", img_src(a.first("div", "sc-art")))
        haz = a.first("div", "sc-haz")
        stages.append({
            "name": a.ctext("div", "sc-name"),
            "difficulty": a.attrs.get("data-diff", "").upper(),
            "boss": a.attrs.get("data-boss", "") or a.ctext("span", "sc-boss"),
            "days": [day] if day in DAYS else DAYS[:],
            "hazards": [s.clean() for s in haz.children("span")] if haz is not None else [],
            "stage_id": banner.group(1) if banner else None,
            "slug": slug,
            "url": f"{SITE}/stages/{slug}/",
        })
    return stages


def parse_crests(text: str, notes: dict | None = None) -> tuple[list[dict], dict[str, list[str]]]:
    """notes (optional dict) gets each unit's remarks: {'Genos': ['Player EXP UP: Needs to
    be the leader'], 'Fosly': ['Any stat specific crest']}."""
    main = main_of(text)
    recs: dict[str, list[str]] = {}
    for art in main.all("article", "rec"):
        name = art.first("a", "rec-unit")
        if name is None:
            continue
        unit = name.ctext("b") or name.clean()
        ol = art.first("ol", "crec")
        recs[unit] = []
        for li in (ol.children("li") if ol is not None else []):
            a = li.first("a")
            rest = li.clean()[len(a.clean()):].strip() if a is not None else li.clean()
            if a is not None:
                recs[unit].append(a.clean())
            if rest and notes is not None:
                notes.setdefault(unit, []).append(f"{a.clean()}: {rest}" if a else rest)

    crests: list[dict] = []
    kinds = {"Crests": "regular", "Unique Crests": "unique", "Event Crests": "event"}
    pane = next((s for s in main.all("section") if s.attrs.get("id") == "all"), None)
    for group in (pane.all("div", "cr-group") if pane is not None else []):
        h2 = group.first("h2")
        title = re.sub(r"\s+\d+$", "", h2.clean()) if h2 is not None else ""
        kind = kinds.get(title, "regular")
        event = None
        for node in [n for sub in group.children("div", "cr-sub") for n in sub.kids]:
            if not isinstance(node, Node):
                continue
            if node.tag == "h3":
                event = node.clean()
                if event == "Other events":
                    event = None
                continue
            if "cr-list" not in node.classes:
                continue
            for d in node.children("details", "cr"):
                c = {"name": d.ctext("span", "cr-name"), "kind": kind, "event": event,
                     "icon": SITE + img_src(d.first("summary")), "levels": {},
                     "effect": None, "drops": []}
                for li in d.all("li"):
                    lv = li.ctext("b")
                    span = li.children("span")
                    val = span[-1].lines() if span else ""
                    if lv in LEVELS:
                        c["levels"][lv] = val
                    elif val:
                        c["effect"] = val
                p = d.first("p", "cr-drops")
                if p is not None:
                    t = p.clean()
                    if t.startswith("Event:"):
                        c["event"] = t.split(":", 1)[1].strip()
                    for a in p.all("a"):
                        slug = slug_of(a.attrs.get("href", ""), "stages")
                        m = re.match(r"(.+?) \[(\w+)\]$", a.clean())
                        if slug and m:
                            c["drops"].append({"stage": m.group(1),
                                               "difficulty": m.group(2).upper(), "slug": slug})
                c["slug"] = slugify(c["name"])
                if not c["levels"]:
                    c.pop("levels")
                if c["effect"] is None:
                    c.pop("effect")
                if c["event"] is None:
                    c.pop("event")
                crests.append(c)
    return crests, recs


def parse_units(text: str) -> list[dict]:
    units = []
    for grp in main_of(text).all("section", "kf-group"):
        h2 = grp.first("h2")
        element = h2.clean().split()[0] if h2 is not None and h2.clean() else None
        for a in grp.all("a", "unit-card"):
            slug = slug_of(a.attrs.get("href", ""), "units")
            if not slug:
                continue
            tid = re.search(r"unit_thumbnail_(\d+)", img_src(a))
            units.append({"name": a.attrs.get("title") or a.ctext("span", "name"),
                          "element": element, "tag": a.ctext("span", "rar") or None,
                          "unit_id": tid.group(1) if tid else None, "slug": slug,
                          "url": f"{SITE}/units/{slug}/"})
    return units


def link_stage_crests(stages: list[dict], crests: list[dict]) -> None:
    by_slug = {s["slug"]: s for s in stages}
    for s in stages:
        s["crests"] = []
    for c in crests:
        for d in c.get("drops", []):
            if d["slug"] in by_slug:
                by_slug[d["slug"]]["crests"].append(c["name"])


# --- one stage's guide ------------------------------------------------------------------
def _face(a: Node) -> dict:
    el = next((c[3:] for c in a.classes if c.startswith("el-")), "")
    return {"name": a.attrs.get("title") or a.clean(),
            "slug": slug_of(a.attrs.get("href", ""), "units"), "element": el,
            "image": img_src(a)}


def _wave(w: Node) -> dict:
    top = w.first("div", "wave-top")
    name = top.first("div", "wave-name") if top is not None else None
    label = name.ctext("span", "wl") if name is not None else ""
    title = name.ctext("b") if name is not None else ""
    muted = [s.clean() for s in name.children("span", "muted")] if name is not None else []
    body = w.first("div", "wave-body")
    chips, notes, enemies = [], [], []
    if body is not None:
        for box in body.children("div", "chips"):
            for c in box.children("span", "chip"):
                tone = next((x[5:] for x in c.classes if x.startswith("tone-")), "")
                chips.append({"text": c.clean(), "tone": tone})
        notes = [p.clean() for p in body.children("p") if p.clean()]
        for foe in body.all("div", "foe"):
            fn = foe.first("span", "fn")
            if fn is None:
                continue
            first = fn.first("span")
            nm = first.ctext("b") if first is not None else ""
            count = first.clean()[len(nm):].strip().replace("×", "x") if first else ""
            stats = {s.attrs["data-l"]: s.clean() for s in fn.all("span")
                     if s.attrs.get("data-l")}
            enemies.append({"name": nm, "count": count, "info": fn.ctext("small"),
                            "stats": stats, "traits": [c.clean() for c in fn.all("span", "chip")],
                            "image": img_src(foe.first("span", "eface"))})
    return {"label": label, "name": title, "details": [m for m in muted if m],
            "chips": chips, "notes": notes, "enemies": enemies,
            "image": img_src(top.first("span", "eface")) if top is not None else ""}


def parse_stage_guide(text: str, stage: dict) -> dict:
    main = main_of(text)
    head = main.first("header", "st-head")
    facts, tags, drops = {}, [], None
    if head is not None:
        dl = head.first("dl", "facts")
        if dl is not None:
            facts = {a.clean(): b.clean() for a, b in zip(dl.children("dt"), dl.children("dd"))}
        chips = head.first("div", "chips")
        tags = [c.clean() for c in chips.children("span", "chip")] if chips is not None else []
        drops = head.first("img", "st-drops")
    waves_sec = section(main, "Waves")
    roles = []
    rec = section(main, "Recommended units")
    for g in (rec.all("div", "pick-group") if rec is not None else []):
        also = g.first("details", "also")
        roles.append({
            "role": g.ctext("h3") or g.attrs.get("data-role", ""),
            "picks": [_face(a) for box in g.children("div", "faces")
                      for a in box.children("a", "face")],
            "also": [_face(a) for a in also.all("a", "face")] if also is not None else [],
        })
    teams = []
    ex = section(main, "Example teams")
    for t in (ex.children("div", "team") if ex is not None else []):
        box = t.first("div", "faces")
        note = t.children("p", "fine")
        builder = next((a.attrs.get("href", "") for a in t.all("a")
                        if a.attrs.get("href", "").startswith("/team-builder/")), "")
        teams.append({"units": [_face(a) for a in box.children("a", "face")] if box else [],
                      "note": note[0].clean() if note else "",
                      "team_builder": SITE + builder if builder else ""})
    src = main.first("p", "sources")
    source = {}
    if src is not None:
        a = src.first("a")
        source = {"text": src.clean(), "url": a.attrs.get("href", "") if a is not None else ""}
    return {
        "name": stage["name"], "difficulty": stage["difficulty"], "slug": stage["slug"],
        "url": stage["url"], "boss": stage.get("boss", ""),
        "subtitle": head.ctext("p", "sub") if head is not None else "", "tags": tags,
        "facts": facts, "summary": main.ctext("p", "summary"),
        "drops_image": drops.attrs.get("src", "") if drops is not None else "",
        "drops_text": drops.attrs.get("alt", "") if drops is not None else "",
        "waves": [_wave(w) for w in waves_sec.children("div", "wave")] if waves_sec else [],
        "roles": roles, "teams": teams, "source": source,
    }


# --- one unit's page --------------------------------------------------------------------
def parse_unit_page(text: str, unit: dict) -> dict:
    main = main_of(text)
    head = main.first("header", "unit-head")
    sub = head.ctext("p", "sub") if head is not None else ""
    # "No. 1069 Water · Human · Ascended"
    parts = [p.strip() for p in re.sub(r"^No\.\s*\d+\s*", "", sub).split("·")]
    race = parts[1] if len(parts) > 1 else ""
    no = re.match(r"No\.\s*(\d+)", sub)
    aka = [s.clean() for s in head.all("span", "aka-name")] if head is not None else []

    moves = []
    kit = section(main, "Kit")
    for mv in (kit.all("div", "move") if kit is not None else []):
        tags = {}
        for g in mv.all("span", "gtag"):
            img = g.first("img")
            if img is not None:
                tags[img.attrs.get("alt", "")] = g.clean()
        p = mv.first("p")
        moves.append({"type": mv.ctext("span", "mv-t"), "name": mv.ctext("span", "move-name"),
                      "tags": tags, "text": p.clean() if p is not None else ""})
    passives, sp = [], []
    if kit is not None:
        lists = kit.children("ul", "passives")
        heads = [h.ctext("span", "mv-t") for h in kit.children("h3", "kit-h")]
        for h, ul in zip(heads, lists):
            items = []
            for li in ul.children("li"):
                b = li.first("b")
                nm = b.clean() if b is not None else ""
                items.append({"name": nm, "text": li.clean()[len(nm):].strip()})
            (sp if h == "SP Art" else passives).extend(items)

    effects = []
    for grp in main.all("div", "fx-group"):
        src = grp.ctext("span", "mv-t")
        for li in grp.all("li"):
            kind = "debuff" if "debuff" in li.classes else "buff"
            effects.append({"from": src, "effect": li.ctext("span", "fx-label"),
                            "target": li.ctext("span", "fx-meta"),
                            "value": li.ctext("span", "fx-val"), "kind": kind})

    side = main.first("aside")
    stats, details, slots, tags, tw = {}, {}, [], {}, {}
    if side is not None:
        for tbl in side.all("table", "stats"):
            for tr in tbl.all("tr"):
                k, v = tr.ctext("th"), tr.ctext("td")
                (details if "details" in tbl.classes else stats)[k] = v
        ul = side.first("ul", "slots")
        slots = [li.clean() for li in ul.children("li")] if ul is not None else []
        for g in side.all("div", "tag-group"):
            tags[g.ctext("span", "tg-name")] = [c.clean() for c in g.children("span", "chip")]
        t = side.first("div", "tw")
        if t is not None:
            tw = {"name": t.ctext("a", "tw-name"), "kind": t.ctext("small"),
                  "text": t.ctext("p"),
                  "passives": [li.clean() for li in t.all("li")]}
    released = ""
    for p in main.all("p", "voice"):
        if p.ctext("span", "tg-name") == "Released":
            released = p.clean().removeprefix("Released").strip()
    return {"name": unit["name"], "slug": unit["slug"], "no": no.group(1) if no else "",
            "race": race, "aka": aka, "moves": moves, "passives": passives, "sp_art": sp,
            "effects": effects, "stats": stats, "details": details, "slots": slots,
            "tags": tags, "true_weapon": tw, "released": released}
