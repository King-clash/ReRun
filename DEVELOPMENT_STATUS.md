# Development status — source of truth for new sessions

**Read this first, then PROJECT_ROADMAP.md, ARCHITECTURE.md, TESTING.md.**

- Source: `C:\Users\dandr\Documents\Rerun` (git, branch main, local only — never push)
- Installed app: `C:\Users\dandr\Downloads\Rerun\Rerun` (Rerun.exe; holds the user's LIVE config,
  stats, history — never overwrite them; ask before closing Rerun)
- Python: `%LOCALAPPDATA%\Programs\Python\Python312\python.exe` (not on PATH)
- Git: `C:\Program Files\Git\cmd\git.exe` (prepend to PATH in a fresh shell)

Note: the checkout is currently on branch `data/gscompanion` (another session's GSC app work,
`gsc_app/`, is committed there too); `main` stops at fdac815.

## Phase 3 (Unit Roster) — BETA, 2026-11-14
Full live scan 15:22–16:40 (build 81e47c8): 191 units, all five elements, 189 with quest clears,
27 names uncertain (incl. junk "wee", "ae", "sc" — removable with the Units tab's Remove button).
Water/Earth elements from that scan are stored "uncertain" (icons not yet verified in that build);
a rescan on 382e212 upgrades them. GSCompanion: link-out only from Rerun (robots.txt).
Phase 4 (Compendium) builds on units/scans.jsonl (quest_clears per scan).

## Phase 4 (Compendium) — BETA, 2026-11-14
rerun/compendium.py + Compendium tab + dashboard line + /compendium. Targets in
units/targets.json. Checked against a temp copy of the live data (191 units). Not live-verified in
the installed app yet. Weekly automatic scans not done (no navigation to the Units list).

## Completed
- Phase 0: recovery, git baseline f4df578, backups, docs.
- Phase 1 (BETA): crest ledger, reconstruction, dashboard tiles, /crests; live-verified 13:57.
- Phase 2 (COMPLETE, Start path live-verified 14:33; Resume/relaunch/relogin simulator-only).
- Phase 3 (BETA): see above.

## Outstanding (Milestone A)
5 Compendium Farm (BLOCKED: no Training/Exploring templates) · 6 Discord.

## Known issues / facts
- History is capped at 2000 entries and deletes the oldest (with thumbnails) — all-time crest stats
  must not depend on it (Phase 1 ledger fixes this).
- User's live config: `discord.allowed_user_ids` is empty, so Discord control commands are refused.
- Crest "keep" default is "4+ and Burst only": Lv4 crests are scrapped (in-game the loop is set to
  end on Lv4+ drops).
- Rerun.exe was running (2 processes) and farming Crest during the 2026-11-14 session.
- Phase 5 navigation templates (`templates/training`, `templates/exploring`) do not exist yet.

## Last successful tests
2026-11-14 65/65 (see TESTING.md).

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

2026-11-14 16:41: build 382e212 installed (exe only; 95 user files hash-verified unchanged;
relaunched, no crash.log). Rollback: `backups/preinstall_20261114_164106/Rerun.exe`.

## Next actions
1. User: Remove the junk units and correct uncertain names in the Units tab (their decision).
2. Live-verify that a crest after a potion refill is logged once (needs a farm that runs out of energy).
3. Phase 4 build 387b9f1 installed 16:52 (exe only, 95 user files unchanged, no crash.log; backup
   backups/preinstall_20261114_165231). User to check the Compendium tab and set targets.
4. Phase 5 Compendium Farm: needs captures of Exploring > Tower of Initiation > Training > Cross Battle.
