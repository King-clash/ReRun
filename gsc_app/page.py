"""GS Companion page: the Crest Palace by day and by week, every crest, every unit's
recommended crests, a farm planner and a crest comparison, in Rerun's iOS look.

It is a plain tk.Frame, so it works in its own window (python -m gsc_app / the exe) and
can be dropped into Rerun's tab bar later (see INTEGRATION.md).

Reads:  data/gscompanion/*.json (rerun.gsc_data.GSCData), data/gscompanion/images/
        (gsc_app/fetch_images.py), and Rerun's unit scan <rerun>/units/roster.json.
Writes: only its own settings file (window, view, filters, text size, starred units,
        farm plan, compared crests). Nothing is downloaded; "Open on GSCompanion"
        opens the site in your browser.
"""
from __future__ import annotations

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

SITE = "https://gscompanion.com"
VIEWS = ["Palace", "Week", "Crests", "Units", "Planner", "Compare"]
DIFFS = ["NOVA", "EXTREME", "PRO"]
DIFF_COLOR = {"NOVA": "red", "EXTREME": "orange", "PRO": "blue"}
LEVELS = ["Lv1", "Lv1+", "Lv2", "Lv2+", "Lv3", "Lv3+", "Lv4", "Lv4+", "Lv5", "Lv5+"]
ALL_DIFFS = "All difficulties"
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
    "Palace": [("name", "Stage", 220), ("difficulty", "Difficulty", 90), ("boss", "Boss", 120),
               ("days", "Open", 120), ("mine", "For you", 80), ("team", "Your picks", 84)],
    "Crests": [("name", "Crest", 220), ("kind", "Kind", 80), ("where", "Where it drops", 230),
               ("mine", "For you", 80)],
    "Units": [("mine", "★", 38), ("name", "Unit", 200), ("element", "Element", 76),
              ("tag", "Type", 56), ("picks", "Recommended crests", 300)],
    "Planner": [("name", "Crest", 190), ("stage", "Stage", 250), ("units", "For", 250)],
}
# Columns that take the spare width, per view (the rest keep their size).
STRETCH = {"Palace": {"name", "boss"}, "Crests": {"name", "where"}, "Units": {"picks"},
           "Planner": {"stage", "units"}}
BOARD_VIEWS = ("Week", "Compare")  # drawn as a grid, not a table
CENTER = {"difficulty", "element", "tag", "kind", "mine", "team"}
HINTS = {"Palace": "stage", "Week": "stage", "Crests": "crest", "Units": "unit"}


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
                 settings_path: Path | None = None, rerun_dir: Path | None = None):
        super().__init__(parent, bg=C["bg"])
        self.gsc = GSCData(root)
        self.pics = Pictures(self.gsc.dir / "images")
        self.guides = Guides(self.gsc.dir)
        self._show_foes = False  # stage guide: list every enemy under each wave
        self.s = Settings(settings_path or self.gsc.dir / "companion_settings.json")
        self.my = MyUnits(self.s, self.gsc, Path(rerun_dir or root))
        self._flash_cb = flash
        self._open_url = open_url
        self._rows: dict[str, dict] = {}
        self._sort: dict[str, tuple[str, bool]] = {v: ("", False) for v in VIEWS}
        self._sel: dict[str, tuple[str, dict] | None] = {v: None for v in VIEWS}
        self._shown: tuple[str, dict] | None = None   # what the detail panel shows
        self._history: list[tuple[str, str, dict]] = []
        self._links = 0
        self._actions: dict[str, object] = {}
        self._week_cells: dict[str, list[tk.Widget]] = {}
        self._week_w = 0
        self._sash_ratio = self.s["sash"] if isinstance(self.s["sash"], float) else 0.6

        view = self.s["view"] if self.s["view"] in VIEWS else "Palace"
        self.view = tk.StringVar(value=view)
        self.q = {v: tk.StringVar() for v in ("Crests", "Units")}
        for v in self.q.values():
            v.trace_add("write", lambda *a: self.refresh())
        self.day = tk.StringVar(value=self._today_label())
        self.diff = tk.StringVar(value=self.s["diff"])
        self.kind = tk.StringVar(value=self.s["kind"])
        self.element = tk.StringVar(value=self.s["element"])
        self.unit_filter = tk.StringVar(value=self.s["unit_filter"])
        size_key = next((k for k, (n, _) in SIZES.items() if n == self.s["size"]), "M")
        self.size = tk.StringVar(value=size_key)

        self._build()
        self._apply_size()
        self._bind_keys()
        self._switch()

    # ================================================================== layout
    def _build(self):
        hdr = ios.page_header(self, "GS Companion")
        ios.Button(hdr, "Open on GSCompanion", self.open_current, kind="tinted",
                   icon="link").pack(side="right")
        ios.Segmented(hdr, list(SIZES), self.size, command=self._size_changed).pack(
            side="right", padx=(px(8), px(18)))
        tk.Label(hdr, text="Text size", bg=C["bg"], fg=C["secondary"],
                 font=F["footnote"]).pack(side="right")
        self.back_btn = ios.Button(hdr, "‹ Back", self.back, kind="plain", small=True)
        self.back_btn.pack(side="right", padx=(0, px(22)))

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
        built = self.gsc._load("crests.json").get("built", "?") if self.gsc.available else "?"
        self.footer.configure(text=f"Fan-site data from gscompanion.com, built {built}. What the game "
                                   "shows always wins.   Ctrl+F search · Alt+← back · Ctrl+1–6 views")

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
        if getattr(self, "_search_entry", None) and self._search_entry.winfo_exists():
            self._search_entry.focus_set()
            self._search_entry.select_range(0, "end")

    def _clear_search(self):
        v = self.view.get()
        if v in self.q and self.q[v].get():
            self.q[v].set("")

    # ================================================================== helpers
    def flash(self, text: str, kind: str = "info"):
        if self._flash_cb:
            self._flash_cb(text, kind)
        else:
            self.summary.configure(text=text)

    def _today_label(self) -> str:
        return f"Today ({today_name()})"

    def _day(self) -> str:
        v = self.day.get()
        return today_name() if v.startswith("Today") else v

    def _save_filters(self):
        for key, var in (("diff", self.diff), ("kind", self.kind), ("element", self.element),
                         ("unit_filter", self.unit_filter)):
            self.s[key] = var.get()
        self.s.save()

    def _filter_changed(self):
        self._save_filters()
        self.refresh()

    def _mine_for_stage(self, s: dict, my: set[str]) -> set[str]:
        out = set()
        for name in s.get("crests", []):
            out |= set(self.gsc.units_wanting(name)) & my
        return out

    # ================================================================== views
    def show_view(self, view: str):
        self.view.set(view)
        self.seg._draw()
        self._switch()

    def _switch(self, keep_detail: bool = False):
        view = self.view.get()
        self.s["view"] = view
        self.s.save()
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

        if view == "Palace":
            if self.day.get().startswith("Today"):
                self.day.set(self._today_label())
            select([self._today_label()] + DAYS, self.day)
            select([ALL_DIFFS] + DIFFS, self.diff, padx=(px(16), 0))
        elif view == "Week":
            self._note("Click a stage for its guide.  ★ = crests your units want  ·  "
                       "✓ = your units it recommends")
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
        sortable = view != "Planner"
        for key, head, w in cols:
            self.tree.heading(key, text=head,
                              command=(lambda k=key: self._sort_by(k)) if sortable else "")
            stretch = key in STRETCH.get(view, ())
            self.tree.column(key, width=px(w * self.k), minwidth=px(36), stretch=stretch,
                             anchor="center" if key in CENTER else "w")
        pw = 0
        if self.pics.available:
            pw = px(104 * self.k) if view == "Palace" else px(48 * self.k)
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
        self._sort[view] = (key, not desc if cur == key else key == "mine")
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
        rows = {"Palace": self._palace_rows, "Crests": self._crest_rows, "Units": self._unit_rows,
                "Planner": self._planner_rows}[view]()
        key, desc = self._sort[view]
        if key:
            rows.sort(key=lambda r: str(r["values"][key]).lower(), reverse=desc)
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
                                    "farm planner”, or use “Add my units”."}
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
    def _palace_rows(self) -> list[dict]:
        day = self._day()
        diff = None if self.diff.get() == ALL_DIFFS else self.diff.get()
        stages = sorted(self.gsc.palace_on(day, diff), key=diff_order)
        today = today_name()
        my = self.my.all()
        self.summary.configure(text=f"{len(stages)} stage{'s' if len(stages) != 1 else ''} on "
                                    f"{day}  ·  game day now: {today}")
        rows = []
        for s in stages:
            n = len(self._mine_for_stage(s, my)) if my else 0
            g = self.guides.for_stage(s)
            t = len(set(Guides.recommended(g)) & my) if g and my else 0
            rows.append({"rec": s, "kind": "stage",
                         "tags": ("open",) if today in s["days"] else (),
                         "values": {"name": s["name"], "difficulty": s["difficulty"],
                                    "boss": s["boss"], "days": short_days(s["days"]),
                                    "mine": f"★ {n}" if n else "",
                                    "team": f"✓ {t}" if t else ""}})
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
            n = len(set(self.gsc.units_wanting(c["name"])) & my) if my else 0
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
        self.summary.configure(text=f"{len(p['units'])} units  ·  "
                                    f"{len({c for u in p['units'] for c in self.gsc.recommendations.get(u, [])})}"
                                    " crests needed")
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
        g = self.guides.for_stage(s)
        t = len(set(Guides.recommended(g)) & my) if g and my else 0
        if t:
            fit = tk.Label(txt, text=f"✓ {t} pick{'s' if t != 1 else ''}" if narrow
                           else f"✓ {t} recommended",
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
        """Units view: a click in the ★ column stars / unstars that unit."""
        if self.view.get() != "Units" or self.tree.identify_region(e.x, e.y) != "cell":
            return
        if self.tree.identify_column(e.x) != "#1":
            return
        iid = self.tree.identify_row(e.y)
        r = self._rows.get(iid)
        if r:
            self.toggle_star(r["rec"])

    def _on_select(self):
        sel = self.tree.selection()
        r = self._rows.get(sel[0]) if sel else None
        view = self.view.get()
        if r and r.get("kind") == "group":  # a day row in the planner: back to the summary
            self._sel[view] = None
            return self._show_plan_panel()
        if not r or not r.get("rec"):
            return
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
            self._link(("★ " if mine else "") + u["name"], "Units", u)
        else:
            self._put(name)

    def _stage_text(self, s: dict, today: str):
        self._link(s["name"], "Palace", s)
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
            mine = [u for u in wanting if u in my]
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
        mine = [u for u in units if u in my]
        if mine:
            self._put(f"YOUR UNITS THAT WANT IT ({len(mine)})\n", "h")
            self._units_list(mine)
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
        self._put("\n")
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
        farm_today = []
        for i, cname in enumerate(picks, 1):
            self._put(f"{i}.  ")
            self._crest_icon(cname)
            self._crest_link(cname)
            self._put("\n")
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
                    self._link(s["name"], "Palace", s)
                    self._put(f" {s['difficulty']}", s["difficulty"])
                    self._put("\n")
            else:
                self._put(f"None of these crests drop on {today}.\n", "dim")
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
                self._link(e["stage"]["name"], "Palace", e["stage"])
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
        if view == "Palace":
            if self._day() not in rec.get("days", []):
                self.day.set(self._today_label() if today_name() in rec.get("days", [])
                             else rec["days"][0])
            if self.diff.get() not in (ALL_DIFFS, rec.get("difficulty")):
                self.diff.set(ALL_DIFFS)
        if view == "Crests":
            self.kind.set(ALL_KINDS)
            self.q["Crests"].set("")
        if view == "Units":
            self.element.set(ALL_ELEMENTS)
            self.unit_filter.set("All units")
            self.q["Units"].set("")
        kind = {"Palace": "stage", "Crests": "crest", "Units": "unit"}[view]
        self._sel[view] = (kind, rec)
        self.view.set(view)
        self.seg._draw()
        self._switch()
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
        if view in ("Palace", "Crests", "Units"):
            self.go(view, rec, push=False)
        else:
            self._sel[view] = (kind, rec) if view == "Week" else self._sel.get(view)
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
            url = {"Palace": f"{SITE}/stages/crest-palace/", "Week": f"{SITE}/stages/crest-palace/",
                   "Crests": f"{SITE}/crests/", "Units": f"{SITE}/units/",
                   "Planner": f"{SITE}/crests/", "Compare": f"{SITE}/crests/"}[self.view.get()]
        self._open_url(url)
        self.flash("Opened GSCompanion in your browser", "info")
