"""Build Rerun.exe:  python build.py  [--out FOLDER]

Produces dist/Rerun/Rerun.exe (or FOLDER/Rerun.exe, e.g. while that copy is running) -
one self-contained file (a one-file build has
no deep internal folders, so it also builds inside long paths that Windows'
260-character limit would otherwise break). Your templates, custom routines,
README and config are copied next to it, so the .exe works exactly like
`python main.py`."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist" / "Rerun"


def main() -> int:
    global DIST
    if "--out" in sys.argv:
        DIST = Path(sys.argv[sys.argv.index("--out") + 1]).resolve()
    sys.path.insert(0, str(ROOT))
    from rerun.appicon import write_ico
    work = Path(tempfile.mkdtemp(prefix="rrb_"))  # short path for PyInstaller's scratch files
    icon = write_ico(work / "rerun.ico")
    cmd = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed", "--onefile",
        "--name", "Rerun", "--icon", str(icon),
        "--distpath", str(DIST), "--workpath", str(work / "build"),
        "--specpath", str(work),
        # App icon picture, loaded at run time for the window (and tray).
        "--add-data", f"{ROOT / 'rerun' / 'assets'}{';' if sys.platform == 'win32' else ':'}rerun/assets",
        # Back ends these libraries load by name at run time.
        "--hidden-import", "pystray._win32",
        "--hidden-import", "pynput.keyboard._win32",
        "--hidden-import", "pynput.mouse._win32",
        # GS Companion tab (imported inside a try block in rerun/gui.py)
        "--hidden-import", "gsc_app.page", "--hidden-import", "gsc_app.update_data",
        "--hidden-import", "gsc_app.scrape",
        "--exclude-module", "matplotlib", "--exclude-module", "pytest",
        str(ROOT / "main.py"),
    ]
    print(" ".join(cmd))
    code = subprocess.call(cmd)
    shutil.rmtree(work, ignore_errors=True)
    if code != 0:
        print("PyInstaller failed")
        return 1
    for folder in ("templates", "routines"):
        src = ROOT / folder
        if src.is_dir():
            shutil.copytree(src, DIST / folder, dirs_exist_ok=True)
    # What this build shipped, so a later template update (rerun/updates.py) knows which
    # files are still untouched and may be replaced, and which ones the user changed.
    from tools.publish_update import content_files
    from rerun.updates import BASELINE_FILE, sha256_file
    baseline = {rel: sha256_file(p) for rel, p in content_files(ROOT).items()}
    (DIST / BASELINE_FILE).write_text(json.dumps({"files": baseline}, indent=1), encoding="utf-8")
    # GS Companion's data is local only (git-ignored, never inside the exe): when you have
    # it, it is copied next to the exe for the Companion tab and unit names.
    gsc = ROOT / "data" / "gscompanion"
    if (gsc / "units.json").exists():
        shutil.copytree(gsc, DIST / "data" / "gscompanion", dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("raw", "companion_settings.json"))
    for f in ("README.md", "config.yaml"):
        if (ROOT / f).exists():
            shutil.copy2(ROOT / f, DIST / f)
    print(f"\nBuilt {DIST / 'Rerun.exe'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
