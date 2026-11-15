# Testing

Interpreter: `%LOCALAPPDATA%\Programs\Python\Python312\python.exe` (Python 3.12.10; `python` is not
on PATH — the Microsoft Store alias intercepts it). Each suite is a plain script:

```
py run_tests.py               # every suite below, 4 at a time (~1 min), timing table, one pass/fail
py run_tests.py --jobs 1      # one at a time (easier to read a failure)
py run_tests.py --ci          # what GitHub Actions runs (skips test_ocr: needs a real Tesseract)
py run_tests.py test_units    # only suites whose name contains this
py -m ruff check .            # lint: syntax errors, undefined names, unused imports (pyproject.toml)
py tests/test_scripts.py      # every script against a simulated game (FakeDevice)
py tests/test_real_screens.py # real 720x1280 screenshots in tests/fixtures (needs templates)
py tests/test_features.py     # energy/potions, history, Queue, script wiring
py tests/test_ocr.py          # Tesseract on real screenshots (needs ReStart's bin)
py tests/test_app.py          # manager, engine, Discord, GUI start/close
py tests/test_crest_stats.py  # Phase 1 crest ledger, stats, reconstruction
py tests/test_past_party.py   # Phase 2
py tests/test_units.py        # Phase 3 roster + unit page readers
py tests/test_compendium.py   # Phase 4 targets, progress, change since last scan
py tests/test_updates.py      # signed updates against a local web server (throwaway key)
py tests/test_crest_home.py   # Crest starts from the Home screen
py tests/test_limits.py        # time limit, energy floor, restart cap
py tests/test_discord_settings.py  # quiet hours, ping kinds, summary contents
py tests/test_ui_options.py   # window memory, start options, Stop All confirm, logging
py tests/test_capture_helper.py  # Suggest Crop on the Templates tab
py tests/test_accounts.py     # Account Manager data, checklist resets, goals, vault, safety, Manager glue
py tests/test_scanning.py     # every scanning path: readers on all real screens, fake-emulator scans, locks, isolation
py tests/test_accounts_gui.py # both workspaces: every section draws, forms, isolation, ToS warning
py tests/test_qol.py          # pure helpers (times, name lists, window position)
py tests/test_errlog.py       # quiet-failure error.log
```

Tests do not write to project data (verified 2026-11-14 by hashing all files before/after).

## Baseline — 2026-11-14 (commit f4df578, before any change)

| Suite | Result | Time |
|---|---|---|
| test_scripts | 10/10 pass | 12 s |
| test_real_screens | 11/11 pass | 2 s |
| test_features | 17/17 pass | 22 s |
| test_ocr | 11/11 pass | 7 s |
| test_app | 5/5 pass | 9 s |
| **Total** | **54/54** | |

No warnings, no pre-existing failures.

## Fixtures

`tests/fixtures/` — 16 real screenshots (home, party, Auto-Loop, results, energy dialog, Equip
Crest Lv3, mailbox, errors). Also `debug_crest/` holds 3 real Equip Crest captures (not in git).

## Live verification log

| Date | What | Result |
|---|---|---|
| 2026-11-14 (prev. session) | Login & Mail, Crest end to end, Any Quest | Verified live |
| 2026-11-14 | Installed Rerun.exe farming Crest during this session (history grew live) | Observed only |

## Regression runs

| Date | Change | Result |
|---|---|---|
| 2026-11-14 | Phase 1 crest ledger | 65/65 (54 original + 11 new test_crest_stats); no new failures |

| 2026-11-14 | Crest double-count fix | 67/67 (13 test_crest_stats) |
| 2026-11-14 | History re-import fix | 69/69 |
| 2026-11-14 | Phase 2 Past Party | 81/81 (12 new test_past_party; test_app made deterministic) |
| 2026-11-14 | Phase 4 Compendium | 107/107 (8 new test_compendium) + test_gsc_data 6/6 |
| 2026-11-14 | Units+Compendium merge, Companion tab, GS Companion names | 118/118 (5 new test_reference_names) + gsc_app/test_page.py 16/16 |
| 2026-11-14 | Updates keep your data (import from an older Rerun) | 139/139 (5 new test_migrate) + gsc_app 16/16; exe shows the import window on a fresh copy |
| 2026-11-14 | Key system + key generator | 132/132 (11 new test_license) + gsc_app 16/16; exe: no/valid/expired key and keygen checked |
| 2026-11-14 | Live View 30 fps (video stream) | 121/121 (3 new test_live_stream) + gsc_app 16/16; live: 30 fps drawn in 3 runs |

**Live (installed exe, 2026-11-14 14:33–14:34):** Crest started from the party screen with Past
Party on; the first run completed at 14:34:09 with no party fallback or failure in History.
That outcome means the verified flow reached Apply + dialog closed (the only other paths record
an entry). The user confirmed the Log showed "Selecting Past Party", "Ticking Include AI" and
"Past Party applied with Include AI - dialog closed".

`py tests/test_past_party.py` — Phase 2. The real party screen (party_reigrad.png) matches
past_party_button 0.96 lit; under the error popup it is dimmed (8 vs 131). No real capture of the
Past Party dialog (Include AI / Apply) exists yet — save one as a fixture on the first live run.

**Live (installed exe, 2026-11-14 13:57–14:01):** Phase 1 ledger recorded 3 runs + 4 crests with
titles, matching History exactly; exposed the double count fixed above (fix not yet live-verified).

Phase 1 also checked by rendering the dashboard against a temp copy of the user's backed-up live
History (52 crest entries + 30 pre-ledger runs rebuilt). That is a screenshot of real data, not a live
farming test: the live Crest hooks will be verified the next time the rebuilt exe farms.

## CI (GitHub Actions) - added in Phase D, not yet run on GitHub
`.github/workflows/tests.yml` runs on every pull request and push to `main` (Windows, Python 3.12):
ruff, compileall, then `py run_tests.py --ci --jobs 4`. It has never run: the first PR after it is merged
is its first real test, so check that run and fix the workflow if needed.
To make it protect `main` (GitHub > Settings > Branches > Add rule for `main`): tick "Require status
checks to pass before merging" and pick the `tests` check; optionally "Require a pull request before merging".
