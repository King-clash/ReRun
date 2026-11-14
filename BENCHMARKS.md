# Benchmarks

Written by `py tools/bench.py` on 2026-11-14. Same-PC comparisons only.

| What | median ms | best ms |
|---|---:|---:|
| find('exploring_button') on home.png | 5.6 | 5.1 |
| find('exploring_button') on party_reigrad.png | 7.4 | 5.9 |
| find('battle_button') on home.png | 5.0 | 4.6 |
| find('battle_button') on party_reigrad.png | 5.1 | 4.1 |
| Crest detect_state on home.png  ->  home_screen | 124.5 | 124.1 |
| Crest detect_state on party_reigrad.png  ->  battle_button | 99.4 | 84.5 |
| Crest detect_state on loop_results.png  ->  drop_info | 73.4 | 71.2 |
| Crest detect_state on equip_crest_lv3.png  ->  equip_crest_screen | 57.6 | 53.7 |
| Crest detect_state on crest_palace_list.png  ->  crest_palace_screen | 109.2 | 104.4 |
| Crest detect_state on quest_list_cursed_claw.png  ->  quest_list | 118.1 | 116.3 |
| closest_screens (stuck report) | 114.7 | 114.1 |
| read_energy (OCR, 6 voters) | 816.2 | 746.9 |
| OCR whole screen (screen_words) | 512.3 | 506.0 |
| one tick on loop_results.png: 21 searches, 19 distinct (2 repeated) | | |
| ADB screenshot (live, read-only) | 229.5 | 177.9 |
