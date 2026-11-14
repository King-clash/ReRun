"""Build the key generator:  py tools/build_keygen.py  ->  dist/Rerun Keygen/Rerun Keygen.exe

The exe holds no signing key: it reads yours from %LOCALAPPDATA%\\Rerun Keygen\\ (or lets you
import a backup), so the exe itself is harmless to copy. Keep it for yourself anyway."""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist" / "Rerun Keygen"


def main() -> int:
    sys.path.insert(0, str(ROOT))
    from rerun.appicon import write_ico
    work = Path(tempfile.mkdtemp(prefix="rrk_"))
    icon = write_ico(work / "keygen.ico")
    sep = ";" if sys.platform == "win32" else ":"
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed", "--onefile",
           "--name", "Rerun Keygen", "--icon", str(icon), "--paths", str(ROOT),
           "--distpath", str(DIST), "--workpath", str(work / "build"), "--specpath", str(work),
           "--add-data", f"{ROOT / 'rerun' / 'assets'}{sep}rerun/assets",
           "--exclude-module", "matplotlib", "--exclude-module", "pytest",
           "--exclude-module", "cv2", "--exclude-module", "numpy", "--exclude-module", "discord",
           str(ROOT / "tools" / "keygen.py")]
    print(" ".join(cmd))
    code = subprocess.call(cmd)
    shutil.rmtree(work, ignore_errors=True)
    if code != 0:
        print("PyInstaller failed")
        return 1
    print(f"\nBuilt {DIST / 'Rerun Keygen.exe'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
