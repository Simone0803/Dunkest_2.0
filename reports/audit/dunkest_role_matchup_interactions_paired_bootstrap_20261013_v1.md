# Dunkest V5 role-conditioned matchup ablation — paired inference

Generated: 2026-10-13

## Question

Does interacting prior opponent defensive form and pace with the player's lagged role (G/F/C) improve official-valid Dunkest player-round PDK prediction beyond the expanded matchup model?

## Method

- Dataset: `data/processed/dunkest_historical_player_week_round_2020-25_v2.parquet`.
- Expanding-origin tests: 2022/23, 2023/24, 2024/25; all training data precedes the held-out season.
- Both models evaluated on the exact same **55,565** held-out player-round rows across **467** season-week-round clusters.
- Challenger adds 12 interactions: lagged role G/F/C × prior-10-game opponent defensive points, rebounds and assists allowed, and pace.
- Paired uncertainty: 10,000 bootstrap samples, resampling complete season-week-round clusters within each held-out season. The reported delta is challenger absolute error minus baseline absolute error; negative favors the challenger.

## Results

| Model | Pooled MAE | Pooled RMSE | Bias |
|---|---:|---:|---:|
| Expanded matchup baseline | 7.502754 | 9.796561 | -0.622456 |
| Role-interaction challenger | 7.502699 | 9.795763 | -0.619239 |

- Paired MAE delta: **-0.000055 PDK** (challenger minus baseline).
- Cluster-bootstrap 95% interval: **[-0.004265, +0.004187] PDK**.
- Bootstrap fraction with delta below zero: **50.89%**.
- Round-level challenger win rate: **52.03% of 467 rounds**; the average round-level delta is +0.000755 PDK, slightly favoring the baseline.
- By held-out season, row-weighted delta MAE is +0.000501 (2022/23), +0.001274 (2023/24), and -0.001882 (2024/25).

## Decision

**Reject the current role-interaction feature set for production.** Its MAE difference is effectively zero, and the paired interval spans small improvements and regressions. The small RMSE change is also too small to justify additional complexity.

This result does not imply that matchup effects are irrelevant. It only says that these 12 linear role-conditioned interactions, added to the tested expanded matchup feature family, provide no measurable incremental value on these folds.

The H2H feature family has lower player-level MAE in the same historical experiment, but a separate restricted lineup proxy found its H2H optimizer worse than the no-H2H optimizer. Therefore, player-level MAE alone is not enough to promote matchup features.

## Reproducibility

- Experiment: `scripts/backtest_dunkest_historical_credits_matchup_walk_forward_v5_role_interactions.py`
- Main report: `reports/audit/dunkest_lagged_credit_matchup_walk_forward_20261013_v5_role_interactions.md`
- Metrics CSV: `reports/audit/dunkest_lagged_credit_matchup_walk_forward_20261013_v5_role_interactions_metrics.csv`
- Prediction CSV: `reports/audit/dunkest_lagged_credit_matchup_walk_forward_20261013_v5_role_interactions_predictions.csv`
- Audit JSON: `reports/audit/dunkest_lagged_credit_matchup_walk_forward_20261013_v5_role_interactions.json`

Production weights/configuration were not changed.
