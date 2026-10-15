# Dunkest schedule ID ↔ NBA season inventory (v6)

## Confirmed regular-season schedules

| NBA season | Schedule ID | Official records | Played games | Postponed | Team sides matched / compared | Exact validity flags / matched |
|---|---:|---:|---:|---:|---:|---:|
| 2022/23 | 1 | 1041 | 1040 | 1 | 2080/2080 | 2080/2080 (100.00%) |
| 2023/24 | 8 | 1014 | 1014 | 0 | 2028/2028 | 2027/2028 (99.95%) |
| 2024/25 | 19 | 1040 | 1037 | 2 | 2076/2076 | 2076/2076 (100.00%) |

## Unresolved historical seasons

| NBA season | Stats API season ID | Schedule ID | Status |
|---|---:|---:|---|
| 2018/19 | 1 | — | Not recovered; do not infer from stats ID |
| 2019/20 | 3 | — | Not recovered; do not infer from stats ID |
| 2020/21 | 5 | — | Not recovered; do not infer from stats ID |
| 2021/22 | 7 | — | Not recovered; do not infer from stats ID |

## Findings

- **2022/23:** 1,041 schedule records include 1,040 played games and one postponed DET–WAS entry. Excluding the postponed entry, all 2,080 team sides and all validity flags match the local archive.
- **2023/24:** all 2,028 team sides from 1,014 played games match the archive; 2,027/2,028 validity flags agree. The only mismatch is BOS–CLE on 2023-12-12.
- **BOS–CLE cross-endpoint check:** the schedule endpoint says Boston `is_valid=true`, Cleveland `is_valid=false`; six sampled player records (three per team) from `/api/player/games` and the saved archive all have `gameValidForDunkest=false`. This indicates the schedule-level and player-level fields cannot be treated as interchangeable without a documented rule. No values were changed.
- **2024/25:** 1,040 records include 1,037 `played`, one `playing` record present in the archive, and two `postponed`. All 2,076 archive-backed team sides and validity flags match.
- **2018/19–2021/22:** schedule IDs remain unresolved. A coarse survey is in progress; no guessed mappings or proxy targets are used.
- Stats API season IDs and schedule IDs are different namespaces.
- No source parquet, official PDK, model, temporal split, or backtest was modified.

## Reports

- `dunkest_official_schedule_vs_archive_validation_v2.json` / `.md` — status-aware schedule/archive comparison for 2022/23–2023/24.
- `dunkest_bos_cle_validity_cross_endpoint_check_v1.json` / `.md` — independent player API check of the only flag discrepancy.
- `dunkest_schedule_2024-25_archive_validation_v3.json` / `.md` — 2024/25 status-aware comparison.
- `dunkest_schedule_season_id_inventory_v6.json` / `.md` — consolidated inventory.
