# GS Companion app

Browse the GS Companion scrape (`data/gscompanion/`) in Rerun's look:

- **Crest Palace**: which stages are open on a day (today by default, Rerun's 06:00 UTC-6
  game day). Shows each stage's boss, hazards and the crests that drop there. Green rows are
  open today.
  Each stage also has its **guide**: strategy, boss facts, every wave's gimmicks (and,
  on request, every enemy), recommended units by role ("Also fits" too), example teams
  with notes and a Team builder link, and the GSGL advisor guide it is based on. The
  "Your picks" column (✓ n) counts your units the guide recommends.
- **Crests**: all 138 crests, searchable and filterable by kind. Each one shows its stats
  for every level, where it drops (and which days), and the units it's recommended for.
- **Units**: all 428 units, searchable and filterable by element. Each one lists its
  recommended crests (best first), where each crest drops, **Farm today**, and the Crest
  Palace stages whose guides recommend it (with the role).

- **Week**: a Monday–Sunday grid of every stage, with today highlighted and, for each
  stage, how many of your units want crests from it.
- **Planner**: choose units, and it lists every crest they need by the day and stage
  you can farm it (today first).
- **Compare**: up to 3 crests side by side at every level.

**Your units** = units you star (★ column in Units) plus units in Rerun's unit scan
(`<Rerun>/units/roster.json` from the Compendium Counter; the exe asks for the folder via
Units › "Rerun folder…"). Stages and crests show "★ n" for how many of your units want
them.

Blue names are links; **‹ Back** (Alt+←) returns. **Text size** S / M / L. Drag the gap
between the list and the detail panel to resize them. Ctrl+F search, Esc clears it,
Ctrl+1–6 switch views. **Open on GSCompanion** opens the selected item in your browser.

It remembers the window, view, filters, text size, stars, plan and compared crests in
one small file: `data/gscompanion/companion_settings.json` (from source / inside Rerun)
or `GS Companion settings.json` next to the exe. Apart from that file it writes nothing
and never touches the emulator. It reads Rerun's unit scan but never writes to it.

**Pictures** (unit thumbnails, stage banners, crest icons) are read from
`data/gscompanion/images/`. To fetch or refresh them (474 files, about 6 MB, one at a time):

```
py gsc_app/fetch_images.py
```

Files already saved are skipped. The pictures belong to the site and the game, so they
stay in `data/`, which git ignores. Without them, the app works the same but shows no pictures.

**Stage guides** (`data/gscompanion/stage_guides.json`, 18 stages) come from each stage's
own page on GS Companion, which credits the GSGL Official Discord Advisor Team. To fetch
them, or refresh them after the site updates:

```
py gsc_app/fetch_guides.py --refresh
```

It saves each page under `data/gscompanion/raw/stages/`, writes the guides file, and saves
any new pictures they use (enemy faces, unit thumbnails). Without the file, stages show
their hazards list as before.

## Run it on its own (works now)

Double-click `gsc_app/Run GS Companion.bat`, or from Rerun's folder:

```
py -m gsc_app
```

### As an exe

`dist/GS Companion/GS Companion.exe` (about 25 MB) is one file with the data and pictures
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

## Add it to Rerun (NOT done yet)

Nothing in Rerun has been changed. When you want the tab, `rerun_tab.patch` makes the
only change needed: two small edits to `rerun/gui.py` that add a **Companion** tab
as the last tab (the Discord tab keeps its position).

```
git apply gsc_app/rerun_tab.patch
```

To take it out again: `git apply -R gsc_app/rerun_tab.patch`.

If `gsc_app/` is ever missing, Rerun simply leaves the tab out.

### Rerun.exe (packaged build)

`build.py` doesn't bundle `gsc_app` or `data/gscompanion/` yet. For the exe to have the tab,
these changes are also needed in `build.py` (not made):

- add `"--hidden-import", "gsc_app.page"` to the PyInstaller command (to be safe: the
  import sits inside a try block)
- copy `data/gscompanion/*.json` to `dist/Rerun/data/gscompanion/`

Running from source (`Run Rerun.bat` / `python main.py`) needs neither.
