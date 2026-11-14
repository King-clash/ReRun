# Testing

Interpreter: `%LOCALAPPDATA%\Programs\Python\Python312\python.exe` (Python 3.12.10; `python` is not
on PATH — the Microsoft Store alias intercepts it). Each suite is a plain script:

```
py tests/test_scripts.py      # every script against a simulated game (FakeDevice)
py tests/test_real_screens.py # real 720x1280 screenshots in tests/fixtures (needs templates)
py tests/test_features.py     # energy/potions, history, Queue, script wiring
py tests/test_ocr.py          # Tesseract on real screenshots (needs ReStart's bin)
py tests/test_app.py          # manager, engine, Discord, GUI start/close
py tests/test_crest_stats.py  # Phase 1 crest ledger, stats, reconstruction
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

Phase 1 also checked by rendering the dashboard against a temp copy of the user's backed-up live
History (52 crest entries + 30 pre-ledger runs rebuilt). That is a screenshot of real data, not a live
farming test: the live Crest hooks will be verified the next time the rebuilt exe farms.
