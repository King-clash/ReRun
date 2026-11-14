# Changelog

## Unreleased — Quality-of-life settings (15 of 16 ideas; BETA, simulator + real fixtures)
**Crest / loop farms** (Settings tab, per script)
- **Palaces to farm, in order of preference** - a comma list ("Cursed Claw, Whirlwind"); the first one that is open
  is used. **Palaces per weekday** - "Mon: Cursed Claw; Sat/Sun: Heavenly Light" overrides the list on those days.
  Weekdays follow the GAME day (resets 6 AM UTC-6), now also for the `crest_palace_<day>` pictures.
- **Stop after N minutes / Stop at HH:MM** - the batch that is running finishes, then the farm ends ("Time limit reached.").
- **Keep at least N energy** - stops instead of using a potion when the next run would leave less (reads the energy
  bar with the text reader; unreadable = no stop; checked between batches).
- **Max game restarts per day** - crash/no-progress restarts count; the daily relogin, maintenance and farm switches do not.
- **If it can't reach the Home screen**: stop (default) / restart the game and try again (2x) / keep trying.
  **Allow the Back key**: off = only pop-ups and the on-screen Home button are used.
**Discord tab**: **Quiet hours** (alerts still posted, without the @mention; may cross midnight), **Ping me for**
  (rare crests / stops and problems / finished / everything else), and what the **daily summary** lists.
**Settings tab**: **Start minimized to the tray**, **Start scripts when Rerun opens**, **Confirm before Stop All**
  (the F12 hotkey and tray menu never ask), and a **Logging** group (what rerun.log records, file size, files kept,
  lines in the Log tab). The window position and open tab are remembered (a position that is no longer on screen is ignored).
**Templates tab**: **Suggest Crop** draws the box for the selected palace tile, quest row or Home button; press Save.
- Defaults keep today's behaviour (all new limits are 0/off, all pings on).
- NOT done: "keep farming after a rare crest" - the script keeps a crest by leaving the Equip Crest screen untouched and
  stopping; how the game lets you keep one AND continue is unknown, so it could scrap a crest you wanted.
- Tests: test_qol (5), test_limits (11), test_discord_settings (6), test_ui_options (10), test_capture_helper (5),
  +6 in test_crest_home, +3 in test_crest_names. Not live-verified.

## Unreleased — Fix: the Log tab now shows lines logged before the window opened
- Found in the final walkthrough: the Log tab started empty and only showed lines logged after the window
  existed, so start-up lines (including the new config warnings) never appeared. It now shows them once
  (`_backfill_log`); later lines still arrive as events. tests/test_app.py: `test_log_tab_shows_lines_logged_before_the_window_opened`.

## Unreleased — Phase H: backlog triage
- `tools/beta_report.py` -> `BETA_CHECKLISTS.md`: for the 13 scripts that never ran on the real game, which pictures
  are captured/missing (only `raid_ticket_target` of Raid Tickets lacks a required one) and one live-check procedure.
- IMPROVEMENT_PLAN.md has an Outcome table; live verification and new features stay with you.

## Unreleased — Phase G: release tooling
- `tools/publish.py`: fixed a defect (it wrote `__init__.py` through Python's text mode, turning its line endings
  into CRLF on Windows); now needs a `## X.Y.Z` CHANGELOG heading and real notes (thin / "see changelog" / no
  testing section are refused); refuses to push unless HEAD contains origin/main; **warns about other branches'
  commits and other worktrees' uncommitted changes that the release would leave out** (the 1.0.2 mistake);
  attaches SHA256SUMS.txt; `--draft` and `--dry-run`; re-reads the live release page and reports if it doesn't
  match the notes or lacks the assets. tests/test_publish.py (7).
- `license.json` added to the private files publish.py refuses to find tracked in git.
- Not done: hosting the signed in-app updates (needs a host + you), code signing, marking v1.0.1/1.0.2 superseded.

## Unreleased — Phase F: structure (no behaviour change)
- `rerun/gui.py` (2,419 lines) is split by tab into mixins: `gui_updates` (updates + key), `gui_dashboard`
  (+ Live View), `gui_settings` (+ setup check), `gui_templates`, `gui_history`, `gui_units`
  (+ Companion), `gui_discord`, `gui_log`; shared imports/constants/widgets in `gui_common`;
  `gui.py` keeps `App` (core: start-up, event loop, tray, closing) and `run_app` (275 lines).
  A pure move: all 128 `App` members, every helper class and every constant have identical
  syntax trees before and after (checked with `ast`), all suites pass, lint is clean.
- `rerun/events.py`: the four events `Manager.emit` sends (log, status, notify, history) as typed
  dicts + `problems()`; `Manager.emit` is typed; test checks every emitted event.
- `rerun/configcheck.py`: config.yaml is checked against the defaults when it loads; unknown keys and
  wrong value types are written to the Log tab as warnings (nothing is changed or rejected).
  Both real configs on this PC check clean. tests/test_events_config.py (4).
- Not done on purpose: splitting `gsc_app/page.py` (a separate app, another session's work) and removing
  the old `party` setting migration (users upgrading from old configs still need it).

## Unreleased — Phase D: tests and CI
- `run_tests.py` runs suites in parallel (`--jobs`, default 4) with a timing table: 63 s instead of ~225 s
  (3 runs in a row, all 20 suites pass). `--ci` skips suites needing a real Tesseract.
- `pyproject.toml`: ruff on real-bug classes only (syntax, undefined names, unused imports/variables).
  Found no real bugs; 6 unused imports removed.
- `.github/workflows/tests.yml`: lint + compile + tests on every PR/push to main (Windows). Not yet run on GitHub.
- The real-screen cases found live (palace list, quest list, Home button, dimmed Home) are fixtures + tests
  from Phase B/C; "every state is detected and handled" already covers all scripts including the BETA ones.

## Unreleased — Phase C: reliability (BETA, simulator + real fixtures)
- **Home button first:** Crest's "start from Home" taps the bottom bar's Home button (new template
  `home_nav_button`, threshold 0.9, matches the real Crest Palace and quest list screens) when it is
  visible and lit, and presses Back only otherwise (or after 4 taps that change nothing). Back from
  inside a battle is still untested on the real game, so keeping Home-button-first matters.
- **Persistent log:** every Log-tab line is also appended to `rerun.log` (1 MB x 4 files, rotated;
  opened per line so no file stays locked). `rerun/runlog.py`.
- **Session summary:** when a script ends, History + Log get one line: how long, why it ended, runs,
  crests, potions, game restarts ("Session ended after 42 min (Crest): stopped: ... | 7 run(s), ...").
- **Closest known screens:** "stuck", "unrecognised for 5 minutes" and "couldn't reach Home" reports now
  say which templates the frame resembled most (e.g. `exploring_button 0.62`).
- **Error audit:** `tools/except_audit.py` lists every broad `except Exception` and whether it tells anyone
  (65 total; silent ones 34 -> 25; the rest are cosmetic: tray, DPI, title-bar colour, or already return an
  error text). Failures in idle energy reads, unit pictures, name suggestions and GS Companion reference
  matching now go to `error.log`.
- Tests: tests/test_runlog.py (4), 3 more in tests/test_crest_home.py.

## Unreleased — Crest finds the palace and quest by name (BETA)
- Palaces rotate and every quest looks different, so hand-captured tile/row pictures break.
  New Crest settings **Palace to farm** and **Quest to farm** (names, optional). Pictures are still
  tried first; when none matches, Crest reads the screen with the text reader (`rerun/textnav.py`)
  and matches the distinctive words (tolerates banner text read partly: "Whirl." = Whirlwind).
  A palace that isn't listed, or two palaces that match equally, stop with a message naming
  what it can read (never a guess). With no quest name, a palace with exactly one quest opens it.
- Settings > Setup check has a new line per Crest instance: "can start from the Home screen" or what is missing.
- Real fixtures: tests/fixtures/crest_palace_list.png, quest_list_cursed_claw.png (live 2026-11-14).
  tests/test_crest_names.py (9). Checked on the fixtures only: not live-verified with names.
- Phase A: LF line endings (.gitattributes), BUILDS.md/builds.jsonl no longer tracked.

## 1.0.3 — Crest always starts from the Home screen (BETA, simulator-tested only)
- Also: error.log for errors that used to be swallowed silently (rerun/errlog.py); tools/publish.py (tests, build --release, tag, GitHub release); run_tests.py; build/config/doc fixes.
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

## 2026-11-14 — Clean release build for other PCs, with Tesseract bundled
- `python build.py --release` → `release/Rerun/` + `release/Rerun-<version>.zip` (git-ignored):
  exe, templates, routines, README, content baseline, and a config made from
  config.example.yaml with every Discord field blanked. No stats, History, units, crest log,
  key, debug or GS Companion data.
- Checked before zipping: no personal file or folder, and none of the Discord tokens found in
  your own configs (config.yaml, dist/*/config.yaml*, backups) appears in any text file; the
  build stops with "NOT SAFE TO SHARE" otherwise.
- Tesseract 5.5.0 (UB Mannheim build, from ReStart's copy) bundled in `tesseract/` next to the
  exe: tesseract.exe + the 34 DLLs it imports (read from the PE headers) + eng.traineddata
  (29 MB) and THIRD_PARTY_NOTICES.txt. `rerun/ocr.py` looks there first.
- Checked: release built (94 MB zip); test_ocr 11/11 using only the bundled copy with ReStart
  hidden and PATH reduced to Windows' folders; the release exe starts from a fresh folder
  (no crash.log). Not yet tried on a second PC.

## 2026-11-14 — Updates: templates without a new exe, and a self-updating Rerun.exe
- New `rerun/updates.py`: one manifest per channel (stable/beta) on any static host, signed
  with the keygen's Ed25519 key (own domain prefix, so it can never pass as a Rerun key).
  Every file is checked by SHA-256; an older release than one installed is refused (serial).
- Templates/routines: downloaded to `.update_staging/`, moved into place only while no script
  runs (else when they stop, or at the next start); the template cache is reloaded. A file is
  replaced only if it is still what the build (`content_baseline.json`, written by build.py)
  or an earlier update (`content_state.json`) put there, so captured/edited ones are kept.
  `_meta.json` is merged per template and keeps a tuned threshold.
- Rerun.exe: offered with release notes, downloaded as `Rerun.update.exe`, checked, and a
  hidden helper swaps it in after Rerun (and the one-file bootloader) exit, keeping
  `Rerun.old.exe`, then restarts it ("Later" installs it when you quit).
- Settings › Updates: check on/off, channel, Check Now, status. Checks at start + every 6 h.
- `tools/publish_update.py` writes `updates_site/` (git-ignored) for upload.
- Off until `UPDATE_URL` in rerun/updates.py is set (no host chosen yet).
- Checked: tests/test_updates.py 12/12 (local web server, throwaway key: tampering, wrong
  key, replayed release, bad download, user edits kept, removals, app download); the real
  window installing a test release; the real signing key verifying a 190-file release; the
  swap helper with a locked exe and a closing parent process. All other suites pass.
  Not yet done: a real Rerun.exe build updating itself from a real host.

## 2026-11-14 — Phase 6: Discord bot upgrade (BETA, not yet live-verified)
- Alerts are embeds coloured by what happened (`alert_kind`): gold = Crest 4+ / Burst / hyper
  rare, red = stopped / stuck / failed / out of energy / game message, green = finished /
  counted / claimed, blue = other. Title, message, screenshot, instance and time; the daily
  summary is a blue embed.
- Buttons under every alert and status message: Stop, Resume (starts the instance's script
  when it isn't paused), Screenshot, Start Crest. Handled in on_interaction by custom id
  `rerun:<action>:<instance>`, so they keep working after a restart. Every press is checked
  against discord.allowed_user_ids (refusals are answered privately and logged).
- Live status board: one message per instance (pinned when the bot may pin), edited only when
  something changed, at most once a minute: status, script, quest, mode, runs, energy, up time,
  targets, last action, errors in 24 h. Message ids in discord_board.json (carried over by
  updates). `discord.status_board: false` turns it off.
- `/energy [instance]`: from the running script, else read from a screenshot
  (`Manager.energy`).
- Tests: tests/test_discord.py (5; fake interactions). 144/144 + gsc_app 16/16.
- Live check 18:47 (test bot from a copy of dist/Rerun, user's server "RERUN PROJECT",
  #rerun-bot): gold / red / green test alerts with buttons and the pinned status board posted;
  user confirmed everything looks good. Found first: the bot had no permissions in #rerun-bot
  (403 Missing Access, so alerts had never arrived); the user granted them. The user's ID was
  added to dist/Rerun/config.yaml (backup config.yaml.before_discord_id.bak); the installed
  copy in Downloads still has an empty allowed list.

## 2026-11-14 — Updates keep your data
- Replacing Rerun.exe in its folder always kept everything (data lives next to the exe; new
  settings are merged into config.yaml). A new copy started from another folder started empty.
- `rerun/migrate.py`: every start records its folder (%LOCALAPPDATA%\Rerun\installs.json). A
  copy with none of your data looks for earlier Rerun folders (that list + Downloads, Desktop,
  Documents, 3 levels; the source folder with .git is skipped) and `rerun/migrate_ui.py` asks
  "Bring your data over?" before sign-in (so the key comes too), listing each folder with its
  units / History / crest records / last use, the fullest preselected; Import, Start fresh
  (not asked again for that folder) or Choose folder…. Closing the window asks again next time.
- Copied, never moved: config.yaml (the new one kept as config.before_import.yaml), stats,
  crest log + screenshots, History, Units (roster, scans, names, targets, renames), license.json,
  summary state, GS Companion data (not raw/), templates you captured or tuned, your routines.
  Files the new copy already has are kept. migrated_from.json records what was copied.
- Settings › "Import from another Rerun…": replaces this copy's data with another folder's
  (this copy's data moved to backups/before_import_<time>/ first), then Rerun closes.
- On this PC it finds Downloads\Rerun\Rerun (191 units, 88 History, 105 crest records) and
  dist\Rerun (24 History, 46 crest records). Two folders are not merged: one is chosen.
- Tests: tests/test_migrate.py (5). 139/139 + gsc_app 16/16. Exe: a fresh copy shows the window
  and writes nothing before you choose.

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
