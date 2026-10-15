# Historical lineup candidate-universe audit — supersession note v3 (2026-10-13)

## Dominant finding: historical team-code mismatch

The strict signature audit found 7,892 unmatched weekly rows. For 7,873 of them (99.76%), season, canonical player, PDK and all 17 boxscore fields match an official game when the source team field is excluded. In all 7,873 cases, the source team code differs from the official NBA team on that game.

This is consistent with a later/current roster association being attached to historical game stats, but the upstream meaning of source team_code is not yet proven. Do not rewrite it globally. Retain it as a separate source field and use the official game-date NBA team for matchup features.

## Residual 19 rows

The remaining 19 rows occur in season ID 5, source week 43 round 2 (16 rows) and week 53 round 2 (3 rows). Only 7 have a same-player/same-season PDK value somewhere in the official archive; 12 do not. Even the nearest official game for the same player differs in 4–12 of the 17 boxscore fields. A repeated PDK value is not a valid game link.

These 19 rows should not be treated as exact game outcomes until source provenance is established. Do not impute them as zero, DNP or ineligible.

## Backtest consequences

The previous conclusion remains: historical weekly tables are outcome archives, not complete timestamped pre-lock market snapshots. This diagnostic does not recover historical credits, injury/availability snapshots, or the full candidate universe.

Artifacts:
- scripts/audit_dunkest_historical_round_game_unmatched_v3.py
- reports/audit/dunkest_historical_round_game_unmatched_20261013_v3.md
- scripts/audit_dunkest_historical_round_game_residuals_v1.py
- reports/audit/dunkest_historical_round_game_residuals_20261013_v1.md
- reports/audit/dunkest_historical_round_game_residuals_20261013_v1.csv
- reports/audit/dunkest_historical_round_game_residuals_20261013_v1.json

No source rows, training labels, production code/config, official PDK targets, temporal splits, or frozen 2026/27 GW1 holdout were changed. Holdout cutoff remains 2026-10-23 12:00 UTC.
