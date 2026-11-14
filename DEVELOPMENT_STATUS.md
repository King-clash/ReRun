# Development status — source of truth for new sessions

**Read this first, then PROJECT_ROADMAP.md, ARCHITECTURE.md, TESTING.md.**

- Source: `C:\Users\dandr\Documents\Rerun` (git, branch main, local only — never push)
- Installed app: `C:\Users\dandr\Downloads\Rerun\Rerun` (Rerun.exe; holds the user's LIVE config,
  stats, history — never overwrite them; ask before closing Rerun)
- Python: `%LOCALAPPDATA%\Programs\Python\Python312\python.exe` (not on PATH)
- Git: `C:\Program Files\Git\cmd\git.exe` (prepend to PATH in a fresh shell)

## Current phase
Milestone A · Phase 1 — Crest 4+ and Burst tracking (IN PROGRESS)

## Completed
- Phase 0 (2026-11-14): recovery, git baseline f4df578, backups, docs, baseline 54/54.

## Active task
Phase 1: crest ledger + stats + reconstruction from History + dashboard tiles + /crests.

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
2026-11-14 baseline 54/54 (see TESTING.md).

## Last commit
f4df578 Baseline

## Next actions
1. Finish Phase 1, run all suites, commit.
2. Phase 2 Past Party verification flow.
