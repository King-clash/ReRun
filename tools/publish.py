"""Publish a Rerun release:  py tools/publish.py 1.1.0 [--push] [--draft] [--dry-run]

Needs, committed before you start:
  * release_notes/vX.Y.Z.md   plain-language notes (the release page; see the github-publish-notes skill)
  * a `## X.Y.Z` heading in CHANGELOG.md
Steps: safety checks -> tests -> bump rerun/__init__.py -> `build.py --release` (clean zip) ->
SHA256SUMS.txt -> commit "Release vX" + tag.
With --push (asks you to type 'yes'): push HEAD to origin/main and the tag, create the GitHub release
(zip + SHA256SUMS.txt attached, notes = the notes file) and then re-read the live page and check it.
--draft: create the release as a draft so you can read it before it goes public.
--dry-run: only the safety checks, nothing is built, changed or pushed.

Safety checks (the lessons of the 1.0.2 mistake): clean tree; no private files tracked; HEAD contains
origin/main (a fast-forward push); the tag is new; and a WARNING lists local branches whose commits are
not in this release and worktrees with uncommitted changes (work that would be left out).
Nothing is pushed without --push AND a typed 'yes'. Needs a git remote named origin."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INIT = ROOT / "rerun" / "__init__.py"
RELEASE_BRANCH = "main"  # what gets pushed to origin, whichever branch you run this from
SECRET_FILES = ("config.yaml", "stats.json", "crest_log.jsonl", "crash.log", "error.log", "license.json")
MIN_NOTES_CHARS = 400
VERSION_RE = re.compile(r"\d+\.\d+\.\d+")


# ------------------------------------------------------------------ pure helpers (unit tested)
def bump_version_text(source: str, version: str) -> str:
    """rerun/__init__.py text with __version__ set (line endings of the file are preserved)."""
    new, n = re.subn(r'__version__ = "[^"]*"', f'__version__ = "{version}"', source)
    if n != 1:
        raise ValueError("expected exactly one __version__ line")
    return new


def changelog_has(version: str, changelog: str) -> bool:
    return re.search(rf"^##\s+v?{re.escape(version)}(?![\d.])", changelog, re.M) is not None


def notes_problems(text: str) -> list[str]:
    t = text.strip()
    if len(t) < MIN_NOTES_CHARS:
        return [f"notes are only {len(t)} characters; write at least {MIN_NOTES_CHARS} "
                "(what changed, what to do, what is and isn't tested)"]
    problems = []
    if re.search(r"see\s+changelog", t, re.I) and len(t) < 800:
        problems.append("notes just point to the changelog; explain the changes in plain language")
    if "not" not in t.lower() or not re.search(r"(checked|tested|verified)", t, re.I):
        problems.append("notes should say what was and wasn't tested")
    return problems


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sums_text(files: list[Path]) -> str:
    """SHA256SUMS.txt content: '<hash>  <name>' per file (the format `sha256sum -c` reads)."""
    return "".join(f"{sha256_of(p)}  {p.name}\n" for p in files)


def unmerged_branches(branches: list[str], current: str, is_ancestor) -> list[str]:
    """Local branches (other than the current one) with commits that are NOT in HEAD."""
    return [b for b in branches if b != current and not is_ancestor(b)]


def verify_release(info: dict, notes_text: str, zip_name: str, sums_name: str = "SHA256SUMS.txt",
                   expect_draft: bool = False) -> list[str]:
    """What is wrong with the live release (from `gh release view --json ...`); empty = fine."""
    problems = []
    norm = lambda s: re.sub(r"\s+", " ", (s or "").strip())  # noqa: E731
    if norm(info.get("body")) != norm(notes_text):
        problems.append("the release page text does not match release_notes/…md")
    names = {a.get("name") for a in info.get("assets") or []}
    for needed in (zip_name, sums_name):
        if needed not in names:
            problems.append(f"asset missing on the release: {needed}")
    for a in info.get("assets") or []:
        if a.get("name") == zip_name and not a.get("size"):
            problems.append(f"{zip_name} is empty")
    if bool(info.get("isDraft")) != expect_draft:
        problems.append("release is a draft" if info.get("isDraft") else "release is not a draft")
    return problems


# ------------------------------------------------------------------ git/gh plumbing
def run(*cmd: str, check: bool = True, capture: bool = False, cwd: Path | None = None) -> subprocess.CompletedProcess:
    # stdin closed so tests/build can never swallow the confirmation prompt's input
    return subprocess.run(cmd, cwd=cwd or ROOT, check=check, text=True, capture_output=capture,
                          stdin=subprocess.DEVNULL)


def out(*cmd: str, cwd: Path | None = None) -> str:
    return run(*cmd, capture=True, cwd=cwd).stdout.strip()


def die(msg: str) -> None:
    print(f"STOP: {msg}")
    raise SystemExit(1)


def left_out_warnings() -> list[str]:
    """Work that would NOT be in this release: other branches' commits, uncommitted edits elsewhere."""
    warnings = []
    current = out("git", "branch", "--show-current")
    branches = out("git", "for-each-ref", "--format=%(refname:short)", "refs/heads").split()
    stray = unmerged_branches(
        branches, current,
        lambda b: run("git", "merge-base", "--is-ancestor", b, "HEAD", check=False).returncode == 0)
    for b in stray:
        n = out("git", "rev-list", "--count", f"HEAD..{b}")
        warnings.append(f"branch '{b}' has {n} commit(s) that are not in this release")
    for line in out("git", "worktree", "list", "--porcelain").splitlines():
        if line.startswith("worktree "):
            path = Path(line[len("worktree "):])
            if path.resolve() == ROOT.resolve() or not path.exists():
                continue
            dirty = run("git", "status", "--porcelain", capture=True, check=False, cwd=path).stdout.strip()
            if dirty:
                warnings.append(f"{path} has uncommitted changes ({len(dirty.splitlines())} file(s)) "
                                "that are not in this release")
    return warnings


def safety_checks(version: str, tag: str) -> Path:
    """Everything that can be checked before building. Returns the notes path."""
    if out("git", "status", "--porcelain"):
        die("working tree is not clean - commit or discard changes first")
    tracked = set(out("git", "ls-files").splitlines())
    leaked = [f for f in SECRET_FILES if f in tracked]
    if leaked:
        die(f"private files are tracked by git: {leaked}")
    if run("git", "rev-parse", tag, check=False, capture=True).returncode == 0:
        die(f"tag {tag} already exists")
    if run("git", "remote", "get-url", "origin", check=False, capture=True).returncode == 0:
        run("git", "fetch", "-q", "origin", check=False)
        if run("git", "merge-base", "--is-ancestor", f"origin/{RELEASE_BRANCH}", "HEAD",
               check=False).returncode != 0:
            die(f"HEAD does not contain origin/{RELEASE_BRANCH}: merge or rebase it first "
                "(the push must be a fast-forward; release from the merged main)")
    if not changelog_has(version, (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")):
        die(f"CHANGELOG.md has no '## {version}' heading: rename the 'Unreleased' sections and commit")
    notes = ROOT / "release_notes" / f"v{version}.md"
    if not notes.exists():
        die(f"write the plain-language release notes first: {notes} (github-publish-notes skill) and commit it")
    bad = notes_problems(notes.read_text(encoding="utf-8"))
    if bad:
        die(f"{notes.name}: " + "; ".join(bad))
    return notes


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    push, draft, dry = "--push" in sys.argv, "--draft" in sys.argv, "--dry-run" in sys.argv
    if len(args) != 1 or not VERSION_RE.fullmatch(args[0]):
        die("usage: py tools/publish.py X.Y.Z [--push] [--draft] [--dry-run]")
    version, tag = args[0], f"v{args[0]}"
    notes = safety_checks(version, tag)
    warnings = left_out_warnings()
    for w in warnings:
        print(f"WARNING: {w}")
    if dry:
        print("Dry run: safety checks passed" + (f" with {len(warnings)} warning(s)." if warnings else "."))
        return 0

    print("Running tests...")
    if run(sys.executable, "run_tests.py", check=False).returncode != 0:
        die("tests failed")

    raw = INIT.read_bytes().decode("utf-8")        # bytes in/out: keep the file's own line endings
    INIT.write_bytes(bump_version_text(raw, version).encode("utf-8"))

    print("Building the clean release (build.py --release: leak check, blank config, bundled OCR)...")
    if run(sys.executable, "build.py", "--release", check=False).returncode != 0:
        run("git", "checkout", "--", str(INIT))
        die("release build failed or was not safe to share")
    zip_path = ROOT / "release" / f"Rerun-{version}.zip"
    if not zip_path.exists():
        run("git", "checkout", "--", str(INIT))
        die(f"expected {zip_path} after the build")
    sums_path = zip_path.with_name("SHA256SUMS.txt")
    sums_path.write_text(sums_text([zip_path]), encoding="utf-8", newline="\n")
    print(f"Built {zip_path}\n  {sums_path.read_text(encoding='utf-8').strip()}")

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
    for w in warnings:
        print(f"WARNING: {w}")
    prompt = f"Push {RELEASE_BRANCH} + {tag} to {remote.stdout.strip()} and create the " \
             f"{'DRAFT ' if draft else ''}release? Type 'yes': "
    if input(prompt) != "yes":
        print("Cancelled; the local commit and tag remain.")
        return 0
    run("git", "push", "origin", f"HEAD:refs/heads/{RELEASE_BRANCH}")
    run("git", "push", "origin", tag)
    if shutil.which("gh") is None:
        print(f"Pushed. 'gh' is not installed, so create the release by hand and attach {zip_path} "
              f"and {sums_path}")
        return 0
    cmd = ["gh", "release", "create", tag, str(zip_path), str(sums_path), "--title", f"Rerun {version}",
           "--notes-file", str(notes)]
    if draft:
        cmd.append("--draft")
    run(*cmd)
    if draft:
        print(f"Draft release created. Read it on GitHub, then publish: gh release edit {tag} --draft=false")
        return 0
    info = json.loads(out("gh", "release", "view", tag, "--json", "body,assets,isDraft,url"))
    bad = verify_release(info, notes.read_text(encoding="utf-8"), zip_path.name)
    if bad:
        print("RELEASE CREATED BUT THE PAGE IS NOT RIGHT:\n  " + "\n  ".join(bad)
              + f"\nFix with gh release edit/upload on {info.get('url')}")
        return 1
    print(f"Release created and checked: {info.get('url')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
