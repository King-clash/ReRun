"""Desktop window in an iOS style: dashboard, script settings, templates,
history, Discord and log, behind a bottom tab bar. Widgets live in ios.py."""
from __future__ import annotations

import queue
import re
import threading
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, ttk

import cv2
import numpy as np
from PIL import Image, ImageTk

from . import ios
from .adb import discover_bluestacks_instances
from .appicon import make_icon
from .ios import C, F, px
from .manager import Manager
from .scripts import SCRIPTS
from .stats import fmt_duration
from .tray import Tray

STATUS_TEXT = {"idle": "Idle", "starting": "Starting", "running": "Running",
               "paused": "Paused", "error": "Error"}
STATUS_COLOR = {"idle": "gray", "starting": "blue", "running": "green",
                "paused": "orange", "error": "red"}
APPEARANCE = {"auto": "Automatic", "light": "Light", "dark": "Dark"}
ALL_INSTANCES = "All instances"
LOG_LEVELS = {"All": None, "Warnings": {"warn", "error"}, "Errors": {"error"}}
HISTORY_KINDS = {"All": None, "Crests": {"crest"}, "Energy": {"energy"},
                 "Problems": {"failure"}, "Other": {"finished", "drop", "arena", "raid", "mines",
                                                   "grand_crusade", "yuna", "queue"}}
IDLE_PREVIEW_EVERY_S = 3.0


def to_photo(img: np.ndarray, max_w: int, max_h: int) -> tuple[ImageTk.PhotoImage, float]:
    h, w = img.shape[:2]
    scale = min(max_w / w, max_h / h, 1.0)
    size = (max(1, int(w * scale)), max(1, int(h * scale)))
    small = img if scale == 1.0 else cv2.resize(img, size, interpolation=cv2.INTER_AREA)
    return ImageTk.PhotoImage(Image.fromarray(cv2.cvtColor(small, cv2.COLOR_BGR2RGB))), scale


def short(text: str, n: int) -> str:
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


class InstanceList(tk.Frame):
    """Inset-grouped rows: status dot, name, address/script, last message, status."""

    def __init__(self, parent, on_select):
        super().__init__(parent, bg=C["card"])
        self._on_select = on_select
        self._rows: dict[str, dict] = {}
        self._order: list[str] = []
        self.sel: str | None = None
        self._painted: tuple | None = None
        self._sel_bg = ios.mix(C["card"], C["blue"], 0.22 if ios.DARK_MODE else 0.12)
        self._rebuild([])

    def set_rows(self, items: list[dict]):
        if [i["name"] for i in items] != self._order or not self._rows and items:
            self._rebuild(items)
        for it in items:
            self._update(it)
        if self.sel not in self._rows:
            self.sel = None
        self._paint()

    def _rebuild(self, items):
        for w in self.winfo_children():
            w.destroy()
        self._rows, self._order, self._painted = {}, [i["name"] for i in items], None
        card = C["card"]
        if not items:
            tk.Label(self, text="No Instances", bg=card, fg=C["label"],
                     font=F["body_semi"]).pack(pady=(px(18), 0))
            tk.Label(self, text="Use Detect BlueStacks or Add to list your emulators.", bg=card,
                     fg=C["secondary"], font=F["footnote"]).pack(pady=(px(2), px(18)))
            return
        for idx, it in enumerate(items):
            if idx:
                tk.Frame(self, height=1, bg=C["sep"]).pack(fill="x", padx=(px(36), 0))
            row = tk.Frame(self, bg=card, cursor="hand2")
            row.pack(fill="x")
            dot = ios.Dot(row, 10)
            dot.pack(side="left", padx=(px(14), px(12)))
            right = tk.Frame(row, bg=card)
            right.pack(side="right", padx=px(14))
            status = tk.Label(right, bg=card, font=F["footnote_semi"], anchor="e")
            status.pack(anchor="e")
            meta = tk.Label(right, bg=card, fg=C["secondary"], font=F["footnote"], anchor="e")
            meta.pack(anchor="e")
            mid = tk.Frame(row, bg=card)
            mid.pack(side="left", fill="x", expand=True, pady=px(9))
            title = tk.Label(mid, bg=card, fg=C["label"], font=F["body_semi"], anchor="w")
            title.pack(fill="x")
            sub = tk.Label(mid, bg=card, fg=C["secondary"], font=F["footnote"], anchor="w")
            sub.pack(fill="x")
            detail = tk.Label(mid, bg=card, fg=C["secondary"], font=F["footnote"], anchor="w")
            detail.pack(fill="x")
            for w in (row, dot, right, status, meta, mid, title, sub, detail):
                w.bind("<Button-1>", lambda e, n=it["name"]: self.select(n, user=True))
            self._rows[it["name"]] = {
                "dot": dot, "status": status, "meta": meta, "title": title, "sub": sub,
                "detail": detail, "color": None,
                "paint": [row, right, status, meta, mid, title, sub, detail]}

    def _update(self, it):
        r = self._rows[it["name"]]
        for key in ("title", "sub", "detail", "status", "meta"):
            if r[key].cget("text") != it[key]:
                r[key].configure(text=it[key])
        color = C[STATUS_COLOR.get(it["state"], "gray")]
        if r["color"] != color:
            r["color"] = color
            r["status"].configure(fg=color)
            r["dot"].set(color)

    def select(self, name: str | None, user: bool = False):
        self.sel = name
        self._paint()
        if user:
            self._on_select()

    def _paint(self):
        key = (self.sel, tuple(self._order))
        if key == self._painted:
            return
        self._painted = key
        for n, r in self._rows.items():
            bg = self._sel_bg if n == self.sel else C["card"]
            for w in r["paint"]:
                w.configure(bg=bg)
            r["dot"].set(bg=bg)


class StatTile(ios.Card):
    """A small card with a big number and a caption."""

    def __init__(self, parent, caption: str):
        super().__init__(parent, pad=4, radius=12)
        self.value = tk.Label(self.body, text="0", bg=C["card"], fg=C["label"], font=F["title"])
        self.value.pack(anchor="w", padx=px(8), pady=(px(4), 0))
        tk.Label(self.body, text=caption, bg=C["card"], fg=C["secondary"],
                 font=F["caption"]).pack(anchor="w", padx=px(8), pady=(0, px(5)))

    def set(self, text: str):
        if self.value.cget("text") != text:
            self.value.configure(text=text)


class App(tk.Tk):
    def __init__(self, manager: Manager):
        ios.enable_dpi_awareness()
        super().__init__()
        self.m = manager
        ios.init(self, str(self.m.config.get("appearance", "auto")))
        self.title("Rerun")
        self.geometry(f"{px(1220)}x{px(840)}")
        self.minsize(px(1060), px(720))
        self._icon = ImageTk.PhotoImage(make_icon(64))
        self.iconphoto(True, self._icon)
        self.events: queue.Queue = queue.Queue()
        self.m.listeners.append(self.events.put)
        self.bot = None
        self._hotkeys = None
        self._closing = False
        self._weak_seen: set[str] = set()

        self.nb = ios.TabView(self)
        self.nb.pack(fill="both", expand=True)
        self.status = self.nb.status
        self.toast = ios.Toast(self.nb.content)
        self._build_dashboard()
        self._build_settings()
        self._build_templates()
        self._build_history()
        self._build_units()
        self._tab_discord = 5
        self._build_discord()
        self._build_log()
        self.status.configure(text="F12 stops everything  ·  F11 pauses or resumes all")

        self.tray = Tray(lambda action: self.events.put({"type": "_tray", "action": action}))
        self._tray_on = self.tray.start()
        self._tray_hinted = False

        self.refresh_instances()
        self.m.start_scheduler()
        if not self.m.config.get("setup_seen"):
            self.after(1200, self.open_setup_check)
        self.after(10, lambda: ios.style_window(self))
        self.after(150, self._poll_events)
        self.after(1000, self._tick)
        self._start_hotkeys()
        if self.m.config["discord"].get("enabled"):
            self.after(500, self.connect_discord)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # small helpers --------------------------------------------------------
    def _page(self, title: str, tab: str, icon: str, scroll: bool = False):
        """Returns (page, content parent, header-right frame)."""
        if scroll:
            page = ios.ScrollFrame(self.nb.content)
            parent = page.inner
        else:
            page = tk.Frame(self.nb.content, bg=C["bg"])
            parent = page
        self.nb.add(page, tab, icon)
        return page, parent, ios.page_header(parent, title)

    def _label(self, parent, text="", secondary=True, font="footnote", **kw):
        return tk.Label(parent, text=text, bg=ios.bg_of(parent),
                        fg=C["secondary"] if secondary else C["label"], font=F[font], **kw)

    # ================================================================ dashboard
    def _build_dashboard(self):
        _, page, hdr = self._page("Dashboard", "Dashboard", "home")
        ios.Button(hdr, "Stop All", self.stop_all, kind="tinted", color="red",
                   icon="stop").pack(side="right", padx=(px(8), 0))
        ios.Button(hdr, "Start All", self.start_all, kind="tinted", icon="play").pack(side="right")

        body = tk.Frame(page, bg=C["bg"])
        body.pack(fill="both", expand=True, padx=px(20), pady=(0, px(14)))
        body.columnconfigure(0, weight=3, uniform="col")
        body.columnconfigure(1, weight=2, uniform="col")
        body.rowconfigure(0, weight=1)
        left = tk.Frame(body, bg=C["bg"])
        left.grid(row=0, column=0, sticky="nsew", padx=(0, px(18)))
        right = tk.Frame(body, bg=C["bg"])
        right.grid(row=0, column=1, sticky="nsew")

        h = ios.section_header(left, "Instances", pady=(0, px(6)))
        ios.Button(h, "Add", self.add_instance, kind="plain", icon="add",
                   small=True).pack(side="right", padx=(px(16), 0))
        ios.Button(h, "Detect BlueStacks", self.detect_instances, kind="plain", icon="search",
                   small=True).pack(side="right")
        card = ios.Card(left)
        card.pack(fill="x")
        self.inst_list = InstanceList(card.body, self._on_select)
        self.inst_list.pack(fill="x")

        g = ios.Group(left)
        g.pack(fill="x", pady=(px(12), 0))
        self.script_var = tk.StringVar()
        self.script_box = ios.Select(g.row("Script", "What the selected instance runs"),
                                     variable=self.script_var, command=self._on_script_change)
        self.script_box.pack()

        bar = tk.Frame(left, bg=C["bg"])
        bar.pack(fill="x", pady=(px(12), 0))
        ios.Button(bar, "Start", self.start_sel, icon="play").pack(side="left")
        self.pause_btn = ios.Button(bar, "Pause", self.pause_sel, kind="tinted", icon="pause")
        self.pause_btn.pack(side="left", padx=px(8))
        ios.Button(bar, "Stop", self.stop_sel, kind="tinted", color="red", icon="stop").pack(side="left")
        ios.Button(bar, "Remove", self.remove_instance, kind="plain", color="red",
                   icon="delete", small=True).pack(side="right")
        ios.Button(bar, "Edit", self.edit_instance, kind="plain", icon="edit",
                   small=True).pack(side="right", padx=(0, px(16)))

        h = ios.section_header(left, "Totals", pady=(px(16), px(6)))
        ios.Button(h, "Reset", self.reset_stats, kind="plain", color="red",
                   small=True).pack(side="right")
        tiles = tk.Frame(left, bg=C["bg"])
        tiles.pack(fill="x")
        self.tiles: dict[str, StatTile] = {}
        for i, (key, cap) in enumerate([("runs", "Runs"), ("kept", "Crests kept"),
                                        ("scrapped", "Scrapped"), ("potions", "Potions"),
                                        ("seconds", "Run time")]):
            t = StatTile(tiles, cap)
            t.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else px(8), 0))
            tiles.columnconfigure(i, weight=1, uniform="tile")
            self.tiles[key] = t

        ios.section_header(left, "Crests", pady=(px(16), px(6)))
        ctiles = tk.Frame(left, bg=C["bg"])
        ctiles.pack(fill="x")
        self.crest_tiles: dict[str, StatTile] = {}
        for i, (key, cap) in enumerate([("4+", "4+ crests"),
                                        ("burst", "Crest Burst"),
                                        ("lv4", "Lv4 (not 4+)"),
                                        ("since", "Runs since last 4+"),
                                        ("rate", "4+ observed rate")]):
            t = StatTile(ctiles, cap)
            t.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else px(8), 0))
            ctiles.columnconfigure(i, weight=1, uniform="ctile")
            self.crest_tiles[key] = t
        self.crest_note = self._label(left, "", anchor="w", justify="left")
        self.crest_note.pack(fill="x", pady=(px(4), 0))
        self._crest_cache_key = None

        ios.section_header(left, "Instructions", pady=(px(16), px(6)))
        _, self.instr = ios.text_box(left)
        self.instr.tag_configure("warn", foreground=C["orange"], font=F["footnote_semi"])
        self.instr.configure(state="disabled")

        h = ios.section_header(right, "Live View", pady=(0, px(6)))
        ios.Button(h, "Screenshot", self.preview_shot, kind="plain", icon="camera",
                   small=True).pack(side="right")
        self.live_auto = tk.BooleanVar(value=bool(self.m.config.get("live_view_auto", True)))
        ios.Switch(h, self.live_auto, command=self._save_live_auto).pack(side="right", padx=(0, px(14)))
        self._label(h, "Auto").pack(side="right", padx=(0, px(6)))
        pc = ios.Card(right, pad=6, stretch=True, color=C["viewer"])
        pc.pack(fill="both", expand=True)
        self.preview = tk.Canvas(pc.body, bg=C["viewer"], highlightthickness=0, bd=0)
        self.preview.pack(fill="both", expand=True)
        self.preview.bind("<Configure>", lambda e: self._draw_preview())
        self._preview_img: np.ndarray | None = None
        self._preview_photo = None
        self._preview_src = None   # last frame object drawn (skip redraws of the same frame)
        self._preview_busy = False
        self._preview_last_idle = 0.0
        self._idle_energy: dict[str, tuple[int, int, float]] = {}

    def selected(self) -> str | None:
        sel = self.inst_list.sel
        return sel if sel in self.m.instances else None

    def refresh_instances(self):
        scripts = self.m.scripts_available()
        self.script_box["values"] = list(scripts.values())
        items = []
        for name, inst in self.m.instances.items():
            stats = self.m.stats.get(name)
            runs = stats.get(f"{inst.script}.runs", "")
            up = fmt_duration(self.m.stats.uptime(name)) if inst.status in ("running", "paused") else ""
            meta = []
            e = self.energy_of(name)
            if e and time.time() - e[2] < 15 * 60:
                meta.append(f"Energy {e[0]}/{e[1]}")
            if runs != "":
                meta.append(f"{runs} run{'' if runs == 1 else 's'}")
            if up:
                meta.append(up)
            items.append({
                "name": name, "title": name, "state": inst.status,
                "sub": f"{inst.serial}  ·  {scripts.get(inst.script, inst.script)}",
                "detail": short(inst.detail or "Ready", 78),
                "status": STATUS_TEXT.get(inst.status, inst.status),
                "meta": "  ·  ".join(meta)})
        self.inst_list.set_rows(items)
        if not self.selected() and self.m.instances:
            self.inst_list.select(next(iter(self.m.instances)), user=True)
        name = self.selected()
        want = "Resume" if name and self.m.instances[name].status == "paused" else "Pause"
        if self.pause_btn._text != want:
            self.pause_btn.set_text(want)
        self._refresh_totals()
        self._refresh_instance_lists()

    def _refresh_totals(self):
        name = self.selected()
        t = self.m.totals(name) if name else {}
        for key, tile in self.tiles.items():
            v = t.get(key, 0)
            tile.set(fmt_duration(v) if key == "seconds" else f"{v:,}")
        self._refresh_crests(name)

    def _refresh_crests(self, name: str | None):
        """Crest 4+ / Burst / Lv4 tiles from the crest ledger (recomputed only when it changes)."""
        led = getattr(self.m, "crests", None)
        if led is None or not hasattr(self, "crest_tiles"):
            return
        key = (name, len(led.records), int(time.time() // 600))
        if key == self._crest_cache_key:
            return
        self._crest_cache_key = key
        s = led.summary(name)
        for cls in ("4+", "burst", "lv4"):
            self.crest_tiles[cls].set(" · ".join(
                f"{s[w]['drops'][cls]:,}" for w in ("today", "session", "all")))
        self.crest_tiles["since"].set(f"{s['since_4+']:,}")
        n = s["all"]["drops"]["4+"]
        self.crest_tiles["rate"].set(f"1/{s['avg_runs_4+']:,.0f}" if n else "–")
        last = s["last_notable"]
        parts = [f"{s['rate_4+'][0].upper()}{s['rate_4+'][1:]} (4+)", f"{s['rate_burst']} (Burst)"]
        parts.append("Last 4+/Burst: " + (time.strftime("%d %b %H:%M", time.localtime(last["t"]))
                                          + f" ({last['rarity']})" if last else "none yet"))
        note = ("Counts: today · this session · all-time.  " + "  ·  ".join(parts)
                + "\nObserved results only, not a prediction.")
        if s["baseline_runs"]:
            note += f" {s['baseline_runs']:,} earlier runs have no dates."
        if s["uncertain"]:
            note += f" {s['uncertain']} uncertain."
        if self.crest_note.cget("text") != note:
            self.crest_note.configure(text=note)

    def reset_stats(self):
        name = self.selected()
        if not name:
            return
        if ios.confirm(self, f"Runs, crests, potions and run time for {name} go back to zero. "
                             "History is kept.", "Reset Stats?", ok="Reset", destructive=True):
            self.flash(self.m.reset_stats(name), "ok")
            self.refresh_instances()

    def _on_select(self):
        name = self.selected()
        if not name:
            return
        inst = self.m.instances[name]
        self.script_var.set(self.m.scripts_available().get(inst.script, ""))
        self._show_instructions(inst.script)
        self._preview_src = None
        self._refresh_totals()

    def _show_instructions(self, script: str):
        cls = SCRIPTS.get(script)
        text = cls.INSTRUCTIONS if cls else "Custom routine - see routines/README.md."
        missing = self.m.missing_templates(script)
        self.instr.configure(state="normal")
        self.instr.delete("1.0", "end")
        if missing:
            self.instr.insert("1.0", f"Setup needed: {len(missing)} template(s) still to capture "
                              f"in the Templates tab:\n", "warn")
            self.instr.insert("end", "  " + "\n  ".join(missing) + "\n\n", "warn")
        self.instr.insert("end", text)
        self.instr.configure(state="disabled")

    def _script_id(self, label: str) -> str | None:
        for k, v in self.m.scripts_available().items():
            if v == label:
                return k
        return None

    def _on_script_change(self):
        name = self.selected()
        sid = self._script_id(self.script_var.get())
        if name and sid:
            if self.m.instances[name].status not in ("idle", "error"):
                ios.alert(self, "Stop the instance before changing its script.")
                self._on_select()
                return
            self.m.set_instance_script(name, sid)
            self._show_instructions(sid)
            self.refresh_instances()

    def start_sel(self):
        name = self.selected()
        if not name:
            return
        script = self.m.instances[name].script
        missing = self.m.missing_templates(script)
        if missing:
            ios.alert(self, "Capture these in the Templates tab first:\n\n" + "\n".join(missing[:20]),
                      "Templates Missing")
            return
        cls = SCRIPTS.get(script)
        if cls and cls.BETA and not ios.confirm(
                self, f"{cls.NAME} was built from ReStart's routine but hasn't been run on your game "
                      "yet. Watch the first runs and stop it (F12) if anything looks wrong.",
                "Beta Script", ok="Start"):
            return
        self.flash(self.m.start(name))

    def stop_sel(self):
        if self.selected():
            self.flash(self.m.stop(self.selected()))

    def pause_sel(self):
        name = self.selected()
        if not name:
            return
        inst = self.m.instances[name]
        self.flash(self.m.resume(name) if inst.status == "paused" else self.m.pause(name))

    def start_all(self):
        self.flash(" | ".join(self.m.start_all()))

    def stop_all(self):
        self.flash(" | ".join(self.m.stop_all()) or "Nothing running")

    def _instance_items(self) -> list[dict]:
        return [dict(i) for i in self.m.config["instances"]]

    def add_instance(self):
        name = ios.ask_string(self, "Add Instance", "Name",
                              initial=f"Instance {len(self.m.instances) + 1}")
        if not name:
            return
        if name in self.m.instances:
            ios.alert(self, "That name is already used.")
            return
        serial = ios.ask_string(self, "Add Instance", "ADB address\n(BlueStacks: 127.0.0.1:<port>)",
                                initial="127.0.0.1:5555")
        if not serial:
            return
        items = self._instance_items() + [{"name": name, "serial": serial, "script": "crest"}]
        self.m.set_instances(items)
        self.refresh_instances()

    def edit_instance(self):
        name = self.selected()
        if not name:
            return
        if self.m.instances[name].status not in ("idle", "error"):
            ios.alert(self, "Stop the instance first.")
            return
        serial = ios.ask_string(self, "Edit Instance", f"ADB address for {name}",
                                initial=self.m.instances[name].serial)
        if not serial:
            return
        items = self._instance_items()
        for i in items:
            if i["name"] == name:
                i["serial"] = serial
        self.m.set_instances(items)
        self.refresh_instances()

    def remove_instance(self):
        name = self.selected()
        if not name:
            return
        if self.m.instances[name].status not in ("idle", "error"):
            ios.alert(self, "Stop the instance first.")
            return
        if not ios.confirm(self, f"{name} will be removed from Rerun.", "Remove Instance?",
                           ok="Remove", destructive=True):
            return
        self.m.set_instances([i for i in self._instance_items() if i["name"] != name])
        self.inst_list.sel = None
        self.refresh_instances()

    def detect_instances(self):
        found = discover_bluestacks_instances()
        if not found:
            ios.alert(self, "No BlueStacks 5 instances found in bluestacks.conf.")
            return
        items = self._instance_items()
        have = {i["serial"] for i in items}
        added = []
        for inst in found:
            if inst["serial"] not in have:
                name = inst["name"]
                while any(i["name"] == name for i in items):
                    name += "+"
                items.append({"name": name, "serial": inst["serial"], "script": "crest"})
                added.append(f"{name} ({inst['serial']})")
        self.m.set_instances(items)
        self.refresh_instances()
        msg = ("Added:\n" + "\n".join(added)) if added else "All BlueStacks instances are already listed."
        if not found[0]["adb_enabled"]:
            msg += ("\n\nADB is OFF in BlueStacks. Turn it on: BlueStacks Settings > Advanced > "
                    "Android Debug Bridge (ADB). Also set Display to 1280x720 "
                    "(the game then runs at 720x1280 portrait).")
        ios.alert(self, msg, "BlueStacks")

    # live view -------------------------------------------------------------
    def preview_shot(self, quiet: bool = False):
        name = self.selected()
        if not name or self._preview_busy:
            return
        self._preview_busy = True

        def work():
            try:
                img = self.m.screenshot(name)
                self.events.put({"type": "_preview", "img": img})
                self._read_idle_energy(name, img)
            except Exception as e:  # noqa: BLE001
                if not quiet:
                    self.events.put({"type": "_error", "message": f"Screenshot failed: {e}"})
            finally:
                self._preview_busy = False
        threading.Thread(target=work, daemon=True).start()

    def _read_idle_energy(self, name: str, img: np.ndarray) -> None:
        """Energy for an idle instance, from its preview frame (worker thread;
        at most once a minute per instance)."""
        last = self._idle_energy.get(name)
        if last and time.time() - last[2] < 60:
            return
        try:
            from .ocr import get_ocr, read_energy
            e = read_energy(get_ocr(self.m.config.get("tesseract_path", "auto")), img)
        except Exception:  # noqa: BLE001 - no OCR: simply not shown
            return
        if e:
            self._idle_energy[name] = (e[0], e[1], time.time())

    def energy_of(self, name: str) -> tuple[int, int, float] | None:
        inst = self.m.instances.get(name)
        e = inst.ctx.params.get("energy") if inst and inst.ctx else None
        return e or self._idle_energy.get(name)

    def _save_live_auto(self):
        self.m.config["live_view_auto"] = bool(self.live_auto.get())
        self.m.save_config()

    def _auto_preview(self):
        """While a script runs, show the frames it already captures (no extra
        ADB work); when idle, take a screenshot every few seconds - and only
        while the Dashboard is actually on screen."""
        if not self.live_auto.get() or self.nb.index() != 0 or self.state() == "withdrawn":
            return
        name = self.selected()
        if not name:
            return
        inst = self.m.instances[name]
        frame = inst.ctx.last_screen if inst.ctx is not None else None
        if frame is not None:
            if frame is not self._preview_src:
                self._preview_img = frame
                self._draw_preview()
            return
        if inst.status in ("idle", "error") and \
                time.monotonic() - self._preview_last_idle >= IDLE_PREVIEW_EVERY_S:
            self._preview_last_idle = time.monotonic()
            self.preview_shot(quiet=True)

    def _draw_preview(self):
        c = self.preview
        c.delete("all")
        W, H = c.winfo_width(), c.winfo_height()
        if self._preview_img is None:
            c.create_text(W // 2, H // 2, justify="center", fill=C["gray"], font=F["footnote"],
                          text="No screenshot yet\nTurn on Auto or press Screenshot")
            return
        self._preview_src = self._preview_img
        self._preview_photo, _ = to_photo(self._preview_img, max(50, W), max(50, H))
        c.create_image(W // 2, H // 2, image=self._preview_photo, anchor="center")

    # ================================================================ settings
    def _build_settings(self):
        _, page, _ = self._page("Script Settings", "Settings", "settings", scroll=True)
        wrap = tk.Frame(page, bg=C["bg"])
        wrap.pack(fill="x", padx=px(20))
        g = ios.Group(wrap)
        g.pack(fill="x")
        self.set_inst = ios.Select(g.row("Instance"), command=self._load_settings_form)
        self.set_inst.pack()
        self.set_script = ios.Select(g.row("Script"),
                                     values=[c.display_name() for c in SCRIPTS.values()],
                                     command=self._load_settings_form)
        self.set_script.pack()
        self.form = tk.Frame(wrap, bg=C["bg"])
        self.form.pack(fill="x", pady=(px(24), 0))
        bar = tk.Frame(wrap, bg=C["bg"])
        bar.pack(fill="x", pady=(px(14), 0))
        ios.Button(bar, "Save Settings", self._save_settings_form, icon="save").pack(side="left")
        self._label(bar, "Changes apply the next time the script starts.").pack(side="left", padx=px(12))

        g2 = ios.Group(wrap, header="App", footer="Theme applies the next time Rerun opens.")
        g2.pack(fill="x", pady=(px(30), px(24)))
        self.appearance = ios.Select(g2.row("Theme"), values=list(APPEARANCE.values()),
                                     command=self._save_appearance)
        self.appearance.set(APPEARANCE.get(str(self.m.config.get("appearance", "auto")), "Automatic"))
        self.appearance.pack()
        self.close_to_tray = tk.BooleanVar(value=bool(self.m.config.get("close_to_tray", True)))
        ios.Switch(g2.row("Keep running in the tray", "Closing the window hides Rerun next to "
                          "the clock instead of quitting. Quit from the tray icon's menu."),
                   self.close_to_tray, command=self._save_close_to_tray).pack()
        ios.Button(g2.row("Setup check", "Checks ADB, your instances, screen size, templates "
                          "and the text reader, with a fix for anything missing."),
                   "Run", self.open_setup_check, kind="tinted", small=True).pack()
        self.form_vars: dict[str, tk.Variable] = {}
        self.set_script.current(1)

    # setup check ------------------------------------------------------------
    def open_setup_check(self):
        """A sheet listing every requirement with a green/red badge and a fix."""
        if getattr(self, "_setup_win", None) is not None and self._setup_win.winfo_exists():
            self._setup_win.lift()
            return
        win = tk.Toplevel(self, bg=C["bg"])
        win.title("Setup Check")
        win.geometry(f"{px(620)}x{px(640)}")
        win.transient(self)
        win.iconphoto(False, self._icon)
        self._setup_win = win
        self.after(10, lambda: ios.style_window(win))
        hdr = ios.page_header(win, "Setup Check")
        ios.Button(hdr, "Check Again", self._run_setup_check, kind="tinted", icon="sync",
                   small=True).pack(side="right")
        self._setup_body = tk.Frame(win, bg=C["bg"])
        self._setup_body.pack(fill="both", expand=True, padx=px(20), pady=(0, px(16)))
        self.m.config["setup_seen"] = True
        self.m.save_config()
        self._run_setup_check()

    def _run_setup_check(self):
        body = self._setup_body
        for w in body.winfo_children():
            w.destroy()
        self._label(body, "Checking ADB, your instances and the text reader…").pack(anchor="w")

        def work():
            from .setup_check import run_checks
            try:
                checks = run_checks(self.m)
            except Exception as e:  # noqa: BLE001
                checks = []
                self.events.put({"type": "_error", "message": f"Setup check failed: {e}"})
            self.events.put({"type": "_setup", "checks": checks})
        threading.Thread(target=work, daemon=True).start()

    def _show_setup_results(self, checks):
        body = getattr(self, "_setup_body", None)
        if body is None or not body.winfo_exists():
            return
        for w in body.winfo_children():
            w.destroy()
        bad = sum(not c.ok for c in checks)
        self._label(body, "Everything Rerun needs is in place." if not bad else
                    f"{bad} thing(s) need attention.", secondary=False, font="body_semi"
                    ).pack(anchor="w", pady=(0, px(10)))
        card = ios.Card(body)
        card.pack(fill="x")
        fixes = {"detect": ("Detect", self.detect_instances),
                 "import": ("Import", self.tpl_import_restart),
                 "adb_help": ("How?", lambda: ios.alert(self, ADB_HELP, "Turn On ADB")),
                 "display_help": ("How?", lambda: ios.alert(self, DISPLAY_HELP, "Screen Size")),
                 "discord_tab": ("Open", lambda: (self.nb.select(self._tab_discord),
                                                  self._setup_win.destroy()))}
        for i, c in enumerate(checks):
            if i:
                tk.Frame(card.body, height=1, bg=C["sep"]).pack(fill="x", padx=(px(40), 0))
            row = tk.Frame(card.body, bg=C["card"])
            row.pack(fill="x")
            tk.Label(row, image=ios.badge("ok" if c.ok else "missing"), bg=C["card"]).pack(
                side="left", padx=(px(12), px(10)), pady=px(10), anchor="n")
            if c.fix and not c.ok and c.fix in fixes:
                label, fn = fixes[c.fix]
                ios.Button(row, label, fn, kind="tinted", small=True).pack(side="right", padx=px(12))
            txt = tk.Frame(row, bg=C["card"])
            txt.pack(side="left", fill="x", expand=True, pady=px(8))
            tk.Label(txt, text=c.title, bg=C["card"], fg=C["label"], font=F["body"],
                     anchor="w").pack(fill="x")
            tk.Label(txt, text=c.detail, bg=C["card"], fg=C["secondary"], font=F["footnote"],
                     anchor="w", justify="left", wraplength=px(430)).pack(fill="x")

    def _save_appearance(self):
        key = next(k for k, v in APPEARANCE.items() if v == self.appearance.get())
        self.m.config["appearance"] = key
        self.m.save_config()
        self.flash(f"Theme set to {APPEARANCE[key]} - restart Rerun to apply", "ok")

    def _save_close_to_tray(self):
        self.m.config["close_to_tray"] = bool(self.close_to_tray.get())
        self.m.save_config()

    def _refresh_instance_lists(self):
        names = list(self.m.instances)
        for box in (self.set_inst, getattr(self, "tpl_inst", None)):
            if box is None:
                continue
            box["values"] = names
            if box.get() not in names and names:
                box.set(names[0])
        for box in (getattr(self, "log_inst", None), getattr(self, "hist_inst", None)):
            if box is not None:
                box["values"] = [ALL_INSTANCES] + names
        if not self.form_vars and names:
            self._load_settings_form()

    def _settings_script_id(self) -> str | None:
        for k, c in SCRIPTS.items():
            if c.display_name() == self.set_script.get():
                return k
        return None

    def _load_settings_form(self):
        for w in self.form.winfo_children():
            w.destroy()
        self.form_vars = {}
        inst, sid = self.set_inst.get(), self._settings_script_id()
        if not inst or not sid:
            return
        values = self.m.script_settings(inst, sid)
        g = ios.Group(self.form, header=f"{SCRIPTS[sid].display_name()} · {inst}")
        g.pack(fill="x")
        for s in SCRIPTS[sid].SETTINGS:
            right = g.row(s.label, s.help or None)
            if s.type == "bool":
                var = tk.BooleanVar(value=bool(values.get(s.key)))
                ios.Switch(right, var).pack()
            elif s.type == "choice":
                var = tk.StringVar(value=str(values.get(s.key)))
                ios.Select(right, values=s.choices, variable=var).pack()
            elif s.type == "int":
                var = tk.StringVar(value=str(values.get(s.key)))
                ios.Stepper(right, var).pack()
            else:
                var = tk.StringVar(value=str(values.get(s.key)))
                ios.Field(right, var, width=26).pack()
            self.form_vars[s.key] = var
        # Per-instance daily schedule (starts whatever script the instance is set to).
        sch = (self.m.config.get("schedules") or {}).get(inst, {})
        gs = ios.Group(self.form, header=f"Schedule · {inst}",
                       footer="Starts this instance's script (the one chosen on the Dashboard) "
                              "every day at that time, using your PC's clock. Use a Chain to "
                              "run several scripts in a row.")
        gs.pack(fill="x", pady=(px(24), 0))
        self.sched_on = tk.BooleanVar(value=bool(sch.get("enabled")))
        ios.Switch(gs.row("Start every day"), self.sched_on).pack()
        self.sched_time = tk.StringVar(value=str(sch.get("time", "06:05")))
        ios.Field(gs.row("At (24-hour HH:MM)"), self.sched_time, width=6, justify="right").pack()

    def _save_settings_form(self):
        inst, sid = self.set_inst.get(), self._settings_script_id()
        if not inst or not sid:
            return
        out = {}
        for s in SCRIPTS[sid].SETTINGS:
            raw = self.form_vars[s.key].get()
            if s.type == "int":
                try:
                    out[s.key] = max(0, int(str(raw).strip() or 0))
                except ValueError:
                    ios.alert(self, f"'{s.label}' must be a whole number.")
                    return
            elif s.type == "bool":
                out[s.key] = bool(raw)
            else:
                out[s.key] = raw
        if sid == "chain":
            from .scripts.chain import parse_steps
            try:
                parse_steps(out.get("steps", ""))
            except ValueError as e:
                ios.alert(self, str(e), "Chain Steps")
                return
        t = self.sched_time.get().strip()
        if self.sched_on.get() and not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", t):
            ios.alert(self, "Write the schedule time as HH:MM, e.g. 06:05 or 21:30.", "Schedule")
            return
        self.m.config.setdefault("schedules", {})[inst] = {"enabled": bool(self.sched_on.get()),
                                                           "time": t}
        self.m.save_script_settings(inst, sid, out)
        self.flash(f"Saved {SCRIPTS[sid].NAME} settings for {inst} (applies next Start)", "ok")

    # ================================================================ templates
    def _build_templates(self):
        _, page, hdr = self._page("Templates", "Templates", "photo")
        ios.Button(hdr, "Import from ReStart", self.tpl_import_restart, kind="tinted",
                   icon="download").pack(side="right")
        body = tk.Frame(page, bg=C["bg"])
        body.pack(fill="both", expand=True, padx=px(20), pady=(0, px(14)))

        left = tk.Frame(body, bg=C["bg"], width=px(350))
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        g = ios.Group(left)
        g.pack(fill="x")
        self.tpl_script = ios.Select(g.row("Checklist for"), command=self.refresh_checklist)
        self.tpl_script.pack()
        h = ios.section_header(left, "Templates", pady=(px(14), px(6)))
        self.tpl_count = self._label(h, "")
        self.tpl_count.pack(side="right")
        tc = ios.Card(left, pad=6, stretch=True)
        tc.pack(fill="both", expand=True)
        sb = ttk.Scrollbar(tc.body, orient="vertical", style="IOS.Vertical.TScrollbar")
        self.tpl_tree = ttk.Treeview(tc.body, columns=("have",), show="tree",
                                     style="IOS.Treeview", selectmode="browse",
                                     yscrollcommand=sb.set)
        sb.configure(command=self.tpl_tree.yview)
        self.tpl_tree.column("#0", width=px(220), stretch=True)
        self.tpl_tree.column("have", width=px(76), stretch=False, anchor="e")
        self.tpl_tree.tag_configure("missing", foreground=C["red"])
        self.tpl_tree.tag_configure("optional", foreground=C["secondary"])
        self.tpl_tree.tag_configure("weak", foreground=C["orange"])
        sb.pack(side="right", fill="y", pady=px(4))
        self.tpl_tree.pack(side="left", fill="both", expand=True)
        self.tpl_tree.bind("<<TreeviewSelect>>", lambda e: self._on_tpl_select())
        self.tpl_desc = self._label(left, wraplength=px(320), justify="left", anchor="w")
        self.tpl_desc.pack(fill="x", padx=px(16), pady=(px(8), 0))

        right = tk.Frame(body, bg=C["bg"])
        right.pack(side="left", fill="both", expand=True, padx=(px(18), 0))
        bar = tk.Frame(right, bg=C["bg"])
        bar.pack(fill="x")
        self._label(bar, "Instance", secondary=False, font="body").pack(side="left")
        self.tpl_inst = ios.Select(bar, accent=True)
        self.tpl_inst.pack(side="left", padx=(px(8), px(18)))
        ios.Button(bar, "Screenshot", self.tpl_screenshot, icon="camera").pack(side="left")
        ios.Button(bar, "Open Image…", self.tpl_open, kind="tinted",
                   icon="folder").pack(side="left", padx=px(8))
        self._label(right, wraplength=px(760), justify="left", anchor="w", text=(
            "Take a screenshot with the game on the right screen, pick a template on the left, "
            "drag a box tightly around the element, then Save Selection. Test shows how well it "
            "matches the current image (green = found).")).pack(fill="x", pady=(px(10), px(8)))
        cc = ios.Card(right, pad=6, stretch=True, color=C["viewer"])
        cc.pack(fill="both", expand=True)
        self.tpl_canvas = tk.Canvas(cc.body, bg=C["viewer"], highlightthickness=0, bd=0,
                                    cursor="crosshair")
        self.tpl_canvas.pack(fill="both", expand=True)
        self.tpl_canvas.bind("<ButtonPress-1>", self._drag_start)
        self.tpl_canvas.bind("<B1-Motion>", self._drag_move)
        self.tpl_canvas.bind("<Configure>", lambda e: self._draw_tpl_image())
        bot = tk.Frame(right, bg=C["bg"])
        bot.pack(fill="x", pady=(px(10), 0))
        ios.Button(bot, "Save Selection", self.tpl_save, icon="save").pack(side="left")
        ios.Button(bot, "Test", self.tpl_test, kind="tinted", icon="search").pack(side="left", padx=px(8))
        ios.Button(bot, "Delete", self.tpl_delete, kind="tinted", color="red",
                   icon="delete").pack(side="left")
        ios.Button(bot, "Read Text", self.tpl_read_text, kind="tinted",
                   icon="edit").pack(side="right")
        self.tpl_img: np.ndarray | None = None
        self.tpl_scale = 1.0
        self.tpl_photo = None
        self.sel_rect = None  # canvas coords
        self._drag_origin = (0, 0)
        self._tpl_info: dict[str, str] = {}
        self.tpl_script["values"] = list(self.m.scripts_available().values())
        self.tpl_script.current(1)
        self.after(50, self.refresh_checklist)

    def refresh_checklist(self):
        sid = self._script_id(self.tpl_script.get())
        keep = self.tpl_tree.selection()
        self.tpl_tree.delete(*self.tpl_tree.get_children())
        if not sid:
            return
        self._tpl_info = {}
        have_n = need_n = 0
        health = self.m.vision.health()
        for name, desc, optional, have in self.m.template_checklist(sid):
            kind = "ok" if have else ("optional" if optional else "missing")
            mark = "" if have else ("Optional" if optional else "Missing")
            hh = health.get(name)
            if have and hh and hh["weak"]:
                kind, mark = "weak", f"Weak {hh['median']:.2f}"
                desc = (f"Matching weakly lately (median {hh['median']:.2f}, needs "
                        f"{hh['threshold']:.2f}) - usually a game update. Re-capture it, or "
                        f"Import from ReStart if ReStart has updated.\n\n{desc}")
            tag = () if kind == "ok" else ((kind,))
            self.tpl_tree.insert("", "end", iid=name, text=f"  {name}", image=ios.badge(kind),
                                 values=(f"{mark}  ",), tags=tag)
            self._tpl_info[name] = desc
            have_n += bool(have)
            need_n += 1
        self.tpl_count.configure(text=f"{have_n} of {need_n} captured")
        if keep and self.tpl_tree.exists(keep[0]):
            self.tpl_tree.selection_set(keep[0])

    def _on_tpl_select(self):
        sel = self.tpl_tree.selection()
        if sel:
            self.tpl_desc.configure(text=f"{sel[0]}\n{self._tpl_info.get(sel[0], '')}")

    def tpl_screenshot(self):
        name = self.tpl_inst.get()
        if not name:
            return

        def work():
            try:
                self.events.put({"type": "_tpl_img", "img": self.m.screenshot(name)})
            except Exception as e:  # noqa: BLE001
                self.events.put({"type": "_error", "message": f"Screenshot failed: {e}"})
        threading.Thread(target=work, daemon=True).start()

    def tpl_open(self):
        path = filedialog.askopenfilename(filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp")])
        if path:
            img = cv2.imdecode(np.fromfile(path, np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                ios.alert(self, "Could not read that image.")
                return
            self.set_tpl_image(img)

    def set_tpl_image(self, img: np.ndarray):
        self.tpl_img = img
        self.sel_rect = None
        h, w = img.shape[:2]
        if (w, h) != (720, 1280):
            self.flash(f"Note: this image is {w}x{h}. Scripts expect 720x1280 "
                       "(BlueStacks Display set to 1280x720).", "warn")
        self._draw_tpl_image()

    def _draw_tpl_image(self, boxes: list | None = None):
        c = self.tpl_canvas
        c.delete("all")
        if self.tpl_img is None:
            c.create_text(c.winfo_width() // 2, c.winfo_height() // 2, justify="center",
                          fill=C["gray"], font=F["footnote"],
                          text="No image yet\nPress Screenshot or Open Image…")
            return
        self.tpl_photo, self.tpl_scale = to_photo(self.tpl_img, max(50, c.winfo_width()),
                                                  max(50, c.winfo_height()))
        c.create_image(0, 0, image=self.tpl_photo, anchor="nw")
        if self.sel_rect:
            c.create_rectangle(*self.sel_rect, outline=C["blue"], width=2, tags="sel")
        for (x, y, w, h, color, label) in boxes or []:
            s = self.tpl_scale
            c.create_rectangle(x * s, y * s, (x + w) * s, (y + h) * s, outline=color, width=2)
            c.create_text(x * s + 2, y * s - 9, text=label, fill=color, anchor="w",
                          font=F["footnote_semi"])

    def _drag_start(self, e):
        self._drag_origin = (e.x, e.y)
        self.sel_rect = (e.x, e.y, e.x, e.y)
        self._draw_tpl_image()

    def _drag_move(self, e):
        x0, y0 = self._drag_origin
        self.sel_rect = (min(x0, e.x), min(y0, e.y), max(x0, e.x), max(y0, e.y))
        self.tpl_canvas.delete("sel")
        self.tpl_canvas.create_rectangle(*self.sel_rect, outline=C["blue"], width=2, tags="sel")

    def tpl_save(self):
        sel = self.tpl_tree.selection()
        if self.tpl_img is None or not self.sel_rect:
            ios.alert(self, "Take a screenshot and drag a box first.")
            return
        name = sel[0] if sel else ios.ask_string(self, "New Template", "Template name")
        if not name:
            return
        s = self.tpl_scale
        x0, y0, x1, y1 = (int(v / s) for v in self.sel_rect)
        h, w = self.tpl_img.shape[:2]
        x0, y0, x1, y1 = max(0, x0), max(0, y0), min(w, x1), min(h, y1)
        if x1 - x0 < 6 or y1 - y0 < 6:
            ios.alert(self, "The box is too small.")
            return
        if self.m.store.has(name) and not ios.confirm(
                self, f"'{name}' already exists.", "Replace Template?", ok="Replace"):
            return
        self.m.store.save(name, self.tpl_img, x0, y0, x1 - x0, y1 - y0)
        self.m.vision.reset_health(name)
        self._weak_seen.discard(name)
        self.flash(f"Saved template '{name}' ({x1 - x0}x{y1 - y0})", "ok")
        self.refresh_checklist()
        if self.selected():
            self._show_instructions(self.m.instances[self.selected()].script)

    def tpl_test(self):
        sel = self.tpl_tree.selection()
        if self.tpl_img is None or not sel:
            return
        name = sel[0]
        if not self.m.store.has(name):
            self.flash(f"'{name}' has not been captured yet", "warn")
            return
        m = self.m.vision.score(self.tpl_img, name)
        thr = self.m.store.threshold(name)
        if not m:
            self.flash(f"'{name}': no match possible on this image", "warn")
            return
        found = m.score >= thr
        self.sel_rect = None
        self._draw_tpl_image([(m.x, m.y, m.w, m.h, C["green"] if found else C["red"],
                               f"{name} {m.score:.2f}")])
        self.flash(f"'{name}': score {m.score:.3f} (needs {thr:.2f}) -> "
                   f"{'FOUND' if found else 'not found'}", "ok" if found else "warn")

    def tpl_read_text(self):
        """OCR the dragged box - shows what scripts would read there."""
        if self.tpl_img is None or not self.sel_rect:
            ios.alert(self, "Take a screenshot and drag a box around some text first.")
            return
        s = self.tpl_scale
        x0, y0, x1, y1 = (int(v / s) for v in self.sel_rect)
        crop = self.tpl_img[max(0, y0):y1, max(0, x0):x1].copy()
        if crop.shape[0] < 6 or crop.shape[1] < 6:
            ios.alert(self, "The box is too small.")
            return
        self.flash("Reading text…")
        path = self.m.config.get("tesseract_path", "auto")

        def work():
            from .ocr import OcrUnavailable, get_ocr
            try:
                r = get_ocr(path).read(crop, line=crop.shape[0] < 80)
                msg = (f"“{r.text}”\n\nConfidence {r.confidence:.0f}%"
                       if r else "No text found in that box.")
                self.events.put({"type": "_alert", "title": "Text Read", "message": msg})
            except OcrUnavailable as e:
                self.events.put({"type": "_error", "message": str(e)})
        threading.Thread(target=work, daemon=True).start()

    def tpl_import_restart(self):
        from .restart_import import default_restart_dir, find_templates_dir, import_templates
        base = default_restart_dir()
        if find_templates_dir(base) is None:
            picked = filedialog.askdirectory(title="Select your ReStart folder")
            if not picked:
                return
            base = Path(picked)
        overwrite = ios.confirm(
            self, "Also replace templates you captured yourself?\n\n"
                  "Keep Mine only fills in the ones you don't have.",
            "Import from ReStart", ok="Replace", cancel="Keep Mine", default_cancel=True)
        try:
            res = import_templates(self.m.store, base, overwrite_own=overwrite)
        except FileNotFoundError as e:
            ios.alert(self, str(e))
            return
        self.m.vision.reset_health()
        self._weak_seen.clear()
        self.refresh_checklist()
        if self.selected():
            self._show_instructions(self.m.instances[self.selected()].script)
        msg = f"Imported {len(res['imported'])} template(s) from ReStart."
        if res["skipped_own"]:
            msg += f"\nKept your own: {', '.join(res['skipped_own'])}"
        if res["not_found"]:
            msg += f"\nNot in this ReStart version: {', '.join(res['not_found'])}"
        ios.alert(self, msg, "Import Complete")

    def tpl_delete(self):
        sel = self.tpl_tree.selection()
        if sel and self.m.store.has(sel[0]) and ios.confirm(
                self, f"'{sel[0]}' will be deleted.", "Delete Template?", ok="Delete",
                destructive=True):
            self.m.store.delete(sel[0])
            self.refresh_checklist()

    # ================================================================ history
    def _build_history(self):
        _, page, hdr = self._page("History", "History", "history")
        ios.Button(hdr, "Clear", self.clear_history, kind="tinted", color="red",
                   icon="delete").pack(side="right")
        bar = tk.Frame(page, bg=C["bg"])
        bar.pack(fill="x", padx=px(20), pady=(0, px(10)))
        self.hist_kind = tk.StringVar(value="All")
        ios.Segmented(bar, list(HISTORY_KINDS), self.hist_kind,
                      command=self.refresh_history).pack(side="left")
        self.hist_inst = ios.Select(bar, values=[ALL_INSTANCES], accent=True,
                                    command=self.refresh_history)
        self.hist_inst.set(ALL_INSTANCES)
        self.hist_inst.pack(side="left", padx=px(16))
        self.hist_summary = self._label(bar, "")
        self.hist_summary.pack(side="right")

        body = tk.Frame(page, bg=C["bg"])
        body.pack(fill="both", expand=True, padx=px(20), pady=(0, px(14)))
        lc = ios.Card(body, pad=6, stretch=True)
        lc.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(lc.body, orient="vertical", style="IOS.Vertical.TScrollbar")
        self.hist_tree = ttk.Treeview(lc.body, columns=("time", "inst", "what"), show="",
                                      style="IOS.Treeview", selectmode="browse",
                                      yscrollcommand=sb.set)
        sb.configure(command=self.hist_tree.yview)
        self.hist_tree.column("time", width=px(130), stretch=False)
        self.hist_tree.column("inst", width=px(110), stretch=False)
        self.hist_tree.column("what", width=px(400), stretch=True)
        for tag, col in (("kept", "green"), ("problem", "red"), ("energy", "orange"),
                         ("quiet", "secondary")):
            self.hist_tree.tag_configure(tag, foreground=C[col])
        sb.pack(side="right", fill="y", pady=px(4))
        self.hist_tree.pack(side="left", fill="both", expand=True)
        self.hist_tree.bind("<<TreeviewSelect>>", lambda e: self._on_hist_select())
        self.hist_empty = tk.Label(lc.body, bg=C["card"], fg=C["secondary"], font=F["footnote"],
                                   justify="center", text="Nothing here yet\nCrests, refills and "
                                   "problems appear here as your scripts run.")

        rc = ios.Card(body, pad=10, stretch=True)
        rc.configure(width=px(380))
        rc.pack(side="left", fill="y", padx=(px(16), 0))
        rc.pack_propagate(False)
        self.hist_pic = tk.Label(rc.body, bg=C["card"])
        self.hist_pic.pack(pady=(px(6), px(10)))
        self.hist_text = tk.Label(rc.body, bg=C["card"], fg=C["label"], font=F["footnote"],
                                  justify="left", anchor="nw", wraplength=px(340),
                                  text="Select an entry to see its picture and details.")
        self.hist_text.pack(fill="x")
        self._hist_rows: dict[str, dict] = {}
        self._hist_photo = None
        self._hist_pending = False
        self.after(80, self.refresh_history)

    def refresh_history(self):
        self._hist_pending = False
        inst = self.hist_inst.get()
        kinds = HISTORY_KINDS.get(self.hist_kind.get())
        entries = [e for e in self.m.history.recent(600, None if inst in ("", ALL_INSTANCES) else inst)
                   if kinds is None or e["kind"] in kinds][:400]
        self.hist_tree.delete(*self.hist_tree.get_children())
        self._hist_rows = {}
        for i, e in enumerate(entries):
            iid = f"h{i}"
            self._hist_rows[iid] = e
            when = datetime.fromtimestamp(e["t"]).strftime("%b %d  %H:%M")
            tag = ("kept",) if e.get("action") == "kept" else \
                ("problem",) if e["kind"] == "failure" or e.get("action") == "stopped" else \
                ("energy",) if e["kind"] == "energy" else \
                ("quiet",) if e.get("action") == "scrapped" else ()
            self.hist_tree.insert("", "end", iid=iid, values=(f"  {when}", e["instance"], e["detail"]),
                                  tags=tag)
        if entries:
            self.hist_empty.place_forget()
        else:
            self.hist_empty.place(relx=0.5, rely=0.45, anchor="center")
        s = self.m.history.crest_summary(None if inst in ("", ALL_INSTANCES) else inst)
        self.hist_summary.configure(
            text=f"Crests kept {s.get('kept', 0)}  ·  scrapped {s.get('scrapped', 0)}"
                 + (f"  ·  unidentified {s['stopped']}" if s.get("stopped") else ""))

    def _on_hist_select(self):
        sel = self.hist_tree.selection()
        e = self._hist_rows.get(sel[0]) if sel else None
        if not e:
            return
        p = self.m.history.thumb_path(e)
        if p:
            img = cv2.imdecode(np.fromfile(str(p), np.uint8), cv2.IMREAD_COLOR)
            if img is not None:
                self._hist_photo, _ = to_photo(img, px(350), px(420))
                self.hist_pic.configure(image=self._hist_photo)
        else:
            self._hist_photo = None
            self.hist_pic.configure(image="")
        when = datetime.fromtimestamp(e["t"]).strftime("%A %d %B, %H:%M:%S")
        script = SCRIPTS[e["script"]].NAME if e["script"] in SCRIPTS else e["script"]
        extra = "".join(f"\n{k.title()}: {e[k]}" for k in ("rarity", "action") if e.get(k))
        self.hist_text.configure(text=f"{e['detail']}\n\n{when}\n{e['instance']} · {script}{extra}")

    def clear_history(self):
        if ios.confirm(self, "Every history entry and its picture will be deleted. Stats are kept.",
                       "Clear History?", ok="Clear", destructive=True):
            self.m.history.clear()
            self.refresh_history()

    # ================================================================ units
    def _build_units(self):
        _, page, hdr = self._page("Units", "Units", "people")
        ios.Button(hdr, "Export CSV", self.units_export, kind="tinted",
                   icon="download").pack(side="right")
        ios.Button(hdr, "Correct Name", self.units_correct, kind="plain", icon="edit",
                   small=True).pack(side="right", padx=(0, px(14)))
        ios.Button(hdr, "Remove", self.units_remove, kind="plain", color="red", icon="delete",
                   small=True).pack(side="right", padx=(0, px(14)))
        ios.Button(hdr, "GSCompanion", self.units_gsc, kind="plain", icon="link",
                   small=True).pack(side="right", padx=(0, px(14)))
        bar = tk.Frame(page, bg=C["bg"])
        bar.pack(fill="x", padx=px(20), pady=(0, px(10)))
        self.units_q = tk.StringVar()
        ios.Field(bar, self.units_q, width=22).pack(side="left")
        self.units_q.trace_add("write", lambda *a: self.refresh_units())
        self.units_el = ios.Select(bar, values=["All elements", "Fire", "Water", "Earth", "Light", "Dark"],
                                   accent=True, command=self.refresh_units)
        self.units_el.set("All elements")
        self.units_el.pack(side="left", padx=px(16))
        self.units_incomplete = tk.BooleanVar(value=False)
        ios.Switch(bar, self.units_incomplete, command=self.refresh_units).pack(side="left")
        self._label(bar, "Unread fields only").pack(side="left", padx=(px(6), 0))
        self.units_summary = self._label(bar, "")
        self.units_summary.pack(side="right")

        lc = ios.Card(page, pad=6, stretch=True)
        lc.pack(fill="both", expand=True, padx=px(20), pady=(0, px(14)))
        cols = ("name", "element", "race", "quest_clears", "first_seen", "last_seen")
        heads = ("Name", "Element", "Race", "Quest clears", "First seen", "Last seen")
        sb = ttk.Scrollbar(lc.body, orient="vertical", style="IOS.Vertical.TScrollbar")
        self.units_tree = ttk.Treeview(lc.body, columns=cols, show="headings", style="IOS.Treeview",
                                       selectmode="browse", yscrollcommand=sb.set)
        sb.configure(command=self.units_tree.yview)
        self._units_sort = ("name", False)
        for c, h, w in zip(cols, heads, (260, 90, 110, 110, 110, 110)):
            self.units_tree.heading(c, text=h, command=lambda c=c: self._units_sort_by(c))
            self.units_tree.column(c, width=px(w), stretch=(c == "name"),
                                   anchor="w" if c in ("name", "race") else "center")
        self.units_tree.tag_configure("uncertain", foreground=C["orange"])
        sb.pack(side="right", fill="y", pady=px(4))
        self.units_tree.pack(side="left", fill="both", expand=True)
        self.units_empty = tk.Label(lc.body, bg=C["card"], fg=C["secondary"], font=F["footnote"],
                                    justify="center",
                                    text="No units yet\nOpen Units in-game and run the Compendium Counter "
                                         "script:\nit reads each unit's page and fills this list.")
        self.after(120, self.refresh_units)

    def _units_sort_by(self, col: str):
        cur, desc = self._units_sort
        self._units_sort = (col, not desc if cur == col else col in ("quest_clears", "last_seen"))
        self.refresh_units()

    def refresh_units(self):
        r = self.m.units
        el = self.units_el.get()
        rows = r.rows(search=self.units_q.get(), sort=self._units_sort[0], desc=self._units_sort[1],
                      element=None if el in ("", "All elements") else el,
                      only_incomplete=self.units_incomplete.get())
        self.units_tree.delete(*self.units_tree.get_children())
        for u in rows:
            def val(f):
                v = r.value(u, f)
                if v is None:
                    return "–"
                st = u["fields"][f].get("status")
                return f"{v:,}" if isinstance(v, int) else (f"{v}?" if st == "uncertain" else str(v))
            unsure = u.get("name_status") == "uncertain"
            self.units_tree.insert("", "end", iid=u["name"], tags=("uncertain",) if unsure else (),
                                   values=(u["name"] + (" ?" if unsure else ""), val("element"),
                                           val("race"), val("quest_clears"),
                                           datetime.fromtimestamp(u["first_seen"]).strftime("%d %b %Y"),
                                           datetime.fromtimestamp(u["last_seen"]).strftime("%d %b %Y")))
        if rows:
            self.units_empty.place_forget()
        else:
            self.units_empty.place(relx=0.5, rely=0.45, anchor="center")
        self.units_summary.configure(text=r.summary_text().replace("**", ""))

    def _units_selected(self) -> str | None:
        sel = self.units_tree.selection()
        return sel[0] if sel else None

    def units_export(self):
        path = filedialog.asksaveasfilename(parent=self, defaultextension=".csv",
                                            initialfile="rerun_units.csv",
                                            filetypes=[("CSV", "*.csv")])
        if path:
            Path(path).write_text(self.m.units.to_csv(), encoding="utf-8", newline="")
            self.flash(f"Saved {Path(path).name}", "ok")

    def units_correct(self):
        name = self._units_selected()
        if not name:
            return ios.alert(self, "Select a unit first.", "Correct Name")
        right = ios.ask_string(self, "Correct Name",
                               f"Rerun read this name as '{name}'. Type the correct name - future "
                               "scans will remember it.", name)
        if right and right.strip() and right.strip() != name:
            self.m.units.correct_name(name, right.strip())
            self.flash(f"Saved: '{name}' is {right.strip()}", "ok")
            self.refresh_units()

    def units_remove(self):
        name = self._units_selected()
        if not name:
            return ios.alert(self, "Select a unit first.", "Remove Unit")
        if ios.confirm(self, f"Remove '{name}' from the roster? Use this for misreadings. "
                             "Earlier scan records are kept; a later scan adds the unit again "
                             "if it is really on your account.", "Remove Unit?",
                       ok="Remove", destructive=True):
            self.m.units.remove(name)
            self.flash(f"Removed '{name}'", "ok")
            self.refresh_units()

    def units_gsc(self):
        """GSCompanion as a reference you open yourself: Rerun copies the unit's name and
        opens GSCompanion's Units page (nothing is downloaded from the site)."""
        import webbrowser
        from .units import GSC_UNITS_URL
        name = self._units_selected()
        if name:
            self.clipboard_clear()
            self.clipboard_append(name)
            self.flash(f"Copied '{name}' - paste it into GSCompanion's search", "info")
        webbrowser.open(GSC_UNITS_URL)

    # ================================================================ discord
    def _build_discord(self):
        _, page, hdr = self._page("Discord Bot", "Discord", "chat", scroll=True)
        self._d_dot = ios.Dot(hdr, 9)
        self._d_dot.pack(side="left", padx=(0, px(8)))
        self.d_status = self._label(hdr, "Not connected", font="footnote")
        self.d_status.pack(side="left")
        cfg = self.m.config["discord"]
        self.d_vars = {
            "enabled": tk.BooleanVar(value=bool(cfg.get("enabled"))),
            "token": tk.StringVar(value=cfg.get("token", "")),
            "channel_id": tk.StringVar(value=str(cfg.get("channel_id") or "")),
            "ping_user_id": tk.StringVar(value=str(cfg.get("ping_user_id") or "")),
            "allowed_user_ids": tk.StringVar(
                value=", ".join(str(x) for x in cfg.get("allowed_user_ids", []) or [])),
        }
        wrap = tk.Frame(page, bg=C["bg"])
        wrap.pack(fill="x", padx=px(20))
        g = ios.Group(wrap)
        g.pack(fill="x")
        ios.Switch(g.row("Connect When Rerun Starts",
                         "Brings the bot online every time you open Rerun."),
                   self.d_vars["enabled"]).pack()
        g2 = ios.Group(wrap, header="Bot",
                       footer="Keep the token secret - anyone with it controls your bot.")
        g2.pack(fill="x", pady=(px(24), 0))
        for label, key, secret, sub in [
                ("Bot Token", "token", True, None),
                ("Alert Channel ID", "channel_id", False, "Where alerts and screenshots are posted"),
                ("User ID to Ping", "ping_user_id", False, "Mentioned on rare crests and failures"),
                ("Allowed User IDs", "allowed_user_ids", False,
                 "Comma separated - who may control Rerun")]:
            ios.Field(g2.row(label, sub), self.d_vars[key], width=34,
                      show="•" if secret else "").pack()
        bar = tk.Frame(wrap, bg=C["bg"])
        bar.pack(fill="x", pady=(px(16), 0))
        ios.Button(bar, "Save & Connect", self.save_discord, icon="sync").pack(side="left")
        ios.Button(bar, "Disconnect", self.disconnect_discord, kind="gray").pack(side="left", padx=px(8))
        ios.Button(bar, "Send Test Message", self.test_discord, kind="tinted",
                   icon="send").pack(side="left")

        summ = self.m.config.get("summary") or {}
        gsum = ios.Group(wrap, header="Daily Summary",
                         footer="Runs, crests kept and scrapped, refills and problems of the last 24 "
                                "hours, posted to the alert channel. Also any time with /summary.")
        gsum.pack(fill="x", pady=(px(24), 0))
        self.sum_on = tk.BooleanVar(value=bool(summ.get("enabled", True)))
        ios.Switch(gsum.row("Post a daily summary"), self.sum_on).pack()
        self.sum_time = tk.StringVar(value=str(summ.get("time", "21:00")))
        ios.Field(gsum.row("At (24-hour HH:MM)"), self.sum_time, width=6, justify="right").pack()

        ios.section_header(wrap, "Setup Guide", pady=(px(28), px(6)))
        gc = ios.Card(wrap)
        gc.pack(fill="x", pady=(0, px(24)))
        guide = tk.Label(gc.body, text=DISCORD_GUIDE, bg=C["card"], fg=C["label"],
                         font=F["footnote"], justify="left", anchor="w", wraplength=px(700))
        guide.pack(fill="x", padx=px(14), pady=px(12))
        gc.body.bind("<Configure>", lambda e: guide.configure(
            wraplength=max(px(200), e.width - px(32))), add="+")

    def _set_d_status(self, text: str):
        self.d_status.configure(text=short(text, 70))
        low = text.lower()
        if "online" in low:
            color = C["green"]
        elif "connecting" in low:
            color = C["orange"]
        elif "could not" in low or "stopped" in low or ":" in text:
            color = C["red"]
        else:
            color = C["gray"]
        self._d_dot.set(color)

    def save_discord(self):
        def to_int(s):
            s = str(s).strip()
            return int(s) if s.isdigit() else 0
        cfg = self.m.config["discord"]
        cfg["enabled"] = bool(self.d_vars["enabled"].get())
        cfg["token"] = self.d_vars["token"].get().strip()
        cfg["channel_id"] = to_int(self.d_vars["channel_id"].get())
        cfg["ping_user_id"] = to_int(self.d_vars["ping_user_id"].get())
        cfg["allowed_user_ids"] = [int(x) for x in self.d_vars["allowed_user_ids"].get().replace(" ", "").split(",") if x.isdigit()]
        t = self.sum_time.get().strip()
        if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", t):
            ios.alert(self, "Write the summary time as HH:MM, e.g. 21:00.", "Daily Summary")
            return
        self.m.config["summary"] = {"enabled": bool(self.sum_on.get()), "time": t}
        self.m.save_config()
        self.connect_discord()

    def connect_discord(self):
        from .discord_bot import DiscordBot
        self.disconnect_discord()
        try:
            self.bot = DiscordBot(self.m)
        except RuntimeError as e:
            self._set_d_status(f"Not connected: {e}")
            return
        if not self.m.config["discord"].get("channel_id"):
            self._set_d_status("Set the alert channel ID first.")
            return
        self.bot.start()
        self._set_d_status("Connecting...")

    def disconnect_discord(self):
        if self.bot:
            self.bot.stop()
            self.bot = None
            self._set_d_status("Disconnected")

    def test_discord(self):
        if not self.bot or not self.bot.ready.is_set():
            self.flash("The bot is not connected yet", "warn")
            return
        self.m.notify("Rerun", "Test message - alerts will arrive here.", ping=True)
        self.flash("Test message sent", "ok")

    # ================================================================ log
    def _build_log(self):
        _, page, hdr = self._page("Log", "Log", "list")
        ios.Button(hdr, "Save Log…", self._save_log, kind="tinted", icon="save").pack(side="right")
        ios.Button(hdr, "Clear", self._clear_log, kind="tinted", color="red",
                   icon="delete").pack(side="right", padx=(0, px(8)))
        bar = tk.Frame(page, bg=C["bg"])
        bar.pack(fill="x", padx=px(20), pady=(0, px(10)))
        self.log_level = tk.StringVar(value="All")
        ios.Segmented(bar, list(LOG_LEVELS), self.log_level, command=self._rebuild_log).pack(side="left")
        self.log_inst = ios.Select(bar, values=[ALL_INSTANCES], accent=True, command=self._rebuild_log)
        self.log_inst.set(ALL_INSTANCES)
        self.log_inst.pack(side="left", padx=px(16))
        self.log_search = tk.StringVar()
        fld = ios.Field(bar, self.log_search, width=28)
        fld.pack(side="right")
        self._label(bar, "Search").pack(side="right", padx=(0, px(8)))
        fld.entry.bind("<KeyRelease>", lambda e: self._debounce_log())
        _, self.log_box = ios.text_box(page, mono=True, wrap="none", padx=px(20), pady=(0, px(14)))
        self.log_box.tag_configure("warn", foreground=C["orange"])
        self.log_box.tag_configure("error", foreground=C["red"])
        self.log_box.configure(state="disabled")
        self._log_after = None
        self._log_hidden_before = 0  # entries removed by Clear

    def _log_match(self, e: dict) -> bool:
        levels = LOG_LEVELS.get(self.log_level.get())
        inst = self.log_inst.get()
        q = self.log_search.get().strip().lower()
        return ((levels is None or e["level"] in levels)
                and (inst in ("", ALL_INSTANCES) or e["instance"] == inst)
                and (not q or q in e["line"].lower()))

    def _debounce_log(self):
        if self._log_after:
            self.after_cancel(self._log_after)
        self._log_after = self.after(250, self._rebuild_log)

    def _rebuild_log(self):
        self._log_after = None
        entries = self.m.log_entries[self._log_hidden_before:]
        box = self.log_box
        box.configure(state="normal")
        box.delete("1.0", "end")
        for e in entries:
            if self._log_match(e):
                box.insert("end", e["line"] + "\n", (e["level"],) if e["level"] != "info" else ())
        box.see("end")
        box.configure(state="disabled")

    def _append_log(self, e: dict):
        if not self._log_match(e):
            return
        box = self.log_box
        at_end = box.yview()[1] >= 0.999
        box.configure(state="normal")
        box.insert("end", e["line"] + "\n", (e["level"],) if e["level"] != "info" else ())
        if int(box.index("end-1c").split(".")[0]) > 5000:
            box.delete("1.0", "1000.0")
        if at_end:
            box.see("end")  # don't yank the view while you're reading older lines
        box.configure(state="disabled")

    def _clear_log(self):
        self._log_hidden_before = len(self.m.log_entries)
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

    def _save_log(self):
        path = filedialog.asksaveasfilename(defaultextension=".txt")
        if path:
            Path(path).write_text("\n".join(self.m.log_lines), encoding="utf-8")
            self.flash("Log saved", "ok")

    # ================================================================ loop
    def flash(self, text: str, kind: str = "info"):
        if text:
            self.toast.show(text, kind)

    def _poll_events(self):
        history_changed = False
        try:
            for _ in range(500):  # bounded: a burst of log lines can't freeze the window
                ev = self.events.get_nowait()
                t = ev.get("type")
                if t == "log":
                    if self._log_hidden_before > len(self.m.log_entries):
                        self._log_hidden_before = 0  # the log was trimmed since Clear
                    self._append_log(ev)
                    if ev["instance"] == "discord":
                        self._set_d_status(ev["message"])
                    if ev["instance"] in self.m.instances:
                        self.m.instances[ev["instance"]].detail = ev["message"][:120]
                elif t == "status":
                    self.refresh_instances()
                    if ev.get("status") in ("idle", "error") and ev.get("detail") not in ("", None):
                        kind = "error" if ev["status"] == "error" else "info"
                        self.flash(f"{ev['instance']}: {ev['detail']}", kind)
                elif t == "history":
                    history_changed = True
                    if ev.get("entry", {}).get("kind") == "compendium":
                        self.after(50, self.refresh_units)  # a unit scan just finished
                elif t == "_preview":
                    self._preview_img = ev["img"]
                    self._draw_preview()
                elif t == "_tpl_img":
                    self.set_tpl_image(ev["img"])
                elif t == "_error":
                    ios.alert(self, ev["message"], "Something Went Wrong")
                elif t == "_alert":
                    ios.alert(self, ev["message"], ev.get("title", "Rerun"))
                elif t == "_setup":
                    self._show_setup_results(ev["checks"])
                elif t == "_hotkey":
                    ev["fn"]()
                elif t == "_tray":
                    self._tray_action(ev["action"])
        except queue.Empty:
            pass
        if history_changed and not self._hist_pending:
            self._hist_pending = True
            self.after(400, self.refresh_history)
        self.after(150, self._poll_events)

    def _tick(self):
        if self.state() != "withdrawn":
            self.refresh_instances()
            self._auto_preview()
        self._ticks = getattr(self, "_ticks", 0) + 1
        if self._ticks % 30 == 0:
            self._check_template_health()
        self.after(1000, self._tick)

    def _check_template_health(self):
        """Warn once per template that starts matching barely above its threshold."""
        for name, h in self.m.vision.health().items():
            if h["weak"] and name not in self._weak_seen:
                self._weak_seen.add(name)
                self.m.log("app", f"Template '{name}' is matching weakly (median {h['median']:.2f}, "
                                  f"needs {h['threshold']:.2f}) - re-capture it in the Templates tab "
                                  "before it stops matching", level="warn")
                self.flash(f"Template '{name}' is fading - see the Templates tab", "warn")

    def _start_hotkeys(self):
        try:
            from pynput import keyboard
        except ImportError:
            return
        hk = self.m.config.get("hotkeys", {})
        mapping = {}
        if hk.get("stop_all"):
            mapping[f"<{hk['stop_all']}>"] = lambda: self.events.put({"type": "_hotkey", "fn": self.stop_all})
        if hk.get("pause_all"):
            mapping[f"<{hk['pause_all']}>"] = lambda: self.events.put(
                {"type": "_hotkey", "fn": self.m.toggle_pause_all})
        try:
            self._hotkeys = keyboard.GlobalHotKeys(mapping)
            self._hotkeys.start()
        except Exception as e:  # noqa: BLE001
            self.flash(f"Global hotkeys unavailable: {e}", "warn")

    # tray / closing ----------------------------------------------------------
    def show_window(self):
        self.deiconify()
        self.lift()
        self.focus_force()
        self.refresh_instances()

    def _tray_action(self, action: str):
        if action == "show":
            self.show_window()
        elif action == "start_all":
            self.start_all()
        elif action == "stop_all":
            self.stop_all()
        elif action == "pause_all":
            self.m.toggle_pause_all()
        elif action == "quit":
            self.show_window()
            self.quit_app()

    def on_close(self):
        """The window's X: hide to the tray if that's on, otherwise quit."""
        if self._tray_on and self.close_to_tray.get():
            self.withdraw()
            if not self._tray_hinted:
                self._tray_hinted = True
                self.tray.notify("Rerun is still running here. Right-click the icon to quit.")
            return
        self.quit_app()

    def quit_app(self):
        running = [n for n, i in self.m.instances.items() if i.status in ("running", "paused", "starting")]
        if running and not ios.confirm(self, "Scripts are still running. Stop them and quit?",
                                       "Quit Rerun?", ok="Stop & Quit", destructive=True):
            return
        self.m.stop_all()
        self.disconnect_discord()
        self.destroy()

    def destroy(self):
        """Always release the tray icon and hotkey threads (they would otherwise
        keep the process alive after the window is gone)."""
        if not self._closing:
            self._closing = True
            self.m.stats.flush()
            tray = getattr(self, "tray", None)
            if tray is not None:
                tray.stop()
            if self._hotkeys:
                self._hotkeys.stop()
        super().destroy()


ADB_HELP = ("In BlueStacks open Settings > Advanced and turn on 'Android Debug Bridge (ADB)'. "
            "It shows the address (127.0.0.1:<port>); then use Detect BlueStacks or Edit on the "
            "Dashboard so Rerun has the same address.")
DISPLAY_HELP = ("In BlueStacks open Settings > Display and choose 1280x720 (and DPI 240). "
                "Grand Summoners runs in portrait, so Rerun then sees 720x1280 frames - the size "
                "all templates were made for. Restart BlueStacks after changing it.")

DISCORD_GUIDE = """One-time setup, about 3 minutes:

1.  Go to https://discord.com/developers/applications and click "New Application".
2.  Open "Bot", click "Reset Token" and paste the token into Bot Token above. Keep it secret - anyone with it controls your bot.
3.  Open "OAuth2 > URL Generator": tick "bot" and "applications.commands", then under Bot Permissions tick "Send Messages", "Attach Files" and "Embed Links". Open the generated link and add the bot to your server.
4.  In Discord: Settings > Advanced > turn on Developer Mode. Right-click your alert channel > Copy Channel ID, and right-click your name > Copy User ID.
5.  Paste them above, put your User ID in Allowed User IDs, and press Save & Connect.

Slash commands:  /status  /start  /stop  /pause  /resume  /screenshot  /stats  /resetstats  /history  /summary  /scripts
Only the user IDs you allowed can start, stop, reset stats or take screenshots.

Alerts:  rare crests, Crest Bursts, hyper rare drops, failures, crashes and finished runs are posted to the alert channel, with a screenshot where useful, pinging the user ID above."""


def run_app(root: str | Path) -> None:
    app = App(Manager(root))
    app.mainloop()
