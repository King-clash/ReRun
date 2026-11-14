"""Rerun - Grand Summoners companion. Start with:  python main.py"""
import sys
import time
import traceback
from pathlib import Path


def app_root() -> Path:
    # Packaged .exe keeps config/templates next to the executable.
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


if __name__ == "__main__":
    root = app_root()
    sys.path.insert(0, str(root))
    try:
        from rerun.gui import run_app
        run_app(root)
    except Exception:  # noqa: BLE001 - the windowed app has no console to show this
        (root / "crash.log").write_text(
            f"{time.strftime('%Y-%m-%d %H:%M:%S')}\n{traceback.format_exc()}", encoding="utf-8")
        raise
