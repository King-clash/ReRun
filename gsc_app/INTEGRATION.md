# GS Companion app

Browse the GS Companion data (`data/gscompanion/`) in Rerun's look. Views (Ctrl+1–7):

- **Today**: the stages open on today's game day (Rerun's 06:00 UTC-6 reset), best for
  your units first, each with the crests your units still need from it and its **Ready**
  score: how many of the guide's roles your units can fill (★ = you own a whole example
  team). While the app is open it notices the reset, refreshes and says what's open (the
  taskbar button flashes if the window is in the background).
- **Week**: Monday–Sunday grid of every stage with today highlighted, ★ crests your units
  need and ✓ readiness; use it for other days.

  Clicking a stage (in either view, or any blue stage name) shows its **guide**:
  strategy, boss facts, every wave's gimmicks (and, on request, every enemy), recommended
  units by role ("Also fits" too), example teams with notes and a Team builder link, the
  crests that drop there, and the GSGL advisor guide it is based on. A stage link opens
  in Today when the stage is open today, otherwise in Week.
- **Crests**: all crests, searchable; stats per level, where each drops, which of your
  units still need it and which have it.
- **Units**: all units, searchable; recommended crests (tick "has it" for crests a unit
  already has; they drop out of Today, the Planner and the counts), the Crest Palace
  stages that recommend it, and its **kit**: skill, arts, true arts, super arts,
  passives, true weapon, equip slots and tags.
- **Team**: pick a stage and up to 4 units (＋ column). It checks the team against the
  stage guide: roles covered or missing (with your units that would fill them), hazard
  warnings (element / race killers, negated damage, Taunt Killer, HP auto-recovery
  killer), and the example teams with how many of each you own. **Suggest a team**
  builds one from your units. It's a rule of thumb, not a promise of a clear.
- **Planner**: choose units, and it lists every crest they still need by the day and
  stage you can farm it (today first).
- **Compare**: up to 3 crests side by side at every level.

**Search everything** (Ctrl+F, box at the top): stage names, bosses and guides, crest
effects, unit names, nicknames and kit text (e.g. "taunt", "freeze"). Esc closes it.

**Your units** = units you star (★ column in Units) plus units in Rerun's unit scan
(`<Rerun>/units/roster.json` from the Compendium Counter; the exe asks for the folder via
Units › "Rerun folder…"). Scan names that match no GS Companion unit are counted in the
Units view ("n not matched").

Blue names are links; **‹ Back** (Alt+←) returns. **Text size** S / M / L. Drag the gap
between the list and the detail panel to resize them. **Open on site** opens the selected
item on gscompanion.com in your browser.

It remembers the window, view, filters, text size, stars, crests units have, team, plan
and compared crests in one small file: `data/gscompanion/companion_settings.json` (from
source / inside Rerun) or `GS Companion settings.json` next to the exe. It never touches
the emulator, and reads Rerun's unit scan but never writes to it.

## Update data

**Update data** (top of the app) downloads the latest from gscompanion.com while you keep
using the app: the Crest Palace, crests (with the GSGL recommendations), units, all 18
stage guides, kit details for units it doesn't have yet, and any new pictures. One page
at a time with a pause between them; a page that doesn't look right never replaces good
data; press it again to stop (what was saved is kept). The footer turns orange when the
data is over a month old. The same from a terminal:

```
py gsc_app/update_data.py                 # everything (unit kits: only new units)
py gsc_app/update_data.py --all-units     # also re-read every unit's kit (~7 minutes)
py gsc_app/update_data.py --only guides   # lists, guides, units or pictures
```

From source it writes `data/gscompanion/`; the exe writes a `data/gscompanion/` folder
next to itself (and uses it from then on). The data belongs to the site, the GSGL advisor
team and the game, so it stays in `data/`, which git ignores. Without pictures, kits or
guides the app still works and simply leaves those parts out.

## Run it on its own (works now)

Double-click `gsc_app/Run GS Companion.bat`, or from Rerun's folder:

```
py -m gsc_app
```

### As an exe

`dist/GS Companion/GS Companion.exe` (about 27 MB) is one file with the data and pictures
inside, so you can copy it anywhere. Rebuild it after refreshing data or pictures:

```
py gsc_app/build_exe.py
```

If a `data/gscompanion/` folder sits next to the exe, it uses that instead of its built-in
copy. If a `config.yaml` sits next to it, it follows its light/dark setting; otherwise it
follows Windows. This build is separate from Rerun's `build.py` and `Rerun.exe`.

Tests: `py gsc_app/test_page.py`. The last test applies the patch below to a
**temporary copy** of Rerun and starts the real Rerun window there. Your own files
are never changed.

## Inside Rerun (done 2026-11-14)

Rerun has a **Companion** tab (the last tab; `rerun/gui.py` `_build_companion`). If
`gsc_app/` is missing, Rerun simply leaves the tab out. Inside Rerun the companion always
reads Rerun's own `units/roster.json` (no "Rerun folder…" button) and is linked both ways
through `RerunLink` (read-only):

- Rerun **Units** tab → **GS Companion** button: opens the selected unit here.
- A unit's panel here → **YOUR ACCOUNT (RERUN)**: quest clears, target, progress and the
  change since the last scan, and **Show in Rerun's Units tab**.
- A scan, a target or a name correction in Rerun refreshes this tab (`rerun_changed`).
- **Correct Name** in Rerun suggests GS Companion's spelling.

**GS Companion's unit names take priority** (rerun/gsc_data.py `reference_name`, applied
by the Manager at start-up and to every scan): when one GS Companion unit clearly matches a
name read from the game ("Clyde, the Crimson Sword God", "IDivine ConquronGediNies SF"),
the unit takes the site's name; its race / element come from the site too when misread.
Names you typed (Correct Name) are never changed, a close call or a clash is left as read,
the old spelling is kept as an alias and every rename is logged in `units/renames.jsonl`.

`build.py` adds the `gsc_app` modules to Rerun.exe and copies your local
`data/gscompanion/` (not `raw/`) next to it; the data is never inside the exe or in git.
