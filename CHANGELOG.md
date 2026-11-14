# Changelog

## Unreleased — Crest always starts from the Home screen (BETA, simulator-tested only)
- New Crest setting **Always start from the Home screen** (`start_home`, default on). On Start the
  script first reaches Home: known popups are closed with their own handlers, anything else gets
  Back (max 30 presses / 2 minutes, then it stops with a screenshot saved to debug/). Home counts
  only when the Exploring button is lit, so a popup dimming Home is not mistaken for it.
- Then it walks Home > Exploring > Crest Palace > palace tile > quest list > quest (the 24/7-mode
  navigation, now also used for a normal Start), and the usual party/Auto-Loop flow takes over.
- Safety: an Equip Crest / Crest Burst screen at Start is never left with Back (an undecided crest
  could be lost) - it stops and asks you to decide it. Missing navigation templates stop the script
  before it touches the game and name the missing ones. Needs a palace tile template
  (`crest_palace_target`, or `crest_palace_<day>`); the repo ships none, so capture one first.
- Tests: tests/test_crest_home.py (9); older Crest tests pass `start_home: False`.

## 2026-11-14 — Phase 3: Unit Roster (BETA)
- Source decision from real captures: the Units list grid has no readable text (portrait, element
  icon, star badge, 'Lv' badge without a number). Tapping a card opens the unit's page (the same
  page ReStart's compendium templates target): name, element icon, race, "Quest cleared: N". No
  level/rarity text is shown there, so those stay empty (never invented).
- `rerun/unit_screens.py`: grid card finder by fixed 5-column geometry (template matching alone
  missed ~25% of cards: 21/30 and 23/28 on the fixtures; now 30/30 and 28/28); unit page reader
  (white-text mask with a 3-threshold vote for the name over artwork, element by icon hue —
  Fire/Light/Dark seen, Water/Earth marked uncertain until seen — race, quest clears).
- `rerun/units.py`: UnitRoster (units/roster.json, scans.jsonl, aliases.json). Provenance per
  field; status order manual > verified > ocr > estimated > uncertain; incomplete scans keep
  values; fuzzy match onto known names; manual corrections learned as aliases; scan comparison;
  CSV export; search/sort/filters.
- Compendium Counter now uses the new reader, feeds the roster, saves partial results when stopped,
  saves a frame for uncertain names. Old guess-based reader removed.
- UI: new **Units** tab (search, element filter, unread-only, sortable columns, Export CSV, Correct
  Name, GSCompanion). ios.py: table header style + People/Link icons.
- GSCompanion: robots.txt disallows Anthropic's crawlers (ClaudeBot, Claude-Web, anthropic-ai) and
  sets `use=reference`; no public API. Decision (user-approved options 2+3): no data is fetched or
  cached; the GSCompanion button copies the unit name and opens gscompanion.com/units/ in the browser.
- Discord `/units [search]`. tools/capture.py and tools/record_screens.py (read-only screenshot helpers).
- Fixtures: units_grid_fire/dark/dark_2.png, unit_profile_ira.png. Tests: tests/test_units.py (11).
  92/92 pass.

## 2026-11-14 — Phase 2: Always re-select Past Party (BETA)
- Setting renamed: the "Party" choice (Last Party / Current Party) is now the switch
  **Always re-select Past Party** (`past_party`). Default ON for Crest (and every Auto-Loop farm),
  OFF for Any Quest / Secret Equip.
- Config migration (read-time, non-destructive): `party: Last Party` → on, `Current Party` → off,
  except Crest, which is on (per the Phase 2 brief). An explicit `past_party` always wins. config.yaml
  is rewritten in the new form only when the user saves Settings. Scripts without the switch
  (Multiplayer Farm) are unaffected.
- Verified flow (rerun/scripts/loop_farm.py): Past Party (must be visible and lit) → Include AI
  ticked (unticked box tapped, max 3, else stop) → re-check on a fresh frame → Apply → confirm the
  dialog closed and the party screen is back (max 3 Applies, else stop).
- Fallbacks: no / greyed Past Party button, or its dialog never opens → continue with the current
  party, notify once per session, History entry.
- Re-applied on: Start, new quest entry (Solo/Challenge, crest quest list, restart after wipe),
  Resume from Pause (new BaseScript.on_resume hook), crash relaunch and daily-reset relogin
  (on_relaunch). Not on Redeploy.
- New BaseScript hooks: `migrate_settings` (also applied in Manager.script_settings), `on_resume`.
- Tests: tests/test_past_party.py (12, incl. a real-screenshot check); test_app updated for the
  rename and made deterministic (its fixed timers raced on a busy PC — flaky TclError). 81/81 pass.

## 2026-11-14 — Fix: History rebuild re-imported live crests on restart (Phase 1 bug)
- Installed the double-count fix (exe only, user files unchanged; backup
  `backups/preinstall_20261114_141002/`). On that restart the History rebuild imported 11 crests the
  script had already logged live (the live crest is also written to History), so the stats would
  have shown them twice.
- Fix (rerun/crest_stats.py): the rebuild skips History crests logged live within 3 s; the summary
  ignores rebuilt copies that match a live drop. The ledger file is not edited (append-only).
- Checked on a copy of the installed data: 76 crests counted = 76 in History; rebuilding again adds 0.
- Tests: 2 new (15 in test_crest_stats). 69/69 pass.

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

