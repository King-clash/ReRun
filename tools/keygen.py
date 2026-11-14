"""Rerun Key Generator: makes the keys Rerun asks for at sign-in (rerun/license.py).

    py tools/keygen.py            the generator window
    py tools/keygen.py --init     create your signing key (once; prints the public key)

Choose a time frame (presets, a custom length, or "until a date"), optionally lock the key
to one PC (the PC ID shown on Rerun's sign-in screen), add a note for your records, and
press Generate. Every key made is listed (and saved in issued_keys.csv).

Your signing key lives only on this PC: %LOCALAPPDATA%\\Rerun Keygen\\signing_key.txt.
Anyone with that file can make Rerun keys - keep it private and keep a backup ("Back up
signing key…"): without it no new keys can be made for the Rerun builds that trust it.
"""
from __future__ import annotations

import csv
import os
import sys
import time
from calendar import monthrange
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if getattr(sys, "frozen", False):
    ROOT = Path(getattr(sys, "_MEIPASS", ROOT))
sys.path.insert(0, str(ROOT))

from rerun import ed25519  # noqa: E402
from rerun.license import (ANY_PC, PUBLIC_KEY, format_pc, make_key, parse_key,  # noqa: E402
                           parse_pc)

HOME = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "Rerun Keygen"
SECRET_FILE = "signing_key.txt"
LOG_FILE = "issued_keys.csv"
LOG_FIELDS = ["issued", "expires", "time_frame", "pc", "note", "key_id", "key"]

PRESETS = {"1 hour": ("hours", 1), "1 day": ("days", 1), "3 days": ("days", 3),
           "7 days": ("days", 7), "14 days": ("days", 14), "30 days": ("days", 30),
           "90 days": ("days", 90), "180 days": ("days", 180), "1 year": ("years", 1),
           "Lifetime": ("lifetime", 0)}
CUSTOM = "Custom length"
UNTIL = "Until a date"
FRAMES = list(PRESETS) + [CUSTOM, UNTIL]
UNITS = ["minutes", "hours", "days", "weeks", "months", "years"]


# ---------------------------------------------------------------- time frames
def add_months(dt: datetime, n: int) -> datetime:
    m = dt.month - 1 + n
    y, m = dt.year + m // 12, m % 12 + 1
    return dt.replace(year=y, month=m, day=min(dt.day, monthrange(y, m)[1]))


def expiry(unit: str, amount: float, start: float | None = None) -> float:
    """Unix time a key made now ends (0 = lifetime)."""
    if unit == "lifetime":
        return 0
    amount = float(amount)
    if amount <= 0:
        raise ValueError("The length must be more than 0")
    t0 = datetime.fromtimestamp(time.time() if start is None else start)
    if unit in ("months", "years"):
        if amount != int(amount):
            raise ValueError("Months and years must be whole numbers")
        end = add_months(t0, int(amount) * (12 if unit == "years" else 1))
    else:
        end = t0 + timedelta(**{unit: amount})
    if end.year > 2105:
        raise ValueError("That is too far ahead - choose Lifetime instead")
    return end.timestamp()


def parse_until(text: str, now: float | None = None) -> float:
    """'2026-12-31' or '2026-12-31 18:00' (local time) -> unix time, must be in the future."""
    text = (text or "").strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(text, fmt)
            break
        except ValueError:
            continue
    else:
        raise ValueError("Write the date as YYYY-MM-DD or YYYY-MM-DD HH:MM, e.g. 2026-12-31 18:00")
    if fmt == "%Y-%m-%d":
        dt = dt.replace(hour=23, minute=59)
    t = dt.timestamp()
    if t <= (time.time() if now is None else now):
        raise ValueError("That date has already passed")
    if dt.year > 2105:
        raise ValueError("That is too far ahead - choose Lifetime instead")
    return t


def describe_end(t: float) -> str:
    return "never (lifetime)" if t == 0 else time.strftime("%a %d %b %Y, %H:%M", time.localtime(t))


# ---------------------------------------------------------------- signing key + log
class Keygen:
    def __init__(self, home: Path = HOME):
        self.home = Path(home)

    @property
    def secret_path(self) -> Path:
        return self.home / SECRET_FILE

    def secret(self) -> bytes | None:
        try:
            raw = bytes.fromhex(self.secret_path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            return None
        return raw if len(raw) == 32 else None

    def init(self) -> bytes:
        """Create the signing key once. Returns the public key. Never overwrites."""
        if self.secret_path.exists():
            raise FileExistsError(f"A signing key already exists: {self.secret_path}")
        self.home.mkdir(parents=True, exist_ok=True)
        seed = os.urandom(32)
        self.secret_path.write_text(seed.hex(), encoding="utf-8")
        return ed25519.public_key(seed)

    def import_secret(self, src: Path) -> None:
        raw = bytes.fromhex(Path(src).read_text(encoding="utf-8").strip())
        if len(raw) != 32:
            raise ValueError("That file is not a Rerun signing key")
        if self.secret_path.exists() and self.secret() != raw:
            raise FileExistsError("A different signing key is already here - remove it first")
        self.home.mkdir(parents=True, exist_ok=True)
        self.secret_path.write_text(raw.hex(), encoding="utf-8")

    def matches_rerun(self) -> bool:
        """Do keys made here open the Rerun build this generator came with?"""
        s = self.secret()
        return bool(s) and ed25519.public_key(s) == PUBLIC_KEY

    def issue(self, expires: float, pc: bytes = ANY_PC, note: str = "",
              frame: str = "", now: float | None = None) -> str:
        s = self.secret()
        if s is None:
            raise RuntimeError("No signing key on this PC")
        now = time.time() if now is None else now
        key = make_key(s, expires, pc, issued=now)
        lic = parse_key(key, ed25519.public_key(s))   # self-check before handing it out
        self.home.mkdir(parents=True, exist_ok=True)
        log = self.home / LOG_FILE
        new = not log.exists()
        with log.open("a", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, LOG_FIELDS)
            if new:
                w.writeheader()
            w.writerow({"issued": time.strftime("%Y-%m-%d %H:%M", time.localtime(now)),
                        "expires": "lifetime" if expires == 0 else
                        time.strftime("%Y-%m-%d %H:%M", time.localtime(expires)),
                        "time_frame": frame, "pc": "any" if pc == ANY_PC else format_pc(pc),
                        "note": note, "key_id": lic.key_id, "key": key})
        return key

    def issued(self) -> list[dict]:
        try:
            with (self.home / LOG_FILE).open(newline="", encoding="utf-8") as fh:
                return list(csv.DictReader(fh))[::-1]
        except OSError:
            return []


# ---------------------------------------------------------------- window
def run_gui(home: Path = HOME) -> None:
    import tkinter as tk
    from tkinter import filedialog, ttk

    from PIL import ImageTk

    from rerun import ios
    from rerun.appicon import make_icon
    from rerun.ios import C, F, px

    kg = Keygen(home)
    ios.enable_dpi_awareness()
    win = tk.Tk()
    ios.init(win, "auto")
    win.title("Rerun Key Generator")
    win.configure(bg=C["bg"])
    icon = ImageTk.PhotoImage(make_icon(64))
    win.iconphoto(True, icon)
    win.geometry(f"{px(760)}x{px(820)}")
    win.minsize(px(640), px(700))
    toast = ios.Toast(win)

    hdr = ios.page_header(win, "Key Generator")
    body = tk.Frame(win, bg=C["bg"])
    body.pack(fill="both", expand=True, padx=px(20), pady=(0, px(16)))

    if kg.secret() is None:
        tk.Label(body, bg=C["bg"], fg=C["secondary"], font=F["body"], justify="center",
                 text=f"No signing key on this PC.\n\nExpected: {kg.secret_path}\n\n"
                      "Import your backup of signing_key.txt to make keys here.").pack(pady=px(40))

        def do_import():
            p = filedialog.askopenfilename(parent=win, title="Your Rerun signing key",
                                           filetypes=[("Signing key", "*.txt"), ("All files", "*.*")])
            if not p:
                return
            try:
                kg.import_secret(Path(p))
            except (OSError, ValueError, FileExistsError) as e:
                return ios.alert(win, str(e), "Import")
            ios.alert(win, "Signing key imported. The generator restarts now.", "Import")
            win.destroy()
            run_gui(home)
        ios.Button(body, "Import signing key…", do_import).pack()
        win.mainloop()
        return

    # ---- time frame
    g = ios.Group(body, "Time frame")
    g.pack(fill="x")
    frame = tk.StringVar(value="30 days")
    ios.Select(g.row("Key works for"), values=FRAMES, variable=frame, accent=True,
               command=lambda: update()).pack()
    amount, unit, until = tk.StringVar(value="2"), tk.StringVar(value="weeks"), tk.StringVar()
    custom_row = g.row("Custom length", "How long, counted from when you press Generate")
    ios.Field(custom_row, amount, width=6, justify="right").pack(side="left")
    ios.Select(custom_row, values=UNITS, variable=unit, accent=True,
               command=lambda: update()).pack(side="left", padx=(px(10), 0))
    until_row = g.row("Until a date", "YYYY-MM-DD or YYYY-MM-DD HH:MM (your local time)")
    ios.Field(until_row, until, width=18).pack()
    for v in (amount, until):
        v.trace_add("write", lambda *a: update())
    ends = tk.Label(body, text="", bg=C["bg"], fg=C["secondary"], font=F["footnote"], anchor="w")
    ends.pack(fill="x", padx=px(16), pady=(px(4), 0))

    # ---- who it's for
    g2 = ios.Group(body, "Who it's for")
    g2.pack(fill="x", pady=(px(10), 0))
    lock = tk.BooleanVar(value=False)
    pc_txt, note = tk.StringVar(), tk.StringVar()
    ios.Switch(g2.row("Lock to one PC", "Only works on the PC whose ID you enter (shown on "
                                         "Rerun's sign-in screen)"), lock,
               command=lambda: update()).pack()
    ios.Field(g2.row("PC ID"), pc_txt, width=22).pack()
    ios.Field(g2.row("Note", "For your records, e.g. who the key is for"), note, width=26).pack()

    # ---- generate
    bar = tk.Frame(body, bg=C["bg"])
    bar.pack(fill="x", pady=(px(14), px(6)))
    gen_btn = ios.Button(bar, "Generate Key", lambda: generate(), icon="add")
    gen_btn.pack(side="left")
    ios.Button(bar, "Copy", lambda: copy(out.get("1.0", "end").strip()), kind="tinted",
               icon="check").pack(side="left", padx=(px(10), 0))
    card = ios.Card(body, pad=8, radius=10, color=C["field"])
    card.pack(fill="x")
    out = tk.Text(card.body, height=4, wrap="char", bd=0, relief="flat", bg=C["field"],
                  fg=C["label"], font=F["mono"], selectbackground=C["blue"])
    out.pack(fill="x")

    # ---- issued keys
    h = ios.section_header(body, "Keys you made (double-click to copy)", padx=px(4))
    lc = ios.Card(body, pad=6, stretch=True)
    lc.pack(fill="both", expand=True)
    cols = ("issued", "expires", "time_frame", "pc", "note")
    tree = ttk.Treeview(lc.body, columns=cols, show="headings", style="IOS.Treeview", height=6)
    for c, t, w in zip(cols, ("Made", "Ends", "Time frame", "PC", "Note"), (120, 120, 100, 150, 200)):
        tree.heading(c, text=t)
        tree.column(c, width=px(w), stretch=(c == "note"), anchor="w" if c == "note" else "center")
    tree.pack(fill="both", expand=True)
    rows: dict[str, str] = {}

    def refresh_list():
        tree.delete(*tree.get_children())
        rows.clear()
        for i, r in enumerate(kg.issued()):
            iid = f"k{i}"
            rows[iid] = r.get("key", "")
            tree.insert("", "end", iid=iid, values=[r.get(c, "") for c in cols])

    tree.bind("<Double-1>", lambda e: copy(rows.get(tree.focus(), "")))

    foot = tk.Frame(win, bg=C["bg"])
    foot.pack(side="bottom", fill="x", padx=px(20), pady=(0, px(12)), before=body)
    warn = "" if kg.matches_rerun() else "  ·  WARNING: this signing key does not match this Rerun build"
    tk.Label(foot, text=f"Signing key: {kg.secret_path}  (keep it private){warn}", bg=C["bg"],
             fg=C["red"] if warn else C["secondary"], font=F["caption"], anchor="w").pack(side="left")

    def backup():
        p = filedialog.asksaveasfilename(parent=win, title="Back up signing key",
                                         initialfile="rerun_signing_key.txt",
                                         defaultextension=".txt", filetypes=[("Text", "*.txt")])
        if p:
            Path(p).write_text(kg.secret_path.read_text(encoding="utf-8"), encoding="utf-8")
            toast.show("Signing key backed up - keep that file somewhere private", "ok")
    ios.Button(hdr, "Back up signing key…", backup, kind="plain", small=True).pack(side="right")

    def copy(text: str):
        if text:
            win.clipboard_clear()
            win.clipboard_append(text)
            toast.show("Key copied", "ok")

    def current_expiry() -> float:
        f = frame.get()
        if f == CUSTOM:
            return expiry(unit.get(), amount.get().strip() or "0")
        if f == UNTIL:
            return parse_until(until.get())
        u, n = PRESETS[f]
        return expiry(u, n)

    def update():
        """'Ends: …' for the chosen time frame (custom fields are used only when chosen)."""
        f = frame.get()
        try:
            ends.configure(text="Ends: " + describe_end(current_expiry())
                           + ("" if f == "Lifetime" else "  (if made now)"), fg=C["secondary"])
        except ValueError as e:
            ends.configure(text=str(e), fg=C["red"])

    def generate():
        try:
            exp = current_expiry()
            pc = parse_pc(pc_txt.get()) if lock.get() else ANY_PC
        except ValueError as e:
            return ios.alert(win, str(e), "Generate Key")
        f = frame.get()
        label = f"{amount.get()} {unit.get()}" if f == CUSTOM else (
            f"until {until.get()}" if f == UNTIL else f)
        key = kg.issue(exp, pc, note.get().strip(), label)
        out.delete("1.0", "end")
        out.insert("1.0", key)
        copy(key)
        refresh_list()

    update()
    refresh_list()
    win.after(10, lambda: ios.style_window(win))
    win.mainloop()


def main(argv: list[str]) -> int:
    kg = Keygen()
    if "--init" in argv:
        try:
            pub = kg.init()
        except FileExistsError as e:
            print(e)
            return 1
        print(f"Signing key created: {kg.secret_path}")
        print(f"Public key (goes into rerun/license.py PUBLIC_KEY): {pub.hex()}")
        return 0
    run_gui()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
