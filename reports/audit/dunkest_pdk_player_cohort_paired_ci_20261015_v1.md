# Paired player-cohort uncertainty audit — V1

Generated UTC: 2026-10-15T13:47:42+00:00

## Protocol

- Source: `reports/audit/dunkest_pdk_lag_rotation_feature_ablation_20261014_v1_predictions.csv`
- Paired rows: 115,364; date clusters: 475; bootstrap resamples: 2,000.
 - Same targets and keys for both variants; target dates resampled within each season.
- Only 2022/23–2024/25 outer folds; no 2025/26 holdout or frozen 2026/27 GW1 loaded.
- Δ = rotation-aware minus expanded-lags; negative MAE/RMSE favours rotation-aware.
- Cohorts with fewer than 50 rows omitted.

## Results

| Model | Axis | Cohort | N | Players | Dates | Δ MAE [95% CI] | Δ RMSE [95% CI] | Δ bias |
|---|---|---|---:|---:|---:|---:|---:|---:|
| et12 | all | all | 57,682 | 671 | 475 | +0.0086 [+0.0034, +0.0136] | -0.0010 [-0.0064, +0.0045] | +0.0563 |
| et12 | history | history_1_4 | 973 | 250 | 290 | +0.0031 [-0.0248, +0.0316] | +0.0104 [-0.0198, +0.0399] | -0.0160 |
| et12 | history | history_20_plus | 53,187 | 597 | 475 | +0.0093 [+0.0041, +0.0143] | -0.0012 [-0.0066, +0.0044] | +0.0625 |
| et12 | history | history_5_19 | 3,273 | 257 | 441 | -0.0026 [-0.0178, +0.0113] | -0.0012 [-0.0175, +0.0156] | -0.0196 |
| et12 | history | no_prior_games | 249 | 249 | 101 | +0.0106 [-0.0100, +0.0308] | +0.0096 [-0.0091, +0.0258] | +0.0067 |
| et12 | minutes | minutes_15_29 | 25,081 | 628 | 475 | +0.0074 [+0.0000, +0.0145] | -0.0019 [-0.0096, +0.0056] | +0.0578 |
| et12 | minutes | minutes_ge30 | 19,008 | 531 | 475 | -0.0105 [-0.0201, -0.0012] | -0.0166 [-0.0263, -0.0074] | +0.0569 |
| et12 | minutes | minutes_lt15 | 13,593 | 625 | 475 | +0.0375 [+0.0292, +0.0461] | +0.0405 [+0.0307, +0.0508] | +0.0525 |
| et12 | actual | actual_pdk_10_24_99 | 21,721 | 630 | 475 | -0.0076 [-0.0153, +0.0002] | -0.0090 [-0.0177, -0.0005] | +0.0601 |
| et12 | actual | actual_pdk_ge25 | 13,104 | 508 | 475 | -0.0321 [-0.0442, -0.0198] | -0.0389 [-0.0497, -0.0275] | +0.0544 |
| et12 | actual | actual_pdk_lt10 | 22,857 | 666 | 475 | +0.0473 [+0.0401, +0.0546] | +0.0428 [+0.0349, +0.0513] | +0.0537 |
| hgb | all | all | 57,682 | 671 | 475 | +0.0022 [-0.0041, +0.0086] | +0.0037 [-0.0035, +0.0112] | +0.0025 |
| hgb | history | history_1_4 | 973 | 250 | 290 | +0.0014 [-0.0161, +0.0206] | +0.0082 [-0.0142, +0.0309] | -0.0402 |
| hgb | history | history_20_plus | 53,187 | 597 | 475 | +0.0030 [-0.0040, +0.0099] | +0.0040 [-0.0038, +0.0117] | +0.0048 |
| hgb | history | history_5_19 | 3,273 | 257 | 441 | -0.0101 [-0.0213, +0.0004] | -0.0022 [-0.0164, +0.0111] | -0.0241 |
| hgb | history | no_prior_games | 249 | 249 | 101 | +0.0112 [-0.0334, +0.0628] | -0.0008 [-0.0388, +0.0475] | +0.0220 |
| hgb | minutes | minutes_15_29 | 25,081 | 628 | 475 | -0.0026 [-0.0107, +0.0053] | +0.0024 [-0.0063, +0.0119] | -0.0025 |
| hgb | minutes | minutes_ge30 | 19,008 | 531 | 475 | +0.0123 [-0.0005, +0.0261] | +0.0065 [-0.0071, +0.0199] | +0.0145 |
| hgb | minutes | minutes_lt15 | 13,593 | 625 | 475 | -0.0030 [-0.0123, +0.0063] | +0.0005 [-0.0116, +0.0129] | -0.0052 |
| hgb | actual | actual_pdk_10_24_99 | 21,721 | 630 | 475 | +0.0086 [-0.0021, +0.0190] | +0.0136 [+0.0013, +0.0263] | +0.0113 |
| hgb | actual | actual_pdk_ge25 | 13,104 | 508 | 475 | +0.0075 [-0.0093, +0.0245] | +0.0052 [-0.0103, +0.0202] | +0.0143 |
| hgb | actual | actual_pdk_lt10 | 22,857 | 666 | 475 | -0.0068 [-0.0149, +0.0011] | -0.0051 [-0.0148, +0.0054] | -0.0127 |

## Interpretation

- CI entirely below zero: evidence of lower error for that cohort on these folds; CI crossing zero: inconclusive; CI above zero: evidence of a small regression.
- Minutes and realized-score strata are retrospective diagnostics, not known pre-match decision variables.
- No cohort result alone authorizes a production promotion; this is player-game accuracy, not realized lineup score.
- No weights/features changed.

## Artifacts
- JSON: `reports/audit/dunkest_pdk_player_cohort_paired_ci_20261015_v1.json`
- CSV: `reports/audit/dunkest_pdk_player_cohort_paired_ci_20261015_v1_cohorts.csv`
