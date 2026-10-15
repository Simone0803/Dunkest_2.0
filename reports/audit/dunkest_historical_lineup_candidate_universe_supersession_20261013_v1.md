# Historical lineup candidate-universe audit — supersession note (2026-10-13)

The earlier `dunkest_historical_lineup_infeasibility_20261013_v1` identified the immediate MILP cause: after its matchup join, 49 failed date slices had too few candidate teams to fill ten player slots under the unchanged three-per-team rule. This is still correct for the inputs supplied to CBC.

The subsequent full-boxscore-signature audit adds important context. Of 93,779 single-game-eligible weekly-round rows, 85,477 (91.1%) uniquely match an official player-game record on season, player, team, PDK and 17 boxscore statistics; 410 remain ambiguous and 7,892 do not match. In the illustrative 2022-12-13 source round, 23 rows include four teams, but only 19 rows uniquely match the target-date boxscore and those matches represent GSW and UTA. The prior PDK-only date mapping also admitted rows from LAL/MIN, which did not match that date's exact source signature.

This means the current lineup proxy has two separate limitations:

1. The target-date matchup join can admit incorrect team-date associations when it relies on PDK values alone.
2. The historical outcome table itself is not a complete timestamped pre-lock market snapshot; exact row linkage cannot fill in missing player/credit/availability states.

Do not loosen the production team cap, impute unmatched rows as zero, automatically quarantine rows, or use the transfer coefficient comparison to tune production. Keep the production transfer penalty at 5. The next defensible step is to separate outcome-linkage validation from lineup-market reconstruction and obtain complete point-in-time player/team/role/credit/availability snapshots before making lineup-level claims.

No source rows, production code/configuration, official PDK labels, temporal splits, or frozen 2026/27 GW1 holdout were changed.
