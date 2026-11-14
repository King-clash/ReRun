# Rerun — Roadmap

Status keys: COMPLETE (implemented + tests + live verified) · BETA (implemented, not verified live)
· IN PROGRESS · INCOMPLETE · BLOCKED · PLANNED

## Existing features (before this roadmap)

| Feature | Status |
|---|---|
| Any Quest, Crest, Login & Mail | COMPLETE (live verified 2026-11-14) |
| Arena, Grand Crusade, Queue, Mines, Multiplayer Farm, Raids, Secret Equip, GC Area, Helper Rewards, Compendium Counter, Chain | BETA |
| iOS-style UI, History tab, tray, hotkeys, scheduler, daily summary, setup check, template health | COMPLETE |
| OCR (Tesseract via ReStart), energy reading | COMPLETE |
| Discord alerts + slash commands | COMPLETE (allowed_user_ids empty in the user's config → control commands refused) |

## Milestone A — original core features

| Phase | Feature | Priority | Status | Notes |
|---|---|---|---|---|
| 0 | Recovery, Git, baseline, backups, docs | P0 | COMPLETE | commit f4df578; backup in backups/ |
| 1 | Crest 4+ / Burst tracking, stats, reconstruction, /crests | P0 | BETA | ledger + tiles + /crests done; needs a live run with the rebuilt exe. Not yet: daily-summary crest line, History-tab crest analytics page (Phase 12) |
| 2 | Always re-select Past Party (verified ticks, Resume, relaunch, relogin) | P0 | PLANNED | extends loop_farm.py party flow |
| 3 | Unit Roster (OCR), /units | P1 | PLANNED | needs real Units-list/Compendium captures |
| 4 | Compendium Counter UI, scans history, /compendium | P1 | PLANNED | builds on compendium_counter.py (Beta) |
| 5 | Compendium Farm (Training > Cross Battle) | P1 | PLANNED | templates/training, templates/exploring not present yet — BLOCKED on captures |
| 6 | Discord embeds, buttons, status board, /energy | P1 | PLANNED | extend discord_bot.py |

## Milestone B — automation foundation
Phase 7 shared services (run tracker, screenshot manager, typed events) · Phase 8 watchdog/recovery,
persistent state, emergency stop (F12 + Discord exist already). PLANNED.

## Milestone C — account management
Phase 9 advanced units · Phase 10 inventory · Phase 11 account snapshots. PLANNED.

## Milestone D — farming intelligence
Phase 12 crest analytics (crest names) · Phase 13 quest DB · Phase 14 farming stats/graphs. PLANNED.

## Milestone E — farm management
Phase 15 Farm Manager (extends Chain/Queue) · Phase 16 energy manager + /energy. PLANNED.

## Milestone F — remote management
Phase 17 advanced Discord · Phase 18 notification centre · Phase 19 reports. PLANNED.

## Milestone G — development tools
Phase 20 diagnostics (Templates tab already has viewer/test/Read Text) · Phase 21 replay
(FakeDevice exists) · Phase 22 maintenance. PLANNED.

## Milestone H — future
Phase 23 plugins (SCRIPTS registry exists) · Phase 24 multi-instance (exists in-process; user has one BlueStacks). PLANNED.

## Dependencies / blockers

- Phase 5 needs real captures of Exploring > Tower of Initiation > Training > Cross Battle
  (`templates/training`, `templates/exploring` named in the brief do not exist in this project
  or in the installed copy — check ReStart's unpacked reference).
- Phase 3/4 OCR work needs real Units-list and Compendium screenshots.
- Discord remote control needs the user's ID in `allowed_user_ids`.
- GSCompanion: research pending (no API assumed).
