# Account Manager and Macro Farming

Rerun now has two main workspaces (the first two tabs). **Account Manager** owns everything about an account.
**Macro Farming** consumes the selected account and owns farming. They share one data layer (`rerun/accounts.py`
and friends); neither keeps its own copy of account data.

Status words used below: **Done and tested** = covered by an automated test that ran. **Done, not live-verified** =
works against the simulator/fixtures, never run on the real game. **Not built** = said so, nothing pretends otherwise.

## Audit (what existed before)

| Area | Before | Now |
|---|---|---|
| Energy reading | `ocr.read_energy`, per emulator only | stored per account with provenance, scan history, chart |
| Unit roster + targets | one global roster (`units/`) | the original account ("Main") keeps it untouched; every new account gets its own `accounts/<id>/units/` |
| Crest ledger | `crest_log.jsonl`, per emulator | attributed to accounts by session / emulator link; Crest Vault on top |
| Game-day reset | Crest only (`crest_stats.game_day`) | `checklist.period_start` (daily + weekly), same 6 AM UTC-6 clock |
| Discord | per-instance alerts, quiet hours, ping kinds | account-prefixed alerts, per-account mute/ping, daily report per account, low-energy and event alerts |
| Scripts | 16 (3 verified) | unchanged; shown in a catalogue, 2 wired to checklist tasks |
| Settings page | script settings + app settings in one page | script settings moved into Macro Farming; app settings stay in **Settings** |

The 13 unfinished (BETA) scripts: Arena, Grand Crusade, GC Area, Queue (GC + Crest), Mines, Multiplayer Farm,
Helper Rewards, Raid Tickets, Raid Host, Raid Guest, Secret Equip, Compendium Counter, Chain. **None was removed or
changed.** Overlaps noticed (not consolidated, because merging untested scripts would break them with no way to check):
Raid Tickets / Host / Guest share a flow; Grand Crusade / GC Area / Queue all run the Grand Crusade screens;
Any Quest and Crest share the loop-farm base. They stay separate until each has been run on the real game.

## Account Manager

| Feature | Status |
|---|---|
| Create, rename, label, note, link to an emulator, switch, remove (files moved to `accounts/_removed/`, not deleted) | Done and tested |
| Data isolation (values, tasks, goals, crests, sessions, units, settings per account) | Done and tested |
| Values with provenance: manual / scanned / verified / unverified; per-field "maintain by hand" lock | Done and tested |
| Validation (ranges, whole numbers, energy <= max, readable messages) | Done and tested |
| Scan: energy and max energy from the emulator; uncertain readings parked, last reliable value kept, scan history, last successful scan | Done and tested (reader itself was verified earlier on real screens) |
| Scan: unit roster | Existing Compendium Counter (BETA), started from the Scanning page |
| Scan: player level/name, gems, gold, tickets, inventory, task screens | **Not built** - no reader exists; marked "Not supported yet"; enter by hand. Needs screenshots of those screens |
| Dashboard: energy, refill estimate (only if you set minutes per point), currencies, checklist, goals, farming, 4 charts, recent changes | Done and tested; charts use recorded data only |
| Checklist: daily/weekly, game-clock resets, manual done/undo, priorities, custom tasks, states (completed / not yet verified / in progress / failed / available), duplicate-run prevention, history | Done and tested |
| Checklist automation: Login reward -> Login & Mail (verified script), Raid tickets -> Raid Tickets (BETA, asks first) | Done and tested against the simulator; a script's "done" stays *Not yet verified* until you confirm |
| Weekly reset weekday | **Assumption**: Monday 6 AM UTC-6. Configurable per account; the real game day is not known to Rerun |
| Goals: resource / unit level / crest / custom; add, edit, remove, priority, progress, history, explained suggestions | Done and tested |
| Run estimates | Only when the ledger holds 20+ runs and a match; otherwise says "not enough data" |
| Crest Vault: search, filter, sort, compare, duplicates, your own keep/discard rules, add by hand, substats by hand | Done and tested; **recommendations only**, no code path scraps or discards |
| Substats read from the screen | **Not built** (no reader) |
| Events: manual add/edit/delete, done per account, reminders to Discord | Done and tested. No shared event list: none verified, so none imported |
| Reports: daily report per account (view, send to Discord), activity history with filters | Done and tested (sending needs Discord connected) |
| Safety: allow automation, dry run, daily limit, session limit, allowed scripts, emergency stop, ToS warning | Done and tested |
| Multi-account on one emulator | Architecture only: link, confirm-which-account-is-open gate, attributed sessions, run plan. **Switching accounts is not automated** (no reader for the login/profile screens, so the right account could not be verified) |

## Macro Farming

| Feature | Status |
|---|---|
| ToS warning, always visible at the top of the workspace (every section) | Done and tested |
| Account strip: selected account, energy, minutes farmed today vs limit, top goal suggestion, dry-run / automation-off flags | Done and tested |
| Dashboard (existing, unchanged): instances, Start / Pause / Stop, totals, crest stats, live view; new Dry Run button | Existing + Dry Run tested |
| Routines catalogue: every script with Verified/Beta, missing templates, Start, Dry Run, Settings | Done and tested (draws; Start goes through the same checks as before) |
| Routine settings (team, stage, targets, automation are the per-script settings the scripts already have) | Existing form moved here |
| Dry run: scripts run, taps/swipes/keys/app start-stop are listed instead of sent, then it stops | Done and tested with a fake device; not run against a real emulator |
| Session limit / daily limit / automation switch enforced at start | Done and tested |
| Session history per account (routine, emulator, duration, status, results, errors); dry runs marked | Done and tested |
| Emergency Stop (also F12) and status light (stopped / running / paused / error) | Done and tested |
| Farming results update the account (crests via the ledger, energy read while farming) | Done and tested |
| Pause/Resume | Existing Pause button |
| Separate "Team" and "Stage" pages | **Not built as separate pages**: those choices live in each routine's settings; a page that only re-labelled them would be a fake |

## Design

Built on the existing iOS-style kit (`rerun/ios.py`), not replaced. Added: side navigation with keyboard control
(Up/Down/Home/End), metric cards, progress bars that ease unless Windows' "Show animations" is off, status pills
(always text + colour), bar charts with honest empty states, banners, wrapped labels that follow the window width,
visible keyboard focus on buttons, a number type scale. Light and dark both work (they follow the system).
Minimum window size is now 1060x800 (the warning and account strip need the room).

## Known gaps

* Nothing in this release has been run against the real game; the screens it relies on are only the ones with fixtures.
* No screen readers for gems, gold, tickets, level, name, inventory or task screens.
* Account switching inside one emulator.
* Discord slash commands are not account-aware yet (alerts are).
* Ambiguous history: when two accounts are linked to the same emulator, crests logged *before* sessions were recorded
  belong to neither vault (Rerun will not guess).
* Weekly reset weekday is an assumption until confirmed in the game.
