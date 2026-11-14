# Rerun — Architecture

Rerun is a Windows desktop (Tkinter) Grand Summoners automation app, a recreation of ReStart.
It drives BlueStacks over ADB, reads the screen with OpenCV template matching and Tesseract OCR,
and is controllable from the desktop UI, tray, global hotkeys and a Discord bot.

The game runs **portrait**: frames are **720×1280** (BlueStacks display set to 1280×720).
Package: `jp.goodsmile.grandsummonersglobal_android`.

## Layout

```
main.py                 entry point (python main.py / Rerun.exe); writes crash.log on failure
tools/publish.py        release: tests -> bump version -> build -> zip -> tag [--push -> gh release]
build.py                one-file PyInstaller build -> dist/Rerun/Rerun.exe (+ templates, routines, README, config.example.yaml; never config.yaml)
config.yaml             user config (instances, per-script settings, Discord token) — NOT in git
config.example.yaml     tokenless copy of the default config
stats.json              lifetime counters per instance ("<script>.<key>": n) — user data
history/                history.jsonl + thumbs/ — user data
templates/              ReStart-compatible template PNGs + _meta.json (thresholds, provenance, resolution)
routines/               user YAML routines (rerun/engine.py)
tests/                  script-style suites (run all: py run_tests.py) + fixtures/ (real 720x1280 game screenshots)
rerun/
  gui.py                App(...mixins, tk.Tk): core (start-up, event loop, tray, closing) + run_app
  gui_<tab>.py          one mixin per tab: gui_updates (updates+key), gui_dashboard (+Live View), gui_settings
                        (+setup check), gui_templates, gui_history, gui_units (+Companion), gui_discord, gui_log;
                        gui_common holds the shared imports, constants and small widgets
  events.py             typed shape of the events Manager.emit sends; configcheck.py warns about bad config keys
  textnav.py            find palace / quest names on screen from OCR words (Crest fallback)
  runlog.py             persistent rerun.log (rotated)
  ios.py                iOS-style widget kit (Card, switches, alerts, tab bar, toasts, light/dark)
  manager.py            Manager: config, instances, start/stop/pause/resume, worker threads,
                        events (emit/listeners), notify, scheduler, daily summary
  engine.py             Context dataclass (per-run services) + YAML routine Runner
  adb.py                Device (persistent shell, raw screencap), FakeDevice, adb discovery
  vision.py             TemplateStore + Vision (grey coarse pass + colour refine, health, brightness)
  ocr.py                Tesseract wrapper (ReStart's bundled copy), read_energy, read_energy_cost
  loop_count.py         reads/sets the Auto-Loop "Loops" counter
  history.py            History: append-only jsonl with thumbnails, capped at 2000 (compacts!)
  stats.py              Stats: counters + uptime, saved to stats.json
  discord_bot.py        DiscordBot: alerts (text + screenshot), slash commands
  unit_screens.py       Units-grid card finder + unit-page reader (OCR, element, quest clears)
  units.py              UnitRoster: units/roster.json, scans.jsonl, aliases.json
  crest_stats.py        CrestLedger / CrestStats (crest_log.jsonl)
  errlog.py             rate-limited error.log for errors that must not stop a script
  setup_check.py        Settings > Setup check
  restart_import.py     imports templates from a local ReStart install
  tray.py, appicon.py   tray icon (pystray), app icon (assets/rerun_icon.png)
  updates.py            signed update manifest: templates/routines (never over your edits,
                        staged then committed while idle) and Rerun.exe self-replacement;
                        published by tools/publish_update.py; Settings › Updates
  scripts/
    base.py             BaseScript: state machine loop (STATES -> handle_<state>), common popups,
                        watchdogs (stuck / no-progress / unknown screen), 24/7 crash relaunch +
                        daily-reset relogin, OCR helpers, record()/count()/notify()
    loop_farm.py        LoopFarmScript: quest -> party (Past Party / Include AI / Apply) ->
                        Battle -> Auto-Loop -> Drop Info (run counted on rising edge) -> Redeploy
    energy.py           EnergyMixin: potion choice by icon row, caps, crystals only if enabled
    crest.py            CrestScript(LoopFarmScript): Equip Crest screen, rarity by icon + OCR title
    any_quest.py, login_mail.py                       live-verified
    arena, grand_crusade, queue_gc_crest, mines, multi_farm, raids, secret_equip,
    gc_area, helper_rewards, compendium_counter, chain  Beta (not run live)
```

## Runtime flow

1. `Manager.start(instance)` spawns a worker thread → builds a `Context` (device, vision, stats,
   history, log/notify callbacks, stop/pause events, params) → instantiates the script class with
   per-instance settings → `script.run()`.
2. `BaseScript.run()` loops: `grab()` frame → `detect_state()` (first visible template in STATES,
   with lit/dimmed checks and context templates) → `handle_<state>()`; `checkpoint()` honours
   stop/pause events. Exceptions: `Done` (finished normally), `Finished` (needs the user),
   `StopRoutine` (stopped), `MissingTemplate`.
3. Scripts report via `count()` → Stats, `record()` → History (+ listeners → GUI/Discord),
   `notify()` → Manager.notify → log + GUI event + Discord message with screenshot.
4. Only one worker per instance (`Manager.start` refuses if starting/running/paused).

## Events

`Manager.emit(dict)` with types `log`, `status`, `notify`, `history`. The GUI polls a queue fed by
listeners (`_poll_events`). There is no typed event bus yet (planned: Milestone B).

## Data stores (current)

| Store | Format | Notes |
|---|---|---|
| config.yaml | YAML | deep-merged with DEFAULT_CONFIG in manager.py |
| stats.json | JSON | `{instance: {"crest.runs": n, "crest.crest_lv3": n, ...}}`; user can Reset |
| history/history.jsonl | JSONL | kinds: crest (rarity, action), energy, failure, finished; **compacted to 2000** |
| crest_log.jsonl (Phase 1) | JSONL | append-only crest ledger, never compacted — see below |
| templates/_meta.json | JSON | per-template threshold, source (ReStart/user), generation, resolution |
| units/roster.json, scans.jsonl, aliases.json (Phase 3) | JSON/JSONL | `rerun/units.py` UnitRoster: units with per-field provenance; every scan appended (with `complete`); learned name corrections |
| units/renames.jsonl | JSONL | names replaced by GS Companion's (from, to, time); undo = Correct Name |
| data/gscompanion/ | JSON + images | GS Companion reference data, local only (git-ignored); `rerun/gsc_data.py` GSCData, `gsc_app/` Companion tab |
| units/targets.json (Phase 4) | JSON | `rerun/compendium.py` Compendium: global / per-unit quest clear targets, near-target %; progress and "+N since" computed from scans.jsonl |

## Crest ledger (Phase 1)

`rerun/crest_stats.py` — `CrestLedger` keeps an append-only `crest_log.jsonl` next to `history/`:
`{"type": "run"|"drop"|"baseline", ...}` with instance, session id, timestamp, rarity class
(`lv3`, `lv3+`, `lv4`, `4+`, `burst`, `?`), action, palace (template / weekday), thumb, `source`
(`live` / `history` reconstruction) and `confidence`. `CrestStats` computes today / session /
all-time counts, rates, runs-since and breakdowns from it. Lv4 is never counted as 4+.

## Updates and data

User data lives next to Rerun.exe (`main.app_root`). `run_app`: `migrate_ui.offer_import`
(only when this folder has no data and an earlier Rerun folder has) -> `require_key` ->
`migrate.remember(root)` -> `App`. `migrate.import_data(src, dst, replace=False)` copies and
never touches `src`. Data formats only ever gain fields; config is deep-merged with defaults.

## Key system

`main.py` -> `rerun.gui.run_app` -> `rerun.license_gate.require_key(root)` before `App` exists:
the saved key in `license.json` if valid, else the sign-in window. `rerun/license.py` checks
Ed25519-signed keys against the embedded `PUBLIC_KEY`; the private key only exists in
`%LOCALAPPDATA%\Rerun Keygen\` for `tools/keygen.py`. `App(manager, license=...)` re-checks
every minute (`_check_key`); on expiry `Manager.locked` blocks `start()`. Tests create `App`
directly, without a key.

## Live View

`rerun/live_stream.py` LiveStream streams `adb exec-out screenrecord --output-format=h264 -`
through a local TCP socket into `cv2.VideoCapture(..., CAP_FFMPEG)` on its own thread; the GUI
(`_manage_stream`, `_live_loop`) draws the newest frame at `live_view_fps` while the Dashboard
is visible, and falls back to screenshots when the stream fails. Scripts never use it: they
keep taking full-size `screencap` frames for recognition.

## OCR

Tesseract 5.5 from `%LOCALAPPDATA%\ReStart\bin` (eng only; tessdata lacks configs, so TSV via
`-c tessedit_create_tsv=1`). Multi-setting majority vote for stylised fonts (energy).

## Discord

`discord.py` client in its own thread/event loop. `send()` is thread-safe. Control commands are
limited to `discord.allowed_user_ids`. Commands: /status /start /stop /pause /resume /screenshot
/stats /resetstats /history /summary /scripts (+ /crests from Phase 1).

## Build

`python build.py` → PyInstaller one-file `dist/Rerun/Rerun.exe`. The exe stores its own config,
stats and history next to itself. Installed copy: `C:\Users\dandr\Downloads\Rerun\Rerun`.
