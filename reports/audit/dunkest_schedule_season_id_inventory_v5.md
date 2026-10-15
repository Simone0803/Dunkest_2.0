# Dunkest schedule ID ↔ NBA season inventory (v5)

## Confirmed regular-season schedules

| NBA season | Schedule ID | Official records | Played games | Postponed | Team sides matched / compared | Exact validity flags / matched |
|---|---:|---:|---:|---:|---:|---:|
| 2022/23 | 1 | 1041 | 1040 | 1 | 2080/2080 | 2079/2080 (99.95%) |
| 2023/24 | 8 | 1014 | 1014 | 0 | 2028/2028 | 2027/2028 (99.95%) |
| 2024/25 | 19 | 1040 | 1037 | 2 | 2076/2076 | 2076/2076 (100.00%) |

## Remaining seasons not mapped

| NBA season | Stats API season ID | Schedule ID | Status |
|---|---:|---:|---|
| 2018/19 | 1 | — | Not recovered yet; do not infer from stats ID |
| 2019/20 | 3 | — | Not recovered yet; do not infer from stats ID |
| 2020/21 | 5 | — | Not recovered yet; do not infer from stats ID |
| 2021/22 | 7 | — | Not recovered yet; do not infer from stats ID |

## Findings

- The DET–WAS record on 2023-02-01 is explicitly `postponed`; it is excluded from played-game matching, so it is not a local archive gap.
- Across 2022/23–2023/24, all 4,108 team sides from 2,054 played games match the archive. There is one unresolved flag mismatch: BOS–CLE on 2023-12-12.
- 2024/25 has two postponed records and one stale `playing` status that is present in the archive; the 2,076 archive-backed team sides match exactly, including all validity flags.
- Schedule IDs are not stats API season IDs. Historical calendars for 2018/19–2021/22 remain unresolved; continue looking, but do not guess.
- No source parquet, official target, model, temporal split, or backtest was modified.

## Detailed reports

- `dunkest_official_schedule_vs_archive_validation_v2.json` and `dunkest_official_schedule_vs_archive_validation_v2_status_aware.md` — status-aware 2022/23–2023/24 validation.
- `dunkest_schedule_2024-25_archive_validation_v3.json` / `.md` — 2024/25 status-aware validation.
- `dunkest_schedule_season_id_inventory_v5.json` / `.md` — consolidated inventory.
