# Changelog

## 2026-11-14 — Work In Progress notice and key countdown
- After every sign-in (app start, a new key after expiry, Change key) Rerun shows a
  "Work In Progress" notice with an OK button.
- Dashboard header: a live countdown of the key's time left ("Key: 29d 23:59:28 left";
  orange under a day, red under an hour; "Key: Lifetime"), updated every second. When it
  reaches zero, scripts stop at once (no longer up to a minute later). Key checks are now
  scheduled one at a time.
- Tests: test_license 13 (timer text; signed-in app shows the notice and the countdown).
  134/134 + gsc_app 16/16. Exe rebuilt to dist/Rerun (key system)/ and started with a test key.

## 2026-11-14 — Key system and key generator
- Rerun now opens only with a valid key (user request). `rerun/license.py`: a key is 21 bytes
  (version, issued, expires or lifetime, optional PC lock, random id) signed with Ed25519
  (`rerun/ed25519.py`, plain Python RFC 8032 code - checked against the RFC's test vector; no
  new library). Rerun holds only the public key, so keys can be checked but not made from it.
- Sign-in screen (`rerun/license_gate.py`) before the app starts: paste the key, see why a key
  is refused (changed, incomplete, expired, other PC, PC clock turned back), copy this PC's ID.
  The accepted key is kept in `<Rerun folder>/license.json` (git-ignored) with the latest time
  seen. While running: checked every minute; the status line and title show the time left
  (click the status line to change key); a warning 3 days before the end; when it ends, every
  script stops, starts are blocked (also from Discord) and the sign-in asks for a new key.
- Key generator `tools/keygen.py` (`tools/build_keygen.py` -> `dist/Rerun Keygen/Rerun Keygen.exe`):
  time frame presets (1 hour ... 1 year, Lifetime), a custom length (minutes ... years) or
  "until a date", optional lock to one PC, a note; shows when the key ends; lists every key made
  (issued_keys.csv, double-click to copy); "Back up signing key…". The private signing key was
  created once (`--init`) in `%LOCALAPPDATA%\Rerun Keygen\signing_key.txt`, never in git or an exe.
- Limits (offline keys): a key can't be withdrawn before it ends; deleting license.json
  defeats the clock-rollback check; losing the signing key means no new keys for these builds.
- build.py: `--out FOLDER` (the dist copy was running). Exe checks: no key -> sign-in only;
  valid key -> app with time left in the title; expired -> sign-in; keygen exe opens.
- Tests: tests/test_license.py (11). 132/132 + gsc_app 16/16.

## 2026-11-14 — New app icon
- The window, tray and .exe icon is now a picture, `rerun/assets/rerun_icon.png` (512 px, glossy
  blue rounded square with a glowing loop arrow, transparent corners). `rerun/appicon.py` loads
  it; the old drawn icon is kept as a fallback if the file is missing.
- `build.py` and `gsc_app/build_exe.py` bundle `rerun/assets` into the exe (`--add-data`).
- Checked: `write_ico` writes all 7 sizes (16-256); the arrow still reads at 16 px. Not yet
  rebuilt as an exe; pytest isn't installed here, so the test suite was not run.

## 2026-11-14 — Live View at 30 fps
- Measured: an ADB screenshot takes ~180 ms on BlueStacks (5.6 fps at most), so the Live View
  (1 s tick; a screenshot every 3 s when idle) could never reach 30 fps that way.
- New `rerun/live_stream.py` LiveStream: the emulator's own `screenrecord --output-format=h264`
  relayed over a local socket to OpenCV's bundled FFmpeg (no new dependency), newest frame
  kept. 800 px tall, 4 Mbit/s. Restarts after screenrecord's 3-minute limit; gives up after 3
  sessions without video and the Live View falls back to screenshots (retries after 60 s).
- Dashboard: frames drawn at `live_view_fps` (config, default 30; 0 = old behaviour) only while
  the Dashboard is shown, Auto is on and the window isn't minimised; the image is updated in
  place; a label shows the rate ("30 fps"). Stopped when leaving the Dashboard and on quit.
  Idle energy is still read from a full screenshot, at most once a minute.
- Measured live (source app, real emulator): 30.0-30.4 fps drawn in 3 runs, 60-120 frames/s
  decoded; leaving and returning to the Dashboard restarts cleanly; the packaged exe streams.
  While it runs, a script's screenshot takes ~10-20% longer (encoder load on the emulator).
- Tests: tests/test_live_stream.py (3, a real 1 s clip played by a fake adb); GUI tests set
  live_view_fps 0 so they never record a real emulator. 121/121 + gsc_app 16/16.

## 2026-11-14 — Unit pictures in the Units tab
- Each row shows the unit's thumbnail from GS Companion's saved pictures
  (data/gscompanion/images/unit_thumbnail_<id>.png), matched by name (units carry GS Companion's
  name after a clear match; otherwise a close match of the same element). Units the site doesn't
  list show no picture. Rows are taller (44 px); pictures are cached per name.
- Checked on a copy of the live roster. Tests: test_app 5/5, test_units 18/18, gsc_app 16/16.
- Installed 17:19 (exe only; 96 user files unchanged; no crash.log). Backup
  `backups/preinstall_20261114_171901/`.

## 2026-11-14 — Units + Compendium merged; GS Companion inside Rerun; GS Companion names win
- One **Units** tab (roster + Compendium): element, race, clears, target, progress,
  remaining, change; filters All / Unread or uncertain / With a target / Near / At target;
  Set Target, Global Target, Correct Name, Remove, GS Companion, Export CSV. Tabs are now
  Dashboard, Settings, Templates, History, Units, Discord, Log, **Companion**.
- **Companion** tab (gsc_app, by the GS Companion session) built into rerun/gui.py
  (`_build_companion`, replaces rerun_tab.patch), linked both ways via `RerunLink`
  (read-only): Units → open the unit in the Companion; the Companion's unit panel shows your
  clears / target / progress / change and links back; scans, targets and corrections refresh it;
  Correct Name suggests GS Companion's spelling.
- **GS Companion names take priority** (user decision): rerun/gsc_data.py `best_unit` /
  `reference_name` match a name read from the game against the site's units of the same
  element (title + name, "Name, the …", run-together OCR, race bonus); taken only when one
  unit clearly wins (≥ 0.78 and 0.05 ahead, or the more specific of two). The Manager applies
  it at start-up and to every scan (`UnitRoster.reference`); race / element come from the
  site when misread or uncertain (status "reference"). Never changed: names and fields you
  typed (manual), verified values, close calls ("Rimuru"), clashes, units the site doesn't
  list. Old spellings become aliases; renames are logged in units/renames.jsonl; Compendium
  targets follow the rename.
- On a copy of the live roster: 89 of 191 names replaced (all checked by eye), uncertain names
  27 → 11, unread/uncertain rows 88 → 36; 64 story/fodder units stay as read.
- build.py: gsc_app modules in the exe; local data/gscompanion (not raw/) copied next to it.
- Tests: tests/test_reference_names.py (5); gsc_app hookup test now drives the real App
  both ways. 118/118 + gsc_app 16/16.
- Installed 17:11 after the user quit Rerun: exe + new data/gscompanion (577 files) next to it;
  95 user files unchanged before launch. On start the app renamed 89 units (units/renames.jsonl),
  11 names still uncertain; no crash.log. Backup `backups/preinstall_20261114_171145/`
  (roster before the renames).

## 2026-11-14 — Phase 4: Compendium (BETA)
- `rerun/compendium.py`: quest clear targets per unit and a global target (units/targets.json),
  progress, remaining clears, near-target (75/80/90/95 %, default 90) and at-target states, change
  since the previous scan that read the unit ("+12 since 14 Nov"), last full scan. Reads the
  roster and units/scans.jsonl (every scan kept, never edited); corrected names keep their
  history (aliases) and their target.
- Scans now record whether they reached the end of the list (`complete`); older scans are
  judged by their History entry ("Reached the end of the list").
- UI: new **Compendium** tab (search, All / With a target / Near target / At target, sortable,
  text progress bars, Set Target, Global Target, double-click to set). Dashboard: one-line
  Compendium summary (last full scan, units, near / at target).
- Discord `/compendium [search] [show]`.
- Weekly scans: not automated. A scan needs the game on the Units list and Rerun cannot navigate
  there yet; the existing scheduler never starts on a busy instance.
- Tests: tests/test_compendium.py (8); test_app covers the new tab. 107/107 (+6 GSC data).
- Installed 16:52 after the user quit Rerun: exe only, 95 user files hash-verified unchanged,
  relaunched without crash.log. Backup `backups/preinstall_20261114_165231/`.

## 2026-11-14 — Third live scan saved; build 382e212 installed
- Scan 15:22–16:40 saved: 191 units (Fire 41, Water 44, Earth 27, Light 41, Dark 38), 189 with
  quest clears, 27 names uncertain (incl. the junk "wee", "ae", "sc" this build now prevents).
- Installed 382e212 at 16:41 after the user quit Rerun: exe only, 95 user files hash-verified
  unchanged, relaunched without crash.log. Backup `backups/preinstall_20261114_164106/`.

## 2026-11-14 — Units scan: third live scan review (unreadable pages, all elements)
- Third live scan (15:22 onward) worked through 145+ units across Fire/Water/Earth/Light into Dark.
  18 names were flagged uncertain (correctly: long names over bright artwork, words run together).
- Two pages caught while still fading in were stored as junk names ("wee", "ae") and a nameless
  unicorn page (no icon, no name) as "sc". Fixes: read a page only when two frames 0.6 s apart
  agree; a page with no element icon and no agreed name is skipped (frame kept in debug/), never
  turned into a unit.
- Element icon test now requires a vivid, shaded icon (plain parchment read as "Light" before).
  Water (hue 103-105) and Earth (63) confirmed on real captures: all five elements now verified.
- Units tab: Remove button (with confirmation) for misread entries; UnitRoster.remove keeps scan records.
- Fixtures: unit_profile_water_nies, _earth_fosly, _light_kingsoul, _noname_unicorn, _fading.
  Tests: 18 in test_units; 99/99 pass.

## 2026-11-14 — Units scan: grey Achievements button (second live scan)
- Live 15:14: the scan read Clyde (and renamed the earlier garbled entry to "Clyde, the Crimson Sword
  God" as designed), then stopped on Rekyuon: units without achievements show a GREY Achievements
  button (colour match 0.71 < 0.80), so the page went unrecognised for 15 s and the scan stopped safely.
- Fix: CompendiumCounter.detect_state falls back to a greyscale shape match of
  compendium_detail_marker around the button (grey 0.85, yellow 1.00, other screens <= 0.38).
- Fixture unit_profile_rekyuon.png (reads "Rekyuon", Fire, Spirit, 0 clears). Tests: 15 in
  test_units; 96/96 pass.
- Repaired CHANGELOG.md text encoding (commit 7a4b774 had re-saved it as double-encoded UTF-8).

## 2026-11-14 — GS Companion reference data (local only)
- Decision change (user): gscompanion.com was scraped once (via Firecrawl) for personal use. Its
  robots.txt still disallows Anthropic's crawlers and signals `ai-train=no, use=reference`, so the
  data is **local only**: `data/` stays gitignored and `build.py` does not bundle it.
- `data/gscompanion/raw/*.md` (scraped pages) → `tools/gscompanion_build.py` → `crest_palace.json`
  (18 stages: days, boss, hazards, crest drops), `crests.json` (138 crests, per-level values),
  `crest_recommendations.json` (427 units, from the Advisor Team's CrestRec doc), `units.json` (428).
- `rerun/gsc_data.py`: GSCData lookups (palace_today on the 06:00 UTC-6 game day, stages_dropping,
  match_crest for OCR titles, recommended, units_wanting, match_unit). Not wired into scripts yet.
- tests/test_gsc_data.py (6); skips when the local data is absent.

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


## 2026-11-14 — Phase 3 live fixes (first live scan)
- Live: the scan read the first unit, then reopened it forever — the Units screen animates, so the
  exact pixel signature used to recognise "same view" never matched. Now a thumbnail compared with
  a tolerance (same view ~0.03, threshold 6), done-cards reset only after Rerun scrolls, plus a
  backstop (6 already-read units in a row -> scroll on). Regression test fails fast on the old code.
- Live: "Clyde, the Crimson Sword God" ran into the race and the flames behind it broke the reading
  ("Clyde thé.Crimson sword G"). Name and race are now read from one line (race = last word by
  position/gap), with 7 masks voting (3 white-text + 4 "outlined text" masks that drop un-outlined
  bright art), compared ignoring case/punctuation/I-l-1, cleanest spelling chosen. Both fixture
  units read exactly; ~2.4 s per unit page.
- A confident reading that fuzzy-matches a unit stored under an uncertain spelling renames it (old
  spelling kept as alias); manual names are never replaced.
- Fixtures: unit_profile_clyde.png, units_grid_fire_top.png. Tests: 14 in test_units. 95/95 pass.
