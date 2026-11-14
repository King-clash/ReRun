"""Run the GS Companion browser in its own window:  py -m gsc_app  (from Rerun's folder).

Uses Rerun's look and theme setting (config.yaml "appearance") but none of Rerun's
runtime: no emulator, no scripts. It remembers its window, view, text size, starred
units, farm plan and compared crests in a small settings file:
  from source:  data/gscompanion/companion_settings.json
  as the exe:   "GS Companion settings.json" next to the exe"""
from __future__ import annotations

import sys
import tkinter as tk
import types
from pathlib import Path

if getattr(sys, "frozen", False):
    # GS Companion.exe: data is bundled inside; a data/gscompanion/ folder next to the
    # exe (e.g. refreshed data) wins over the bundled copy.
    EXE_DIR = Path(sys.executable).parent
    ROOT = EXE_DIR if (EXE_DIR / "data" / "gscompanion" / "crests.json").exists() \
        else Path(sys._MEIPASS)
    CONFIG = EXE_DIR / "config.yaml"
    SETTINGS = EXE_DIR / "GS Companion settings.json"
    RERUN_DIR = EXE_DIR  # change it in the app: Units > "Rerun folder…"
    DATA_OUT = EXE_DIR / "data" / "gscompanion"  # "Update data" writes here
    # rerun.crest_stats imports OpenCV/numpy for screenshot saving, which this app never
    # uses; the exe leaves them out (≈ 70 MB), so give those imports empty stand-ins.
    for _m in ("cv2", "numpy"):
        sys.modules.setdefault(_m, types.ModuleType(_m))
else:
    ROOT = Path(__file__).resolve().parents[1]
    CONFIG = ROOT / "config.yaml"
    SETTINGS = ROOT / "data" / "gscompanion" / "companion_settings.json"
    RERUN_DIR = ROOT
    DATA_OUT = None  # data/gscompanion/ itself
    sys.path.insert(0, str(ROOT))

from PIL import ImageTk  # noqa: E402

from rerun import ios  # noqa: E402
from rerun.appicon import make_icon  # noqa: E402
from rerun.ios import px  # noqa: E402

from gsc_app.page import GSCompanionPage  # noqa: E402


def appearance() -> str:
    try:
        import yaml
        cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8")) or {}
        return str(cfg.get("appearance", "auto"))
    except Exception:  # noqa: BLE001 - no/old config: follow Windows
        return "auto"


def on_screen(win: tk.Tk, geometry: str) -> bool:
    """A saved 'WxH+X+Y' is used only if most of it is on the (virtual) screen."""
    try:
        size, x, y = geometry.replace("+-", "+~").split("+")
        w, h = (int(v) for v in size.split("x"))
        x, y = int(x.replace("~", "-")), int(y.replace("~", "-"))
    except ValueError:
        return False
    sw, sh = win.winfo_vrootwidth() or win.winfo_screenwidth(), \
        win.winfo_vrootheight() or win.winfo_screenheight()
    return w >= 600 and h >= 400 and -w // 2 < x < sw - 100 and 0 <= y < sh - 100


def main() -> None:
    ios.enable_dpi_awareness()
    win = tk.Tk()
    ios.init(win, appearance())
    win.title("GS Companion")
    win.minsize(px(980), px(620))
    icon = ImageTk.PhotoImage(make_icon(64))
    win.iconphoto(True, icon)
    page = GSCompanionPage(win, ROOT, settings_path=SETTINGS, rerun_dir=RERUN_DIR,
                           data_out=DATA_OUT)
    geo = page.s["geometry"]
    if isinstance(geo, dict) and geo.get("zoomed"):
        win.geometry(f"{px(1320)}x{px(860)}")
        win.state("zoomed")
    elif isinstance(geo, dict) and geo.get("geometry") and on_screen(win, geo["geometry"]):
        win.geometry(geo["geometry"])
    else:
        w = min(px(1320), win.winfo_screenwidth() - px(60))
        h = min(px(860), win.winfo_screenheight() - px(80))
        win.geometry(f"{w}x{h}")
    page.pack(fill="both", expand=True)
    toast = ios.Toast(page)
    page._flash_cb = toast.show

    def close():
        zoomed = win.state() == "zoomed"
        if zoomed:
            page.s["geometry"] = {"zoomed": True}
        else:
            page.s["geometry"] = {"geometry": win.geometry()}
        page.save_state()
        win.destroy()

    win.protocol("WM_DELETE_WINDOW", close)
    win.after(10, lambda: ios.style_window(win))
    win.mainloop()


if __name__ == "__main__":
    main()
