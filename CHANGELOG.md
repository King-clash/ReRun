# Changelog

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
