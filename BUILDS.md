# Builds

Every build of Rerun, GS Companion and the Keygen, newest first. Written by `tools/buildlog.py` each time a build script runs (from `builds.jsonl`); do not edit by hand.

**9 builds** (9 ok, 0 failed). Latest good build of each:

| App | Kind | When | Version | Commit | Exe | Output |
|---|---|---|---|---|---|---|
| GS Companion | build | 2026-11-14 16:51:17 | - | `~43f4673` | 26.5 MB | `dist/GS Companion` |
| Rerun | build | 2026-11-14 18:37:05 | - | `~281b2eb` | 78.6 MB | `dist/Rerun (key system)` |
| Rerun | release | 2026-11-14 19:22:41 | 1.0.0 | `a282c7b +4` | 78.6 MB | `release/Rerun` |
| Rerun Keygen | build | 2026-11-14 20:04:37 | - | `-` | 19.1 MB | `dist/Rerun Keygen (fixed)` |

## All builds

| When | App | Kind | Version | Commit | Result | Took | Exe MB | Exe SHA-256 | Zip MB | Templates | Routines | OCR | Leak check | Output |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-11-14 20:04:37 | Rerun Keygen | build | - | `-` | ok | 17 s | 19.1 | `8e91618b44f4` | - | - | - | - | - | `dist/Rerun Keygen (fixed)` |
| 2026-11-14 19:49:53 | Rerun Keygen | build | - | `-` | ok | 54 s | 19.1 | `686cd4c9c128` | - | - | - | - | - | `dist/Rerun Keygen` |
| 2026-11-14 19:37:51 | Rerun Keygen | build | - | `a282c7b +4` | ok | 22 s | 19.1 | `d0594f66f951` | - | - | - | - | - | `dist/Rerun Keygen` |
| 2026-11-14 19:22:41 | Rerun | release | 1.0.0 | `a282c7b +4` | ok | 172 s | 78.6 | `ddd116b31d7e` | 93.8 | 188 | 1 | Tesseract 5.5.0 | passed | `release/Rerun` |
| 2026-11-14 19:12:52 | Rerun | release | - | `~8f77cf5` | ok | - | 78.6 | `f4f81a779f4b` | 93.8 | 188 | - | bundled | - | `release/Rerun` |
| 2026-11-14 18:37:05 | Rerun | build | - | `~281b2eb` | ok | - | 78.6 | `c64b027928d1` | - | 188 | - | - | - | `dist/Rerun (key system)` |
| 2026-11-14 17:53:36 | Rerun Keygen | build | - | `~0824631` | ok | - | 19.1 | `18282aa65404` | - | - | - | - | - | `dist/Rerun Keygen` |
| 2026-11-14 17:37:31 | Rerun | build | - | `~0824631` | ok | - | 78.6 | `fe1eb45a5deb` | - | 188 | - | - | - | `dist/Rerun` |
| 2026-11-14 16:51:17 | GS Companion | build | - | `~43f4673` | ok | - | 26.5 | `2d413e5db1a6` | - | - | - | - | - | `dist/GS Companion` |

*Commit*: `+N` = N files had uncommitted changes when it was built; `~` = guessed from the file date (built before this log existed).
