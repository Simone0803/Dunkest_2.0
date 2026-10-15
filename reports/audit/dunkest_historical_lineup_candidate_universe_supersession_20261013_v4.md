# Historical lineup candidate-universe audit — supersession note v4 (2026-10-13)

## Confirmed issue: source team and historical NBA game team are different fields

The strict signature audit found 7,892 weekly rows without a match when requiring season, player, source team, PDK and 17 boxscore fields. A team-free match using the same PDK and 17 statistics produced 7,873 candidate rows. The final versioned derivative classifies these without guessing:

- 7,828 rows uniquely link to a game whose official NBA team differs from the source team code.
- 12 rows uniquely match the PDK/stat/date signature, but the enriched archive has no NBA team ID. These have a date/outcome link only, with no inferred NBA team or NBA game ID.
- 33 rows have multiple team-free candidates and remain ambiguous.
- 19 rows have no exact 17-stat signature even when team and PDK are ignored.

Across all 93,779 source tot rows with gp=1, the derivative links 93,317 uniquely: 85,477 strict team-inclusive matches, 7,828 unique links with an identified team mismatch, and 12 date/outcome links without NBA team IDs. The other 462 rows are ambiguous or unresolved (410 strict ambiguities, 33 team-free ambiguities, 19 unmatched).

## How to use the derivative

- Keep source team_code and team_name unchanged; they are not reliable historical NBA game-team fields.
- Use linked_nba_game_team_code for matchup features only when populated and the link status is unique.
- Keep the 12 no-team-ID links out of team-specific matchup features.
- Keep ambiguous/unresolved rows out of exact game-level matchup features.
- Preserve gameValidForDunkest_observed; one unique linked row is marked False and must not become a valid training target.
- This dataset links outcomes only. It is not a timestamped pre-lock market snapshot and does not reconstruct credits, injury/availability snapshots, historical rosters, or the full candidate universe.

## Artifacts

- Builder: scripts/build_dunkest_historical_game_linked_rows_v2.py
- Dataset: data/processed/dunkest_historical_game_linked_rows_20261013_v2.parquet
- Report: reports/audit/dunkest_historical_game_linked_rows_20261013_v2.md
- Summary: reports/audit/dunkest_historical_game_linked_rows_20261013_v2_summary.csv
- Ambiguous/unresolved rows: reports/audit/dunkest_historical_game_linked_rows_20261013_v2_unresolved.csv
- Manifest: reports/audit/dunkest_historical_game_linked_rows_20261013_v2.json

The first-pass derivative was discarded after validation exposed a missing-value counting defect; only v2 remains as the retained dataset. No source data, production code/config, target labels, temporal splits, or frozen 2026/27 GW1 holdout was changed. The holdout remains frozen until 2026-10-23 12:00 UTC.
