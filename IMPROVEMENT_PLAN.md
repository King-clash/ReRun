# Rerun — Improvement plan (phases A–H)

Written 2026-11-14 after the v1.0.3 release. Every number below was measured on the repo that day.
Nothing here is built yet. Each phase can be done on its own, in the order listed, and ends with
something you can check.

## Where things stand (context)

| Fact | Value |
|---|---|
| Latest release | v1.0.3 (GitHub `King-clash/ReRun`, `main` = `9123f68`) |
| Not on GitHub yet | local commits `64a445c` (quest-row stop message) and `76007f7` (docs/notes) on branch `publish/1.0.3` |
| Tests | 18 suites, all pass, about 3–4 minutes (`py run_tests.py`). **No CI** (no `.github/`), so PR #1 showed "no checks" |
| Biggest files | `rerun/gui.py` 2,419 lines, `gsc_app/page.py` 2,204, `rerun/ios.py` 995 |
| Broad `except Exception` | 58 across `rerun/` and `gsc_app/` (5 silent ones already routed to `error.log`) |
| Scripts | 188 templates; 11 scripts still marked BETA (arena, chain, compendium counter, GC area, grand crusade, helper rewards, mines, multi farm, queue, raids, secret equip) |
| Release zip | 90 MB (includes bundled Tesseract); `release/Rerun` 107 MB |
| Branches | `main`, `feat/new-app-icon`, `data/gscompanion`, `release/1.0.3`, `publish/1.0.3`, `claude/folder-optimization-review-…` — all merged into `main` except the two local commits above |
| Live-verified | Crest from Home (Home > Exploring > Crest Palace > Cursed Claw > quest > farming), Past Party, Units scan, Live View 30 fps, Discord embeds |
| Not live-verified | Back button from inside a battle, in-app updates from a real host, any run on a second PC, the 11 BETA scripts |

Lessons from this session that shape the plan:
- Crest from Home stopped twice for the same reason: **every Crest Palace and its quest look different, and palaces rotate**, so single hand-captured template pictures break (tile, then quest row).
- A script that fails **silently** (sat on the quest list) is worse than one that stops with a message.
- I published from the wrong branch once. A release must be built from the merged `main` and checked against every branch that holds work.
- Some of your work lived uncommitted in the primary folder. Anything not committed is not in a release.

Standing rules for every phase (also in the execution prompt):
- Never read or print `config.yaml` in full (it holds the Discord token). Use targeted `grep` for keys only.
- Never touch uncommitted work in the primary `Rerun` folder without asking. Never push, merge, release or delete on GitHub without your go-ahead for that action.
- Anything published on GitHub follows the `github-publish-notes` skill (plain-language notes a high schooler can follow, honest "what is and isn't tested").
- Measure before optimising. Simulator-only results are labelled "not live-verified".

---

## Phase A — Git and repo hygiene (small, do first)

**Goal:** one clean source of truth, nothing unpublished, no dirty-tree surprises.

Why: the wrong-branch release and the "uncommitted work isn't in the release" scare both came from
scattered branches and a build that rewrites tracked files.

Tasks
1. Push the two local commits (`64a445c`, `76007f7`) to `main` via a PR (it is the only way the
   rule "main is the published state" stays true).
2. Update the primary folder safely: it is on `feat/new-app-icon`, which is behind `origin/main`.
   With your approval, switch it to `main` and fast-forward; keep a backup branch until verified.
3. Delete merged branches (local + `origin/release/1.0.3`) after confirming each is an ancestor of `main`.
4. Stop `BUILDS.md` / `builds.jsonl` from dirtying the tree on every build: either git-ignore them
   or have `tools/buildlog.py` write outside the repo. (Decide; the file is referenced by README.)
5. `.gitattributes` with `* text=auto eol=lf` for source files. Mixed CRLF/LF already caused a
   whole-file conflict in `gui.py` during the merge and a 298-line noisy diff in `publish_update.py`.
6. Add a `CONTRIBUTING`-style "how a release is made" section to `DEVELOPMENT_STATUS.md`
   (merge to `main` first, then `tools/publish.py`).

Done when: `git branch -a` shows only `main`; `git status` is clean after a build; the primary
folder matches `origin/main`.
Needs from you: approval to switch/fast-forward the primary folder; choice for item 4.

## Phase B — Crest setup without hand-captured pictures (highest user value)

**Goal:** Crest from Home works on any day without capturing a new tile and quest row each time.

Context: `crest_palace_target` (tile) and `quest_list_entry` (row) are pictures of one specific
palace/quest; they fail when that palace rotates out or you farm another one. The palace screen
shows the palace **name** as readable text, and the quest list shows the quest **title**.

Tasks
1. Add a Crest setting "Palace to farm" (text, e.g. `Shrine of Cursed Claw`). On the Crest Palace
   screen, read the tile names with Tesseract (bundled) and tap the best fuzzy match; keep the
   existing `crest_palace_target` / weekday pictures as the first choice and the name as fallback.
2. Same for the quest list: setting "Quest to farm" (text) and/or "tap the first quest if only one";
   keep `quest_list_entry*` as first choice.
3. If the palace is not in the list (rotated out), stop with a plain message naming the palaces
   that **are** shown, so you can pick one.
4. Add a Crest line to Settings > Setup check (`rerun/setup_check.py`): "Start from Home: ready"
   or exactly what is missing. Reuse `check_nav_templates`.
5. Save the two real screenshots taken today as fixtures (`palace_screen.png`, `quest_list_cursed_claw.png`)
   and test the new readers on them.
6. Optional capture helper: a button in the Templates tab, "Capture this screen's tile", that
   pre-fills the name and a suggested crop.

Verify: tests on the real fixtures; then one live run from Home with the palace chosen **by name only**
(temporarily remove the picture templates).
Risks: OCR misreads stylised banner text — keep the picture templates as primary and the OCR as fallback;
log what was read.
Needs from you: a screenshot of at least one other palace's quest list; which palace you farm.

## Phase C — Reliability and observability

**Goal:** failures are visible, recoverable and explained; Home navigation is safer.

Tasks
1. **Prefer the on-screen Home button to the Back key.** Both real screens captured today
   (Crest Palace, quest list) show a bottom bar with a **Home** icon. Use a `home_nav_button`
   template (new, captured once) and press Back only as a fallback. Back mid-battle is the one
   unverified risk of the new feature. Live-test: from a battle, from Auto-Loop, from the results screen.
2. **Persist the log.** The Log tab is in memory; after a crash or restart the story is gone.
   Write a rotating `rerun.log` (size-capped) next to the app, one line per entry with instance and time.
3. **Audit the 58 broad `except Exception`.** Classify each: cosmetic (keep), reported (keep),
   silent-and-important (route to `errlog.note`, narrow the exception). Output a table in the PR.
4. **Stuck-screen kit:** when a script stops for "stuck", "no progress" or "template missing", always
   save the frame, name the screen's closest template match and its score in the message, so
   the next capture is one step. (The quest-row stop message already does this for one case.)
5. **Run summary per session** (start/stop reason, runs, crests, potions, restarts) appended to
   `history/` and posted to Discord, so "why did it stop" is answerable the next morning.
6. Revisit `NO_PROGRESS_RESTART_S` (20 min), `MAX_REPEAT` (25) and `HOME_MAX_BACKS` (30): log actual
   values reached so they can be tuned from data.

Verify: simulator tests per item; live: items 1 and 2.
Risks: item 1 needs real captures; keep Back as fallback so nothing regresses.

## Phase D — Testing and CI

**Goal:** `main` cannot be broken silently; tests are faster and cover the live-found bugs.

Why: there is no CI, tests take 3–4 minutes serially, several suites are plain scripts, and three
live-found failures today (home stuck, missing tile, wrong quest row) were only caught by you.

Tasks
1. GitHub Actions workflow (`windows-latest`): install `requirements.lock`, run `py_compile` over
   everything and the suites that need no emulator or ReStart. Mark OCR/GUI suites that need
   local assets as `skip` with a reason instead of failing.
2. Add `ruff` (config in `pyproject.toml`): unused imports, undefined names, `except Exception` without handling.
3. Make `run_tests.py` run suites **in parallel** (they are independent processes) and print a
   timing table; target under 90 seconds.
4. Add the live-found cases as fixtures + tests: palace list screen, quest list for a palace whose
   row differs, Home with a dimmed overlay, results screen at start.
5. Cover the scripts that have no tests (BETA ones) at least with the "every state is detected and
   handled" test already used in `test_features.py`.
6. Branch protection on `main` (require the check) — you do this in GitHub settings; I provide the steps.

Verify: a deliberately broken PR turns the check red; a good one turns it green.
Needs from you: turning on branch protection.

## Phase E — Performance (measure first)

**Goal:** faster, calmer runs with less emulator load — only where the numbers say so.

Context: an ADB screenshot costs about 180 ms; scripts poll about every 0.8 s; `detect_state`
tries templates in order every tick; the Live View already pulls a 30 fps H.264 stream; while it
runs a script's screenshots are 10–20% slower.

Tasks
1. **Benchmark first.** A script `tools/bench.py` that times, on fixtures and live: screencap, grey coarse
   pass, colour refine, `detect_state`, OCR energy read. Write results to `BENCHMARKS.md`. No
   optimisation without a number.
2. **Per-frame match cache:** inside one tick the same template is searched repeatedly
   (`detect_state`, `results_bar_live`, handlers). Cache `(frame id, template, region)` for the tick.
3. **Order/limit the search:** keep a "last state" hint so the likely next states are tried first,
   and restrict searches to the template's known region where it is stable (Exploring button,
   bottom bar).
4. **Feed scripts from the live stream** when Live View is on: one capture path instead of two.
   Gate on measurement; fall back to screencap on any stream gap.
5. **Release size:** the 90 MB zip is mostly Tesseract (`eng.traineddata` 29 MB). Try the "fast"
   tessdata model; keep it only if `test_ocr` accuracy on the energy and crest-title fixtures is unchanged.
6. Idle CPU of the GUI (dashboard timers, Live View redraw) — profile with the window open and idle.

Verify: before/after table in `BENCHMARKS.md`; every optimisation keeps all suites green and
the live Crest loop unchanged.
Risks: item 4 touches the core capture path — do last, behind a setting.

## Phase F — Code structure and configuration

**Goal:** smaller files, one place for settings, easier to extend (Milestone B in the old roadmap).

Tasks
1. Split `rerun/gui.py` (2,419 lines) into one module per tab (`gui/dashboard.py`, `settings.py`,
   `templates.py`, `history.py`, `units.py`, `discord.py`, `log.py`, `companion.py`) with `App`
   composing them. Pure move: no behaviour change, tests unchanged, one commit per tab.
2. Same idea for `gsc_app/page.py` (2,204 lines).
3. Typed events (the planned "event bus"): replace ad-hoc dicts in `Manager.emit` with small dataclasses;
   keep the same names so Discord and the GUI keep working.
4. Config schema: validate `config.yaml` on load, list unknown keys, migrate with a version number,
   and write a `.bak` before any migration. (Old keys like `party` are already handled by hand.)
5. Remove the now-dead pieces: the old `party` migration after a deprecation window; unused templates
   after a check (the `loopdigit_*` files are loaded by prefix — keep).

Verify: `run_tests.py` green after each move; GUI starts and closes; a screenshot of each tab matches before/after.
Risks: large diffs; do tab by tab and rely on the CRLF/LF fix from Phase A.

## Phase G — Releases, updates and distribution

**Goal:** shipping is boring, safe and checkable; users can update without re-downloading 90 MB.

Tasks
1. **Turn on the signed in-app updates** (`rerun/updates.py`): host the manifest on GitHub Pages for
   this repo (`https://king-clash.github.io/ReRun`), set `UPDATE_URL`, publish with `tools/publish_update.py`,
   and run a real exe update end to end. (The changelog lists this as "not yet done".)
2. `tools/publish.py`: after publishing, re-read the release page and fail if the notes are
   missing or garbled; attach `SHA256SUMS.txt` for the zip; mark releases that are superseded.
3. Draft-first flow: create the release as a draft, let you read it, then publish.
4. Old releases v1.0.1 / v1.0.2: add a "superseded by 1.0.3" line or mark pre-release (you said to
   leave them; this stays optional).
5. Code signing / SmartScreen: unsigned exes show a Windows warning for other people. Document it
   in the release notes; evaluate signing options and cost.
6. Version policy: patch for fixes, minor for features; one `__version__`; a CHANGELOG entry required by `publish.py`.
7. A tested "upgrade from older folder" path is already built (`migrate.py`); add it to the install
   steps with a screenshot.

Verify: a real update applied to a copy of the app; checksum file matches.
Needs from you: confirm GitHub Pages hosting; your signing key stays untouched (never read or moved).

## Phase H — Feature backlog (pick after A–D)

1. Verify the 11 BETA scripts live, one at a time, each with a short checklist and fixtures captured
   during the run (they are labelled BETA because they have never run on the real game).
2. Compendium Farm (Training > Cross Battle): blocked on real captures of those screens.
3. Weekly automatic Units/Compendium scans (needs navigation to the Units list; the Home-first
   code from Phase B/C is the foundation).
4. Notification centre and daily report in Discord (Phase 18/19 in the old roadmap).
5. Multi-instance (the app already supports several instances in-process; you use one BlueStacks).

---

## Suggested order and size

| Phase | Size | Depends on | Live testing needed |
|---|---|---|---|
| A Git hygiene | small | — | no |
| B Crest setup by name | medium | screenshots from you | yes (1 run) |
| C Reliability | medium | B optional | yes (Home button, battle) |
| D Tests and CI | medium | A | no |
| E Performance | medium | measurements | yes |
| F Structure | large | A, D | smoke only |
| G Releases/updates | medium | A, D | yes (real update) |
| H Features | open-ended | all | yes |

Recommended: A, then B and D side by side (they touch different files), then C, G, E, F, H.

---

## Prompt to feed me (copy everything in the box)

```
You are working on Rerun (Windows Tkinter app that automates Grand Summoners on BlueStacks)
in C:\Users\dandr\Documents\Rerun (use a git worktree; the primary folder may hold my
uncommitted work: never touch it without asking). Read IMPROVEMENT_PLAN.md,
DEVELOPMENT_STATUS.md and TESTING.md first. Python:
%LOCALAPPDATA%\Programs\Python\Python312\python.exe; tests: py run_tests.py; GitHub repo
King-clash/ReRun (gh is at C:\Program Files\GitHub CLI and signed in).

TASK: execute PHASE <LETTER(S)> of IMPROVEMENT_PLAN.md, nothing from other phases.

HOW TO WORK (efficiently)
1. Start by confirming the starting state in ONE parallel batch: git status/branches vs
   origin/main, test baseline (run_tests.py), and the files the phase names. Report any
   surprise before editing.
2. Keep a task list. Do independent reads/searches in parallel. Use subagents/sessions only
   for parts that are truly independent (different files); never two writers on one file.
3. One branch per phase off the current origin/main (name: phase-<letter>-<topic>), small
   commits with clear messages (Co-Authored-By line as required), tests updated in the same
   commit as the code. Run the full suite before each commit and at the end.
4. Measure before optimising; show before/after numbers. Label anything not run on the real game
   as "not live-verified". When a live check is needed, ask me to set up the screen, take
   screenshots only (no taps) unless I say otherwise, and never print config.yaml.
5. Ask me only when blocked on a decision the plan marks "Needs from you", or when an action is
   outward-facing (push, PR merge, release, deleting branches, GitHub settings, touching the
   primary folder). Otherwise decide, state the choice in one line, and continue.

GUARDRAILS
- Never read or print config.yaml in full, tokens, keys or signing keys. Use targeted greps.
- Anything published on GitHub (PR body, release, README) must follow the github-publish-notes
  skill: plain language a high schooler can follow, what changed and why, what is and is not tested.
  Write long bodies to a file and use --body-file; re-read the live page after posting.
- Do not publish a release unless I say so in the same message; releases are built from merged
  main via tools/publish.py with release_notes/vX.Y.Z.md written first.
- Do not change behaviour in a "pure refactor" phase; if a test must change, say why.

DONE MEANS: the phase's "Done when / Verify" lines are met, all suites pass, the working tree is
clean, docs (CHANGELOG, DEVELOPMENT_STATUS, TESTING) are updated, and you give me a short report:
what changed, what was measured, what is untested, what I must do next (with exact steps), and the
PR link. If you skipped or deferred anything, say so.
```

Examples: `PHASE A`, `PHASE B and D (in parallel sessions)`, `PHASE E measure only, no changes`.
