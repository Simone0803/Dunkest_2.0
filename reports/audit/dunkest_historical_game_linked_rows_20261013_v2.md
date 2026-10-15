# Historical Dunkest game-linked row dataset — v1

Generated UTC: 2026-10-13T11:35:52.024077+00:00

## Purpose

Creates a derived row-level dataset linking historical Dunkest total rows with gp=1 to official NBA player-game records. The original Dunkest team assignment remains unchanged in team_code; the historical NBA game team is stored separately as linked_nba_game_team_code. This is an outcome-link dataset, not a pre-lock market snapshot.

## Match policy

- First require season, canonical player, source team, PDK rounded to two decimals, and all 17 boxscore fields to identify one NBA game.
- If the strict match is absent, exclude team from the key and accept a link only if exactly one official NBA game matches season, player, PDK and all 17 boxscore fields.
- If multiple games match, preserve candidate counts and leave game fields null.
- If no game matches, leave the row unresolved; never infer zero, DNP or ineligibility.

## Results

- Source total rows: **93,785**; eligible gp=1 rows: **93,779**.
- Unique linked rows: **93,317 (99.5%)**.
- Unique strict team-inclusive matches: **85,477**.
- Unique team-free matches with an identified NBA team: **7,828**.
- Unique date/outcome matches without an NBA team ID: **12**.
- Ambiguous strict signatures: **410**; ambiguous team-free signatures: **33**.
- No exact signature even without team and PDK: **19**.
- Of all uniquely linked rows, one has `gameValidForDunkest=False`; the observed flag is retained and this row must not be treated as a valid training target.

## Data semantics and safeguards

- team_code and team_name are preserved as source fields; no global rewrite.
- Linked NBA game team, opponent, date and game ID are separate derived fields.
- gameValidForDunkest_observed records the official archive value; it is not inferred.
- The output cannot be used as a complete historical market: historical credits, injury/availability snapshots, lock-time rosters and full candidate universe are still missing.
- The 12 rows without NBA team IDs are linked to the Dunkest per-game date/outcome signature only; no NBA team or NBA game ID is inferred.
- No production model/config, source file, target label, temporal split, or frozen prospective holdout was changed. No commit/push was performed.

## Artifacts

- Parquet: data/processed/dunkest_historical_game_linked_rows_20261013_v2.parquet
- Summary CSV: reports/audit/dunkest_historical_game_linked_rows_20261013_v2_summary.csv
- Ambiguous/unresolved CSV: reports/audit/dunkest_historical_game_linked_rows_20261013_v2_unresolved.csv
- JSON: reports/audit/dunkest_historical_game_linked_rows_20261013_v2.json
