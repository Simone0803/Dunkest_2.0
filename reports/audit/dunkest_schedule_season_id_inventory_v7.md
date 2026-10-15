# Dunkest schedule ID ↔ NBA season inventory (v7)

## Confirmed regular-season schedules

| NBA season | Schedule ID | Official records | Played games | Postponed | Team sides matched / compared | Exact validity flags / matched |
|---|---:|---:|---:|---:|---:|---:|
| 2022/23 | 1 | 1041 | 1040 | 1 | 2080/2080 | 2080/2080 (100.00%) |
| 2023/24 | 8 | 1014 | 1014 | 0 | 2028/2028 | 2027/2028 (99.95%) |
| 2024/25 | 19 | 1040 | 1037 | 2 | 2076/2076 | 2076/2076 (100.00%) |

## Historical schedule search

- Surveyed **3,920** read-only ID pairs across schedule IDs 1–49 and 80 sampled matchday IDs.
- NBA schedule IDs observed: **1, 3, 8, 19, 36**. Schedule 3 sample is playoffs; schedules 1, 8, 19, 36 correspond to 2022/23, 2023/24, 2024/25, 2025/26.
- No regular-season schedule for 2018/19–2021/22 was found in this sample. This is not proof that no such data exists; those seasons remain unresolved.

## Remaining cross-endpoint discrepancy

- BOS–CLE on 2023-12-12: the schedule endpoint says Boston `is_valid=true`, Cleveland `is_valid=false`; six sampled player-games API records and local archived player rows have `gameValidForDunkest=false` for both teams. The fields may have different semantics or the schedule API has a stale/inconsistent flag. Preserve both raw sources; do not rewrite targets.

## Findings

- 2022/23: after excluding the one officially postponed DET–WAS record, all 2,080 team sides and all flags match.
- 2023/24: all 2,028 team sides match; 2,027/2,028 flags match.
- 2024/25: all 2,076 archive-backed team sides and all flags match; postponed records are excluded and one stale `playing` status is handled explicitly.
- No source parquet, official PDK, model, temporal split, or backtest was modified.

## Audit files

- `dunkest_historical_schedule_coarse_survey_v1.json` / `.md` — coarse historical ID survey.
- `dunkest_official_schedule_vs_archive_validation_v2.json` and `dunkest_official_schedule_vs_archive_validation_v2_status_aware.md` — status-aware 2022/23–2023/24 validation.
- `dunkest_bos_cle_validity_cross_endpoint_check_v1.json` / `.md` — player API verification of the mismatch.
- `dunkest_schedule_2024-25_archive_validation_v3.json` / `.md` — 2024/25 status-aware validation.
- `dunkest_schedule_season_id_inventory_v7.json` / `.md` — consolidated inventory.
