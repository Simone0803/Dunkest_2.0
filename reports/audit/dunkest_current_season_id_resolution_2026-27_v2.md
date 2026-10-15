# Dunkest 2026–27 Player ID Resolution Audit — V2

Generated UTC: 2026-10-12T20:52:28.103022+00:00

## Resolution summary

- Unique market names: **566**
- Resolved IDs: **496 (87.6%)**
- Unmatched names: **70**
- Ambiguous names remaining: **0**
- Official catalogue entries: **1540**

## New resolutions

- **Dru Smith → ID 1085**. The duplicate profile ID 1007 returns 0 rows for season 25; ID 1085 returns 70 rows, including 53 Dunkest-valid rows.
- **Jaylin Williams → ID 1115**. The duplicate profile ID 2406 returns 0 rows for season 25; ID 1115 returns 80 rows, including 66 Dunkest-valid rows.
- **Elijah Harkless → ID 2553** via the unique official slug ej-harkless. The official profile page title is EJ Harkless Stats | Dunkest; its season-25 endpoint returns 26 rows.

## Source checks

- The live official player directory contains 1540 unique profile IDs; its ID set matches the saved 1,540-entry catalogue.
- A fresh Lineups capture at 2026-10-12T20:47:03.987286+00:00 contains 600 rows (570 players and 30 coaches). The exported market has no player-ID or profile-slug column, so it cannot directly resolve the remaining names.

## Remaining unresolved names

No fuzzy match was applied. The 70 names listed in the resolution CSV remain unresolved; a separate CSV gives up to three similarity-based candidates per name for manual inspection only. Similarity is not identity evidence.

## Outputs

- Resolution audit: reports/audit/dunkest_current_season_id_resolution_2026-27_v2.csv
- Candidate review list: reports/audit/dunkest_current_season_id_resolution_candidates_2026-27_v2.csv
- Evidence JSON: reports/audit/dunkest_current_season_id_resolution_2026-27_v2.json

## Safety

The collector now includes two explicit ID overrides and one reviewed alias. No broad fuzzy matching was introduced, and no season data was collected or canonical player-game parquet overwritten by this audit.

Re-run with: PYTHONPATH=src ./.venv/bin/python scripts/audit_dunkest_current_season_id_resolution_v2.py
