# Historical player matchup backtest — supersession note

- V1: opponent defensive PTS/REB/AST allowed and opponent identity.
- V2: adds opponent STL/BLK/TOV allowed, rolling possession/pace proxies, and selected prior-5-game trends. Current matchup features are shifted before target game.
- V3: adds individual player-vs-opponent history (prior official-valid Dunkest PDK and NBA minutes) from games strictly before the target calendar date; same-day games excluded.
- V4: adds a shrunk head-to-head PDK feature, blending prior official-valid H2H PDK with the player's general previous-five-round PDK mean using three pseudo-observations.
- V2 report: `dunkest_lagged_credit_matchup_walk_forward_20261013_v2.md`.
- V3 report: `dunkest_lagged_credit_matchup_walk_forward_20261013_v3.md`.
- V4 report: `dunkest_lagged_credit_matchup_walk_forward_20261013_v4.md`.
- Paired inference: `dunkest_h2h_paired_bootstrap_20261013_v1.md`, resampling complete season-week-round clusters within each held-out season.
- V4 MAE 7.4543 vs V2 MAE 7.5028 on the same 55,565 held-out player-round targets; macro-season paired delta MAE -0.0483, 95% CI [-0.0803, -0.0221]. 2022-23's individual interval crosses zero.
- Shrinkage does not materially improve MAE over unshrunk H2H, but slightly improves RMSE. Do not switch production based on this experiment alone; require validation on an untouched holdout and a production-equivalent pre-lock feature audit.
