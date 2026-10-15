# Dunkest schedule ID ↔ NBA season inventory (v4)

## Confirmed regular-season schedules

| NBA season | Schedule ID | Matchdays | Official records | Date range | Team sides matched / compared | Validity flags exact / compared |
|---|---:|---:|---:|---|---:|---:|
| 2022/23 | 1 | 65 | 1041 | 2022-10-18 – 2023-04-09 | 4108/4110 | 4107/4108 (99.98%) |
| 2023/24 | 8 | 63 | 1014 | 2023-10-24 – 2024-04-12 | 4108/4110 | 4107/4108 (99.98%) |
| 2024/25 | 19 | 64 | 1040 | 2024-10-22 – 2025-04-11 | 2076/2076 | 2076/2076 (100.00%) |

## Other NBA schedule IDs observed

- **Schedule 3:** NBA playoffs 2022/23, not regular season.
- **Schedule 20:** NBA playoffs 2024/25, not regular season.
- **Schedule 36:** NBA regular season 2025/26, identified by a sampled matchday only.
- **Schedule 57:** current NBA 2026/27 config; matchday 1858, round 2890, date 2026-10-20.

## Seasons not yet mapped

| NBA season | Stats API season ID | Official schedule ID | Status |
|---|---:|---:|---|
| 2018/19 | 1 | — | Not recovered in this audit |
| 2019/20 | 3 | — | Not recovered in this audit |
| 2020/21 | 5 | — | Not recovered in this audit |
| 2021/22 | 7 | — | Not recovered in this audit |

## Anomalies and findings

- **2022/23–2023/24:** 4,108/4,110 team sides matched. Exact validity flags agreed for 4,107/4,108 matched sides. Remaining anomalies:
  - DET–WAS, 2023-02-01: official API record exists but no corresponding game was found in the local enriched archive.
  - BOS–CLE, 2023-12-12: API says BOS `is_valid=true` and CLE `is_valid=false`; the local archive stores `gameValidForDunkest=false` for both sides.
- **2024/25:** 1,040 official records across 64 matchdays: 1,037 `played`, one `playing` but present in the archive, and two `postponed`. Excluding only postponed entries, all 2,076 archive-backed team sides match and all validity flags agree.
- **2018/19–2021/22:** schedule IDs were not recovered. The API search is evidence of non-recovery, not proof that the historical calendars never existed. Do not assign guessed IDs or use reconstructed proxies as official targets.
- Stats API season IDs and schedule IDs are different namespaces; never infer one from the other.
- No source parquet, PDK target, model, temporal split, or backtest was modified.

## Detailed audit files

- `dunkest_official_schedule_vs_archive_validation_v1.json` / `.md` — 2022/23 and 2023/24.
- `dunkest_schedule_2024-25_archive_validation_v3.json` / `.md` — status-aware 2024/25 audit.
- `dunkest_schedule_season_id_inventory_v4.json` / `.md` — consolidated inventory.
