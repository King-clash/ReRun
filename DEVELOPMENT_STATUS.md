# Development status — source of truth for new sessions

**Read this first, then PROJECT_ROADMAP.md, ARCHITECTURE.md, TESTING.md.**

- Source: `C:\Users\dandr\Documents\Rerun` (git, branch main, local only — never push)
- Installed app: `C:\Users\dandr\Downloads\Rerun\Rerun` (Rerun.exe; holds the user's LIVE config,
  stats, history — never overwrite them; ask before closing Rerun)
- Python: `%LOCALAPPDATA%\Programs\Python\Python312\python.exe` (not on PATH)
- Git: `C:\Program Files\Git\cmd\git.exe` (prepend to PATH in a fresh shell)

## Phase 3 (Unit Roster) — BETA, 2026-11-14
Built from real captures; live full scan pending: user stops farming, opens Units (top of list),
starts Compendium Counter. Check: units/roster.json fills, uncertain names have debug/ frames,
grid scrolling dedupes. GSCompanion: never fetch/cache its data (robots.txt blocks Anthropic
crawlers) — link-out only. Phase 4 (Compendium) builds on units/scans.jsonl (quest_clears per scan).

## Current phase
Milestone A · Phase 2 COMPLETE (Start path live-verified 2026-11-14 14:33; Resume/relaunch/relogin
simulator-only). Phase 3 Unit Roster BETA (built, live scan pending); Phase 4 Compendium next.
Phase 2 live check: on Start, the log should show "Selecting Past Party", "Ticking Include AI"
(or straight to Apply), "Past Party applied with Include AI - dialog closed"; capture the Past
Party dialog as tests/fixtures/past_party_dialog.png.

## Completed
- Phase 0 (2026-11-14): recovery, git baseline f4df578, backups, docs, baseline 54/54.
- Phase 1 (2026-11-14, BETA): crest ledger (rerun/crest_stats.py), reconstruction, dashboard
  tiles, /crests. 65/65 tests. Not yet live-verified with the rebuilt exe.

## Active task
None open. Phase 2 is done; Phase 3 awaits its live scan.

## Outstanding (Milestone A)
3 Units (live scan) · 4 Compendium · 5 Compendium Farm · 6 Discord.

## Known issues / facts
- History is capped at 2000 entries and deletes the oldest (with thumbnails) — all-time crest stats
  must not depend on it (Phase 1 ledger fixes this).
- User's live config: `discord.allowed_user_ids` is empty, so Discord control commands are refused.
- Crest "keep" default is "4+ and Burst only": Lv4 crests are scrapped (in-game the loop is set to
  end on Lv4+ drops).
- Rerun.exe was running (2 processes) and farming Crest during the 2026-11-14 session.
- Phase 5 navigation templates (`templates/training`, `templates/exploring`) do not exist yet.

## Last successful tests
2026-11-14 92/92 (`py run_tests.py`; see TESTING.md).

## Last commit
See `git log` (Phase 1 commit follows e795766).

## Installed build
2026-11-14 13:54: Phase 1 build installed (exe only). Rollback: copy
`backups/preinstall_20261114_135429/Rerun.exe` back. Phase 1 live check pending: after the next
Crest farming session, confirm crest_log.jsonl gains "run" and live "drop" records and the
dashboard tiles move.

Phase 1 recording verified live 13:57–14:01 (runs + crests + titles). Double-count fix installed
14:10; History re-import fix installed 14:16 (backup backups/preinstall_20261114_141610). Verified on
the installed app: restart added 0 records; counted crests 76 = History 76. The installed
crest_log.jsonl keeps 11 duplicate "history" records from the 14:10 restart, ignored at read time
(do not delete them).

## Next actions
1. Live-verify that a crest after a potion refill is logged once (needs a farm that runs out of energy).
2. Phase 3 live full scan (see top section), then Phase 4 Compendium.
