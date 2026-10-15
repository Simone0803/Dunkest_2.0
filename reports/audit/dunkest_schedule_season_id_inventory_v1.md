# Dunkest schedule ID ↔ NBA season inventory (v1)

## Confirmed regular-season schedules

| NBA season | Schedule ID | Matchdays with games | Official games | Official date range | Archive comparison |
|---|---:|---:|---:|---|---|
| 2022/23 | 1 | 65 | 1041 | 2022-10-18 – 2023-04-09 | See detailed prior audit |
| 2023/24 | 8 | 63 | 1014 | 2023-10-24 – 2024-04-12 | See detailed prior audit |
| 2024/25 | 19 | 64 | 1040 | 2024-10-22 – 2025-04-11 | 2076/2080 team sides; flags 2076/2076 (100.00%) |

## Other NBA schedule IDs observed

- **Schedule 3:** NBA playoffs 2022/23 (not a regular-season calendar).
- **Schedule 20:** NBA playoffs 2024/25 (not a regular-season calendar).
- **Schedule 36:** NBA regular season 2025/26; confirmed only by sampled matchday data, not fully audited here.
- **Schedule 57:** current NBA 2026/27 configuration; current matchday ID 1858, matchday number 1, date 2026-10-20.

## Seasons not yet mapped

| NBA season | Stats API season ID | Official schedule ID | Status |
|---|---:|---:|---|
| 2018/19 | 1 | — | Not recovered from the public schedule endpoint in this audit |
| 2019/20 | 3 | — | Not recovered from the public schedule endpoint in this audit |
| 2020/21 | 5 | — | Not recovered from the public schedule endpoint in this audit |
| 2021/22 | 7 | — | Not recovered from the public schedule endpoint in this audit |

## Findings and limits

- **Do not equate stats API season IDs with schedule IDs.** They are separate identifiers.
- The official schedule and local archive agree strongly for 2022/23–2024/25. The detailed 2024/25 audit found 1,040 official games across 64 matchdays (2024-10-22 to 2025-04-11); 2,076/2,080 team sides matched the archive and all 2,076 matched validity flags agreed.
- Two 2024/25 games remain unmatched locally: LAL–CHA on 2025-01-09 and NOP–MIL on 2025-01-22. These are archive-coverage anomalies to investigate, not reasons to impute or alter target values.
- The survey of candidate schedule IDs/matchday IDs 66–230 found NBA playoff records under schedule 3 but did not recover NBA regular-season calendars for 2018/19–2021/22. This is **not proof of nonexistence**; those seasons remain unresolved and should not be assigned guessed IDs.
- No source parquet, official PDK target, model, temporal split, or backtest was modified.

## Audit files

- `dunkest_official_schedule_vs_archive_validation_v1.json` and `.md` — 2022/23 and 2023/24 detailed validation.
- `dunkest_schedule_2024-25_archive_validation_v1.json` and `.md` — 2024/25 detailed validation.
- `dunkest_schedule_season_id_inventory_v1.json` and `.md` — consolidated inventory.
