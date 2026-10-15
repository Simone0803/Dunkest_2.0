# Dunkest weekly-round archive integrity audit (v1)

Generated UTC: 2026-10-12T13:46:56.140138+00:00

## Summary

- Parquet files: **1,558**; manifest completed entries: **1,558**.
- Rows: **187,570**; schema variants: **1**.
- Manifest errors: **0**; tasks without files: **0**; files missing from manifest: **0**.
- Empty files: **0**; duplicate player-ID rows: **0**; null IDs: **0**; null PDK: **0**.
- Unpaired avg/tot rounds: **0**; integrity issues: **0**.

## Per-season coverage observed

| Season ID | Files | Rows | Weeks with data | Week range | Rounds | Paired avg/tot | Gaps inside observed range |
|---:|---:|---:|---:|---:|---:|---:|---|
| 5 | 280 | 35,362 | 59 | 1–59 | 140 | 140 | None |
| 7 | 330 | 36,844 | 64 | 1–64 | 165 | 165 | None |
| 9 | 324 | 38,330 | 64 | 1–64 | 162 | 162 | None |
| 13 | 308 | 37,854 | 62 | 1–62 | 154 | 154 | None |
| 19 | 316 | 39,180 | 64 | 1–64 | 158 | 158 | None |

## Findings

No internal consistency errors were detected in the saved collection.

## Interpretation and limits

This is an integrity audit, not proof of complete historical API coverage. It validates file readability, task metadata, manifest/file correspondence, player-ID uniqueness within each table, and matching player-ID sets between avg and tot tables.
The weekly-round endpoint archive includes stats season IDs 5, 7, 9, 13 and 19. IDs 1 and 3 (2018/19 and 2019/20) are handled separately through the per-player game-history endpoint; their `gameValidForDunkest` flags remain unaltered and must not be interpreted as official eligible targets without independent verification.

Source files were read only. No raw data, production configuration, targets, temporal splits, models, or backtests were modified.

JSON details: `reports/audit/dunkest_week_round_collection_audit_v1.json`
