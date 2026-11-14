"""Run every tests/test_*.py suite and report one pass/fail:  py run_tests.py"""
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main() -> int:
    failed = []
    for t in sorted((ROOT / "tests").glob("test_*.py")):
        t0 = time.time()
        r = subprocess.run([sys.executable, str(t)], cwd=ROOT, capture_output=True, text=True)
        ok = r.returncode == 0 and "FAIL" not in r.stdout
        print(f"{'ok  ' if ok else 'FAIL'} {t.name} ({time.time() - t0:.0f}s)")
        if not ok:
            failed.append(t.name)
            print(r.stdout[-1500:], r.stderr[-1500:])
    print("all suites passed" if not failed else f"FAILED: {', '.join(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
