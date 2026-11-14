"""Run every tests/test_*.py suite and report one pass/fail:

    py run_tests.py                 all suites, 4 at a time, with a timing table
    py run_tests.py --jobs 1        one at a time (easier to read a failure)
    py run_tests.py --ci            skip suites that need a real Tesseract / local assets (GitHub Actions)
    py run_tests.py test_units      only suites whose name contains 'test_units'
"""
import concurrent.futures as cf
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SKIP_IN_CI = {"test_ocr.py"}   # reads real screenshots with the real Tesseract (ReStart's or bundled)


def run_one(path: Path) -> tuple[str, bool, float, str]:
    t0 = time.time()
    r = subprocess.run([sys.executable, str(path)], cwd=ROOT, capture_output=True, text=True)
    ok = r.returncode == 0 and "FAIL" not in r.stdout
    return path.name, ok, time.time() - t0, "" if ok else (r.stdout[-1500:] + r.stderr[-1500:])


def main() -> int:
    args = sys.argv[1:]
    ci = "--ci" in args
    jobs = int(args[args.index("--jobs") + 1]) if "--jobs" in args else 4
    names = [a for a in args if not a.startswith("--") and not a.isdigit()]
    suites = sorted((ROOT / "tests").glob("test_*.py"))
    if names:
        suites = [s for s in suites if any(n in s.name for n in names)]
    skipped = [s.name for s in suites if ci and s.name in SKIP_IN_CI]
    suites = [s for s in suites if s.name not in skipped]
    t0 = time.time()
    results = []
    with cf.ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        for res in pool.map(run_one, suites):
            results.append(res)
            print(f"{'ok  ' if res[1] else 'FAIL'} {res[0]} ({res[2]:.0f}s)", flush=True)
            if not res[1]:
                print(res[3], flush=True)
    failed = [r[0] for r in results if not r[1]]
    busy = sum(r[2] for r in results)
    print(f"\n{len(results) - len(failed)}/{len(results)} suites passed in {time.time() - t0:.0f}s "
          f"(would take {busy:.0f}s one by one)" + (f"; skipped in CI: {', '.join(skipped)}" if skipped else ""))
    print("all suites passed" if not failed else f"FAILED: {', '.join(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
