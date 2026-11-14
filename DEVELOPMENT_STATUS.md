# Development status — source of truth for new sessions

**Read this first, then PROJECT_ROADMAP.md, ARCHITECTURE.md, TESTING.md.**

- Source: `C:\Users\dandr\Documents\Rerun` (git, branch main, local only — never push)
- Installed app: `C:\Users\dandr\Downloads\Rerun\Rerun` (Rerun.exe; holds the user's LIVE config,
  stats, history — never overwrite them; ask before closing Rerun)
- Python: `%LOCALAPPDATA%\Programs\Python\Python312\python.exe` (not on PATH)
- Git: `C:\Program Files\Git\cmd\git.exe` (prepend to PATH in a fresh shell)

## Current phase
Milestone A · Phase 2 — Always re-select Past Party (next)

## Completed
- Phase 0 (2026-11-14): recovery, git baseline f4df578, backups, docs, baseline 54/54.
- Phase 1 (2026-11-14, BETA): crest ledger (rerun/crest_stats.py), reconstruction, dashboard
  tiles, /crests. 65/65 tests. Not yet live-verified with the rebuilt exe.

## Active task
Phase 2: rename the party setting to "Always re-select Past Party" (default on for Crest), with a
migration from `party: Last Party/Current Party`; verify Include AI is ticked before Apply; re-apply
on Start, relaunch, relogin, new quest entry and Resume, never on Redeploy.

## Outstanding (Milestone A)
Phase 2 Past Party · 3 Units · 4 Compendium · 5 Compendium Farm · 6 Discord.

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

Phase 1 recording verified live 13:57–14:01 (runs + crests + titles). Double-count fix built at
14:04 (dist/) — install pending the user's OK to close Rerun.

## Next actions
1. Install the double-count fix build (exe only) when the user agrees; then verify after a potion
   refill that the crest is logged once.
2. Phase 2 Past Party verification flow (see Active task).
3. Phase 3 needs real Units-list / Compendium screenshots — ask the user to open those screens.
