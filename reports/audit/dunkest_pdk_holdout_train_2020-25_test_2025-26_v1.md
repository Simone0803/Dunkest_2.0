# Dunkest PDK: fixed holdout training 2020/21–2024/25, test 2025/26

Created: 2026-10-12T15:51:43.824700+00:00

## Protocol

- **Training target labels:** official Dunkest PDK, valid rows from 2020/21–2024/25 only.
- **Held-out test:** official valid PDK rows from 2025/26; none of these labels enters `fit`.
- **2018/19–2019/20:** NBA boxscore history contributes to strictly pre-game features, but PDK rows are excluded from supervised labels because every returned `gameValidForDunkest` flag is `False`.
- **Evaluation mode:** one-step-ahead within the test season. Features for a later 2025/26 game may use that player's earlier valid 2025/26 games, but never the current game's outcome.
- **Leakage guard:** curated 79-feature whitelist excludes the current target and current-game boxscore fields; NBA history is strictly earlier than target date.

## Results

| Model | N | MAE | RMSE | Bias (prediction − actual) | R² |
|---|---:|---:|---:|---:|---:|
| Random Forest | 18,412 | 7.5775 | 9.8563 | -0.1725 | 0.4214 |
| Previous-10 PDK mean | 18,412 | 7.7886 | 10.1539 | -0.0479 | 0.3859 |

Random Forest improves MAE by **0.2112 PDK (2.71%)** versus the previous-10 baseline. This is a real held-out-season improvement, but it is modest rather than proof of high absolute accuracy.

## Artifacts

- Model: `data/processed/dunkest_pdk_historical_random_forest_train_2020-25_test_2025-26_v1.joblib`
- Per-game predictions: `data/processed/dunkest_pdk_holdout_2025-26_predictions_v1.csv`
- Metrics: `data/processed/dunkest_pdk_holdout_2025-26_metrics_v1.csv`
- Audit/metadata: `data/processed/dunkest_pdk_holdout_2025-26_audit_v1.json` and `data/processed/dunkest_pdk_historical_random_forest_train_2020-25_test_2025-26_v1.json`

## Production status

The model is intentionally **not yet integrated** into the production season-opener. It uses a different, game-level feature schema from the existing production predictor. Integration requires a matching inference feature builder and separate regression tests; this artifact alone does not change current forecasts or lineup recommendations.
