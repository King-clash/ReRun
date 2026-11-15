"""Team & Damage: the site's Team Builder and Damage Calculator as one page, in Rerun's look.

Pick up to 4 units (leader, order, which moves are on, stacks, dream, equips), choose who attacks
and with which move, set the enemy and crest, and the damage updates as you edit.  The same
setup is the team in both halves, so nothing has to be re-entered.  The numbers come from
gsc_app/calc.py, checked against the live site (gsc_app/calc_check.py), and the link this page
makes opens the identical setup on gscompanion.com/damage-calc/.
"""
from __future__ import annotations

import tkinter as tk
import webbrowser
from tkinter import ttk

from rerun import ios
from rerun.ios import C, F, px

from . import calc
from .calc import CalcData, js_round
from .calc_model import MOVE_SHORT, CalcModel, fresh_state

MAX_PICK_ROWS = 250
ALL_PARTS = ("slots", "attack", "enemy", "extra")
# What each edit needs redrawn (the damage figures are always redrawn)
PARTS = {
    "add_unit": ("slots", "attack"), "remove_unit": ("slots", "attack"),
    "move_unit": ("slots", "attack"), "set_attacker": ("slots", "attack"),
    "select_hit": ("slots", "attack"), "set_leader": ("slots",), "toggle_move": ("slots",),
    "set_stack": ("slots",), "toggle_equip": ("slots",), "set_equip_target": ("slots",),
    "set_equip": ("slots", "attack"), "remove_equip": ("slots", "attack"),
    "set_dream": ("slots", "attack"), "set_enemy": ("enemy",), "toggle_status": ("enemy",),
    "set_crest": ("extra", "attack"), "set_crest_level": ("extra", "attack"),
}
ELEMENT_COLORS = {"Fire": "red", "Water": "blue", "Earth": "green", "Light": "orange",
                  "Dark": "secondary"}
TERM_NAMES = {
    "multFactor": "Multiplier ×", "multAdd": "Multiplier +", "atk": "ATK", "atkFlat": "Flat ATK",
    "dmg": "DMG UP", "critDmg": "CRI DMG UP · crits only", "res": "RES DOWN",
    "defDown": "DEF DOWN", "ignoreDef": "Ignore DEF", "criRate": "CRI rate",
    "superCriRate": "Super CRI rate"}
EXTRA_KEY = {"atk": "atk", "dmg": "dmg", "critDmg": "critDmg", "res": "res",
             "ignoreDef": "ignoreDef", "criRate": "criRate"}
SOURCE_NAMES = {"passive": "Passive", "trueWeapon": "True Weapon", "dream": "Dream Awakening",
                "crest": "Crest"}
STATUS_NAMES = {"Burn": "Burning", "Poison": "Poisoned", "Freeze": "Frozen",
                "Paralysis": "Paralysed", "Faint": "Fainted", "Blind": "Blinded",
                "Disease": "Diseased", "Seal": "Sealed", "Curse": "Cursed"}


def n0(x) -> str:
    return f"{js_round(x):,}"


def short(x) -> str:
    if x >= 1e9:
        return f"{x / 1e9:.2f}B"
    if x >= 1e6:
        return f"{x / 1e6:.2f}M"
    if x >= 1e4:
        return f"{x / 1e3:.1f}K"
    return n0(x)


def pct(x) -> str:
    return f"{round(x, 1):g}%"


def signed(x) -> str:
    return f"{'+' if x >= 0 else '−'}{abs(round(x, 1)):g}%"


def times(x) -> str:
    return f"×{round(x, 3):g}"


def fmt_term(term: str, v: float) -> str:
    if term == "multFactor":
        return times(v)
    if term == "multAdd":
        return f"+{n0(v)}%"
    if term == "atkFlat":
        return f"+{n0(v)}"
    return pct(v)


def to_num(text: str) -> float:
    try:
        v = float(str(text).strip())
    except ValueError:
        return 0
    return int(v) if v == int(v) else v


class Tip:
    """A small hover label (what S / NA / TA ... stand for)."""

    def __init__(self, widget, text: str):
        self.w, self.text, self.top = widget, text, None
        widget.bind("<Enter>", self._show, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<Destroy>", self._hide, add="+")

    def _show(self, _e=None):
        if self.top or not self.text:
            return
        self.top = tk.Toplevel(self.w)
        self.top.overrideredirect(True)
        self.top.attributes("-topmost", True)
        tk.Label(self.top, text=self.text, bg="#1C1C1E", fg="#FFFFFF", font=F["caption"],
                 padx=px(8), pady=px(3)).pack()
        self.top.geometry(f"+{self.w.winfo_rootx() + px(4)}+{self.w.winfo_rooty() + self.w.winfo_height() + px(4)}")

    def _hide(self, _e=None):
        if self.top is not None:
            self.top.destroy()
            self.top = None


class Pill(tk.Canvas):
    """A rounded on / off toggle: hover and pressed states, a disabled look, optional tooltip."""

    def __init__(self, parent, text, on=False, command=None, tip=None, disabled=False,
                 color: str = "blue"):
        self._bg = ios.bg_of(parent)
        self._text, self._on, self._cmd, self._disabled = text, on, command, disabled
        self._accent = C[color]
        # an "off" pill is the opposite shade of whatever it sits on, so it always reads
        self._off = C["field"] if self._bg == C["card"] else C["card"]
        self._font = F["footnote_semi"]
        w, h = ios.measure(self._font, text) + px(20), px(26)
        super().__init__(parent, width=w, height=h, bg=self._bg, highlightthickness=0, bd=0,
                         cursor="hand2" if command and not disabled else "arrow")
        self._state = "normal"
        self.bind("<Enter>", lambda e: self._set("hover"))
        self.bind("<Leave>", lambda e: self._set("normal"))
        self.bind("<ButtonPress-1>", lambda e: self._set("pressed"))
        self.bind("<ButtonRelease-1>", self._release)
        if tip:
            Tip(self, tip)
        self._draw()

    def _set(self, st):
        if self._disabled:
            return
        self._state = st
        self._draw()

    def _release(self, e):
        if self._disabled:
            return
        inside = 0 <= e.x <= int(self["width"]) and 0 <= e.y <= int(self["height"])
        self._set("hover" if inside else "normal")
        if inside and self._cmd:
            self._cmd()

    def _draw(self):
        self.delete("all")
        w, h = int(self["width"]), int(self["height"])
        fill = self._accent if self._on else self._off
        if self._state == "hover":
            fill = ios.mix(fill, C["label"], 0.07)
        elif self._state == "pressed":
            fill = ios.mix(fill, C["label"], 0.16)
        fg = "#FFFFFF" if self._on else C["label"]
        if self._disabled:
            fill = ios.mix(fill, self._bg, 0.35)
            fg = ios.mix(fg, self._bg, 0.35)
        ios.rounded_rect(self, 0, 0, w, h, px(8), fill, self._bg)
        self.create_text(w // 2, h // 2, text=self._text, fill=fg, font=self._font)


class Check(tk.Canvas):
    """A small rounded check box (the system one looks wrong on a dark background)."""

    def __init__(self, parent, on: bool, command):
        self._bg = ios.bg_of(parent)
        self._on, self._cmd = on, command
        s = px(18)
        super().__init__(parent, width=s, height=s, bg=self._bg, highlightthickness=0, bd=0,
                         cursor="hand2")
        self.bind("<ButtonRelease-1>", self._click)
        self._draw()

    def _click(self, _e):
        self._on = not self._on
        self._draw()
        self._cmd(self._on)

    def _draw(self):
        self.delete("all")
        s = px(18)
        if self._on:
            ios.rounded_rect(self, 0, 0, s, s, px(5), C["blue"], self._bg)
            self.create_line(px(4.5), px(9.5), px(7.8), px(12.8), px(13.5), px(5.5),
                             fill="#FFFFFF", width=px(2), capstyle="round", joinstyle="round")
        else:
            ios.rounded_rect(self, 0, 0, s, s, px(5), C["tertiary"], self._bg)
            ios.rounded_rect(self, px(1.5), px(1.5), s - px(1.5), s - px(1.5), px(4),
                             self._bg, C["tertiary"])


class CalcPanel(tk.Frame):
    """parent: any Tk container.  data: CalcData.  pics: the app's Pictures.
    settings: the app's Settings (the setup is remembered under "calc")."""

    def __init__(self, parent, data: CalcData, pics, settings=None, flash=None,
                 open_url=webbrowser.open, my_units=None, on_update=None, crest_icon=None):
        super().__init__(parent, bg=C["bg"])
        self.data, self.pics, self.s = data, pics, settings
        self.crest_icon = crest_icon   # crest name -> its picture file (or None)
        self._open: set[int] = set()   # slots whose Details are open
        self._narrow = False
        self._anim = None
        self._last_big = None
        self._flash = flash or (lambda t, k="info": None)
        self._open_url = open_url
        self.my_units = my_units or (lambda: set())
        self.model = CalcModel(data)
        self.k = 1.0
        self._vars: dict[str, tuple[tk.StringVar, object]] = {}
        self._save_after = None
        self._photos: list = []
        saved = (settings["calc"] if settings is not None else None)
        if isinstance(saved, dict) and saved.get("slots"):
            self.model.load(saved)
        if not data.available:
            box = tk.Frame(self, bg=C["bg"])
            box.pack(expand=True)
            tk.Label(box, text="Team & Damage needs its data", bg=C["bg"], fg=C["label"],
                     font=F["title"]).pack()
            tk.Label(box, text="It is a one-time download from gscompanion.com (about 8 MB).",
                     bg=C["bg"], fg=C["secondary"], font=F["footnote"]).pack(pady=(px(4), px(12)))
            if on_update:
                ios.Button(box, "Update data", on_update, kind="filled").pack()
            return
        self._build()
        self.refresh()

    # ============================================================== layout
    def _build(self):
        self.body = tk.Frame(self, bg=C["bg"])
        self.body.pack(fill="both", expand=True)
        self.body.grid_columnconfigure(0, weight=3, uniform="c")
        self.body.grid_columnconfigure(1, weight=2, uniform="c")
        self.body.grid_rowconfigure(0, weight=1)
        self.left = ios.ScrollFrame(self.body)
        self.right = ios.ScrollFrame(self.body)
        self._place_columns(False)
        self.body.bind("<Configure>", self._on_resize)
        for sf in (self.left, self.right):
            sf.canvas.bind("<MouseWheel>", sf.scroll)
            sf.inner.bind("<MouseWheel>", sf.scroll)

        L, R = self.left.inner, self.right.inner
        # --- team
        bar = self._card(L, "Team")
        tools = tk.Frame(bar, bg=C["card"])
        tools.pack(fill="x", pady=(0, px(8)))
        for text, fn, kind in (("Copy link", self.copy_link, "tinted"),
                               ("Open on site", self.open_site, "gray"),
                               ("Load link…", self.load_link, "gray"),
                               ("Clear", self.clear, "plain")):
            ios.Button(tools, text, fn, kind=kind, small=True,
                       color="red" if text == "Clear" else "blue").pack(side="left",
                                                                         padx=(0, px(8)))
        self.slots_box = tk.Frame(bar, bg=C["card"])
        self.slots_box.pack(fill="x")
        for c in (0, 1):
            self.slots_box.grid_columnconfigure(c, weight=1, uniform="s")
        # --- attack
        self.attack_box = self._card(L, "Attack")
        # --- enemy
        self.enemy_box = self._card(L, "Enemy")
        # --- crest + extras
        self.extra_box = self._card(L, "Crest and extra modifiers")
        # --- results
        self.result_box = self._card(R, "Damage")
        self.moves_box = self._card(R, "Every move")
        self.mods_box = self._card(R, "Modifiers")
        self.hp_label = tk.Label(R, bg=C["bg"], fg=C["secondary"], font=F["caption"],
                                 justify="left", anchor="w", wraplength=px(420))
        self.hp_label.pack(fill="x", padx=px(20), pady=(0, px(14)))

    def _place_columns(self, narrow: bool):
        """Two columns (team | damage) when there is room, one stacked column otherwise."""
        for sf in (self.left, self.right):
            sf.grid_forget()
        for r in range(2):
            self.body.grid_rowconfigure(r, weight=0)
        if narrow:
            self.body.grid_columnconfigure(0, weight=1, uniform="")
            self.body.grid_columnconfigure(1, weight=0, uniform="")
            self.body.grid_rowconfigure(0, weight=3)
            self.body.grid_rowconfigure(1, weight=2)
            self.left.grid(row=0, column=0, columnspan=2, sticky="nsew", pady=(0, px(8)))
            self.right.grid(row=1, column=0, columnspan=2, sticky="nsew")
        else:
            self.body.grid_columnconfigure(0, weight=3, uniform="c")
            self.body.grid_columnconfigure(1, weight=2, uniform="c")
            self.body.grid_rowconfigure(0, weight=1)
            self.left.grid(row=0, column=0, sticky="nsew", padx=(0, px(8)))
            self.right.grid(row=0, column=1, sticky="nsew", padx=(px(8), 0))
        self._narrow = narrow

    def _on_resize(self, e):
        narrow = e.width < px(980)
        if narrow != self._narrow:
            self._place_columns(narrow)

    def _animate_big(self, label: tk.Label, old, new):
        """The damage figure eases to its new value (a short count, not a flash)."""
        if self._anim:
            self.after_cancel(self._anim)
            self._anim = None
        if old is None or old == new or abs(new - old) < 2:
            label.configure(text=n0(new))
            return
        steps = 7

        def tick(i=1):
            if not label.winfo_exists():
                return
            t = 1 - (1 - i / steps) ** 3   # ease out
            label.configure(text=n0(old + (new - old) * t))
            self._anim = self.after(18, lambda: tick(i + 1)) if i < steps else None

        tick()

    def _card(self, parent, title: str) -> tk.Frame:
        ios.section_header(parent, title, padx=px(8), pady=(px(10), px(6)))
        card = ios.Card(parent, pad=10, stretch=True)
        card.pack(fill="x", padx=px(4))
        return card.body

    # ============================================================== helpers
    def _clear(self, frame: tk.Frame):
        for w in frame.winfo_children():
            w.destroy()

    def _label(self, parent, text, kind="body", fg=None, **pack):
        lbl = tk.Label(parent, text=text, bg=parent.cget("bg"), fg=fg or C["label"],
                       font=F[kind], anchor="w", justify="left")
        if pack is not None:
            lbl.pack(**pack)
        return lbl

    def _chip(self, parent, text, on, command, tip=None, disabled=False):
        return Pill(parent, text, on=on, command=command, tip=tip, disabled=disabled)

    def _photo(self, path, h, max_w=None):
        if not path:
            return None
        p = self.pics.site(path, h, max_w) if isinstance(path, str) else             self.pics.get(path, h, max_w)
        if p is not None:
            self._photos.append(p)
        return p

    def _unit_pic(self, unit, h):
        return self._photo(f"/images/{unit['thumb']}.png", px(h * self.k)) if unit.get("thumb") \
            else None

    def _num(self, parent, key: str, get, set_, width=8, label=None):
        """A number field bound to the model; typing updates the results only."""
        wrap = tk.Frame(parent, bg=parent.cget("bg"))
        if label:
            tk.Label(wrap, text=label, bg=wrap.cget("bg"), fg=C["secondary"],
                     font=F["caption"]).pack(anchor="w")
        var = tk.StringVar(value=self._fmt_num(get()))
        self._vars[key] = (var, get)

        def changed(*_):
            v = to_num(var.get())
            if v != get():
                set_(v)
                self.refresh_results()

        var.trace_add("write", changed)
        ios.Field(wrap, var, width=width, justify="right").pack(anchor="w")
        return wrap

    @staticmethod
    def _fmt_num(v) -> str:
        return "" if v in (0, None) else (str(int(v)) if v == int(v) else str(v))

    def _sync_vars(self):
        for key, (var, get) in list(self._vars.items()):
            try:
                if to_num(var.get()) != get():
                    var.set(self._fmt_num(get()))
            except tk.TclError:
                self._vars.pop(key, None)

    def _changed(self, parts=None):
        """Persist (debounced), then redraw only what the change touches."""
        if self.s is not None:
            if self._save_after:
                self.after_cancel(self._save_after)
            self._save_after = self.after(400, self._save)
        self.refresh(parts)

    def _save(self):
        self._save_after = None
        if self.s is not None:
            self.s["calc"] = self.model.state_copy()
            self.s.save()

    # ============================================================== refresh
    def refresh(self, parts=None):
        """Rebuild the named sections (all by default) and the damage figures. The scroll
        positions are kept, so nothing jumps; sections you did not touch are left alone."""
        parts = ALL_PARTS if parts is None else tuple(parts)
        ys = [sf.canvas.yview()[0] for sf in (self.left, self.right)]
        build = {"slots": self._build_slots, "attack": self._build_attack,
                 "enemy": self._build_enemy, "extra": self._build_extra}
        for name in ALL_PARTS:
            if name in parts:
                build[name]()
        self.refresh_results()
        self.update_idletasks()
        for sf, y in zip((self.left, self.right), ys):
            sf.canvas.yview_moveto(y)

    def _drop_vars(self, *prefixes):
        self._vars = {k: v for k, v in self._vars.items()
                      if not any(k.startswith(p) for p in prefixes)}

    def refresh_results(self):
        if self.s is not None:
            if self._save_after:
                self.after_cancel(self._save_after)
            self._save_after = self.after(400, self._save)
        self._results()
        self._sync_vars()

    # ------------------------------------------------------------- slots
    def _build_slots(self):
        self._clear(self.slots_box)
        m = self.model
        lead = m.leader()
        hp = m.team_hp()
        gen = calc.arts_gen(m.team())["units"]
        for i in range(4):
            cell = ios.Card(self.slots_box, pad=8, radius=10, color=C["field"])
            cell.grid(row=i // 2, column=i % 2, sticky="nsew", padx=px(4), pady=px(4))
            b = cell.body
            slot = m.s["slots"][i]
            if not slot:
                ios.Button(b, "+ Add unit", lambda i=i: self.pick_unit(i), kind="plain",
                           small=True).pack(pady=px(26))
                continue
            u = m.data.units[slot["id"]]
            tk.Frame(b, bg=C[ELEMENT_COLORS.get(u["element"], "secondary")], height=px(3)
                     ).pack(fill="x", pady=(0, px(6)))
            top = tk.Frame(b, bg=b.cget("bg"))
            top.pack(fill="x")
            pic = self._unit_pic(u, 40)
            if pic:
                tk.Label(top, image=pic, bg=top.cget("bg")).pack(side="left", padx=(0, px(8)))
            who = tk.Frame(top, bg=top.cget("bg"))
            who.pack(side="left", fill="x", expand=True)
            tk.Label(who, text=u["name"], bg=who.cget("bg"), fg=C["label"],
                     font=F["body_semi"], anchor="w").pack(fill="x")
            sub = tk.Frame(who, bg=who.cget("bg"))
            sub.pack(fill="x")
            for path, name in ((f"/images/elem_{u['element'].lower()}.png", u["element"]),
                               (f"/images/race_{u['race'].lower()}.png", u["race"])):
                ic = self._photo(path, px(16 * self.k))
                if ic:
                    tk.Label(sub, image=ic, bg=sub.cget("bg")).pack(side="left", padx=(0, px(3)))
                Tip(sub.winfo_children()[-1], name) if ic else None
            tk.Label(sub, text=f"{u['element']} · {u['race']}" + (f" · HP {hp[i]:,}" if hp[i]
                                                                 else "")
                     + (f" · Arts +{gen[i]:g}/s" if gen.get(i) else ""),
                     bg=sub.cget("bg"), fg=C[ELEMENT_COLORS.get(u["element"], "secondary")],
                     font=F["caption"], anchor="w").pack(side="left")
            ctl = tk.Frame(top, bg=top.cget("bg"))
            ctl.pack(side="right")
            for txt, d in (("‹", -1), ("›", 1)):
                if 0 <= i + d < 4:
                    self._mini(ctl, txt, lambda d=d, i=i: self._do(m.move_unit, i, d))
            self._mini(ctl, "✕", lambda i=i: self._do(m.remove_unit, i), color="red")
            row = tk.Frame(b, bg=b.cget("bg"))
            row.pack(fill="x", pady=(px(6), 0))
            self._chip(row, "★ Leader", i == lead,
                       lambda i=i: self._do(m.set_leader, i)).pack(side="left",
                                                                    padx=(0, px(6)))
            self._chip(row, "Attacker" if i == m.s["atk"] else "Set attacker", i == m.s["atk"],
                       lambda i=i: self._do(m.set_attacker, i)).pack(side="left")
            mv = tk.Frame(b, bg=b.cget("bg"))
            mv.pack(fill="x", pady=(px(6), 0))
            for kind in u.get("moves") or []:
                if kind not in MOVE_SHORT:
                    continue
                forced = i == m.s["atk"] and (m.s["hit"] or {}).get("kind") == kind
                on = bool(slot["active"].get(kind)) or forced
                c = self._chip(mv, MOVE_SHORT[kind], on,
                               (lambda: None) if forced else
                               (lambda i=i, kind=kind: self._do(m.toggle_move, i, kind)),
                               tip=calc.HITKIND.get(kind, kind) + (
                                   " (the attacking move is always on)" if forced else ""),
                               disabled=forced)
                c.pack(side="left", padx=(0, px(4)))
            for st in calc.J(u)["list"]:
                if st["max"] <= 1:
                    continue
                self._stack_row(b, i, slot, st)
            if u.get("dream"):
                dr = tk.Frame(b, bg=b.cget("bg"))
                dr.pack(fill="x", pady=(px(6), 0))
                tk.Label(dr, text="Dream", bg=dr.cget("bg"), fg=C["secondary"],
                         font=F["caption"]).pack(side="left", padx=(0, px(6)))
                var = tk.StringVar(value=slot.get("dream") or "None")
                ios.Select(dr, values=["None"] + list(u["dream"]), variable=var, accent=True,
                           command=lambda i=i, var=var: self._do(
                               m.set_dream, i, None if var.get() == "None" else var.get()
                           )).pack(side="left")
            self._equip_rows(b, i, slot, u)
            self._details(b, i, u, gen.get(i, 0))

    def _details(self, b, i, u, aps):
        """Passives, arts gauge and the kit text of a unit (a tap to open)."""
        opened = i in self._open
        row = tk.Frame(b, bg=b.cget("bg"))
        row.pack(fill="x", pady=(px(8), 0))
        self._chip(row, "Details ▾" if opened else "Details ▸", opened,
                   lambda i=i: self._toggle_details(i)).pack(side="left")
        if not opened:
            return
        kit = self.model.data.kits.get(u["id"]) or []
        fx = [e for e in (u.get("effects") or []) if e.get("type") in
              ("arts_regen", "arts_instant", "arts_quest_start") and e.get("value") is not None]

        def section(title, lines, color=None):
            if not lines:
                return
            tk.Label(b, text=title, bg=b.cget("bg"), fg=C["secondary"], font=F["footnote_semi"],
                     anchor="w").pack(fill="x", pady=(px(8), px(2)))
            for text in lines:
                tk.Label(b, text="•  " + text, bg=b.cget("bg"), fg=color or C["label"],
                         font=F["caption"], anchor="w", justify="left",
                         wraplength=px(330)).pack(fill="x")

        gauge = [f"{calc.HITKIND.get(e.get('source'), 'Passive' if e.get('source') == 'passive' else e.get('source'))}: "
                 f"{e.get('text', '')}" for e in fx]
        head = f"Arts gauge: +{aps:g} per second with this team" if aps else             "Arts gauge: no steady gain with this team"
        tk.Label(b, text=head, bg=b.cget("bg"), fg=C["label"], font=F["footnote_semi"],
                 anchor="w").pack(fill="x", pady=(px(8), 0))
        section("Gauge effects", list(dict.fromkeys(gauge)))
        section("Passives", [t for k, t in kit if k == "passive"])
        for k, title in (("skill", "Skill"), ("arts", "Arts"), ("trueArts", "True Arts"),
                         ("superArts", "Super Arts")):
            section(title, [" ".join(t.split()) for kk, t in kit if kk == k], C["secondary"])

    def _toggle_details(self, i: int):
        (self._open.discard if i in self._open else self._open.add)(i)
        self._changed(("slots",))

    def _mini(self, parent, text, command, color="blue"):
        lbl = tk.Label(parent, text=text, bg=parent.cget("bg"), fg=C[color],
                       font=F["body_semi"], padx=px(4), cursor="hand2")
        lbl.bind("<Button-1>", lambda e: command())
        lbl.pack(side="left")

    def _stack_row(self, b, i, slot, st):
        row = tk.Frame(b, bg=b.cget("bg"))
        row.pack(fill="x", pady=(px(4), 0))
        n = calc.Y(slot, st)
        tk.Label(row, text=st["label"], bg=row.cget("bg"), fg=C["secondary"],
                 font=F["caption"]).pack(side="left", padx=(0, px(6)))
        self._mini(row, "−", lambda: self._do(self.model.set_stack, i, st["id"], max(1, n - 1)))
        tk.Label(row, text=f"{n}/{st['max']}", bg=row.cget("bg"), fg=C["label"],
                 font=F["footnote_semi"]).pack(side="left")
        self._mini(row, "+", lambda: self._do(self.model.set_stack, i, st["id"],
                                              min(st["max"], n + 1)))

    def _equip_rows(self, b, i, slot, u):
        m = self.model
        eqs = slot.get("equips") or [None] * len(u.get("slots") or [])
        for k, sl in enumerate(u.get("slots") or []):
            e = eqs[k] if k < len(eqs) else None
            q = m.data.equips.get(e["id"]) if e else None
            row = tk.Frame(b, bg=b.cget("bg"))
            row.pack(fill="x", pady=(px(5), 0))
            kind = f"{sl['star']}★ " + "/".join(t.upper() for t in sl["types"])
            if not q:
                for t in sl["types"]:
                    st = self._photo(f"/images/lbstone_{t}.png", px(20 * self.k))
                    if st:
                        tk.Label(row, image=st, bg=row.cget("bg")).pack(side="left",
                                                                        padx=(0, px(2)))
                ios.Button(row, f"+ {kind}", lambda i=i, k=k: self.pick_equip(i, k),
                           kind="plain", small=True).pack(side="left")
                continue
            ph = self._photo(f"/images/{q['img']}.png", px(26 * self.k)) if q.get("img") else None
            if ph:
                tk.Label(row, image=ph, bg=row.cget("bg")).pack(side="left", padx=(0, px(6)))
            name = tk.Label(row, text=q["name"], bg=row.cget("bg"), fg=C["blue"],
                            font=F["footnote_semi"], cursor="hand2", anchor="w")
            name.pack(side="left")
            name.bind("<Button-1>", lambda ev, i=i, k=k: self.pick_equip(i, k))
            if q.get("effects") and any(f_.get("source") != "passive" for f_ in q["effects"]):
                on = e.get("on") is not False
                self._chip(row, "on" if on else "off", on,
                           lambda i=i, k=k: self._do(m.toggle_equip, i, k)).pack(
                    side="left", padx=(px(6), 0))
            self._mini(row, "✕", lambda i=i, k=k: self._do(m.remove_equip, i, k), color="red")
            if any(f_.get("target") == "target" and f_.get("source") != "passive"
                   for f_ in q["effects"]):
                self._target_select(b, i, k, e)

    def _target_select(self, b, i, k, e):
        m = self.model
        names = {j: m.data.units[s["id"]]["name"] for j, s in enumerate(m.s["slots"]) if s}
        to = e.get("to") if e.get("to") in names else i
        row = tk.Frame(b, bg=b.cget("bg"))
        row.pack(fill="x")
        tk.Label(row, text="Target", bg=row.cget("bg"), fg=C["secondary"],
                 font=F["caption"]).pack(side="left", padx=(px(32), px(6)))
        var = tk.StringVar(value=names[to])
        ios.Select(row, values=list(names.values()), variable=var, accent=True,
                   command=lambda: self._do(m.set_equip_target, i, k, next(
                       j for j, n in names.items() if n == var.get()))).pack(side="left")

    def _do(self, fn, *args):
        fn(*args)
        self._changed(PARTS.get(getattr(fn, "__name__", ""), ALL_PARTS))

    # ------------------------------------------------------------- attack
    def _build_attack(self):
        b = self.attack_box
        self._clear(b)
        self._drop_vars("mult", "a_")
        m = self.model
        u = m.unit()
        if not u:
            self._label(b, "Add a unit to choose who attacks.", "footnote", C["secondary"],
                        anchor="w")
            return
        hits = m.hits()
        cur = m.s["hit"] or {}
        labels = {}
        for h in hits:
            lab = f"{m.hit_label(h)} — {n0(h['multiplier'])}% {h.get('element') or 'Elementless'}" \
                  f" {h['dmgType']}"
            labels[lab] = h
        custom = m.custom_equip_hit(u)
        labels["Custom equip — any multiplier"] = custom
        current_label = next((lab for lab, h in labels.items()
                              if h["kind"] == cur.get("kind") and h["idx"] == cur.get("idx")), "")
        var = tk.StringVar(value=current_label)
        row = tk.Frame(b, bg=b.cget("bg"))
        row.pack(fill="x")
        pic = self._unit_pic(u, 34)
        if pic:
            tk.Label(row, image=pic, bg=row.cget("bg")).pack(side="left", padx=(0, px(8)))
        tk.Label(row, text=u["name"], bg=row.cget("bg"), fg=C["label"],
                 font=F["body_semi"]).pack(side="left", padx=(0, px(10)))
        ios.Select(row, values=list(labels), variable=var, accent=True,
                   command=lambda: self._do(m.select_hit, labels[var.get()]["kind"],
                                            labels[var.get()]["idx"])).pack(side="left")
        row2 = tk.Frame(b, bg=b.cget("bg"))
        row2.pack(fill="x", pady=(px(8), 0))
        self._num(row2, "mult", lambda: m.s["mult"], lambda v: m.s.__setitem__("mult", v),
                  width=8, label="Multiplier %").pack(side="left", padx=(0, px(14)))
        self._icon_row(row2, "Element", [("", "–", None)] + [
            (el, el, f"/images/elem_{el.lower()}.png") for el in calc.ELEMENTS],
            m.s["hitEl"], lambda v: self._set_field(m.s, "hitEl", v))
        wrap = tk.Frame(row2, bg=row2.cget("bg"))
        wrap.pack(side="left", padx=(px(14), 0))
        tk.Label(wrap, text="Type", bg=wrap.cget("bg"), fg=C["secondary"],
                 font=F["caption"]).pack(anchor="w")
        tr = tk.Frame(wrap, bg=wrap.cget("bg"))
        tr.pack(anchor="w")
        for t in ("PHY", "MAG"):
            self._chip(tr, t, m.s["hitType"] == t,
                       lambda t=t: self._set_field(m.s, "hitType", t)).pack(side="left",
                                                                           padx=(0, px(4)))
        row3 = tk.Frame(b, bg=b.cget("bg"))
        row3.pack(fill="x", pady=(px(8), 0))
        for key, label, get, set_ in (
                ("a_unit", "Unit ATK", lambda: m.s["base"]["unit"],
                 lambda v: m.s["base"].__setitem__("unit", v)),
                ("a_tas", "Tasmon", lambda: m.s["base"]["tasmon"],
                 lambda v: m.s["base"].__setitem__("tasmon", v)),
                ("a_eq", "Equips", lambda: m.s["base"]["equip"],
                 lambda v: m.s["base"].__setitem__("equip", v)),
                ("a_cr", "Crest", lambda: m.s["base"]["crest"],
                 lambda v: m.s["base"].__setitem__("crest", v))):
            self._num(row3, key, get, set_, width=7, label=label).pack(side="left",
                                                                      padx=(0, px(8)))
        row4 = tk.Frame(b, bg=b.cget("bg"))
        row4.pack(fill="x", pady=(px(10), 0))
        tk.Label(row4, text="Crit", bg=row4.cget("bg"), fg=C["secondary"],
                 font=F["caption"]).pack(side="left", padx=(0, px(8)))
        cv = tk.StringVar(value={"auto": "Auto", "none": "Normal", "crit": "Crit",
                                 "super": "Super"}[m.s["crit"]])
        names = {"Auto": "auto", "Normal": "none", "Crit": "crit", "Super": "super"}
        ios.Segmented(row4, list(names), cv,
                      command=lambda: self._set_field(m.s, "crit", names[cv.get()])
                      ).pack(side="left")

    def _set_field(self, d: dict, key: str, value):
        """Change a plain setting; only the damage figures need redrawing (and the picker
        rows that show the setting)."""
        d[key] = value
        self._changed(("attack",) if key in ("hitEl", "hitType") else ())

    def _icon_row(self, parent, label, options, current, on_pick):
        """A row of picture buttons (element / race): one tap picks, no pop-up menu."""
        wrap = tk.Frame(parent, bg=parent.cget("bg"))
        wrap.pack(side="left", padx=(0, px(6)))
        tk.Label(wrap, text=label, bg=wrap.cget("bg"), fg=C["secondary"],
                 font=F["caption"]).pack(anchor="w")
        row = tk.Frame(wrap, bg=wrap.cget("bg"))
        row.pack(anchor="w")
        for value, name, path in options:
            on = (current or "") == value
            cell = tk.Canvas(row, width=px(30), height=px(30), bg=wrap.cget("bg"),
                             highlightthickness=0, bd=0, cursor="hand2")
            cell.pack(side="left", padx=px(1))
            if on:
                ios.rounded_rect(cell, 0, 0, px(30), px(30), px(8), C["blue"], wrap.cget("bg"))
            img = self._photo(path, px(22)) if path else None
            if img:
                cell.create_image(px(15), px(15), image=img)
            else:
                cell.create_text(px(15), px(15), text="–", fill="#FFFFFF" if on else C["secondary"],
                                 font=F["footnote_semi"])
            cell.bind("<ButtonRelease-1>", lambda e, v=value: on_pick(v))
            Tip(cell, name if name != "–" else "None")

    def _pick_button(self, parent, text, command, pic=None):
        """A 'tap to choose' control that shows the current choice with its picture."""
        row = tk.Frame(parent, bg=parent.cget("bg"), cursor="hand2")
        if pic:
            lbl = tk.Label(row, image=pic, bg=row.cget("bg"), cursor="hand2")
            lbl.pack(side="left", padx=(0, px(8)))
            lbl.bind("<Button-1>", lambda e: command())
        t = tk.Label(row, text=text + "  ▾", bg=row.cget("bg"), fg=C["blue"],
                     font=F["body_semi"], cursor="hand2", anchor="w")
        t.pack(side="left")
        t.bind("<Button-1>", lambda e: command())
        row.bind("<Button-1>", lambda e: command())
        return row

    # ------------------------------------------------------------- enemy
    def _build_enemy(self):
        b = self.enemy_box
        self._clear(b)
        self._drop_vars("e_")
        m = self.model
        en = m.s["enemy"]
        e = m.data.enemy_by_id.get(en.get("id") or "")
        row = tk.Frame(b, bg=b.cget("bg"))
        row.pack(fill="x")
        pic = self._photo(e["icon"], px(36 * self.k), px(118 * self.k)) if e and e.get("icon") \
            else None
        self._pick_button(row, f"{e['name']} — {e['stage']}" if e else "Custom enemy",
                          self.pick_enemy, pic).pack(side="left")
        if e:
            info = "  ·  ".join(x for x in (f"HP {n0(e['hp'])}" if e.get("hp") else "",
                                             f"DEF {n0(e['def'])}" if e.get("def") else "") if x)
            self._label(b, info, "caption", C["secondary"], anchor="w")
            for t in e.get("traits") or []:
                self._label(b, "• " + t["text"], "caption",
                            C["orange"] if t.get("tone") == "warn" else C["secondary"],
                            anchor="w")
        row2 = tk.Frame(b, bg=b.cget("bg"))
        row2.pack(fill="x", pady=(px(8), 0))
        self._icon_row(row2, "Element", [("", "–", None)] + [
            (el, el, f"/images/elem_{el.lower()}.png") for el in calc.ELEMENTS],
            en.get("element"), lambda v: self._set_field(en, "element", v))
        row2b = tk.Frame(b, bg=b.cget("bg"))
        row2b.pack(fill="x", pady=(px(8), 0))
        self._icon_row(row2b, "Race", [("", "–", None)] + [
            (r, r, f"/images/race_{r.lower()}.png") for r in calc.RACES],
            en.get("race"), lambda v: self._set_field(en, "race", v))
        row2c = tk.Frame(b, bg=b.cget("bg"))
        row2c.pack(fill="x", pady=(px(8), 0))
        self._num(row2c, "e_def", lambda: en["def"], lambda v: en.__setitem__("def", v),
                  width=7, label="DEF").pack(side="left", padx=(0, px(8)))
        self._num(row2c, "e_res", lambda: en["res"], lambda v: en.__setitem__("res", v),
                  width=6, label="RES %").pack(side="left", padx=(0, px(8)))
        row3 = tk.Frame(b, bg=b.cget("bg"))
        row3.pack(fill="x", pady=(px(8), 0))
        self._chip(row3, "In Break", bool(en.get("broken")),
                   lambda: self._toggle_break()).pack(side="left", padx=(0, px(8)))
        for st in (e or {}).get("while") or {}:
            on = st in (en.get("status") or [])
            self._chip(row3, STATUS_NAMES.get(st, st), on,
                       lambda st=st, on=on: self._do(self.model.toggle_status, st, not on)).pack(
                side="left", padx=(0, px(6)))

    def _toggle_break(self):
        en = self.model.s["enemy"]
        en["broken"] = not en.get("broken")
        self._changed(("enemy",))

    def pick_enemy(self):
        m = self.model
        rows = [{"key": "", "pic": None, "cells": ("Custom enemy", "set DEF, element and race "
                                                                    "yourself", ""),
                 "text": "custom enemy"}]
        for x in m.data.enemies:
            rows.append({"key": x["id"], "pic": x.get("icon"),
                         "cells": (x["name"], x["stage"], f"HP {n0(x['hp'])}" if x.get("hp")
                                   else ""),
                         "text": f"{x['name']} {x['stage']} {x.get('group', '')}".lower()})
        return self._picker("Choose an enemy", rows,
                            lambda key: self._do(m.set_enemy, key),
                            [("name", "Enemy", 220), ("stage", "Stage", 280), ("hp", "HP", 120)],
                            [])[0]

    # ------------------------------------------------------------- crest / extra
    def _crest_path(self, name):
        return self.crest_icon(name) if self.crest_icon else None

    def _build_extra(self):
        b = self.extra_box
        self._clear(b)
        self._drop_vars("x_")
        m = self.model
        c = m.data.crests.get(m.s["crest"]["id"])
        row = tk.Frame(b, bg=b.cget("bg"))
        row.pack(fill="x")
        pic = self._photo(self._crest_path(c["name"]), px(30 * self.k)) if c else None
        self._pick_button(row, c["name"] if c else "No crest", self.pick_crest, pic).pack(
            side="left")
        if c and len(c["lv"]) > 1:
            lv = tk.StringVar(value=c["lv"][m.s["crest"]["lv"]]["n"])
            ios.Select(row, values=[x["n"] for x in c["lv"]], variable=lv, accent=True,
                       command=lambda: self._do(
                           m.set_crest_level, [x["n"] for x in c["lv"]].index(lv.get())
                       )).pack(side="left", padx=(px(12), 0))
        if c:
            self._label(b, c["lv"][m.s["crest"]["lv"]].get("text", "").replace("\n", " · "),
                        "caption", C["secondary"], anchor="w")
        row2 = tk.Frame(b, bg=b.cget("bg"))
        row2.pack(fill="x", pady=(px(8), 0))
        for key, label in (("atk", "ATK UP %"), ("dmg", "DMG UP %"), ("critDmg", "CRI DMG %"),
                           ("res", "RES DOWN %"), ("ignoreDef", "Ignore DEF %"),
                           ("criRate", "CRI rate %")):
            self._num(row2, "x_" + key, lambda key=key: m.s["extra"][key],
                      lambda v, key=key: m.s["extra"].__setitem__(key, v), width=6,
                      label=label).pack(side="left", padx=(0, px(8)))

    def pick_crest(self):
        m = self.model
        rows = [{"key": 0, "pic": None, "cells": ("No crest", ""), "text": "no crest none"}]
        for c in m.data.crest_list:
            rows.append({"key": c["id"], "pic": self._crest_path(c["name"]),
                         "cells": (c["name"], c["lv"][-1].get("text", "").replace("\n", " · ")),
                         "text": (c["name"] + " " + " ".join(
                             lv.get("text", "") for lv in c["lv"])).lower()})
        return self._picker("Choose a crest", rows, lambda key: self._do(m.set_crest, key),
                            [("name", "Crest", 220), ("text", "Effect at the top level", 460)],
                            [])[0]

    # ============================================================== results
    def _results(self):
        m = self.model
        box = self.result_box
        self._clear(box)
        r = m.result()
        self._rphotos = []
        if not r:
            self._label(box, "Add a unit to start.", "footnote", C["secondary"], anchor="w")
            self._clear(self.moves_box)
            self._clear(self.mods_box)
            self.hp_label.configure(text="")
            return
        t, inp = r["result"], r["input"]
        big = tk.Label(box, text=n0(t["shown"]), bg=box.cget("bg"), fg=C["label"],
                       font=(F["large"][0], px(34), "bold"), anchor="w")
        big.pack(fill="x")
        self._animate_big(big, self._last_big, t["shown"])
        self._last_big = t["shown"]
        kind = {"none": "Normal hit", "crit": "Crit", "super": "Super Crit"}[r["hitType"]]
        bits = [kind + (" (auto)" if m.s["crit"] == "auto" else ""),
                "Break" if m.s["enemy"].get("broken") else "",
                "Strong element" if inp["elem"] > 1 else "Weak element" if inp["elem"] < 1 else "",
                (r["negated"] or {}).get("text", "")]
        hp = (m.data.enemy_by_id.get(m.s["enemy"].get("id") or "") or {}).get("hp")
        if hp and t["shown"]:
            p = t["shown"] / hp * 100
            bits.append(f"{round(p, 2 if p < 10 else 1):g}% of HP")
        self._label(box, "  ·  ".join(x for x in bits if x), "footnote", C["secondary"],
                    anchor="w")
        rates = r["rates"]
        avg = (0 < rates["criRate"] < 100) or (rates["criRate"] > 0 and 0 < rates["superCriRate"] < 100)
        self._label(box, f"CRI {round(rates['criRate'], 1):g}%  ·  Super "
                         f"{round(rates['superCriRate'], 1):g}%"
                         + (f"  ·  average {short(r['expected'])}" if avg else ""),
                    "caption", C["secondary"], anchor="w")
        grid = tk.Frame(box, bg=box.cget("bg"))
        grid.pack(fill="x", pady=(px(8), 0))
        grid.grid_columnconfigure(1, weight=1)
        rows = [
            ("ATK", f"{n0(inp['atkBase'])} × (1 + {pct(inp['atkUp'])})", n0(t["atk"])),
            ("ATK curve", "700·ATK / (ATK + 3500)", f"{t['atkCurve']:,.2f}"),
            ("Multiplier", n0(inp["multiplier"]) + "%" if inp["multiplier"] == r["baseMultiplier"]
             else f"{n0(r['baseMultiplier'])}% → {n0(inp['multiplier'])}%",
             times(inp["multiplier"] / 100)),
            ("Element", f"{m.s['hitEl']} → {m.s['enemy']['element']}" if m.s["hitEl"]
             and m.s["enemy"]["element"] else "neutral", times(inp["elem"])),
            ("Break", "in Break" if m.s["enemy"].get("broken") else "not broken",
             times(t["breakF"])),
            ("Crit", kind, times(t["critF"])),
            ("DMG UP", signed(inp["dmgUp"]) + (f", CRI DMG {signed(inp['critDmgUp'])}"
                                                if r["hitType"] != "none" and inp["critDmgUp"]
                                                else ""), times(t["dmgF"])),
            ("RES", f"{signed(inp['resDown'])} down" + (f", enemy {round(inp['enemyRes'], 1):g}%"
                                                         if inp["enemyRes"] else ""),
             times(t["resF"])),
            ("DEF", f"{n0(t['effDef'])} effective DEF" if r["hitType"] == "none"
             else "ignored by crit", times(t["mitigation"])),
        ]
        if r["negated"]:
            rows.append(("Enemy", r["negated"].get("text", ""), "×0"))
        rows.append(("On screen", f"dealt {n0(t['dealt'])}", n0(t["shown"])))
        for n, (a, bb, c) in enumerate(rows):
            last = n == len(rows) - 1
            f_ = F["footnote_semi"] if last else F["footnote"]
            tk.Label(grid, text=a, bg=box.cget("bg"), fg=C["label"], font=f_, anchor="w"
                     ).grid(row=n, column=0, sticky="w", padx=(0, px(10)))
            tk.Label(grid, text=bb, bg=box.cget("bg"), fg=C["secondary"], font=F["caption"],
                     anchor="w").grid(row=n, column=1, sticky="w")
            tk.Label(grid, text=c, bg=box.cget("bg"), fg=C["label"], font=f_, anchor="e"
                     ).grid(row=n, column=2, sticky="e")
        self._moves_table()
        self._mods_list(r)
        hp_list = m.team_hp()
        self.hp_label.configure(text="Team HP: " + "  ·  ".join(
            f"{m.data.units[s['id']]['name']} {hp_list[i]:,}" for i, s in enumerate(m.s["slots"])
            if s and hp_list[i]))

    def _moves_table(self):
        b = self.moves_box
        self._clear(b)
        m = self.model
        rows = m.all_moves()
        top = max([x["shown"] for x in rows] + [1])
        for x in rows:
            h = x["hit"]
            on = (m.s["hit"] or {}).get("kind") == h["kind"] and (m.s["hit"] or {}).get(
                "idx") == h["idx"]
            row = tk.Frame(b, bg=b.cget("bg"), cursor="hand2")
            row.pack(fill="x", pady=px(1))
            eq = m.data.equips.get(h["idx"]) if h["kind"] == "equip" and h["idx"] else None
            ph = self._photo(f"/images/{eq['img']}.png", px(20 * self.k)) if eq and eq.get(
                "img") else None
            if ph:
                tk.Label(row, image=ph, bg=b.cget("bg")).pack(side="left", padx=(0, px(4)))
            name = m.hit_label(h) + (f"  {'S.CRIT' if x['type'] == 'super' else 'CRIT'}"
                                     if x["type"] != "none" else "")
            lab = tk.Label(row, text=name, bg=b.cget("bg"),
                           fg=C["blue"] if on else C["label"],
                           font=F["footnote_semi" if on else "footnote"], anchor="w",
                           width=20 if ph else 22)
            lab.pack(side="left")
            bar = tk.Canvas(row, height=px(8), bg=b.cget("bg"), highlightthickness=0, bd=0)
            bar.pack(side="left", fill="x", expand=True, padx=px(6))
            bar.bind("<Configure>", lambda e, bar=bar, v=x["shown"]: (
                bar.delete("all"), bar.create_rectangle(
                    0, 0, max(2, e.width * v / top), px(8), fill=C["blue"], width=0)))
            val = tk.Label(row, text=short(x["shown"]), bg=b.cget("bg"), fg=C["label"],
                           font=F["footnote_semi"], anchor="e", width=9)
            val.pack(side="left")
            for w in (row, lab, bar, val):
                w.bind("<Button-1>", lambda e, h=h: self._do(m.select_hit, h["kind"], h["idx"]))

    def _mods_list(self, r):
        b = self.mods_box
        self._clear(b)
        m = self.model
        rel = [x for x in r["mods"] if x["relevant"]]
        na = [x for x in r["mods"] if not x["relevant"]]
        order = {"applied": 0, "overridden": 1, "off": 2}
        shown = False
        for term, name in TERM_NAMES.items():
            items = sorted([x for x in rel if x["term"] == term],
                           key=lambda x: (order[r["status"][x["key"]]], -x["value"]))
            extra = m.s["extra"].get(EXTRA_KEY.get(term, ""), 0) if term in EXTRA_KEY else 0
            if not items and not extra:
                continue
            shown = True
            val = (r["rates"][term] if term in ("criRate", "superCriRate")
                   else r["terms"][term] + extra)
            head = tk.Frame(b, bg=b.cget("bg"))
            head.pack(fill="x", pady=(px(8), px(2)))
            tk.Label(head, text=name, bg=head.cget("bg"), fg=C["secondary"],
                     font=F["footnote_semi"]).pack(side="left")
            tk.Label(head, text=fmt_term(term, val), bg=head.cget("bg"), fg=C["label"],
                     font=F["footnote_semi"]).pack(side="right")
            for x in items:
                self._mod_row(b, r, x)
            if extra:
                self._label(b, f"✎ Extra {pct(extra)}", "caption", C["secondary"], anchor="w")
        if not shown:
            self._label(b, "No damage modifiers from this team for this hit.", "footnote",
                        C["secondary"], anchor="w")
        if na:
            det = tk.Label(b, text=f"{len(na)} not for this hit ▸", bg=b.cget("bg"),
                           fg=C["blue"], font=F["footnote"], cursor="hand2", anchor="w")
            det.pack(fill="x", pady=(px(8), 0))
            body = tk.Frame(b, bg=b.cget("bg"))

            def toggle(_e=None):
                if body.winfo_manager():
                    body.pack_forget()
                    det.configure(text=f"{len(na)} not for this hit ▸")
                else:
                    body.pack(fill="x")
                    det.configure(text=f"{len(na)} not for this hit ▾")

            det.bind("<Button-1>", toggle)
            for x in na:
                tk.Label(body, text=f"{x['label']} {pct(x['value'])}  —  {x['unit']} · "
                                    f"{x['reason']}", bg=b.cget("bg"), fg=C["secondary"],
                         font=F["caption"], anchor="w", justify="left", wraplength=px(380)
                         ).pack(fill="x")

    def _mod_row(self, parent, r, x):
        st = r["status"][x["key"]]
        val = r["effValue"].get(x["key"], x["value"])
        row = tk.Frame(parent, bg=parent.cget("bg"))
        row.pack(fill="x", pady=px(1))
        cb = Check(row, st in ("applied", "overridden"),
                   lambda on: self._override(x["key"], on))
        cb.pack(side="left", anchor="n", padx=(0, px(8)), pady=(px(2), 0))
        src_pic = None
        eq = self.model.data.equips.get(x.get("equipId")) if x.get("equipId") else None
        if eq and eq.get("img"):
            src_pic = self._photo(f"/images/{eq['img']}.png", px(22 * self.k))
        elif x.get("crest"):
            src_pic = self._photo(self._crest_path(x["crest"]), px(22 * self.k))
        else:
            slot = self.model.s["slots"][x["unitIdx"]] if x.get("unitIdx") is not None else None
            u = self.model.data.units.get(slot["id"]) if slot else None
            src_pic = self._unit_pic(u, 22) if u else None
        if src_pic:
            tk.Label(row, image=src_pic, bg=row.cget("bg")).pack(side="left", anchor="n",
                                                                 padx=(0, px(6)))
        col = tk.Frame(row, bg=row.cget("bg"))
        col.pack(side="left", fill="x", expand=True)
        dim = C["secondary"] if st != "applied" else C["label"]
        top = tk.Frame(col, bg=row.cget("bg"))
        top.pack(fill="x")
        tk.Label(top, text=x["label"], bg=top.cget("bg"), fg=dim, font=F["footnote_semi"],
                 anchor="w").pack(side="left")
        tk.Label(top, text=fmt_term(x["term"], val), bg=top.cget("bg"), fg=dim,
                 font=F["footnote_semi"]).pack(side="right")
        src = (x["equip"] or (f"{x['crest']} (Crest)" if x.get("crest") else None)
               or SOURCE_NAMES.get(x["source"]) or calc.HITKIND.get(x["source"]) or x["source"])
        notes = []
        if x.get("formula"):
            notes.append(x["formula"])
        if x.get("count") is not None:
            notes.append(f"×{x['count']} in team")
        if st == "overridden":
            notes.append("weaker, doesn't stack")
        c = x["cond"]
        if c["state"] == "unmet":
            notes.append(f"{c['label']}: not met")
        elif c["state"] == "unknown":
            notes.append(f"needs {c['label']}")
        elif c["state"] == "assumed":
            notes.append(f"assumes {c['label']}")
        elif c["state"] == "met" and c["label"]:
            notes.append(c["label"])
        tk.Label(col, text=" · ".join([f"{x['unit']} · {src}"] + notes), bg=row.cget("bg"),
                 fg=C["secondary"], font=F["caption"], anchor="w", justify="left",
                 wraplength=px(360)).pack(fill="x")
        stk = x.get("stack")
        if stk and stk["max"] > 1 and self.model.s["slots"][x["unitIdx"]]:
            sr = tk.Frame(col, bg=row.cget("bg"))
            sr.pack(fill="x")
            tk.Label(sr, text=stk["label"], bg=sr.cget("bg"), fg=C["secondary"],
                     font=F["caption"]).pack(side="left", padx=(0, px(6)))
            n = stk["n"]
            i = x["unitIdx"]
            self._mini(sr, "−", lambda: self._do(self.model.set_stack, i, stk["id"],
                                                 max(1, n - 1)))
            tk.Label(sr, text=f"{n}/{stk['max']}", bg=sr.cget("bg"), fg=C["label"],
                     font=F["caption"]).pack(side="left")
            self._mini(sr, "+", lambda: self._do(self.model.set_stack, i, stk["id"],
                                                 min(stk["max"], n + 1)))

    def _override(self, key, on):
        self.model.set_override(key, on)
        self.refresh_results()

    # ============================================================== pickers
    def pick_unit(self, slot_index: int):
        m = self.model
        mine = {n.lower() for n in self.my_units()}
        rows = []
        for u in m.data.unit_list:
            rows.append({"key": u["id"], "pic": f"/images/{u['thumb']}.png" if u.get("thumb")
                         else None,
                         "cells": (u["name"], u["element"], u["race"], u.get("rarity", "")),
                         "text": " ".join([u["name"], u.get("fullName", ""),
                                           " ".join(u.get("aliases") or [])]).lower(),
                         "el": u["element"], "mine": u["name"].lower() in mine})
        top, draw, _ = self._picker(
            "Add a unit", rows, lambda uid: self._do(m.add_unit, slot_index, uid),
            [("name", "Unit", 280), ("element", "Element", 90), ("race", "Race", 90),
             ("rarity", "Rarity", 80)],
            [("el", ["All elements"] + calc.ELEMENTS, "All elements",
              lambda r, v: v == "All elements" or r["el"] == v),
             ("mine", ["All units", "My units"], "All units",
              lambda r, v: v == "All units" or r["mine"])])
        return top

    def pick_equip(self, i: int, k: int):
        m = self.model
        u = m.unit(i)
        sl = u["slots"][k]
        rows = []
        for q in m.data.equips.values():
            if q["type"] not in sl["types"] or q["star"] > sl["star"]:
                continue
            skill = " ".join((q.get("skill") or "").split())
            rows.append({"key": q["id"], "pic": f"/images/{q['img']}.png" if q.get("img")
                         else None, "cells": (q["name"], f"{q['star']}★", skill),
                         "text": (q["name"] + " " + skill).lower(), "star": q["star"],
                         "tw": q["id"] == u.get("tw")})
        rows.sort(key=lambda r: (not r["tw"], -r["star"], r["cells"][0].lower()))
        return self._picker(
            f"{u['name']} · {sl['star']}★ " + "/".join(t.upper() for t in sl["types"]) + " slot",
            rows, lambda eid: self._do(m.set_equip, i, k, eid),
            [("name", "Equip", 260), ("star", "★", 50), ("skill", "Skill", 400)], [])[0]

    def _picker(self, title, rows, on_pick, columns, filters):
        """_picker with row filters given as (name, values, default, fn(row, value))."""
        top = tk.Toplevel(self)
        top.title(title)
        top.configure(bg=C["bg"])
        top.transient(self.winfo_toplevel())
        top.geometry(f"{px(780)}x{px(640)}")
        q = tk.StringVar()
        bar = tk.Frame(top, bg=C["bg"])
        bar.pack(fill="x", padx=px(14), pady=(px(12), px(6)))
        fld = ios.Field(bar, q, width=30)
        fld.pack(side="left")
        fvars = []
        for name, values, default, fn in filters:
            v = tk.StringVar(value=default)
            fvars.append((v, fn))
            ios.Select(bar, values=values, variable=v, accent=True,
                       command=lambda: draw()).pack(side="left", padx=(px(12), 0))
        note = tk.Label(bar, bg=C["bg"], fg=C["secondary"], font=F["caption"])
        note.pack(side="right")
        wrap = ios.Card(top, pad=6, stretch=True)
        wrap.pack(fill="both", expand=True, padx=px(14), pady=(0, px(12)))
        tree = ttk.Treeview(wrap.body, show="tree headings", style="GSC.IOS.Treeview",
                            columns=[c[0] for c in columns], selectmode="browse")
        sb = ttk.Scrollbar(wrap.body, orient="vertical", command=tree.yview,
                           style="IOS.Vertical.TScrollbar")
        tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        tree.pack(side="left", fill="both", expand=True)
        tree.heading("#0", text="")
        tree.column("#0", width=px(52), stretch=False)
        for j, (key, head, w) in enumerate(columns):
            tree.heading(key, text=head)
            tree.column(key, width=px(w), anchor="w", stretch=j == len(columns) - 1)
        shown: dict[str, dict] = {}
        photos: list = []

        def draw(*_):
            tree.delete(*tree.get_children())
            shown.clear()
            photos.clear()
            text = q.get().strip().lower()
            n = total = 0
            for r in rows:
                if text and text not in r["text"]:
                    continue
                if any(not fn(r, v.get()) for v, fn in fvars):
                    continue
                total += 1
                if n >= MAX_PICK_ROWS:
                    continue
                n += 1
                pic = self._photo(r["pic"], px(34)) if r.get("pic") else None
                if pic:
                    photos.append(pic)
                iid = f"p{n}"
                shown[iid] = r
                tree.insert("", "end", iid=iid, values=r["cells"], **({"image": pic} if pic
                                                                      else {}))
            note.configure(text=f"{n} of {total}" if total > n else f"{total}")
            kids = tree.get_children()
            if kids:
                tree.selection_set(kids[0])

        def choose(_e=None):
            sel = tree.selection()
            if sel:
                key = shown[sel[0]]["key"]
                top.destroy()
                on_pick(key)

        q.trace_add("write", draw)
        tree.bind("<Double-Button-1>", choose)
        tree.bind("<Return>", choose)
        fld.entry.bind("<Return>", choose)
        fld.entry.bind("<Down>", lambda e: tree.focus_set())
        top.bind("<Escape>", lambda e: top.destroy())
        top.draw = draw
        top.query = q
        top.tree = tree
        top.choose = choose
        draw()
        fld.entry.focus_set()
        return top, draw, fvars

    # ============================================================== actions
    def copy_link(self):
        link = self.model.to_link()
        self.clipboard_clear()
        self.clipboard_append(link)
        self._flash("Link copied: it opens this exact setup on gscompanion.com", "ok")

    def open_site(self):
        self._open_url(self.model.to_link() if self.model.unit() else
                       "https://gscompanion.com/damage-calc/")
        self._flash("Opened the damage calculator with this setup", "info")

    def load_link(self):
        text = ios.ask_string(self.winfo_toplevel(), "Load link",
                              "Paste a damage calculator or team builder link from "
                              "gscompanion.com:")
        if not text:
            return
        if self.model.load_link(text):
            self._changed()
            self._flash("Setup loaded", "ok")
        else:
            ios.alert(self.winfo_toplevel(), "That isn't a calculator link.", "Load link")

    def clear(self):
        self.model.s = fresh_state()
        self._changed()

    def set_scale(self, k: float):
        self.k = k
        if self.data.available and hasattr(self, "slots_box"):
            self.refresh()
