# Historical lineup candidate-universe audit — supersession note v2 (2026-10-13)

The earlier full-signature audit found 7,892 rows with no match when matching season, player, source team, PDK and 17 boxscore fields. A follow-up diagnostic resolves the dominant cause without modifying the source.

## New evidence

For 7,873 of those 7,892 rows (99.76%), the official archive contains an exact match on season, canonical player, PDK rounded to two decimals, and all 17 boxscore fields once the source team field is excluded. In every one of these 7,873 cases, the source team code differs from the official NBA team on the matched game record.

Example: season ID 13, source week 10 round 1 (2023-11-18) assigns Vasilije Micic to CHA, Cameron Payne to PHI, and Seth Curry to CHA. Their exact PDK/stat signatures point to official game teams OKC, MIL and DAL respectively. This is consistent with historical stats being joined to a later/current roster assignment or another Dunkest-side team identity. The upstream semantics of source team_code have not yet been established.

The remaining 19 rows have no exact 17-stat signature even when both team and PDK are ignored; they cluster in season ID 5, week 43 round 2 (16 rows) and week 53 round 2 (3 rows).

## Consequence for historical lineup work

The earlier conclusion remains valid but is now more specific:

1. A strict team-inclusive signature fails largely because source team_code does not reliably represent the NBA team for the historical game date.
2. PDK plus boxscore statistics can often identify the actual game outcome even when the source team differs.
3. The weekly table still is not a complete timestamped pre-lock market snapshot; this diagnosis does not reconstruct historical credits, injuries, availability, or the full candidate universe.

Do not globally overwrite team_code. Preserve the original source value, and keep the official game-date NBA team in a separate field for matchup features. If source team_code is useful as a Dunkest-side assignment, retain it separately with documented semantics. The 19 residual rows remain unresolved; do not impute them as zero, DNP, or ineligible.

## Artifacts

- scripts/audit_dunkest_historical_round_game_unmatched_v3.py
- reports/audit/dunkest_historical_round_game_unmatched_20261013_v3.md
- reports/audit/dunkest_historical_round_game_unmatched_20261013_v3_rows.csv
- reports/audit/dunkest_historical_round_game_unmatched_20261013_v3_seasons.csv
- reports/audit/dunkest_historical_round_game_unmatched_20261013_v3_rounds.csv
- reports/audit/dunkest_historical_round_game_unmatched_20261013_v3.json

No production code/config, source rows, training labels, official PDK targets, temporal splits, or frozen 2026/27 GW1 holdout were changed. Holdout cutoff remains 2026-10-23 12:00 UTC.
