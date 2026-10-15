# Historical pre-lock archive inventory (read-only)

Date: 2026-10-13

## Scope and exclusions

This audit inventories filenames and sidecar metadata under data/processed; it does not read prediction outputs, score models, alter labels, or modify production code.
It deliberately excludes season ID 25 (2025/26 holdout) and season ID 26 (frozen 2026/27 prospective GW1) from the historical-season scan.
Season IDs scanned: 1, 3, 5, 7, 9, 13, 19.

## Season-specific archives found

| Snapshot family | Files present | Season IDs with no matching file |
|---|---:|---:|
| fixture_mapping | 0 | 7 |
| player_market | 0 | 7 |
| injury_snapshot | 0 | 7 |
| coach_market | 0 | 7 |
| player_week_outcomes | 0 | 7 |
| coach_outcomes | 0 | 7 |

## Legacy/season-ambiguous candidates

| File | Present | Sidecar fetched_at | Sidecar source |
|---|---|---|---|
| dunkest_players_gw1.parquet | yes | 2026-09-29T20:52:44.627778+00:00 | dunkest_api/stats/table |
| dunkest_players_gw35.parquet | yes | 2026-09-29T20:43:23.693283+00:00 | dunkest_api/stats/table |
| coaches_gw1.parquet | yes | 2026-09-30T15:45:35.739921+00:00 | coach_lineup_market+schedule |
| coaches_gw35.parquet | yes | 2026-09-29T20:41:58.175797+00:00 | coach_join_schedule |
| opening_market_gw1.parquet | yes | 2026-09-29T20:51:31.762766+00:00 | opening_market |
| injuries.parquet | yes | 2026-10-14T17:49:16.211699+00:00 | dunkest_html/infortuni |

## Interpretation

A current or historical outcome table is not evidence of a pre-lock market snapshot. Sidecar fetched_at records when this pipeline fetched/wrote a file, not necessarily the source's original publication time or the Dunkest lock cutoff.
A legacy filename without a season ID, round-linked fixture identity, and cutoff evidence cannot be promoted to a valid historical pre-lock roster/CR/injury/coach archive.
Missing snapshot files are classified as missing; this report does not infer that a player was unavailable, had zero points, or was not in the market.

## Recommended next step

Treat historical lineup-level backtests as blocked until a round-by-round archive manifest can establish roster universe, player CR/role/team, availability report, coach CR/opponent, fixture identity, and each artifact's availability at the actual prediction cutoff. Do not use post-lock/current data to fill historical gaps.

Machine-readable inventory: reports/audit/dunkest_prelock_archive_inventory_20261013_v1.csv.

No model training, hyperparameter tuning, production changes, holdout evaluation, commit, or push was performed.
