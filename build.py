"""Build Rerun.exe:  python build.py

Produces dist/Rerun/Rerun.exe - one self-contained file (a one-file build has
no deep internal folders, so it also builds inside long paths that Windows'
260-character limit would otherwise break). Your templates, custom routines,
README and config are copied next to it, so the .exe works exactly like
`python main.py`."""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist" / "Rerun"


def main() -> int:
    sys.path.insert(0, str(ROOT))
    from rerun.appicon import write_ico
    work = Path(tempfile.mkdtemp(prefix="rrb_"))  # short path for PyInstaller's scratch files
    icon = write_ico(work / "rerun.ico")
    cmd = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed", "--onefile",
        "--name", "Rerun", "--icon", str(icon),
        "--distpath", str(DIST), "--workpath", str(work / "build"),
        "--specpath", str(work),
        # Back ends these libraries load by name at run time.
        "--hidden-import", "pystray._win32",
        "--hidden-import", "pynput.keyboard._win32",
        "--hidden-import", "pynput.mouse._win32",
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
    for f in ("README.md", "config.yaml"):
        if (ROOT / f).exists():
            shutil.copy2(ROOT / f, DIST / f)
    print(f"\nBuilt {DIST / 'Rerun.exe'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
