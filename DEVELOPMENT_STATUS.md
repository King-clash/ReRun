# Development status — source of truth for new sessions

**Read this first, then PROJECT_ROADMAP.md, ARCHITECTURE.md, TESTING.md.**

- Source: `C:\Users\dandr\Documents\Rerun` (git, branch main; local only until a GitHub repo exists — then push/release ONLY via
  `py tools/publish.py X.Y.Z --push`, and only when the user asks)
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

## Units + Companion (2026-11-14, user request)
Units and Compendium are one tab; the GS Companion app is the last tab (Companion), linked both
ways. GS Companion unit names take priority over OCR names on a clear match (user decision,
overrides the brief's "never overwrite" for names read by OCR; manual names/fields are never
touched). Data stays local: data/gscompanion (git-ignored), copied next to the exe by build.py.
The installed app needs that folder next to Rerun.exe for the tab and the names.
Installed 17:11 (83b5283): 89 units renamed on start, 11 uncertain; backup
backups/preinstall_20261114_171145 holds the roster before the renames.

## Installed build
2026-11-14 17:32: c5e9c31 (Units pictures + Live View 30 fps), exe only; 96 user files unchanged;
relaunched, no crash.log, the Live View stream started. Backup backups/preinstall_20261114_173247.
Not in this exe: the new app icon (another session's uncommitted work in rerun/appicon.py,
rerun/assets/, build.py).

## Crest start-from-Home (v1.0.3) — LIVE-VERIFIED from Home (2026-11-14): Home > Exploring > Crest Palace > Cursed Claw > quest > farming. Back-from-battle untested.
Needs per-palace templates: crest_palace_target (tile) and quest_list_entry (row; _2/_3/_4 for other palaces). Rotating palaces break them.
(older note:) 
Crest goes Home first on Start (setting `start_home`, default on), then walks Exploring > Crest
Palace > palace tile > quest. The installed templates have no `crest_palace_target` /
`crest_palace_<day>` tile, so Crest stops with a "missing template" message until one is captured
(Templates tab) or the setting is turned off. Live check: log should read "Getting to the Home
screen first" > "On the Home screen" > Exploring > Crest Palace > "Opened palace" > quest.
Releases: `py tools/publish.py X.Y.Z --push` (tests, `build.py --release`, tag, GitHub release for
King-clash/ReRun; only when the user asks). The signed in-app update system (rerun/updates.py) is
separate and stays off until `UPDATE_URL` is set.

## How a release is made (since 1.0.3)
1. Work on a branch, open a PR into `main`, merge it (PR checks must pass once CI exists).
2. Start from the merged `main` (`git switch -c publish/X.Y.Z origin/main`) with a clean tree.
3. Write `release_notes/vX.Y.Z.md` in plain language (see the `github-publish-notes` skill) and commit it.
4. `py tools/publish.py X.Y.Z --push` - tests, `build.py --release` (clean zip), tag, push, GitHub release.
5. Re-read the live release page. Never release from a feature branch or with uncommitted work.
`BUILDS.md` / `builds.jsonl` are generated locally and git-ignored; line endings are LF (`.gitattributes`).

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

2026-11-14 16:41: build 382e212 installed (exe only; 95 user files hash-verified unchanged;
relaunched, no crash.log). Rollback: `backups/preinstall_20261114_164106/Rerun.exe`.

## Key system (2026-11-14, user request)
Rerun needs a key (rerun/license.py, sign-in rerun/license_gate.py). Signing key:
%LOCALAPPDATA%\Rerun Keygen\signing_key.txt (back it up; never commit). Public key in
rerun/license.py. Key generator: tools/keygen.py / dist/Rerun Keygen/. Before installing a
key-system build, the user needs a key for themselves (or the installed app stops at sign-in).
Built to dist/Rerun (key system)/ because dist/Rerun/Rerun.exe was running.

## Next actions
1. User: Remove the junk units and correct uncertain names in the Units tab (their decision).
2. Live-verify that a crest after a potion refill is logged once (needs a farm that runs out of energy).
3. Phase 4 build 387b9f1 installed 16:52 (exe only, 95 user files unchanged, no crash.log; backup
   backups/preinstall_20261114_165231). User to check the Compendium tab and set targets.
4. Phase 5 Compendium Farm: needs captures of Exploring > Tower of Initiation > Training > Cross Battle.
