# Dunkest PDK model tuning — 20261012_v1

Created: 2026-10-12T17:36:08.858131+00:00

## Protocol

- Hyperparameter/model selection uses expanding-season folds testing 2022/23, 2023/24 and 2024/25 only.
- Final fit uses all verified official labels from 2020/21–2024/25 (93,766 player-game rows).
- 2025/26 (18,412 rows) is excluded from tuning and used for final historical comparison.
- 2018/19–2019/20 are excluded as supervised target seasons because the archived validity flags are all false; their verified NBA boxscores remain usable as prior features.
- 79 curated pre-game features; current-game target/boxscore fields are excluded.
- Temporal checks: 0 lag1 value mismatches, 0 lag1 missingness mismatches, 0 current/future NBA history rows.

## Expanding validation summary

| Model | Weighted MAE | Weighted RMSE | Weighted bias | Folds |
|---|---:|---:|---:|---:|
| extra_trees_deep | 7.56350 | 9.83284 | -0.17421 | 3 |
| extra_trees_regularized | 7.56390 | 9.83822 | -0.21052 | 3 |
| rf_baseline | 7.58796 | 9.85488 | -0.08805 | 3 |
| rf_regularized | 7.58880 | 9.84993 | -0.00764 | 3 |
| rf_deeper | 7.59848 | 9.85436 | 0.01168 | 3 |
| ridge | 7.62791 | 9.87785 | 0.15695 | 3 |

Selected model: **extra_trees_deep**.

## 2025/26 final historical comparison

| Model | N | MAE | RMSE | Bias | R² |
|---|---:|---:|---:|---:|---:|
| Selected extra_trees_deep | 18,412 | 7.56126 | 9.83753 | -0.17141 | 0.42360 |
| Previous-10 PDK mean | 18,412 | 7.78863 | 10.15390 | -0.04792 | 0.38593 |

Against the existing Random Forest reference on the same 2025/26 rows (MAE 7.57748, RMSE 9.85634), the tuned Extra Trees candidate reduces MAE by about 0.0162 and RMSE by about 0.0188. This is a small improvement, not a step-change. It reduces MAE by about 0.2274 versus the previous-10 mean baseline.

## Artifacts

- Training model: `data/processed/dunkest_pdk_historical_tuned_train_2020-25_test_2025-26_20261012_v1.joblib`
- Model metadata: `data/processed/dunkest_pdk_historical_tuned_train_2020-25_test_2025-26_20261012_v1.json`
- Validation predictions: `data/processed/dunkest_pdk_model_tuning_walk_forward_20261012_v1.csv`
- Fold metrics: `data/processed/dunkest_pdk_model_tuning_metrics_20261012_v1.csv`
- Full audit: `data/processed/dunkest_pdk_model_tuning_audit_20261012_v1.json`

## Production status

The tuned candidate is trained and saved, but remains separate from production. It uses a game-level feature schema that is not yet wired into the production inference path. Do not replace the production model until a matching feature builder and paired lineup-level validation are in place. The 2025/26 season was not used to select this candidate, but previous project experiments have inspected that same season, so it is not globally unseen.
