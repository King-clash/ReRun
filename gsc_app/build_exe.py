"""Build the standalone GS Companion app:  py gsc_app/build_exe.py

Produces dist/GS Companion/GS Companion.exe - one file with the app, the GS Companion
data (JSON) and the pictures inside, so it runs on its own anywhere. Rerun's own
build.py and Rerun.exe are not touched.

Needs: pyinstaller (pip install pyinstaller), the data in data/gscompanion/, and
optionally the pictures (py gsc_app/fetch_images.py)."""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "gscompanion"
DIST = ROOT / "dist" / "GS Companion"
NAME = "GS Companion"


def main() -> int:
    if not (DATA / "crests.json").exists():
        print("No data in data/gscompanion - run tools/gscompanion_build.py first")
        return 1
    sys.path.insert(0, str(ROOT))
    from rerun.appicon import write_ico
    work = Path(tempfile.mkdtemp(prefix="gscb_"))  # short path for PyInstaller's scratch files
    try:
        # Stage only what the app reads: the JSON and the pictures (not raw/ scrapes).
        stage = work / "stage" / "data" / "gscompanion"
        stage.mkdir(parents=True)
        for f in DATA.glob("*.json"):
            shutil.copy2(f, stage / f.name)
        pics = DATA / "images"
        if pics.is_dir():
            shutil.copytree(pics, stage / "images")
        else:
            print("Note: no pictures yet (py gsc_app/fetch_images.py) - building without them")
        icon = write_ico(work / "gsc.ico")
        cmd = [
            sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed",
            "--onefile", "--name", NAME, "--icon", str(icon),
            "--distpath", str(DIST), "--workpath", str(work / "build"), "--specpath", str(work),
            "--paths", str(ROOT),
            "--add-data", f"{work / 'stage' / 'data'}{';' if sys.platform == 'win32' else ':'}data",
            # App icon picture, loaded at run time for the window (and tray).
            "--add-data", f"{ROOT / 'rerun' / 'assets'}{';' if sys.platform == 'win32' else ':'}rerun/assets",
            # Only Tk + Pillow are needed; see the stand-ins in __main__.py.
            "--exclude-module", "cv2", "--exclude-module", "numpy",
            "--exclude-module", "discord", "--exclude-module", "matplotlib",
            "--exclude-module", "pytest", "--exclude-module", "pynput",
            "--exclude-module", "pystray",
            str(ROOT / "gsc_app" / "__main__.py"),
        ]
        print(" ".join(cmd))
        code = subprocess.call(cmd)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if code != 0:
        print("PyInstaller failed")
        return 1
    exe = DIST / f"{NAME}.exe"
    print(f"\nBuilt {exe}  ({exe.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
