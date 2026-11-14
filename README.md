# Rerun — Grand Summoners companion

An open-source take on ReStart's purpose: smart routines that read the screen and
react, instead of replaying blind macros. Multi-instance, crest detection, Discord bot,
in an iOS-style window (light and dark).

## Scripts

| Script | What it does |
|---|---|
| **Any Quest** | Farms the open quest with the in-game Auto-Loop, Redeploys after each batch, counts runs on "Drop Info". Stops and tells you if the game drops back to Home. |
| **Crest** | Crest Palace farming. On the Equip Crest screen it ticks your equipped crests, identifies the new crest (orange row) by its rarity icon, keeps + pings you for wanted rarities, scraps the rest via Redeploy. Crest Burst (5+) always stops and pings. |
| **Login & Mail** | Logs in from the Game Start screen, clears popups, Claim All until the mailbox is empty. |
| Arena *(Beta)* | Finds opponents, readies up, fights; waits for orbs (or restores them with crystals, capped). |
| Grand Crusade *(Beta)* | Auto-advance, next areas, Yuna Chance, popups; stop or wait when stamina runs out; optional Load Team. |
| Queue *(Beta)* | Grand Crusade until stamina runs out, then Crest for N minutes, repeat. A rare crest stops everything. |
| Mines *(Beta)* | Mines event loop: support pick, auto-advance, results; Omega boss: stand by / fight / change boss. |
| Multiplayer Farm *(Beta)* | Ready/Battle in a lobby, results, crest judging like Crest (scraps with OK), hyper-rare alerts. |
| Raid Tickets / Host / Guest *(Beta)* | Buy tickets; create raids with SOS; join SOS raids (auto-refreshes an empty list). |
| Secret Equip *(Beta)* | Any Quest's loop with its own counters, for secret equipment quests. |
| GC Area *(Beta)* | Farms one Grand Crusade area: after each clear it reads the area list and heads back. |
| Helper Rewards *(Beta)* | Joins Helper Reward lobbies matching your difficulties, picks a cheese, runs, leaves; each host once a day. |
| Compendium Counter *(Beta)* | Opens every unit in the Units compendium and writes their quest clear counts to `compendium_report.csv`. |
| Chain *(Beta)* | Runs scripts in a row, e.g. `login_mail; crest 90m; arena`; stops if a step needs you. |
| Custom routines | Your own YAML routines in `routines/` (see `routines/README.md`). |

*Beta* scripts follow ReStart's own routine flow and templates but have not been run on a real
game yet; Rerun asks you to confirm before starting one.

## Running unattended

- **Schedule** (Settings): start an instance's script every day at a set time.
- **Chain**: several scripts in a row; combine with a schedule for a daily routine.
- **Energy**: read from the top bar (shown on the Dashboard); with refills off, Rerun compares
  it with the quest's Energy Cost before pressing Battle.
- **Crest double-check**: the new crest's level is read from its title ("Lv3", "Lv4+") as well as
  its icon; if they disagree nothing is scrapped.
- **Text safety net**: an unrecognised screen is read after a few seconds; "unexpected error",
  "communication error", "date has changed" popups are dismissed by their button's label,
  maintenance waits (24/7) or stops, "please update" stops.
- **Template health**: templates whose real matches drift down towards their threshold are
  flagged orange in the Templates tab (usually a game update) before they fail.
- **Daily summary** to Discord (and `/summary`), **Setup check** (Settings › Setup check).

All scripts: stop/pause from the app, the tray icon, Discord, or global hotkeys (F12 stop all,
F11 pause/resume all); optional 24/7 mode (crash relaunch, 6 AM UTC-6 daily reset relogin);
a stuck watchdog (same screen handled 25 times → stop, frame saved to `debug/`) and a
no-progress watchdog.

## Reading on-screen text (OCR)

Rerun reads text with Tesseract OCR, the engine ReStart uses. Nothing to install when ReStart is
on the PC: Rerun uses the copy in `%LOCALAPPDATA%\ReStart\bin` (or a normal Tesseract install, or
`tesseract_path` in config.yaml). Plain game text reads word-for-word (~95% confidence, 0.1–0.4 s);
decorative fonts are less reliable, so scripts only act on confident readings.

- Scripts: `read_text(x, y, w, h)` / `read_number(...)` on the 720×1280 frame.
- The Loops counter falls back to OCR if its digit images don't match.
- Stuck and unrecognised-screen reports include the words on screen.
- Templates tab › **Read Text** shows what Rerun reads inside the box you drag.

## Energy and spending

- **Energy refill**: choose L, M or S Potion, the Rekyuon Cupcake, or none. Rerun finds that
  item's icon in the refill dialog and taps the Use button on *its* row.
- **Max potions / Max crystal refills per session**: Rerun stops and tells you at the cap.
- Crystals are only ever spent with *Use crystals* turned on.
- *Let the game refill energy mid-loop* turns on Auto-Loop's own refill (off by default: the game
  then picks the potion and Rerun can't count or cap it).

## The window

- **Dashboard**: instances, Start/Pause/Stop, totals (runs, crests kept/scrapped, potions, run
  time, with Reset), instructions, and a live view that follows the running script's own frames
  (no extra capture work) or refreshes every 3 s when idle.
- **Settings**: per-instance script settings; theme (automatic/light/dark); keep running in the tray.
- **Templates**: checklist with green/red badges, capture, test, Import from ReStart.
- **History**: every crest (with a picture of its row), refill, failure and finish; filter by kind
  and instance.
- **Discord**, **Log** (filter by level and instance, search).

## Setup

1. BlueStacks 5: Settings › Display **1280×720**; Settings › Advanced › **Android Debug Bridge on**.
   (The game runs in portrait, so Rerun sees 720×1280 frames.)
2. Double-click **Run Rerun.bat** (or `python main.py`, or `dist\Rerun\Rerun.exe` once built).
3. Dashboard › **Detect BlueStacks** to add your instances (one row per instance = multi-instance farming).
4. **Templates** tab: **Import from ReStart** copies the game-UI templates from your local ReStart
   install (`%LOCALAPPDATA%\ReStart`). Your own captures are kept unless you choose to replace them.
5. **Settings**: runs, party, energy refill and caps, crests to keep, 24/7 mode.
6. **Discord** tab: follow the guide, Save & Connect.
7. Start.

ADB: Rerun uses the adb server that's already running (e.g. another tool's), otherwise the newest adb
it finds — two different adb versions kill each other's server.

## Building the .exe

`python build.py` (needs `pip install pyinstaller`) makes `dist\Rerun\Rerun.exe` and copies your
templates, routines, README and config next to it. The .exe keeps its own stats and history.

**Sharing Rerun with other people:** use `python build.py --release`, never your own `dist\Rerun`
(it holds your Discord token, stats, History, units and key). The release build makes
`release\Rerun-<version>.zip` with the exe, templates, routines, README, a blank config and
its own Tesseract (so text reading works without ReStart), and refuses to finish if any of
your data or your Discord token got in. GS Companion data is left out. Testers need Windows
10/11 64-bit, BlueStacks (ADB on, 1280×720, DPI 240) and a key from your keygen.

## Publishing updates

Rerun checks a signed update folder when it opens and every 6 hours (Settings › Updates).
New templates and routines install by themselves once no script runs; a template or routine
the user captured or edited is never overwritten. A newer Rerun.exe is offered, downloaded,
checked and swapped in on restart (the old one stays as `Rerun.old.exe`).

1. Set `UPDATE_URL` in `rerun/updates.py` to your host, e.g. `https://you.github.io/rerun-updates`,
   and build (only builds with an address can update).
2. Templates only: `py tools/publish_update.py`. A new app version: bump `__version__` in
   `rerun/__init__.py`, `python build.py`, then
   `py tools/publish_update.py --exe dist\Rerun\Rerun.exe --notes "What's new"`.
   `--channel beta` publishes to Beta testers only.
3. Upload the `updates_site\` folder so `<UPDATE_URL>/stable/manifest.json` is reachable.

Releases are signed with the keygen's signing key; a release from anyone else, a changed file
or an older release is refused.

## Tests

```
python tests/test_scripts.py      # every script against a simulated game
python tests/test_real_screens.py # real screenshots from the game (needs imported templates)
python tests/test_features.py     # energy/potions, history, Queue, every script's state wiring
python tests/test_app.py          # manager, engine, Discord, GUI
python tests/test_ocr.py          # text reading on real screenshots (needs Tesseract)
```

## Notes

Automating gameplay may break Grand Summoners' Terms of Service — use at your own risk.
Rerun only looks at the screen and sends taps through ADB; it does not modify the game.
