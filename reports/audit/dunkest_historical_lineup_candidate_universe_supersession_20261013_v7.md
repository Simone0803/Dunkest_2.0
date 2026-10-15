# Historical lineup candidate-universe audit — supersession note v7 (2026-10-13)

## Persisted date-assisted game-link dataset

The v3 builder was corrected to take `dunkest_historical_player_week_round_2020-25_v2.parquet` as the source of truth and join linkage metadata by `(source_season_id, source_week, source_round, id)`. An earlier build with two source-stat mismatches was discarded before this final version was accepted.

- Dataset: `data/processed/dunkest_historical_game_linked_rows_20261013_v3_date_assisted.parquet` (93,785 rows).
- Date-assisted unique links: 441 from 475 eligible unresolved single-game rows; 36 of the 441 use an NBA game team different from source Dunkest team.
- All 441 have exact rounded PDK + 17-stat agreement with the original source and an official-valid NBA candidate matching persisted date, game ID, and NBA team.
- Remaining unresolved: 34 (32 with no exact candidate, 2 date candidates with signature mismatch); multi-game aggregates are never date-assisted.

## Reproducibility

V9 consumes the persisted v3 dataset and calculates round-date consensus from v2 links only. V8 and V9 produce identical target labels and prediction rows: 285,304/285,304; maximum absolute prediction difference is 2.85e-14. This is a reproducibility check, not a predictive gain.

The paired V8-vs-V7 evaluation remains inconclusive (95% round-cluster intervals include zero). No production code/config changed, no commit/push was performed, and the frozen 2026/27 GW1 holdout remains untouched until 2026-10-23 12:00 UTC.

## Artifacts

- `scripts/build_dunkest_historical_game_linked_rows_v3_date_assisted.py`
- `reports/audit/dunkest_historical_game_linked_rows_20261013_v3_date_assisted.md`
- `scripts/backtest_dunkest_historical_credits_matchup_walk_forward_v9_persisted_date_link.py`
- `reports/audit/dunkest_lagged_credit_matchup_walk_forward_20261013_v9_persisted_date_link.md`
- `scripts/audit_dunkest_persisted_v3_vs_v8_predictions_v1.py`
- `reports/audit/dunkest_persisted_v3_vs_v8_prediction_parity_20261013_v1.md`
- `reports/audit/dunkest_project_followup_2026-10-13_v21.md`
