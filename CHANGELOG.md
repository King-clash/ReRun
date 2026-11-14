# Changelog

## 2026-11-14 — Phase 1 live check + fix: crest counted twice after a popup
- Live check (installed build, 13:57–14:01): 3 runs and 4 crest records, all with OCR titles
  ("Break Power Lv3", "CRI rate UP Lv3", ...); the ledger matched History one-for-one.
- Bug found live (pre-existing, also in History and stats.json): Redeploy → out of energy → L Potion
  → the same Equip Crest screen came back and "Freeze Resistance Lv3" was judged and counted twice.
- Fix (rerun/scripts/crest.py): a crest of the same rarity (and same title when both were read)
  seen again with no completed run in between is not counted again; it is still scrapped/redeployed.
- Tests: 2 new (13 in test_crest_stats); the regression test fails on the old code. 67/67 pass.
- The one duplicate already recorded (14:00:27) is left in History/ledger/stats as recorded (not
  edited silently): it inflates all-time Lv3 by 1.

## 2026-11-14 — Build and install (Phase 1)
- Rebuilt with `build.py` (one-file PyInstaller, 77.9 MB). Smoke-tested from a temp copy (starts,
  no crash.log, crest log rebuilt).
- Installed to `C:\Users\dandr\Downloads\Rerun\Rerun` after the user quit Rerun themselves: only
  Rerun.exe and README.md replaced; config, stats, history and templates verified unchanged (hash
  comparison). Previous exe + data backed up to `backups/preinstall_20261114_135429/`.
- On first start the installed app rebuilt its crest log: 65 crests (62 Lv3, 2 Lv3+, 1 uncertain)
  and 42 earlier undated runs.

## 2026-11-14 — Phase 1: Crest 4+ and Burst tracking (BETA)
- New `rerun/crest_stats.py`: append-only crest ledger `crest_log.jsonl` (runs, drops, pre-ledger
  run baseline), never compacted, tolerant of a torn last line. Rarity classes lv3 / lv3+ / lv4 /
  4+ / burst / ?; Lv4 is never counted as 4+. Records carry session, source (live/history),
  confidence (verified/assumed/uncertain), palace (24/7 tile), OCR title.
- Notable drops (4+, Burst, Lv4) keep a full screenshot in `crest_shots/`.
- Stats: today (game day, resets 06:00 UTC-6) / session / all-time, observed rate
  ("1 drop per N runs"), average runs per drop, runs since last 4+/Burst, last drop, palace and
  weekday breakdowns.
- Reconstruction from History + stats.json on startup; keyed, so it is repeatable and never double-counts.
- Crest script (and Multiplayer Farm / Queue, which inherit it) writes runs and every crest outcome.
- Dashboard: new "Crests" tiles (4+, Burst, Lv4 as today · session · all, runs since last 4+,
  observed rate) with a plain-language note.
- Discord: `/crests [instance]` (gold embed, last 4+/Burst screenshot attached).
- Files: rerun/crest_stats.py (new), rerun/engine.py (Context.crests), rerun/manager.py,
  rerun/scripts/crest.py, rerun/gui.py, rerun/discord_bot.py, tests/test_crest_stats.py (new),
  .gitignore. No changes to existing data formats; no migration needed.

## 2026-11-14 — Phase 0: recovery and baseline
- Recovered the project from the previous session's scratch folder to `C:\Users\dandr\Documents\Rerun`
  (457 files, byte totals verified identical).
- Installed Git for Windows (winget, with the user's approval); initialised a local repo (never pushed).
- Added `.gitignore` (config.yaml with the Discord token, stats, history, debug, build output, backups).
- Added `config.example.yaml` (tokenless copy of the default config).
- Backed up the installed app's live data (history, stats, config, template meta) to
  `backups/installed_20261114_133742/` (git-ignored).
- Baseline tests: 54/54 pass.
- Docs: ARCHITECTURE, PROJECT_ROADMAP, TESTING, DEVELOPMENT_STATUS, CHANGELOG.
- Commits: f4df578 (baseline).
