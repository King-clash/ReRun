"""Publish a Rerun release:  py tools/publish.py 1.1.0 [--push]

Steps: check the tree is clean and no secrets are tracked -> run all tests -> bump
rerun/__init__.py -> build Rerun.exe -> zip it -> commit "Release vX" and tag vX.
With --push (asks to confirm): push HEAD to origin/main and the tag, then create the GitHub release
with the zip attached (needs the GitHub CLI `gh`, signed in).

Nothing is pushed without --push AND a typed 'yes'. Needs a git remote named origin."""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INIT = ROOT / "rerun" / "__init__.py"
RELEASE_BRANCH = "main"  # what gets pushed to origin, whichever branch you run this from
SECRET_FILES = ("config.yaml", "stats.json", "crest_log.jsonl", "crash.log", "error.log")


def run(*cmd: str, check: bool = True, capture: bool = False) -> subprocess.CompletedProcess:
    # stdin closed so tests/build can never swallow the confirmation prompt's input
    return subprocess.run(cmd, cwd=ROOT, check=check, text=True, capture_output=capture,
                          stdin=subprocess.DEVNULL)


def out(*cmd: str) -> str:
    return run(*cmd, capture=True).stdout.strip()


def die(msg: str) -> None:
    print(f"STOP: {msg}")
    raise SystemExit(1)


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    push = "--push" in sys.argv
    if len(args) != 1 or not re.fullmatch(r"\d+\.\d+\.\d+", args[0]):
        die("usage: py tools/publish.py X.Y.Z [--push]")
    version, tag = args[0], f"v{args[0]}"

    if out("git", "status", "--porcelain"):
        die("working tree is not clean - commit or discard changes first")
    tracked = set(out("git", "ls-files").splitlines())
    leaked = [f for f in SECRET_FILES if f in tracked]
    if leaked:
        die(f"private files are tracked by git: {leaked}")
    if run("git", "rev-parse", tag, check=False, capture=True).returncode == 0:
        die(f"tag {tag} already exists")
    if f"## {version}" not in (ROOT / "CHANGELOG.md").read_text(encoding="utf-8") and \
            version not in (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"):
        print(f"note: CHANGELOG.md has no entry mentioning {version}")

    print("Running tests...")
    if run(sys.executable, "run_tests.py", check=False).returncode != 0:
        die("tests failed")

    INIT.write_text(re.sub(r'__version__ = ".*"', f'__version__ = "{version}"',
                           INIT.read_text(encoding="utf-8")), encoding="utf-8")

    print("Building...")
    if run(sys.executable, "build.py", check=False).returncode != 0:
        run("git", "checkout", "--", str(INIT))
        die("build failed")
    zip_base = ROOT / "dist" / f"Rerun-{version}"
    zip_path = Path(shutil.make_archive(str(zip_base), "zip", ROOT / "dist" / "Rerun"))
    print(f"Built {zip_path}")

    run("git", "add", "rerun/__init__.py")
    run("git", "commit", "-m", f"Release {tag}")
    run("git", "tag", "-a", tag, "-m", f"Rerun {version}")
    print(f"Committed and tagged {tag} locally.")

    if not push:
        print("Not pushed (no --push). Re-run with --push, or push yourself.")
        return 0
    remote = run("git", "remote", "get-url", "origin", check=False, capture=True)
    if remote.returncode != 0:
        die("no git remote 'origin' - add one first")
    branch = RELEASE_BRANCH
    if input(f"Push {branch} + {tag} to {remote.stdout.strip()} and create the release? Type 'yes': ") != "yes":
        print("Cancelled; the local commit and tag remain.")
        return 0
    run("git", "push", "origin", f"HEAD:refs/heads/{branch}")
    run("git", "push", "origin", tag)
    if shutil.which("gh") is None:
        print(f"Pushed. 'gh' is not installed, so create the release by hand and attach {zip_path}")
        return 0
    run("gh", "release", "create", tag, str(zip_path), "--title", f"Rerun {version}",
        "--notes", f"Rerun {version}. See CHANGELOG.md.")
    print("Release created.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
