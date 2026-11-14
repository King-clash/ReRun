"""GS Companion page: today's farming, the Crest Palace week with each
stage's guide, every crest, every unit (kit and recommended crests), a team checker, a
farm planner and a crest comparison, in Rerun's iOS look.

It is a plain tk.Frame, so it works in its own window (python -m gsc_app / the exe) and
can be dropped into Rerun's tab bar later (see INTEGRATION.md).

Reads:  data/gscompanion/*.json (rerun.gsc_data.GSCData + stage_guides / unit_details),
        data/gscompanion/images/, and Rerun's unit scan <rerun>/units/roster.json.
Writes: its own settings file (window, view, filters, text size, starred units, crests
        units have, team, farm plan, compared crests). Only "Update data" downloads, when
        you press it (gsc_app/update_data.py); "Open on GSCompanion" opens your browser.
"""
from __future__ import annotations

import json
import shutil
import threading
import time
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, ttk

from PIL import Image, ImageTk

from rerun import ios
from rerun.crest_stats import game_day
from rerun.gsc_data import DAYS, GSCData
from rerun.ios import C, F, px

from .guides import Guides
from .store import MyUnits, Settings
from .team import TEAM_SIZE, TeamCheck, hazard_hits, hazards

SITE = "https://gscompanion.com"
VIEWS = ["Today", "Week", "Crests", "Units", "Team", "Planner", "Compare"]
FIND = "Find"  # search results across stages, crests and units (not a tab)
DIFFS = ["NOVA", "EXTREME", "PRO"]
DIFF_COLOR = {"NOVA": "red", "EXTREME": "orange", "PRO": "blue"}
LEVELS = ["Lv1", "Lv1+", "Lv2", "Lv2+", "Lv3", "Lv3+", "Lv4", "Lv4+", "Lv5", "Lv5+"]
ALL_KINDS = "All kinds"
ALL_ELEMENTS = "All elements"
KINDS = {"Regular": "regular", "Unique": "unique", "Event": "event"}
ELEMENTS = ["Fire", "Water", "Earth", "Light", "Dark"]
UNIT_FILTERS = ["All units", "My units", "Starred", "Rerun scan"]
SIZES = {"S": ("Small", 0.9), "M": ("Medium", 1.0), "L": ("Large", 1.2)}
MAX_UNIT_LINKS = 60
MAX_COMPARE = 3
MIN_LIST_W, MIN_DETAIL_W = 380, 300

# (key, heading, width) - widths are starting proportions; text columns stretch.
COLUMNS = {
    "Today": [("name", "Stage / crest", 250), ("difficulty", "Difficulty", 90),
              ("ready", "Ready", 80), ("units", "For your units", 260)],
    "Team": [("team", "Team", 52), ("name", "Unit", 200), ("element", "Element", 76),
             ("fit", "Fits this stage as", 280)],
    FIND: [("name", "Name", 250), ("what", "Type", 80), ("info", "Details", 320)],
    "Crests": [("name", "Crest", 220), ("kind", "Kind", 80), ("where", "Where it drops", 230),
               ("mine", "For you", 80)],
    "Units": [("mine", "★", 38), ("name", "Unit", 200), ("element", "Element", 76),
              ("tag", "Type", 56), ("picks", "Recommended crests", 300)],
    "Planner": [("name", "Crest", 190), ("stage", "Stage", 250), ("units", "For", 250)],
}
# Columns that take the spare width, per view (the rest keep their size).
STRETCH = {"Crests": {"name", "where"}, "Units": {"picks"},
           "Planner": {"stage", "units"}, "Today": {"name", "units"}, "Team": {"fit"},
           FIND: {"name", "info"}}
BOARD_VIEWS = ("Week", "Compare")  # drawn as a grid, not a table
CENTER = {"difficulty", "element", "tag", "kind", "mine", "team", "ready", "what"}
HINTS = {"Week": "stage", "Crests": "crest", "Units": "unit",
         "Today": "stage or crest", FIND: "result"}
NBSP = " "  # keeps a unit's name on one line in the detail panel
DAY_CHECK_MS = 60_000


def short_days(days: list[str]) -> str:
    if len(days) == 7:
        return "Every day"
    return ", ".join(d[:3] for d in sorted(days, key=DAYS.index))


def today_name(t: float | None = None) -> str:
    """Weekday of the current game day (rolls over at the same reset Rerun uses)."""
    return DAYS[game_day(time.time() if t is None else t).weekday()]


def level_icon_name(lv: str) -> str:
    """'Lv3+' -> 'lv3p.png' (the site's per-level crest icons)."""
    return lv.lower().replace("+", "p") + ".png"


def scaled(font: tuple, k: float) -> tuple:
    return (font[0], max(7, round(font[1] * k)), *font[2:])


def diff_order(s: dict) -> tuple:
    return (DIFFS.index(s["difficulty"]) if s["difficulty"] in DIFFS else 9, s["name"])


class Pictures:
    """Loads the saved pictures as Tk images, resized and cached. Missing file -> None."""

    def __init__(self, folder: Path):
        self.dir = folder
        self._cache: dict[tuple, ImageTk.PhotoImage | None] = {}

    @property
    def available(self) -> bool:
        return self.dir.is_dir()

    def path_for(self, rec: dict, kind: str) -> Path | None:
        if kind == "unit" and rec.get("unit_id"):
            return self.dir / f"unit_thumbnail_{rec['unit_id']}.png"
        if kind == "stage" and rec.get("stage_id"):
            for ext in (".webp", ".png", ".jpg"):
                p = self.dir / "stages" / f"banner_{rec['stage_id']}{ext}"
                if p.exists():
                    return p
            return None
        if kind == "crest" and rec.get("icon"):
            return self.dir / "crests" / rec["icon"].rsplit("/", 1)[-1]
        return None

    def get(self, path: Path | None, h: int, max_w: int | None = None):
        """Image `h` px tall (aspect kept, at most max_w wide)."""
        if path is None:
            return None
        key = (str(path), h, max_w)
        if key not in self._cache:
            photo = None
            try:
                with Image.open(path) as im:
                    im = im.convert("RGBA")
                    w = max(1, round(im.width * h / im.height))
                    h2 = h
                    if max_w and w > max_w:
                        w, h2 = max_w, max(1, round(im.height * max_w / im.width))
                    photo = ImageTk.PhotoImage(im.resize((w, h2), Image.LANCZOS))
            except (OSError, ValueError):
                photo = None
            self._cache[key] = photo
        return self._cache[key]

    def of(self, rec: dict, kind: str, h: int, max_w: int | None = None):
        return self.get(self.path_for(rec, kind), h, max_w)

    def level(self, lv: str, h: int):
        return self.get(self.dir / "crests" / level_icon_name(lv), h)

    def site(self, src: str, h: int, max_w: int | None = None):
        """A picture by its site path, e.g. /images/enemies/101176112.webp."""
        if not src.startswith("/images/") or ".." in src:
            return None
        return self.get(self.dir / src[len("/images/"):], h, max_w)


class GSCompanionPage(tk.Frame):
    """parent:        any Tk container (ios.init must already have run).
    root:          the folder holding data/gscompanion/ (Rerun's folder).
    flash:         optional (text, kind) -> None, e.g. Rerun's toast.
    settings_path: where to remember things (default data/gscompanion/companion_settings.json).
    rerun_dir:     Rerun folder whose units/roster.json lists your scanned units (default root)."""

    def __init__(self, parent, root: str | Path, flash=None, open_url=webbrowser.open,
                 settings_path: Path | None = None, rerun_dir: Path | None = None,
                 data_out: Path | None = None):
        super().__init__(parent, bg=C["bg"])
        self._load_data(Path(root))
        # "Update data" writes here (the exe: a data folder next to it).
        self.data_out = Path(data_out) if data_out else self.gsc.dir
        self._updater = None
        self._show_foes = False  # stage guide: list every enemy under each wave
        self._show_kit = True    # unit panel: the kit section
        self.s = Settings(settings_path or self.gsc.dir / "companion_settings.json")
        self.my = MyUnits(self.s, self.gsc, Path(rerun_dir or root))
        self._game_day = today_name()
        self._flash_cb = flash
        self._open_url = open_url
        self._rows: dict[str, dict] = {}
        self._sort: dict[str, tuple[str, bool]] = {v: ("", False) for v in VIEWS + [FIND]}
        self._sel: dict[str, tuple[str, dict] | None] = {v: None for v in VIEWS + [FIND]}
        self._shown: tuple[str, dict] | None = None   # what the detail panel shows
        self._history: list[tuple[str, str, dict]] = []
        self._links = 0
        self._actions: dict[str, object] = {}
        self._week_cells: dict[str, list[tk.Widget]] = {}
        self._week_w = 0
        self._sash_ratio = self.s["sash"] if isinstance(self.s["sash"], float) else 0.6

        view = self.s["view"] if self.s["view"] in VIEWS else "Today"
        self.view = tk.StringVar(value=view)
        self._before_find = view
        self.q = {v: tk.StringVar() for v in ("Crests", "Units", "Team")}
        for v in self.q.values():
            v.trace_add("write", lambda *a: self.refresh())
        self.find_q = tk.StringVar()
        self.find_q.trace_add("write", lambda *a: self._find_changed())
        self.team_filter = tk.StringVar(value=self.s["team_filter"])
        self.team_stage = tk.StringVar()
        self.kind = tk.StringVar(value=self.s["kind"])
        self.element = tk.StringVar(value=self.s["element"])
        self.unit_filter = tk.StringVar(value=self.s["unit_filter"])
        size_key = next((k for k, (n, _) in SIZES.items() if n == self.s["size"]), "M")
        self.size = tk.StringVar(value=size_key)

        self._build()
        self._apply_size()
        self._bind_keys()
        self._switch()
        self._last_day_seen = self.s["last_day"]
        self.s["last_day"] = self._game_day
        self.s.save()
        self.after(DAY_CHECK_MS, self._check_day)

    def _load_data(self, root: Path):
        """(Re)load everything read from data/gscompanion/ under root."""
        self.root_dir = root
        self.gsc = GSCData(root)
        self.pics = Pictures(self.gsc.dir / "images")
        self.guides = Guides(self.gsc.dir)
        try:
            doc = json.loads((self.gsc.dir / "unit_details.json").read_text(encoding="utf-8"))
            self.details = doc.get("units", {}) if isinstance(doc, dict) else {}
        except (OSError, ValueError):
            self.details = {}
        self.teams = TeamCheck(self.gsc, self.guides, self.details)
        if hasattr(self, "my"):
            self.my.gsc = self.gsc
            self.my._scan_key = None

    # ================================================================== layout
    def _build(self):
        hdr = ios.page_header(self, "GS Companion")
        ios.Button(hdr, "Open on site", self.open_current, kind="tinted",
                   icon="link").pack(side="right")
        ios.Segmented(hdr, list(SIZES), self.size, command=self._size_changed).pack(
            side="right", padx=(px(8), px(18)))
        tk.Label(hdr, text="Text size", bg=C["bg"], fg=C["secondary"],
                 font=F["footnote"]).pack(side="right")
        self.back_btn = ios.Button(hdr, "‹ Back", self.back, kind="plain", small=True)
        self.back_btn.pack(side="right", padx=(0, px(18)))
        self.update_btn = ios.Button(hdr, "Update data", self.update_data, kind="plain",
                                     small=True)
        self.update_btn.pack(side="right", padx=(0, px(14)))
        find = ios.Field(hdr, self.find_q, width=20)
        find.pack(side="right", padx=(px(6), px(18)))
        tk.Label(hdr, text=ios.icon_text("search") or "Search", bg=C["bg"], fg=C["secondary"],
                 font=F["icon"] if ios.ICON_FONT else F["footnote"]).pack(side="right",
                                                                          padx=(px(24), 0))
        self.find_entry = find.entry
        self.find_entry.bind("<Escape>", lambda e: self._close_find())
        self.find_entry.bind("<Return>", lambda e: self._find_changed(force=True))

        bar = tk.Frame(self, bg=C["bg"])
        bar.pack(fill="x", padx=px(20), pady=(0, px(8)))
        self.seg = ios.Segmented(bar, VIEWS, self.view, command=self._switch)
        self.seg.pack(side="left")
        self.summary = tk.Label(bar, bg=C["bg"], fg=C["secondary"], font=F["footnote"])
        self.summary.pack(side="right")

        fbar = tk.Frame(self, bg=C["bg"])
        fbar.pack(fill="x", padx=px(20), pady=(0, px(10)))
        self.filters = tk.Frame(fbar, bg=C["bg"])
        self.filters.pack(side="left")
        self.side_note = tk.Label(fbar, bg=C["bg"], fg=C["secondary"], font=F["footnote"])
        self.side_note.pack(side="right")

        self.footer = tk.Label(self, bg=C["bg"], fg=C["secondary"], font=F["caption"], anchor="w")
        self.footer.pack(side="bottom", fill="x", padx=px(24), pady=(0, px(8)))
        self._set_footer()

        st = ttk.Style(self)
        st.configure("GSC.TPanedwindow", background=C["bg"])
        st.configure("Sash", sashthickness=px(16), gripcount=0, background=C["bg"],
                     lightcolor=C["bg"], darkcolor=C["bg"], bordercolor=C["bg"])
        self.paned = ttk.PanedWindow(self, orient="horizontal", style="GSC.TPanedwindow")
        self.paned.pack(fill="both", expand=True, padx=px(20), pady=(0, px(6)))
        lc = ios.Card(self.paned, pad=6, stretch=True)
        rc = ios.Card(self.paned, pad=10, stretch=True)
        self.paned.add(lc, weight=3)
        self.paned.add(rc, weight=2)
        self.paned.bind("<Configure>", lambda e: self.after_idle(self._place_sash))
        self.paned.bind("<ButtonRelease-1>", lambda e: self._sash_moved(), add="+")

        # List side: a table, or the week grid.
        self.list_body = lc.body
        self.tree_sb = ttk.Scrollbar(lc.body, orient="vertical", style="IOS.Vertical.TScrollbar")
        self.tree = ttk.Treeview(lc.body, show="tree headings", style="GSC.IOS.Treeview",
                                 selectmode="browse", yscrollcommand=self.tree_sb.set)
        self.tree_sb.configure(command=self.tree.yview)
        self.tree.tag_configure("open", foreground=C["green"])
        self.tree.tag_configure("quiet", foreground=C["secondary"])
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._on_select())
        self.tree.bind("<Button-1>", self._tree_click, add="+")
        self.tree.bind("<Configure>", lambda e: self.after_idle(self._fit_columns), add="+")
        self.week_sf = ios.ScrollFrame(lc.body)
        self.week = self.week_sf.inner
        self.week_sf.canvas.bind("<Configure>", self._week_resized, add="+")
        self.empty = tk.Label(lc.body, bg=C["card"], fg=C["secondary"], font=F["footnote"],
                              justify="center")

        # Detail side.
        dsb = ttk.Scrollbar(rc.body, orient="vertical", style="IOS.Vertical.TScrollbar")
        self.detail = tk.Text(rc.body, wrap="word", bg=C["card"], fg=C["label"], relief="flat",
                              bd=0, highlightthickness=0, padx=px(6), pady=px(4), width=1,
                              height=1, cursor="arrow", selectbackground=C["blue"],
                              selectforeground="#FFFFFF", yscrollcommand=dsb.set)
        dsb.configure(command=self.detail.yview)
        dsb.pack(side="right", fill="y", pady=px(4))
        self.detail.pack(side="left", fill="both", expand=True)
        d = self.detail
        d.tag_configure("dim", foreground=C["secondary"])
        d.tag_configure("good", foreground=C["green"])
        d.tag_configure("link", foreground=C["blue"])
        d.tag_configure("action", foreground=C["blue"])
        d.tag_configure("mine", foreground=C["orange"])
        for diff, col in DIFF_COLOR.items():
            d.tag_configure(diff, foreground=C[col])
        for t in ("link", "action"):
            d.tag_bind(t, "<Enter>", lambda e: d.configure(cursor="hand2"))
            d.tag_bind(t, "<Leave>", lambda e: d.configure(cursor="arrow"))

    def data_age_days(self) -> int | None:
        built = self.gsc._load("crests.json").get("built") if self.gsc.available else None
        try:
            return (time.time() - time.mktime(time.strptime(built, "%Y-%m-%d"))) // 86400
        except (TypeError, ValueError):
            return None

    def _set_footer(self, text: str | None = None):
        if text is None:
            built = self.gsc._load("crests.json").get("built", "?") if self.gsc.available else "?"
            age = self.data_age_days()
            old = f"  ·  {int(age)} days old: press Update data" if age and age > 30 else ""
            text = (f"Fan-site data from gscompanion.com, built {built}{old}. What the game shows "
                    f"always wins.   Ctrl+F search · Alt+← back · Ctrl+1–{len(VIEWS)} views")
            self.footer.configure(fg=C["orange"] if old else C["secondary"])
        self.footer.configure(text=text)

    def _apply_size(self):
        """Text size: list rows, pictures and the detail panel (controls keep Rerun's size)."""
        name, k = SIZES.get(self.size.get(), SIZES["M"])
        self.k = k
        self.thumb = px(32 * k)
        f = {
            "row": scaled(F["body"], k), "head": scaled(F["footnote_semi"], k),
            "d": scaled(F["footnote"], k * 1.12), "d_semi": scaled(F["footnote_semi"], k * 1.12),
            "d_title": scaled(F["title"], k * 1.05), "d_h": scaled(F["footnote_semi"], k),
            "w_name": scaled(F["footnote_semi"], k), "w_sub": scaled(F["caption"], k * 1.05),
            "w_day": scaled(F["body_semi"], k),
        }
        self.f = f
        st = ttk.Style(self)
        st.configure("GSC.IOS.Treeview", font=f["row"], rowheight=px(42 * k), indent=0)
        st.configure("GSC.IOS.Treeview.Heading", font=f["head"])
        self.tree.tag_configure("day", font=scaled(F["body_semi"], k), foreground=C["label"])
        self.tree.tag_configure("today", font=scaled(F["body_semi"], k), foreground=C["blue"])
        d = self.detail
        d.configure(font=f["d"], tabs=(px(70 * k),), spacing1=px(1), spacing3=px(2))
        d.tag_configure("title", font=f["d_title"], spacing3=px(2))
        d.tag_configure("sub", foreground=C["secondary"], spacing3=px(6))
        d.tag_configure("h", font=f["d_h"], foreground=C["secondary"], spacing1=px(14),
                        spacing3=px(5))
        d.tag_configure("semi", font=f["d_semi"])
        d.tag_configure("good", font=f["d_semi"])
        d.tag_configure("bad", foreground=C["red"])
        d.tag_configure("role", spacing1=px(8))
        d.tag_configure("indent", lmargin1=px(26 * k), lmargin2=px(26 * k))

    def _size_changed(self):
        self.s["size"] = SIZES[self.size.get()][0]
        self.s.save()
        self._apply_size()
        self._week_w = 0
        self._switch(keep_detail=True)

    def _place_sash(self):
        w = self.paned.winfo_width()
        if w < MIN_LIST_W + MIN_DETAIL_W:
            return
        pos = int(w * self._sash_ratio)
        pos = max(px(MIN_LIST_W), min(pos, w - px(MIN_DETAIL_W)))
        try:
            if abs(self.paned.sashpos(0) - pos) > 2:
                self.paned.sashpos(0, pos)
        except tk.TclError:
            pass

    def _sash_moved(self):
        w = self.paned.winfo_width()
        if w > 1:
            self._sash_ratio = round(self.paned.sashpos(0) / w, 3)
            self._place_sash()
            self.s["sash"] = self._sash_ratio
            self.s.save()

    def save_state(self):
        """Call when the window closes (the exe does)."""
        self.s["view"] = self.view.get()
        self.s.save()

    # ================================================================== keys
    def _bind_keys(self):
        top = self.winfo_toplevel()

        def when_shown(fn):
            def h(e):
                if self.winfo_ismapped():
                    return fn(e)
            return h

        top.bind("<Control-f>", when_shown(lambda e: self._focus_search()), add="+")
        top.bind("<Alt-Left>", when_shown(lambda e: self.back()), add="+")
        top.bind("<Escape>", when_shown(lambda e: self._clear_search()), add="+")
        for i, v in enumerate(VIEWS, 1):
            top.bind(f"<Control-Key-{i}>", when_shown(lambda e, v=v: self.show_view(v)), add="+")

    def _focus_search(self):
        """Ctrl+F: the search-everything box (header)."""
        self.find_entry.focus_set()
        self.find_entry.select_range(0, "end")

    def _clear_search(self):
        v = self.view.get()
        if v == FIND:
            return self._close_find()
        if v in self.q and self.q[v].get():
            self.q[v].set("")

    # --- search everything --------------------------------------------------------
    def _find_changed(self, force: bool = False):
        q = self.find_q.get().strip()
        if not q:
            if self.view.get() == FIND:
                self._close_find()
            return
        if len(q) < 2 and not force:
            return
        if self.view.get() != FIND:
            self._before_find = self.view.get()
            self.view.set(FIND)
            self.seg._draw()
            self._switch()
        else:
            self.refresh()

    def _close_find(self):
        if self.find_q.get():
            self.find_q.set("")
        if self.view.get() == FIND:
            self.view.set(self._before_find if self._before_find in VIEWS else "Today")
            self.seg._draw()
            self._switch()

    def _find_rows(self) -> list[dict]:
        q = self.find_q.get().strip().lower()
        my = self.my.all()
        stages, crests, units = [], [], []
        for s in sorted(self.gsc.stages, key=diff_order):
            g = self.guides.for_stage(s) or {}
            hay = " ".join([s["name"], s["boss"], s["difficulty"], " ".join(s.get("hazards", [])),
                            " ".join(s.get("crests", [])), g.get("summary", "")]).lower()
            if q in hay:
                stages.append({"rec": s, "kind": "stage", "values": {
                    "name": s["name"], "what": s["difficulty"],
                    "info": f"{s['boss']}  ·  {short_days(s['days'])}"}})
        for c in self.gsc.crests:
            hay = " ".join([c["name"], c.get("event") or "", c.get("effect") or "",
                            " ".join((c.get("levels") or {}).values())]).lower()
            if q in hay:
                crests.append({"rec": c, "kind": "crest", "values": {
                    "name": c["name"], "what": c["kind"].title(), "info": self._crest_where(c)}})
        for u in self.gsc.units:
            d = self.details.get(u["name"], {})
            names = " ".join([u["name"]] + d.get("aka", [])).lower()
            kit = self.teams_kit(u["name"])
            if q in names or q in kit:
                why = "" if q in names else self._kit_match(d, q)
                units.append({"rec": u, "kind": "unit", "values": {
                    "name": ("★ " if u["name"] in my else "") + u["name"],
                    "what": u["element"], "info": why or ", ".join(
                        self.gsc.recommendations.get(u["name"], [])) or "–"}})
        total = len(stages) + len(crests) + len(units)
        self.summary.configure(text=f"{total} result{'s' if total != 1 else ''} for “{q}”  ·  "
                                    "Esc closes")
        rows = []
        for title, items in (("Stages", stages), ("Crests", crests), ("Units", units)):
            if items:
                rows.append({"rec": None, "kind": "group", "tags": ("day",),
                             "values": {"name": f"{title} ({len(items)})"},
                             "children": items[:200]})
        return rows

    def teams_kit(self, name: str) -> str:
        from .team import _kit_text
        return _kit_text(self.details.get(name))

    @staticmethod
    def _kit_match(d: dict, q: str, width: int = 70) -> str:
        """Where in the kit the search matched: 'Arts: …reduces all allies' DMG…'."""
        items = [(m.get("type", "Kit"), m.get("text", "")) for m in d.get("moves", [])]
        items += [("Passive", f"{p['name']}: {p['text']}") for p in d.get("passives", [])]
        items += [(e.get("from", "") or "Effect", e.get("effect", ""))
                  for e in d.get("effects", [])]
        items += [(k, c) for k, v in d.get("tags", {}).items() for c in v]
        for label, text in items:
            i = text.lower().find(q)
            if i >= 0:
                a = max(0, i - width // 3)
                snip = ("…" if a else "") + text[a:a + width].strip() + \
                    ("…" if a + width < len(text) else "")
                return f"{label}: {snip}"
        return "kit"

    # ================================================================== helpers
    def flash(self, text: str, kind: str = "info"):
        if self._flash_cb:
            self._flash_cb(text, kind)
        else:
            self.summary.configure(text=text)

    def _save_filters(self):
        for key, var in (("kind", self.kind), ("element", self.element),
                         ("unit_filter", self.unit_filter)):
            self.s[key] = var.get()
        self.s.save()

    def _filter_changed(self):
        self._save_filters()
        self.refresh()

    def _mine_for_stage(self, s: dict, my: set[str]) -> set[str]:
        """Your units that still need a crest dropping at stage s."""
        out = set()
        for name in s.get("crests", []):
            out |= set(self.my.needing(name, set(self.gsc.units_wanting(name)) & my))
        return out

    def _ready_text(self, s: dict, my: set[str]) -> tuple[str, float]:
        """'3/5' roles your units can fill (+ ' ★' when you own a whole example team)."""
        r = self.teams.readiness(s, my)
        if not r["guide"] or not r["roles"]:
            return "", -1.0
        n = len(r["filled"])
        score = n / r["roles"] + (1 if r["full_teams"] else 0)
        return f"{n}/{r['roles']}" + (" ★" if r["full_teams"] else ""), score

    def _stage_label(self, s: dict) -> str:
        return f"{s['name']} ({s['difficulty']})"

    def team_stage_rec(self) -> dict | None:
        slug = self.s["team_stage"]
        st = next((s for s in self.gsc.stages if s["slug"] == slug), None)
        if st is None:
            today = self.gsc.palace_on(today_name())
            st = sorted(today, key=diff_order)[0] if today else (
                self.gsc.stages[0] if self.gsc.stages else None)
        return st

    # ================================================================== views
    def show_view(self, view: str):
        self.view.set(view)
        self.seg._draw()
        self._switch()

    def _switch(self, keep_detail: bool = False):
        view = self.view.get()
        if view != FIND:
            self.s["view"] = view
            self.s.save()
            if self.find_q.get():
                self.find_q.set("")
        for w in self.filters.winfo_children():
            w.destroy()
        self._search_entry = None
        self.side_note.configure(text="")
        self._build_filters(view)
        if view in BOARD_VIEWS:
            self.tree.pack_forget()
            self.tree_sb.pack_forget()
            self.empty.place_forget()
            self.week_sf.pack(fill="both", expand=True)
            self.week_sf.canvas.yview_moveto(0)
            self.refresh()
        else:
            self.week_sf.pack_forget()
            self.tree_sb.pack(side="right", fill="y", pady=px(4))
            self.tree.pack(side="left", fill="both", expand=True)
            self._set_columns(view)
            self.refresh()
        sel = self._sel.get(view)
        if keep_detail and self._shown:
            self._show(*self._shown)
        elif sel:
            self._show(*sel)
        else:
            self._show_placeholder(view)

    def _build_filters(self, view: str):
        f = self.filters

        def select(values, var, **pack):
            ios.Select(f, values=values, variable=var, accent=True,
                       command=self._filter_changed).pack(side="left", **pack)

        def search():
            tk.Label(f, text=ios.icon_text("search") or "Search", bg=C["bg"], fg=C["secondary"],
                     font=F["icon"] if ios.ICON_FONT else F["footnote"]).pack(side="left",
                                                                            padx=(0, px(6)))
            fld = ios.Field(f, self.q[view], width=24)
            fld.pack(side="left", padx=(0, px(16)))
            self._search_entry = fld.entry

        if view == "Today":
            n = len(self.my.all())
            self._note(f"Stages open on {today_name()} (game day, resets 06:00 UTC−6), best "
                       f"for you first  ·  {n} unit{'s' if n != 1 else ''} of yours"
                       if n else "Star your units in Units to see what to farm for them")
        elif view == "Team":
            labels = [self._stage_label(s) for s in sorted(self.gsc.stages, key=diff_order)]
            st = self.team_stage_rec()
            self.team_stage.set(self._stage_label(st) if st else (labels[0] if labels else ""))
            ios.Select(f, values=labels, variable=self.team_stage, accent=True,
                       command=self._team_stage_changed).pack(side="left", padx=(0, px(16)))
            search()
            ios.Select(f, values=["My units", "All units"], variable=self.team_filter,
                       accent=True, command=self._team_filter_changed).pack(side="left")
            ios.Button(f, "Suggest a team", self.team_suggest, kind="gray",
                       small=True).pack(side="left", padx=(px(16), 0))
            ios.Button(f, "Clear", self.team_clear, kind="plain", color="red",
                       small=True).pack(side="left", padx=(px(10), 0))
            self._note(f"Click ＋ to add a unit (up to {TEAM_SIZE})")
        elif view == FIND:
            self._note("Searches stage names, bosses and guides, crest effects, unit names, "
                       "nicknames and kits")
        elif view == "Week":
            self._note("Click a stage for its guide.  ★ = crests your units need  ·  "
                       "✓ = roles your units can fill (★ = a whole example team)")
        elif view == "Crests":
            search()
            select([ALL_KINDS] + list(KINDS), self.kind)
        elif view == "Units":
            search()
            select([ALL_ELEMENTS] + ELEMENTS, self.element)
            select(UNIT_FILTERS, self.unit_filter, padx=(px(16), 0))
            ios.Button(f, "Rerun folder…", self.choose_rerun_dir, kind="plain",
                       small=True).pack(side="left", padx=(px(16), 0))
            self._note(f"★ starred · ✓ in your Rerun scan · click the ★ column to star  ·  "
                       f"{self.my.scan_status()}")
        elif view == "Planner":
            n = len(self.s["plan"])
            ios.Button(f, f"Add my units ({len(self.my.all())})", self.plan_add_mine,
                       kind="gray", small=True).pack(side="left")
            ios.Button(f, "Clear plan", self.plan_clear, kind="plain", color="red",
                       small=True).pack(side="left", padx=(px(16), 0))
            self._note(f"{n} unit{'s' if n != 1 else ''} in the plan  ·  add more from a unit's "
                       "details")
        elif view == "Compare":
            ios.Button(f, "Clear", self.compare_clear, kind="plain", color="red",
                       small=True).pack(side="left")
            self._note(f"Up to {MAX_COMPARE} crests  ·  add them from a crest's details")

    def _note(self, text: str):
        self.side_note.configure(text=text)

    def _set_columns(self, view: str):
        cols = COLUMNS[view]
        self._cols = cols
        self.tree.configure(columns=[c[0] for c in cols], displaycolumns=[c[0] for c in cols])
        sortable = view not in ("Planner", "Today", FIND)
        for key, head, w in cols:
            self.tree.heading(key, text=head,
                              command=(lambda k=key: self._sort_by(k)) if sortable else "")
            stretch = key in STRETCH.get(view, ())
            self.tree.column(key, width=px(w * self.k), minwidth=px(36), stretch=stretch,
                             anchor="center" if key in CENTER else "w")
        pw = 0
        if self.pics.available:
            pw = px(104 * self.k) if view == "Today" else px(48 * self.k)
        self.tree.heading("#0", text="")
        self.tree.column("#0", width=pw, minwidth=pw, stretch=False, anchor="center")
        self._pic_w = pw
        self._fit_columns()

    def _fit_columns(self, _e=None):
        """Share the table's width: wide enough -> spare space goes to the view's main text
        columns; too narrow -> every column shrinks in proportion (nothing pushed off)."""
        view = self.view.get()
        if view in BOARD_VIEWS or not getattr(self, "_cols", None):
            return
        avail = self.tree.winfo_width() - getattr(self, "_pic_w", 0) - px(4)
        if avail < px(200):
            return
        base = [(key, px(w * self.k)) for key, _, w in self._cols]
        total = sum(w for _, w in base)
        grow = STRETCH.get(view, set())
        grow_total = sum(w for k, w in base if k in grow) or 1
        widths = {}
        if avail >= total:
            extra = avail - total
            for k, w in base:
                widths[k] = w + (int(extra * w / grow_total) if k in grow else 0)
        else:
            for k, w in base:
                widths[k] = max(px(30), int(w * avail / total))
        for k, w in widths.items():
            self.tree.column(k, width=w, stretch=False)

    def _sort_by(self, key: str):
        view = self.view.get()
        cur, desc = self._sort[view]
        self._sort[view] = (key, not desc if cur == key else key in ("mine", "ready", "team"))
        self.refresh()

    def refresh(self):
        view = self.view.get()
        if view == "Week":
            self._render_week()
            return
        if view == "Compare":
            self._render_compare()
            return
        if not self.gsc.available:
            self.tree.delete(*self.tree.get_children())
            self._empty("No GS Companion data\nBuild it with:  py tools/gscompanion_build.py")
            return
        rows = {"Crests": self._crest_rows, "Units": self._unit_rows,
                "Planner": self._planner_rows, "Today": self._today_rows,
                "Team": self._team_rows, FIND: self._find_rows}[view]()
        key, desc = self._sort[view]
        if key:
            def sort_key(r):
                v = r.get("sortkeys", {}).get(key)
                return (0, v, "") if v is not None else (1, 0, str(r["values"][key]).lower())
            rows.sort(key=sort_key, reverse=desc)
        self.tree.delete(*self.tree.get_children())
        self._rows = {}
        names = [c[0] for c in self._cols]
        first_text = next((n for n in names if n not in CENTER), None)

        def insert(r, parent=""):
            iid = f"r{len(self._rows)}"
            self._rows[iid] = r
            pic = self._row_pic(r)
            vals = [("  " if n == first_text else "") + str(r["values"].get(n, "")) for n in names]
            self.tree.insert(parent, "end", iid=iid, tags=r.get("tags", ()), open=True,
                             values=vals, **({"image": pic} if pic else {}))
            for c in r.get("children", []):
                insert(c, iid)

        for r in rows:
            insert(r)
        if rows:
            self.empty.place_forget()
        else:
            self._empty({"Planner": "No units in the plan yet\nOpen a unit and choose “Add to "
                                    "farm planner”, or use “Add my units”.",
                         "Team": "No units to show\nStar your units in Units, or switch the "
                                 "list to “All units”.",
                         FIND: "Nothing found\nTry a shorter or different word."}
                        .get(view, "Nothing matches\nTry another search or filter."))
        sel = self._sel.get(view)
        if sel:
            for iid, r in self._rows.items():
                if r.get("rec") is sel[1]:
                    self.tree.selection_set(iid)
                    self.tree.see(iid)
                    break

    def _empty(self, text: str):
        self.empty.configure(text=text)
        self.empty.place(relx=0.5, rely=0.42, anchor="center")
        self.empty.lift()

    def _row_pic(self, r: dict):
        rec, kind = r.get("rec"), r.get("kind")
        if r.get("pic") is not None:
            return r["pic"]
        if not rec:
            return None
        if kind == "stage":
            return self.pics.of(rec, "stage", self.thumb, px(96 * self.k))
        if kind in ("unit", "crest"):
            return self.pics.of(rec, kind, self.thumb)
        return None

    # --- rows -----------------------------------------------------------------
    def _today_rows(self) -> list[dict]:
        """Stages open today, best for your units first, each with the crests your units
        still need from it."""
        today = today_name()
        my = self.my.all()
        stages = self.gsc.palace_on(today)
        rows, crest_n = [], 0
        for s in stages:
            ready, score = self._ready_text(s, my) if my else ("", -1.0)
            kids = []
            for cname in s.get("crests", []):
                who = sorted(self.my.needing(cname, set(self.gsc.units_wanting(cname)) & my))
                if who:
                    c = self.gsc.crest(cname)
                    kids.append({"rec": c, "kind": "crest", "values": {
                        "name": cname, "units": ", ".join(who)}})
            crest_n += len(kids)
            rows.append({"rec": s, "kind": "stage", "tags": ("open",), "children": kids,
                         "score": (score, len(kids), -diff_order(s)[0]),
                         "values": {"name": s["name"], "difficulty": s["difficulty"],
                                    "ready": ready,
                                    "units": f"{len(kids)} crest{'s' if len(kids) != 1 else ''}"
                                             " to farm" if kids else
                                             ("nothing your units need" if my else "")}})
        rows.sort(key=lambda r: r["score"], reverse=True)
        self.summary.configure(text=f"{today}: {len(stages)} stages open  ·  {crest_n} crest "
                                    f"drop{'s' if crest_n != 1 else ''} your units need")
        return rows

    def _team_rows(self) -> list[dict]:
        st = self.team_stage_rec()
        g = self.guides.for_stage(st) if st else None
        roles: dict[str, list[str]] = {}
        for r in (g or {}).get("roles", []):
            for u in r.get("picks", []):
                roles.setdefault(u["name"], []).append(r["role"])
            for u in r.get("also", []):
                roles.setdefault(u["name"], []).append(r["role"] + " (also)")
        bad = hazards(st, g) if st else []
        q = self.q["Team"].get().strip().lower()
        mine = self.team_filter.get() == "My units"
        my = self.my.all()
        team = list(self.s["team"])
        units = [u for u in self.gsc.units
                 if (not mine or u["name"] in my or u["name"] in team)
                 and (not q or q in u["name"].lower())]
        rows = []
        for u in units:
            fit = ", ".join(roles.get(u["name"], []))
            warn = next((w for h in bad
                         if (w := hazard_hits(h, u, self.details.get(u["name"])))), None)
            text = fit + (("   ⚠ " + warn) if warn else "")
            rows.append({"rec": u, "kind": "unit",
                         "tags": () if fit else ("quiet",),
                         "sortkeys": {"team": 1 if u["name"] in team else 0},
                         "order": (u["name"] not in team, not fit, bool(warn), u["name"]),
                         "values": {"team": "✓" if u["name"] in team else "＋",
                                    "name": ("★ " if u["name"] in my else "") + u["name"],
                                    "element": u["element"], "fit": text or "–"}})
        rows.sort(key=lambda r: r["order"])
        self.summary.configure(text=f"Team {len(team)}/{TEAM_SIZE}  ·  "
                                    f"{self._stage_label(st) if st else 'no stage'}")
        return rows

    def _crest_where(self, c: dict) -> str:
        if c.get("event"):
            return f"Event: {c['event']}"
        stages = self.gsc.stages_dropping(c["name"])
        if not stages:
            return "–"
        days = sorted({d for s in stages for d in s["days"]}, key=DAYS.index)
        n = len(stages)
        return f"{n} stage{'s' if n != 1 else ''}  ·  {short_days(days)}"

    def _crest_rows(self) -> list[dict]:
        q = self.q["Crests"].get().strip().lower()
        kind = KINDS.get(self.kind.get())
        my = self.my.all()
        out = [c for c in self.gsc.crests
               if (not kind or c["kind"] == kind)
               and (not q or q in c["name"].lower() or q in (c.get("event") or "").lower()
                    or q in (c.get("effect") or "").lower())]
        self.summary.configure(text=f"{len(out)} of {len(self.gsc.crests)} crests")
        rows = []
        for c in out:
            n = len(self.my.needing(c["name"], set(self.gsc.units_wanting(c["name"])) & my)) \
                if my else 0
            rows.append({"rec": c, "kind": "crest",
                         "tags": () if self.gsc.stages_dropping(c["name"]) or c.get("event")
                         else ("quiet",),
                         "values": {"name": c["name"], "kind": c["kind"].title(),
                                    "where": self._crest_where(c), "mine": f"★ {n}" if n else ""}})
        return rows

    def _unit_rows(self) -> list[dict]:
        q = self.q["Units"].get().strip().lower()
        el = None if self.element.get() == ALL_ELEMENTS else self.element.get()
        which = self.unit_filter.get()
        keep = {"My units": self.my.all(), "Starred": self.my.starred,
                "Rerun scan": self.my.scanned()}.get(which)
        out = [u for u in self.gsc.units
               if (not el or u["element"] == el) and (not q or q in u["name"].lower())
               and (keep is None or u["name"] in keep)]
        self.summary.configure(text=f"{len(out)} of {len(self.gsc.units)} units"
                                    f"  ·  {len(self.my.all())} yours")
        rows = []
        for u in out:
            picks = self.gsc.recommendations.get(u["name"], [])
            rows.append({"rec": u, "kind": "unit", "tags": () if picks else ("quiet",),
                         "values": {"mine": self.my.mark(u["name"]), "name": u["name"],
                                    "element": u["element"], "tag": u["tag"],
                                    "picks": ", ".join(picks) if picks else "–"}})
        return rows

    def plan(self) -> dict:
        """Farm plan for the planner units: {"every": [...], "days": {day: [...]},
        "elsewhere": [...]}, each entry {"crest", "stage", "units"}."""
        units = [n for n in self.s["plan"] if self.gsc.match_unit(n)]
        need: dict[str, list[str]] = {}
        for name in units:
            for c in self.gsc.recommendations.get(name, []):
                if not self.my.has(name, c):  # crests a unit already has are skipped
                    need.setdefault(c, []).append(name)
        every, days, elsewhere = [], {d: [] for d in DAYS}, []
        for cname, who in need.items():
            stages = self.gsc.stages_dropping(cname)
            if not stages:
                elsewhere.append({"crest": cname, "stage": None, "units": who})
            for s in sorted(stages, key=diff_order):
                e = {"crest": cname, "stage": s, "units": who}
                if len(s["days"]) == 7:
                    every.append(e)
                else:
                    for d in s["days"]:
                        days[d].append(e)
        return {"every": every, "days": days, "elsewhere": elsewhere, "units": units}

    def _planner_rows(self) -> list[dict]:
        p = self.plan()
        today = today_name()
        order = DAYS[DAYS.index(today):] + DAYS[:DAYS.index(today)]
        n_need = len({e["crest"] for e in p["every"] + p["elsewhere"]}
                     | {e["crest"] for es in p["days"].values() for e in es})
        self.summary.configure(text=f"{len(p['units'])} units  ·  {n_need} crests still needed")
        if not p["units"]:
            return []

        def child(e):
            c = self.gsc.crest(e["crest"])
            s = e["stage"]
            return {"rec": c, "kind": "crest",
                    "values": {"name": c["name"] if c else e["crest"],
                               "stage": f"{s['name']} ({s['difficulty']})" if s else
                               (f"Event: {c['event']}" if c and c.get("event")
                                else "Not in the palace"),
                               "units": ", ".join(e["units"])}}

        def group(title, entries, tag="day"):
            return {"rec": None, "kind": "group", "tags": (tag,),
                    "values": {"name": title, "stage": f"{len(entries)} to farm"},
                    "children": [child(e) for e in sorted(entries, key=lambda e: e["crest"])]}

        rows = []
        for d in order:
            if p["days"][d]:
                rows.append(group(f"{d}" + ("  ·  today" if d == today else ""), p["days"][d],
                                  "today" if d == today else "day"))
        if p["every"]:
            rows.append(group("Every day", p["every"]))
        if p["elsewhere"]:
            rows.append(group("Not in the Crest Palace", p["elsewhere"]))
        return rows

    # ================================================================== compare
    def _render_compare(self):
        """Crests side by side: one column per crest, one row per level; text wraps."""
        wf = self.week
        for w in wf.winfo_children():
            w.destroy()
        self._week_cells = {}
        crests = [c for c in (self.gsc.crest(n) for n in self.s["compare"]) if c]
        self.summary.configure(text=f"Comparing {len(crests)} crest{'s' if len(crests) != 1 else ''}")
        self.compare_table: list[list[str]] = []
        card = C["card"]
        if not crests:
            tk.Label(wf, text="\n\n\nNothing to compare yet\nOpen a crest and choose “⇄ Compare”.",
                     bg=card, fg=C["secondary"], font=F["footnote"], justify="center").pack(
                fill="x", pady=px(40))
            return
        width = max(self.week_sf.canvas.winfo_width(), px(480))
        lvw = px(84 * self.k)
        colw = max(px(120), (width - lvw - px(24)) // len(crests))
        stripe = ios.mix(card, C["bg"], 0.55 if not ios.DARK_MODE else 0.35)
        grid = tk.Frame(wf, bg=card)
        grid.pack(fill="x", padx=px(6), pady=px(6))
        grid.columnconfigure(0, minsize=lvw)
        for i in range(len(crests)):
            grid.columnconfigure(i + 1, weight=1, uniform="crest", minsize=colw)
        # Header: icon + name (click opens the crest).
        for i, c in enumerate(crests):
            hd = tk.Frame(grid, bg=card, cursor="hand2")
            hd.grid(row=0, column=i + 1, sticky="w", padx=px(8), pady=(px(2), px(10)))
            ws = [hd]
            pic = self.pics.of(c, "crest", px(30 * self.k))
            if pic:
                ws.append(tk.Label(hd, image=pic, bg=card, cursor="hand2"))
                ws[-1].pack(side="left", padx=(0, px(6)))
            ws.append(tk.Label(hd, text=c["name"], bg=card, fg=C["blue"], font=self.f["d_semi"],
                               cursor="hand2", wraplength=colw - px(50), justify="left"))
            ws[-1].pack(side="left")
            for w in ws:
                w.bind("<Button-1>", lambda e, c=c: self.go("Crests", c))
        rows = []
        if any(c.get("effect") for c in crests):
            rows.append(("Effect", None, [c.get("effect") or "–" for c in crests]))
        if any(c.get("levels") for c in crests):
            for lv in LEVELS:
                rows.append((lv, self.pics.level(lv, px(18 * self.k)),
                             [(c.get("levels") or {}).get(lv, "–") for c in crests]))
        for r, (label, pic, vals) in enumerate(rows, 1):
            bg = stripe if r % 2 else card
            lc = tk.Label(grid, text=f" {label}", image=pic or "", compound="left", bg=bg,
                          fg=C["secondary"], font=self.f["d"], anchor="w")
            lc.grid(row=r, column=0, sticky="nsew")
            for i, v in enumerate(vals):
                tk.Label(grid, text=v, bg=bg, fg=C["label"], font=self.f["d"], anchor="nw",
                         justify="left", wraplength=colw - px(20)).grid(
                    row=r, column=i + 1, sticky="nsew", ipadx=px(8), ipady=px(5))
            self.compare_table.append([label] + vals)

    # ================================================================== week
    def _week_resized(self, e):
        view = self.view.get()
        if abs(e.width - self._week_w) > px(12) and view in BOARD_VIEWS:
            self._week_w = e.width
            self.after_idle(self.refresh)

    def _render_week(self):
        wf = self.week
        for w in wf.winfo_children():
            w.destroy()
        self._week_cells = {}
        if not self.gsc.available:
            return
        today = today_name()
        my = self.my.all()
        card = C["card"]
        width = max(self.week_sf.canvas.winfo_width(), px(560))
        colw = max(px(70), (width - px(8) * 8) // 7)
        stages = self.gsc.stages
        every = sorted([s for s in stages if len(s["days"]) == 7], key=diff_order)
        self.summary.configure(text=f"{len(stages)} stages  ·  game day now: {today}")

        if every:
            top = tk.Frame(wf, bg=card)
            top.pack(fill="x", padx=px(6), pady=(px(6), px(4)))
            tk.Label(top, text="OPEN EVERY DAY", bg=card, fg=C["secondary"],
                     font=self.f["w_sub"]).pack(anchor="w", pady=(0, px(4)))
            row = tk.Frame(top, bg=card)
            row.pack(fill="x")
            for s in every:
                self._week_cell(row, s, my, colw * 2, horizontal=True).pack(side="left",
                                                                            padx=(0, px(8)))
        grid = tk.Frame(wf, bg=card)
        grid.pack(fill="both", expand=True, padx=px(2), pady=(px(6), px(6)))
        for i, d in enumerate(DAYS):
            grid.columnconfigure(i, weight=1, uniform="day", minsize=colw)
            is_today = d == today
            hd = tk.Frame(grid, bg=ios.mix(card, C["blue"], 0.14) if is_today else card)
            hd.grid(row=0, column=i, sticky="ew", padx=px(3), pady=(0, px(6)))
            tk.Label(hd, text=d[:3] if colw < px(110) else d, bg=hd.cget("bg"),
                     fg=C["blue"] if is_today else C["label"], font=self.f["w_day"]).pack(
                pady=(px(4), 0))
            tk.Label(hd, text="Today" if is_today else " ", bg=hd.cget("bg"), fg=C["blue"],
                     font=self.f["w_sub"]).pack(pady=(0, px(4)))
            col = tk.Frame(grid, bg=card)
            col.grid(row=1, column=i, sticky="nsew", padx=px(3))
            day_stages = sorted([s for s in stages if d in s["days"] and len(s["days"]) < 7],
                                key=diff_order)
            for s in day_stages:
                self._week_cell(col, s, my, colw).pack(fill="x", pady=(0, px(8)))
            if not day_stages:
                tk.Label(col, text="–", bg=card, fg=C["secondary"], font=self.f["w_sub"]).pack()
        self._paint_week()

    def _week_cell(self, parent, s: dict, my: set[str], width: int, horizontal: bool = False):
        bg = C["card"]
        cell = tk.Frame(parent, bg=bg, cursor="hand2")
        ws = [cell]
        pic = self.pics.of(s, "stage", px(40 * self.k), width - px(4))
        if pic:
            lab = tk.Label(cell, image=pic, bg=bg, cursor="hand2")
            lab.pack(side="left" if horizontal else "top", anchor="w")
            ws.append(lab)
        txt = tk.Frame(cell, bg=bg, cursor="hand2")
        txt.pack(side="left" if horizontal else "top", fill="x", padx=(px(6) if horizontal else 0, 0))
        ws.append(txt)
        n = len(self._mine_for_stage(s, my)) if my else 0
        # Narrow day columns: drop the "Shrine of" / "Temple of" every stage shares, so
        # names wrap between words instead of mid-word.
        narrow = not horizontal and width < px(150 * self.k)
        label = s["name"]
        if narrow:
            for pre in ("Shrine of the ", "Shrine of ", "Temple of "):
                if label.startswith(pre):
                    label = label[len(pre):]
                    break
        font = scaled(F["footnote_semi"], self.k * 0.86) if narrow else self.f["w_name"]
        name = tk.Label(txt, text=label, bg=bg, fg=C["label"], font=font,
                        anchor="w", justify="left", wraplength=width - px(4), cursor="hand2")
        name.pack(fill="x")
        sub = tk.Label(txt, text=f"{s['difficulty']} · {s['boss']}", bg=bg,
                       fg=C[DIFF_COLOR.get(s["difficulty"], "secondary")], font=self.f["w_sub"],
                       anchor="w", justify="left", wraplength=width - px(4), cursor="hand2")
        sub.pack(fill="x")
        ws += [name, sub]
        if n:
            mine = tk.Label(txt, text=f"★ {n} yours" if narrow else f"★ {n} of your units",
                            bg=bg, fg=C["orange"], font=self.f["w_sub"], anchor="w",
                            cursor="hand2")
            mine.pack(fill="x")
            ws.append(mine)
        ready = self._ready_text(s, my)[0] if my else ""
        if ready:
            fit = tk.Label(txt, text=f"✓ {ready}" if narrow else f"✓ ready {ready}",
                           bg=bg, fg=C["green"], font=self.f["w_sub"], anchor="w",
                           cursor="hand2")
            fit.pack(fill="x")
            ws.append(fit)
        for w in ws:
            w.bind("<Button-1>", lambda e, s=s: self._week_pick(s))
        self._week_cells.setdefault(s["slug"], []).extend(ws)
        return cell

    def _week_pick(self, s: dict):
        self._sel["Week"] = ("stage", s)
        self._show("stage", s)
        self._paint_week()

    def _paint_week(self):
        sel = self._sel.get("Week")
        slug = sel[1]["slug"] if sel else None
        on = ios.mix(C["card"], C["blue"], 0.22 if ios.DARK_MODE else 0.12)
        for sl, ws in self._week_cells.items():
            for w in ws:
                try:
                    w.configure(bg=on if sl == slug else C["card"])
                except tk.TclError:
                    pass

    # ================================================================== selection
    def _tree_click(self, e):
        """Units view: a click in the ★ column stars / unstars that unit.
        Team view: a click in the Team column adds / removes that unit."""
        view = self.view.get()
        if view not in ("Units", "Team") or self.tree.identify_region(e.x, e.y) != "cell":
            return
        if self.tree.identify_column(e.x) != "#1":
            return
        iid = self.tree.identify_row(e.y)
        r = self._rows.get(iid)
        if r:
            if view == "Units":
                self.toggle_star(r["rec"])
            else:
                self.toggle_team(r["rec"]["name"])
            return "break"

    def _on_select(self):
        sel = self.tree.selection()
        r = self._rows.get(sel[0]) if sel else None
        view = self.view.get()
        if r and r.get("kind") == "group":  # a day row in the planner: back to the summary
            self._sel[view] = None
            return self._show_placeholder(view)
        if not r or not r.get("rec"):
            return
        if view == "Team":  # the panel stays on the team check; the row is just a pick
            self._sel[view] = None
            return self._show_team_panel()
        self._sel[view] = (r["kind"], r["rec"])
        self._show(r["kind"], r["rec"])

    def _show(self, kind: str, rec: dict):
        self._shown = (kind, rec)
        {"stage": self._show_stage, "crest": self._show_crest,
         "unit": self._show_unit}.get(kind, lambda r: None)(rec)

    def _show_placeholder(self, view: str):
        self._shown = None
        if view == "Planner":
            return self._show_plan_panel()
        if view == "Compare":
            return self._show_compare_panel()
        if view == "Team":
            return self._show_team_panel()
        if view == "Today":
            return self._show_today_panel()
        self._begin()
        self._put(f"\nSelect a {HINTS.get(view, 'row')} to see its details.\n\n", "dim")
        self._put("Blue names are links to other stages, crests and units; ‹ Back (Alt+←) "
                  "returns.\n", "dim")
        if not self.my.all():
            self._put("\nTip: star the units you own in Units (★ column), or point “Rerun "
                      "folder…” at your Rerun to use its unit scan. Stages and crests then show "
                      "which of your units want them.", "dim")
        self._end()

    # ================================================================== detail
    def _begin(self):
        d = self.detail
        d.configure(state="normal")
        d.delete("1.0", "end")
        for t in d.tag_names():
            if t[:1] in ("L", "A") and t[1:].isdigit():
                d.tag_delete(t)
        self._links = 0
        self._actions = {}

    def _end(self):
        self.detail.configure(state="disabled")
        self.detail.yview_moveto(0)

    def _put(self, text: str, *tags):  # not "_w": Tk widgets keep their path name in _w
        self.detail.insert("end", text, tags)

    def _pic(self, photo, padx: int = 0) -> bool:
        if photo is None:
            return False
        self.detail.image_create("end", image=photo, padx=padx, align="center")
        return True

    def _link(self, text: str, view: str, rec: dict, *tags):
        self._links += 1
        tag = f"L{self._links}"
        self.detail.insert("end", text, ("link", tag) + tags)
        self.detail.tag_bind(tag, "<Button-1>", lambda e: self.go(view, rec))

    def _action(self, text: str, fn, *tags):
        self._links += 1
        tag = f"A{self._links}"
        self.detail.insert("end", text, ("action", "semi", tag) + tags)
        self.detail.tag_bind(tag, "<Button-1>", lambda e: fn())
        self._actions[text] = fn  # what each action on the panel does (for tests)

    def _crest_icon(self, name: str, size: int = 18):
        c = self.gsc.crest(name)
        if c and self._pic(self.pics.of(c, "crest", px(size * self.k))):
            self._put(" ")

    def _crest_link(self, name: str):
        c = self.gsc.crest(name)
        if c:
            self._link(c["name"], "Crests", c)
        else:
            self._put(name)

    def _unit_link(self, name: str):
        u = self.gsc.match_unit(name)
        mine = name in self.my.all()
        if u:
            self._link((("★ " if mine else "") + u["name"]).replace(" ", NBSP), "Units", u)
        else:
            self._put(name.replace(" ", NBSP))

    def _stage_text(self, s: dict, today: str):
        self._link(s["name"], "Stage", s)
        self._put(f" {s['difficulty']}", s["difficulty"])
        self._put(f"  {short_days(s['days'])}", "dim")
        if today in s["days"]:
            self._put("  open today", "good")

    def _units_list(self, names: list[str]):
        for i, name in enumerate(names[:MAX_UNIT_LINKS]):
            if i:
                self._put(",  ")
            self._unit_link(name)
        if len(names) > MAX_UNIT_LINKS:
            self._put(f"  and {len(names) - MAX_UNIT_LINKS} more", "dim")
        self._put("\n")

    def _show_stage(self, s: dict):
        today = today_name()
        my = self.my.all()
        self._begin()
        if self._pic(self.pics.of(s, "stage", px(170 * self.k), self._detail_w())):
            self._put("\n")
        self._put(s["name"] + "\n", "title")
        self._put(s["difficulty"], s["difficulty"], "semi")
        self._put(f"  ·  Boss: {s['boss']}\n", "sub")
        g = self.guides.for_stage(s)
        self._put("OPEN\n", "h")
        self._put(short_days(s["days"]))
        if today in s["days"]:
            self._put("   open today", "good")
        self._put("\n")
        if g:
            self._guide_top(g, my)
        elif s.get("hazards"):
            self._put("HAZARDS\n", "h")
            for hz in s["hazards"]:
                self._put(f"•  {hz}\n")
        self._put("CRESTS THAT DROP HERE\n", "h")
        for name in s.get("crests", []):
            self._put("•  ")
            self._crest_icon(name)
            self._crest_link(name)
            wanting = self.gsc.units_wanting(name)
            mine = self.my.needing(name, [u for u in wanting if u in my])
            if wanting:
                self._put(f"   {len(wanting)} unit{'s' if len(wanting) != 1 else ''}", "dim")
            if mine:
                self._put(f"  ★ {len(mine)} yours", "mine")
            self._put("\n")
        mine_here = sorted(self._mine_for_stage(s, my)) if my else []
        if mine_here:
            self._put(f"YOUR UNITS THAT WANT CRESTS HERE ({len(mine_here)})\n", "h")
            self._units_list(mine_here)
        if g:
            self._guide_waves(g)
            src = g.get("source") or {}
            if src.get("text"):
                self._put("\n")
                if src.get("url", "").startswith("https://"):
                    self._put(src["text"].rstrip(".") + "  ", "dim")
                    self._action("Open guide ↗", lambda u=src["url"]: self._open_url(u))
                else:
                    self._put(src["text"], "dim")
                self._put("\n")
        elif self.guides.available is False:
            self._put("\nNo stage guide saved. Fetch them with:  py gsc_app/fetch_guides.py\n",
                      "dim")
        self._end()

    # --- stage guide ------------------------------------------------------------
    def _face(self, name: str, h: int = 22):
        """Small unit picture + linked name (★ when it's yours)."""
        u = self.gsc.match_unit(name)
        if u and self._pic(self.pics.of(u, "unit", px(h * self.k))):
            self._put(" ")
        self._unit_link(name)

    def _faces(self, units: list[dict], sep: str = "    "):
        for i, u in enumerate(units):
            if i:
                self._put(sep)
            self._face(u["name"])

    def _guide_top(self, g: dict, my: set[str]):
        facts = g.get("facts") or {}
        if g.get("summary"):
            self._put("STRATEGY\n", "h")
            self._put(g["summary"] + "\n")
        if facts or g.get("tags"):
            self._put("BOSS\n", "h")
            sub = g.get("subtitle", "").removeprefix("Boss:").strip()
            self._put((sub or g.get("boss", "")) + "\n", "semi")
            tags = [t for t in g.get("tags", []) if "(PST)" not in t]
            line = "  ·  ".join(tags + [f"{k} {v}" for k, v in facts.items()])
            if line:
                self._put(line + "\n", "dim")
        rec = Guides.recommended(g)
        mine = [n for n in rec if n in my]
        if g.get("roles"):
            self._put("RECOMMENDED UNITS\n", "h")
            if mine:
                self._put(f"★ {len(mine)} of yours are recommended here\n", "mine")
            for r in g["roles"]:
                self._put(r["role"] + "\n", "semi", "role")
                self._faces(r["picks"])
                self._put("\n")
                if r.get("also"):
                    self._put("Also fits:  ", "dim")
                    self._faces(r["also"], ",  ")
                    self._put("\n")
        if g.get("teams"):
            self._put(f"EXAMPLE TEAMS ({len(g['teams'])})\n", "h")
            for i, t in enumerate(g["teams"], 1):
                self._put(f"{i}.  ", "semi")
                self._faces(t["units"], "  ·  ")
                have = sum(1 for u in t["units"] if u["name"] in my)
                if my and have:
                    self._put(f"   ★ {have}/{len(t['units'])}", "mine")
                self._put("\n")
                link = t.get("team_builder", "").startswith("https://gscompanion.com/")
                if t.get("note"):
                    self._put(t["note"] + ("   " if link else "\n"), "dim", "indent")
                if link:
                    self._action("Team builder ↗",
                                 lambda u=t["team_builder"]: self._open_url(u), "indent")
                    self._put("\n", "indent")

    def _guide_waves(self, g: dict):
        waves = g.get("waves") or []
        if not waves:
            return
        self._put("WAVES\n", "h")
        self._action("Hide enemy details" if self._show_foes else "Show enemy details",
                     self._toggle_foes)
        self._put("\n")
        for w in waves:
            self._put("\n")
            if self._pic(self.pics.site(w.get("image", ""), px(30 * self.k))):
                self._put(" ")
            self._put(w.get("label", ""), "dim")
            self._put("  " + w.get("name", ""), "semi")
            if w.get("details"):
                self._put("   " + "  ·  ".join(w["details"]), "dim")
            self._put("\n")
            chips = w.get("chips") or []
            if chips:
                for i, c in enumerate(chips):
                    if i:
                        self._put("  ·  ", "dim")
                    self._put(c["text"], "bad" if c.get("tone") == "bad" else "dim")
                self._put("\n")
            for n in w.get("notes", []):
                self._put(n + "\n")
            if self._show_foes:
                for e in w.get("enemies", []):
                    self._put("", "indent")
                    if self._pic(self.pics.site(e.get("image", ""), px(20 * self.k))):
                        self._put(" ")
                    self._put(e["name"] + (f" {e['count']}" if e.get("count") else ""), "semi",
                              "indent")
                    bits = [e.get("info", "")] + [f"{k} {v}" for k, v in e.get("stats", {}).items()]
                    self._put("   " + "  ·  ".join(b for b in bits if b) + "\n", "dim", "indent")
                    if e.get("traits"):
                        self._put("  ·  ".join(e["traits"]) + "\n", "dim", "indent")

    def _toggle_foes(self):
        self._show_foes = not self._show_foes
        y = self.detail.yview()[0]
        if self._shown:
            self._show(*self._shown)
            self.detail.yview_moveto(y)

    def _detail_w(self) -> int:
        return max(px(200), self.detail.winfo_width() - px(24))

    def _show_crest(self, c: dict):
        today = today_name()
        my = self.my.all()
        self._begin()
        if self._pic(self.pics.of(c, "crest", px(48 * self.k))):
            self._put("  ")
        self._put(c["name"] + "\n", "title")
        sub = c["kind"].title() + " crest" + (f"  ·  event: {c['event']}" if c.get("event") else "")
        self._put(sub + "\n", "sub")
        if c["name"] in self.s["compare"]:
            self._action("✓ In Compare – remove", lambda: self.toggle_compare(c))
        else:
            self._action("⇄ Compare", lambda: self.toggle_compare(c))
        self._put("\n")
        if c.get("effect"):
            self._put("EFFECT\n", "h")
            self._put(c["effect"] + "\n")
        if c.get("levels"):
            self._put("BY LEVEL\n", "h")
            for lv, text in c["levels"].items():
                if self._pic(self.pics.level(lv, px(18 * self.k))):
                    self._put(" ")
                self._put(f"{lv}\t", "dim")
                self._put(text.replace("\n", "  ·  ") + "\n")
        stages = self.gsc.stages_dropping(c["name"])
        self._put("WHERE IT DROPS\n", "h")
        if stages:
            for s in sorted(stages, key=diff_order):
                self._put("•  ")
                self._stage_text(s, today)
                self._put("\n")
        elif c.get("event"):
            self._put(f"From the {c['event']} event, not the Crest Palace.\n", "dim")
        else:
            self._put("Not listed in any Crest Palace stage.\n", "dim")
        units = self.gsc.units_wanting(c["name"])
        mine = self.my.needing(c["name"], [u for u in units if u in my])
        done = [u for u in units if u in my and u not in mine]
        if mine:
            self._put(f"YOUR UNITS THAT STILL NEED IT ({len(mine)})\n", "h")
            self._units_list(mine)
        if done:
            self._put(f"YOUR UNITS THAT HAVE IT ({len(done)})\n", "h")
            self._units_list(done)
        self._put(f"RECOMMENDED FOR {len(units)} UNIT{'S' if len(units) != 1 else ''}\n", "h")
        if units:
            self._units_list(units)
        else:
            self._put("No unit lists this crest.\n", "dim")
        self._end()

    def _show_unit(self, u: dict):
        today = today_name()
        name = u["name"]
        self._begin()
        if self._pic(self.pics.of(u, "unit", px(76 * self.k))):
            self._put("  ")
        self._put(name + "\n", "title")
        self._put(f"{u['element']}  ·  {u['tag']}", "sub")
        if name in self.my.scanned():
            self._put("  ·  in your Rerun scan", "good")
        self._put("\n")
        if self.my.is_starred(name):
            self._action("★ Starred – unstar", lambda: self.toggle_star(u))
        else:
            self._action("☆ Star (my unit)", lambda: self.toggle_star(u))
        self._put("      ")
        if name in self.s["plan"]:
            self._action("✓ In farm planner – remove", lambda: self.toggle_plan(u))
        else:
            self._action("＋ Add to farm planner", lambda: self.toggle_plan(u))
        self._put("      ")
        self._action("⚔ Add to team", lambda: (self.toggle_team(name)
                                               if name not in self.s["team"] else None,
                                               self.show_view("Team")))
        self._put("\n")
        d = self.details.get(name) or {}
        if d.get("aka"):
            self._put("Also known as: " + ", ".join(d["aka"]) + "\n", "dim")
        stages = {s["slug"]: s for s in self.gsc.stages if s.get("slug")}
        rec_in = [(stages[slug], role) for slug, role in self.guides.stages_for_unit(name)
                  if slug in stages]
        if rec_in:
            self._put(f"RECOMMENDED IN THE CREST PALACE ({len(rec_in)})\n", "h")
            for s, role in sorted(rec_in, key=lambda x: diff_order(x[0])):
                self._put("•  ")
                self._stage_text(s, today)
                self._put(f"\n      {role}\n", "dim")
        picks = self.gsc.recommendations.get(name, [])
        self._put("RECOMMENDED CRESTS (BEST FIRST)\n", "h")
        if not picks:
            self._put("No crest recommendation for this unit.\n", "dim")
        for note in self.gsc._load("crest_recommendations.json").get("notes", {}).get(name, []):
            self._put(note + "\n", "dim")
        farm_today = []
        for i, cname in enumerate(picks, 1):
            have = self.my.has(name, cname)
            self._put(f"{i}.  ")
            self._crest_icon(cname)
            self._crest_link(cname)
            self._put("    ")
            self._action("✓ has it" if have else "☐ has it",
                         lambda c=cname: self.toggle_have(u, c))
            self._put("\n")
            if have:
                continue
            c = self.gsc.crest(cname)
            stages = self.gsc.stages_dropping(cname)
            if stages:
                for s in sorted(stages, key=diff_order):
                    self._put("      ")
                    self._stage_text(s, today)
                    self._put("\n")
                    if today in s["days"]:
                        farm_today.append((cname, s))
            elif c and c.get("event"):
                self._put(f"      event: {c['event']}\n", "dim")
            else:
                self._put("      not in the Crest Palace\n", "dim")
        if picks:
            self._put("FARM TODAY\n", "h")
            if farm_today:
                for cname, s in farm_today:
                    self._put("•  ")
                    self._crest_icon(cname)
                    self._crest_link(cname)
                    self._put("  in  ")
                    self._link(s["name"], "Stage", s)
                    self._put(f" {s['difficulty']}", s["difficulty"])
                    self._put("\n")
            elif all(self.my.has(name, c) for c in picks):
                self._put("It has every recommended crest.\n", "good")
            else:
                self._put(f"None of the crests it still needs drop on {today}.\n", "dim")
        self._kit_section(name)
        self._end()

    def _show_plan_panel(self):
        self._shown = None
        p = self.plan()
        today = today_name()
        self._begin()
        self._put("Farm planner\n", "title")
        self._put("The crests your chosen units need, by the day they can be farmed.\n", "sub")
        todays = p["days"][today] + p["every"]
        self._put(f"TODAY ({today.upper()})\n", "h")
        if not p["units"]:
            self._put("Add units with “Add my units”, or open any unit and choose "
                      "“Add to farm planner”.\n", "dim")
        elif todays:
            for e in sorted(todays, key=lambda e: e["crest"]):
                self._put("•  ")
                self._crest_icon(e["crest"])
                self._crest_link(e["crest"])
                self._put("  in  ")
                self._link(e["stage"]["name"], "Stage", e["stage"])
                self._put(f" {e['stage']['difficulty']}", e["stage"]["difficulty"])
                self._put(f"\n      for {', '.join(e['units'])}\n", "dim")
        else:
            self._put("Nothing in this plan drops today.\n", "dim")
        if p["units"]:
            self._put(f"UNITS IN THE PLAN ({len(p['units'])})\n", "h")
            for name in p["units"]:
                u = self.gsc.match_unit(name)
                if u and self._pic(self.pics.of(u, "unit", px(22 * self.k))):
                    self._put(" ")
                self._unit_link(name)
                self._put("   ")
                self._action("remove", lambda n=name: self.toggle_plan({"name": n}))
                self._put("\n")
        self._end()

    def _show_today_panel(self):
        self._shown = None
        today = today_name()
        my = self.my.all()
        self._begin()
        self._put(f"Today: {today}\n", "title")
        self._put("Game day (resets 06:00 UTC−6). Pick a stage or crest for its details.\n",
                  "sub")
        if not my:
            self._put("\nStar the units you own in Units (★ column), or point “Rerun folder…” "
                      "at your Rerun to use its unit scan. Today then shows what to farm for "
                      "them and how ready you are for each stage.\n", "dim")
        best = None
        rows = self._today_rows()
        for r in rows:
            s = r["rec"]
            self._put("\n")
            self._link(s["name"], "Stage", s, "semi")
            self._put(f"  {s['difficulty']}", s["difficulty"])
            if r["values"]["ready"]:
                self._put(f"   ready {r['values']['ready']}",
                          "dim" if r["values"]["ready"].startswith("0/") else "good")
            self._put("\n")
            for kid in r.get("children", []):
                self._put("•  ")
                self._crest_icon(kid["values"]["name"])
                self._crest_link(kid["values"]["name"])
                self._put(f"   for {kid['values']['units']}\n", "dim")
            if not r.get("children") and my:
                self._put("Nothing your units still need.\n", "dim")
            if best is None and r.get("children"):
                best = s
        if best is not None:
            self._put("\n")
            self._action(f"Check a team for {best['name']} ›",
                         lambda s=best: self.open_team_for(s))
            self._put("\n")
        if self.s["have"]:
            n = sum(len(v) for v in self.s["have"].values())
            self._put(f"\n{n} crest{'s' if n != 1 else ''} marked as already had are left out. "
                      "Change that on a unit's page.\n", "dim")
        self._end()

    def _show_team_panel(self):
        self._shown = None
        st = self.team_stage_rec()
        team = [n for n in self.s["team"] if self.gsc.match_unit(n)]
        my = self.my.all()
        self._begin()
        if st is None:
            self._put("No Crest Palace data.\n", "dim")
            return self._end()
        self._put("Team check\n", "title")
        self._link(st["name"], "Stage", st)
        self._put(f"  {st['difficulty']}", st["difficulty"])
        self._put(f"   ·   {short_days(st['days'])}\n", "dim")
        res = self.teams.check(team, st, my)
        g = res["guide"]
        self._put(f"TEAM ({len(team)}/{TEAM_SIZE})\n", "h")
        for i in range(TEAM_SIZE):
            self._put(f"{i + 1}.  ", "dim")
            if i < len(team):
                self._face(team[i])
                self._put("   ")
                self._action("remove", lambda n=team[i]: self.toggle_team(n))
            else:
                self._put("empty – click ＋ next to a unit in the list", "dim")
            self._put("\n")
        if team:
            self._action("Clear team", self.team_clear)
            self._put("      ")
        self._action("Suggest a team from my units", self.team_suggest)
        self._put("\n")
        if not g:
            self._put("\nNo guide for this stage, so there is nothing to check against.\n", "dim")
            return self._end()
        self._put("ROLES THE GUIDE ASKS FOR\n", "h")
        for r in res["roles"]:
            if r["covered"]:
                self._put("✓  ", "good")
                self._put(r["role"], "semi")
                self._put("   ")
                for j, n in enumerate(r["covered"]):
                    if j:
                        self._put(", ")
                    self._unit_link(n)
                self._put("\n")
            else:
                self._put("✗  ", "bad")
                self._put(r["role"], "semi")
                if r["yours"]:
                    self._put("   yours: ", "dim")
                    for j, n in enumerate(r["yours"][:6]):
                        if j:
                            self._put(", ")
                        self._unit_link(n)
                        self._put(" ")
                        self._action("＋", lambda n=n: self.toggle_team(n))
                else:
                    self._put("   none of yours – top picks: ", "dim")
                    self._units_inline(r["picks"][:4])
                self._put("\n")
        self._put("HAZARD WARNINGS\n", "h")
        if res["warnings"]:
            for name, why in res["warnings"]:
                self._put("⚠  ", "bad")
                self._unit_link(name)
                self._put(f": {why}\n")
        elif team:
            self._put("None found for this team.\n", "dim")
        else:
            self._put("Add units to check them against: " +
                      ", ".join(hazards(st, g)) + "\n", "dim")
        if res["no_details"] and self.details:
            self._put(f"No kit details for {', '.join(res['no_details'])}: only element "
                      "checks were made for them.\n", "dim")
        elif not self.details:
            self._put("Unit kits aren't downloaded (Update data), so only element hazards "
                      "are checked.\n", "dim")
        if res["teams"]:
            self._put(f"EXAMPLE TEAMS ({len(res['teams'])})\n", "h")
            for t in res["teams"]:
                self._put(f"{t['n']}.  ", "semi")
                self._units_inline(t["units"])
                own = len(t["owned"])
                self._put("\n")
                self._put(f"you have {own}/{len(t['units'])}",
                          "good" if own == len(t["units"]) else "dim", "indent")
                self._put("   ", "indent")
                self._action("Use this team", lambda t=t: self.team_set(t["units"]), "indent")
                self._put("\n", "indent")
                if t["note"]:
                    self._put(t["note"] + "\n", "dim", "indent")
        self._put("\nA rule-of-thumb check against the stage guide; equips, levels and "
                  "playing it out still decide the clear.\n", "dim")
        self._end()

    def _units_inline(self, names: list[str]):
        for j, n in enumerate(names):
            if j:
                self._put(", ")
            self._unit_link(n)

    def _kit_section(self, name: str):
        d = self.details.get(name)
        if not d:
            return
        self._put("KIT\n", "h")
        self._action("Hide kit" if self._show_kit else "Show kit", self._toggle_kit)
        bits = [d.get("race", ""), d.get("details", {}).get("Attack", ""),
                ("Released " + d["released"]) if d.get("released") else ""]
        line = "  ·  ".join(b for b in bits if b)
        if line:
            self._put("    " + line, "dim")
        self._put("\n")
        if not self._show_kit:
            return
        for m in d.get("moves", []):
            self._put(m.get("type", "") + "  ", "dim")
            self._put(m.get("name", ""), "semi")
            tags = "  ·  ".join(f"{k} {v}" for k, v in m.get("tags", {}).items())
            if tags:
                self._put("   " + tags, "dim")
            self._put("\n" + m.get("text", "") + "\n", "indent")
        if d.get("passives"):
            self._put("Passives\n", "semi", "role")
            for p in d["passives"]:
                self._put(p["name"], "semi", "indent")
                self._put("  " + p["text"] + "\n", "indent")
        tw = d.get("true_weapon") or {}
        if tw.get("name"):
            self._put("True weapon  ", "dim", "role")
            self._put(tw["name"], "semi", "role")
            self._put(("   " + tw["kind"]) if tw.get("kind") else "", "dim", "role")
            self._put("\n" + tw.get("text", "") + "\n", "indent")
            for p in tw.get("passives", []):
                self._put("•  " + p + "\n", "indent")
        if d.get("slots"):
            self._put("Equip slots  ", "dim", "role")
            self._put("   ".join(d["slots"]) + "\n", "role")
        tags = {k: v for k, v in d.get("tags", {}).items()
                if k not in ("Equip Slots", "Source", "Race") and v}
        if tags:
            self._put("Tags\n", "semi", "role")
            for k, v in tags.items():
                self._put(k + ":  ", "dim", "indent")
                self._put(", ".join(v) + "\n", "indent")

    def _toggle_kit(self):
        self._show_kit = not self._show_kit
        y = self.detail.yview()[0]
        if self._shown:
            self._show(*self._shown)
            self.detail.yview_moveto(y)

    def _show_compare_panel(self):
        self._shown = None
        self._begin()
        self._put("Compare crests\n", "title")
        self._put(f"Side by side at every level (up to {MAX_COMPARE}).\n", "sub")
        names = [n for n in self.s["compare"] if self.gsc.crest(n)]
        if not names:
            self._put("\nOpen any crest and choose “⇄ Compare”.\n", "dim")
        for n in names:
            self._put("\n")
            self._crest_icon(n, 22)
            self._crest_link(n)
            self._put("   ")
            self._action("remove", lambda n=n: self.toggle_compare(self.gsc.crest(n)))
        self._put("\n")
        self._end()

    # ================================================================== actions
    def toggle_have(self, u: dict, crest: str):
        on = self.my.toggle_have(u["name"], crest)
        self.flash(f"{u['name']}: {'has' if on else 'still needs'} {crest}", "ok")
        self._refresh_keep()

    def toggle_team(self, name: str):
        team = [n for n in self.s["team"] if n != name]
        if len(team) == len(self.s["team"]):
            if len(team) >= TEAM_SIZE:
                return self.flash(f"The team is full ({TEAM_SIZE}): remove someone first", "warn")
            team.append(name)
        self.s["team"] = team
        self.s.save()
        self._refresh_keep()

    def team_set(self, names: list[str]):
        self.s["team"] = [n for n in names if self.gsc.match_unit(n)][:TEAM_SIZE]
        self.s.save()
        self._refresh_keep()

    def team_clear(self):
        self.team_set([])

    def team_suggest(self):
        st = self.team_stage_rec()
        my = self.my.all()
        if not my:
            return self.flash("Star your units in Units first", "warn")
        team = self.teams.suggest(st, my, self.s["team"]) if st else []
        if not team:
            return self.flash("None of your units are in this stage's guide", "warn")
        self.team_set(team)
        self.flash(f"Suggested: {', '.join(team)}", "ok")

    def open_team_for(self, s: dict):
        self.s["team_stage"] = s["slug"]
        self.s.save()
        self.show_view("Team")

    def _team_stage_changed(self):
        label = self.team_stage.get()
        st = next((s for s in self.gsc.stages if self._stage_label(s) == label), None)
        if st:
            self.s["team_stage"] = st["slug"]
            self.s.save()
        self.refresh()
        self._show_team_panel()

    def _team_filter_changed(self):
        self.s["team_filter"] = self.team_filter.get()
        self.s.save()
        self.refresh()

    # --- new game day ---------------------------------------------------------------
    def _check_day(self):
        """Every minute: when the game day rolls over (06:00 UTC−6) refresh and say what's
        open; the taskbar button flashes if the window isn't in front."""
        try:
            now = today_name()
            if now != self._game_day:
                self._game_day = now
                self.s["last_day"] = now
                self.s.save()
                self._new_day(now)
        finally:
            if self.winfo_exists():
                self.after(DAY_CHECK_MS, self._check_day)

    def _new_day(self, day: str):
        my = self.my.all()
        n = sum(len(r.get("children", [])) for r in self._today_rows())
        self.flash(f"New game day: {day}. " + (f"{n} crest drops your units need are open."
                                                if my else "Today's stages are open."), "ok")
        if self.view.get() in ("Today", "Week"):
            self._switch(keep_detail=self.view.get() != "Today")
        self._flash_taskbar()

    def _flash_taskbar(self):
        try:
            import ctypes
            top = self.winfo_toplevel()
            if top.focus_displayof() is not None:
                return
            hwnd = ctypes.windll.user32.GetParent(top.winfo_id())
            ctypes.windll.user32.FlashWindow(hwnd, True)
        except Exception:  # noqa: BLE001 - not Windows / no window: nothing to flash
            pass

    # --- update data ----------------------------------------------------------------
    def update_data(self):
        if self._updater is not None:
            if ios.confirm(self.winfo_toplevel(), "Stop the update? What was downloaded so far "
                           "is kept.", "Stop Updating?", ok="Stop", destructive=True):
                self._updater.cancel()
            return
        n_units = len(self.gsc.units)
        missing = n_units - len(self.details)
        msg = ("Download the latest data from gscompanion.com: the Crest Palace, crests, "
               "units, every stage guide and new pictures"
               + (f", plus kit details for {missing} units (about {max(1, missing // 100)} "
                  "minutes)" if missing > 0 else "")
               + ". One page at a time; you can keep using the app.")
        if not ios.confirm(self.winfo_toplevel(), msg, "Update Data?", ok="Update"):
            return
        out = self.data_out
        try:
            if out.resolve() != self.gsc.dir.resolve() and not (out / "crests.json").exists():
                shutil.copytree(self.gsc.dir, out, dirs_exist_ok=True)  # start from bundled copy
        except OSError as e:
            return ios.alert(self.winfo_toplevel(), f"Can't write to {out}:\n{e}", "Update Failed")
        from .update_data import Updater
        state = {"text": "Starting…", "done": False}

        def progress(text, done, total):
            state["text"] = f"Updating: {text}  {done}/{total}" if total else f"Updating: {text}"

        up = Updater(out, progress)
        self._updater = up

        def work():
            try:
                state["ok"] = up.run()
            except Exception as e:  # noqa: BLE001 - network down, site changed...
                state["ok"] = False
                up.failed.append(("update", str(e)))
            state["done"] = True

        threading.Thread(target=work, daemon=True).start()

        def poll():
            if not self.winfo_exists():
                return
            if not state["done"]:
                self._set_footer(state["text"])
                return self.after(400, poll)
            self._updater = None
            self._set_button_text(self.update_btn, "Update data")
            self._data_updated(up, state.get("ok", False))

        self._set_button_text(self.update_btn, "Stop update")
        poll()

    @staticmethod
    def _set_button_text(btn, text: str):
        try:
            btn.set_text(text)
        except tk.TclError:
            pass

    def _data_updated(self, up, ok: bool):
        root = self.data_out.parent.parent
        self._load_data(root)
        self._history.clear()
        self._sel = {v: None for v in VIEWS + [FIND]}
        self._shown = None
        self._set_footer()
        self._switch()
        done = "; ".join(up.summary) or "nothing changed"
        if ok:
            self.flash(f"Data updated: {done}", "ok")
        else:
            fails = len(up.failed)
            self.flash(f"Update finished with {fails} problem{'s' if fails != 1 else ''}: "
                       f"{done}" if fails else f"Update stopped: {done}", "warn")

    def toggle_star(self, u: dict):
        on = self.my.toggle_star(u["name"])
        self.flash(f"{'Starred' if on else 'Unstarred'} {u['name']}", "ok" if on else "info")
        self._refresh_keep()

    def toggle_plan(self, u: dict):
        plan = list(self.s["plan"])
        name = u["name"]
        if name in plan:
            plan.remove(name)
            msg = f"Removed {name} from the farm planner"
        else:
            plan.append(name)
            msg = f"Added {name} to the farm planner"
        self.s["plan"] = plan
        self.s.save()
        self.flash(msg, "ok")
        self._refresh_keep()

    def plan_add_mine(self):
        mine = sorted(self.my.all())
        if not mine:
            return self.flash("No units of yours yet: star some in Units first", "warn")
        plan = list(self.s["plan"]) + [n for n in mine if n not in self.s["plan"]]
        self.s["plan"] = plan
        self.s.save()
        self.flash(f"Farm planner: {len(plan)} units", "ok")
        self._switch()

    def plan_clear(self):
        if self.s["plan"] and ios.confirm(self.winfo_toplevel(), "Remove every unit from the farm "
                                          "planner? Your starred units are kept.", "Clear Plan?",
                                          ok="Clear", destructive=True):
            self.s["plan"] = []
            self.s.save()
            self._sel["Planner"] = None
            self._switch()

    def toggle_compare(self, c: dict | None):
        if not c:
            return
        lst = [n for n in self.s["compare"] if n != c["name"]]
        if len(lst) == len(self.s["compare"]):
            lst.append(c["name"])
            lst = lst[-MAX_COMPARE:]
            self.flash(f"Comparing {len(lst)}: {', '.join(lst)}", "ok")
        self.s["compare"] = lst
        self.s.save()
        self._refresh_keep()

    def compare_clear(self):
        self.s["compare"] = []
        self.s.save()
        self._switch()

    def _refresh_keep(self):
        """Redraw the current view and detail after a star / plan / compare change."""
        view = self.view.get()
        shown = self._shown
        self._build_filters_again(view)
        self.refresh()
        if shown:
            self._show(*shown)
        else:
            self._show_placeholder(view)

    def _build_filters_again(self, view: str):
        focus = self.focus_get()
        typing = focus is not None and focus is getattr(self, "_search_entry", None)
        if typing:
            return  # don't rebuild under the user's cursor
        for w in self.filters.winfo_children():
            w.destroy()
        self._build_filters(view)

    def choose_rerun_dir(self):
        d = filedialog.askdirectory(parent=self.winfo_toplevel(), title="Choose your Rerun folder",
                                    initialdir=str(self.my.rerun_dir or Path.home()))
        if not d:
            return
        if not (Path(d) / "units" / "roster.json").exists():
            ios.alert(self.winfo_toplevel(), "That folder has no units/roster.json yet. In Rerun, "
                      "run the Compendium Counter (Units tab) first, then choose the folder that "
                      "holds Rerun.exe or main.py.", "No Unit Scan")
            return
        self.s["rerun_dir"] = d
        self.s.save()
        self.flash(self.my.scan_status(), "ok")
        self._switch()

    # ================================================================== navigation
    def go(self, view: str, rec: dict, push: bool = True):
        """Jump to a record in another view (links in the detail panel)."""
        if push and self._shown:
            self._history.append((self.view.get(),) + self._shown)
            self._history = self._history[-50:]
        if view not in ("Crests", "Units"):
            view = "Stage" if "boss" in rec else \
                "Crests" if "kind" in rec and "tag" not in rec else "Units"
        if view == "Stage":
            # A stage opens in Today when it's open today, otherwise in the Week grid.
            view = "Today" if today_name() in rec.get("days", []) else "Week"
            self._sel[view] = ("stage", rec)
            self.view.set(view)
            self.seg._draw()
            self._switch()
            if view == "Week":
                self._paint_week()
            else:
                self._select_rec(rec)
            return
        if view == "Crests":
            self.kind.set(ALL_KINDS)
            self.q["Crests"].set("")
        if view == "Units":
            self.element.set(ALL_ELEMENTS)
            self.unit_filter.set("All units")
            self.q["Units"].set("")
        kind = {"Crests": "crest", "Units": "unit"}[view]
        self._sel[view] = (kind, rec)
        self.view.set(view)
        self.seg._draw()
        self._switch()
        self._select_rec(rec)

    def _select_rec(self, rec: dict):
        for iid, r in self._rows.items():
            if r.get("rec") is rec:
                self.tree.selection_set(iid)
                self.tree.see(iid)
                self.tree.focus(iid)
                break

    def back(self):
        if not self._history:
            return self.flash("Nothing to go back to", "info")
        view, kind, rec = self._history.pop()
        if view in ("Crests", "Units") or (kind == "stage" and view in ("Today", "Week")):
            self.go(view if view in ("Crests", "Units") else "Stage", rec, push=False)
        else:
            if view == FIND:
                view = self._before_find if self._before_find in VIEWS else "Today"
            self._sel[view] = (kind, rec) if view in ("Week", "Today") else self._sel.get(view)
            self.view.set(view)
            self.seg._draw()
            self._switch()
            self._show(kind, rec)

    def open_current(self):
        shown = self._shown
        if shown and shown[1].get("url"):
            url = shown[1]["url"]
        elif shown and shown[0] == "crest":
            url = f"{SITE}/crests/"
        else:
            url = {"Week": f"{SITE}/stages/crest-palace/",
                   "Today": f"{SITE}/stages/crest-palace/", "Team": f"{SITE}/team-builder/",
                   "Crests": f"{SITE}/crests/", "Units": f"{SITE}/units/",
                   "Planner": f"{SITE}/crests/", "Compare": f"{SITE}/crests/"}.get(
                self.view.get(), SITE + "/")
        self._open_url(url)
        self.flash("Opened GSCompanion in your browser", "info")
