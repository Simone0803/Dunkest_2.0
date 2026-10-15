# Dunkest schedule ID ↔ NBA season inventory (v2)

## Confirmed regular-season schedules

| NBA season | Schedule ID | Matchdays | Official records | Date range | Team sides matched / compared | Validity flags exact / compared |
|---|---:|---:|---:|---|---:|---:|
| 2022/23 | 1 | 65 | 1041 | 2022-10-18 – 2023-04-09 | 4108/4110 | 4107/4108 (99.98%) |
| 2023/24 | 8 | 63 | 1014 | 2023-10-24 – 2024-04-12 | 4108/4110 | 4107/4108 (99.98%) |
| 2024/25 | 19 | 64 | 1040 | 2024-10-22 – 2025-04-11 | 2074/2074 | 2074/2074 (100.00%) |

## Other NBA schedule IDs observed

- **Schedule 3:** NBA playoffs 2022/23, not regular season.
- **Schedule 20:** NBA playoffs 2024/25, not regular season.
- **Schedule 36:** NBA regular season 2025/26, identified by a sampled matchday only.
- **Schedule 57:** current NBA 2026/27 config; current matchday 1858, round 2890, date 2026-10-20.

## Seasons not yet mapped

| NBA season | Stats API season ID | Official schedule ID | Status |
|---|---:|---:|---|
| 2018/19 | 1 | — | Not recovered in this audit |
| 2019/20 | 3 | — | Not recovered in this audit |
| 2020/21 | 5 | — | Not recovered in this audit |
| 2021/22 | 7 | — | Not recovered in this audit |

## Key findings

- Never infer a schedule ID from the stats API season ID; these identifiers differ.
- **2024/25 is validated status-aware:** 1,040 official records across 64 matchdays include 1,038 played games and 2 postponed entries. All 2,076 played team sides match the archive, and all 2,076 validity flags agree.
- **2022/23–2023/24:** 4,108 of 4,110 team sides matched; 4,107 of 4,108 matched validity flags agreed. One played-game discrepancy remains.
- 2018/19–2021/22 remain unresolved; the endpoint survey did not recover regular-season calendars. This does not prove they never existed; do not assign guessed IDs or use proxies as official targets.
- No source parquet, PDK target, model, temporal split, or backtest was modified.

## Detailed audit files

- `dunkest_official_schedule_vs_archive_validation_v1.json` / `.md` — 2022/23 and 2023/24.
- `dunkest_schedule_2024-25_archive_validation_v2.json` / `.md` — 2024/25 with postponed status handled correctly.
- `dunkest_schedule_season_id_inventory_v2.json` / `.md` — consolidated inventory.
