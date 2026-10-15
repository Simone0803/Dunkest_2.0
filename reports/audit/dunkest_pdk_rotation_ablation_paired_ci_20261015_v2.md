# PDK rotation-feature ablation: paired date-cluster confidence intervals — V2

Generated UTC: 2026-10-15T13:42:55+00:00

## Protocol

- Source: `reports/audit/dunkest_pdk_lag_rotation_feature_ablation_20261014_v1_predictions.csv`; no model retraining.
- Identical paired player-game rows and targets for expanded-lag and rotation-aware variants.
- Seasons: 2022/23–2024/25 only. 2025/26 final holdout and frozen 2026/27 GW1 were not loaded.
- 2,000 paired bootstrap resamples of target-date clusters, sampled within season.
- Delta = rotation-aware minus expanded-lag; negative MAE/RMSE favours rotation-aware.

- Paired rows: 115,364; distinct season-date clusters: 475.

## Results

| Model | Cohort | N | Dates | Expanded MAE | Rotation MAE | Δ MAE (95% CI) | Expanded RMSE | Rotation RMSE | Δ RMSE (95% CI) |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| et12 | all | 57,682 | 475 | 7.5696 | 7.5782 | +0.0086 [+0.0034, +0.0136] | 9.8456 | 9.8446 | -0.0010 [-0.0064, +0.0045] |
| et12 | actual_pdk_ge_25 | 13,104 | 475 | 12.2241 | 12.1920 | -0.0321 [-0.0442, -0.0196] | 14.7351 | 14.6962 | -0.0389 [-0.0498, -0.0279] |
| et12 | history_games_lt_5 | 1,222 | 318 | 5.1372 | 5.1418 | +0.0046 [-0.0174, +0.0262] | 7.0384 | 7.0487 | +0.0103 [-0.0133, +0.0342] |
| et12 | no_prior_games | 249 | 101 | 5.0763 | 5.0869 | +0.0106 [-0.0103, +0.0310] | 6.7962 | 6.8059 | +0.0096 [-0.0094, +0.0265] |
| hgb | all | 57,682 | 475 | 7.5615 | 7.5637 | +0.0022 [-0.0043, +0.0088] | 9.8241 | 9.8279 | +0.0037 [-0.0035, +0.0114] |
| hgb | actual_pdk_ge_25 | 13,104 | 475 | 12.1245 | 12.1320 | +0.0075 [-0.0105, +0.0250] | 14.6383 | 14.6435 | +0.0052 [-0.0110, +0.0209] |
| hgb | history_games_lt_5 | 1,222 | 318 | 5.1876 | 5.1910 | +0.0034 [-0.0152, +0.0229] | 7.0558 | 7.0622 | +0.0064 [-0.0137, +0.0274] |
| hgb | no_prior_games | 249 | 101 | 5.3590 | 5.3702 | +0.0112 [-0.0334, +0.0625] | 6.8257 | 6.8250 | -0.0008 [-0.0385, +0.0424] |

## Interpretation rules

- A confidence interval spanning zero is inconclusive for that metric and cohort.
- Even an interval below zero supports only a player-level predictive gain on these outer folds; it does not certify lineup-score improvement.
- No team-change claim is made: the source lacks a verified team-change label.
- Production configuration and model weights are unchanged.

## Artifacts

- JSON: `reports/audit/dunkest_pdk_rotation_ablation_paired_ci_20261015_v2.json`
- CSV: `reports/audit/dunkest_pdk_rotation_ablation_paired_ci_20261015_v2_comparisons.csv`
- This report is an uncertainty audit over existing saved predictions; it is not a new holdout.
