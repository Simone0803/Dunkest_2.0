# Production ensemble: single-season vs multi-season walk-forward

Generated UTC: 2026-10-18T09:28:32.284668+00:00

This experiment runs the actual production ensemble and feature adapter on official Dunkest PDK labels. It does not modify production weights or configuration.

## Overall metrics

| Test season | Method | Train rows | MAE | RMSE | Bias | Ensemble weights |
|---|---|---:|---:|---:|---:|---|
| 2022-23 | previous_season_only | 18422 | 7.5432 | 9.7648 | 0.1302 | `{"gbr": 0.3313282630758549, "rf": 0.33432202873535033, "ridge": 0.33434970818879484}` |
| 2022-23 | all_prior_seasons | 36084 | 7.5229 | 9.7590 | -0.0520 | `{"gbr": 0.3322394096547068, "rf": 0.3328939431719925, "ridge": 0.3348666471733007}` |
| 2022-23 | all_prior_seasons_low_history_weighted | 36084 | 7.5193 | 9.7538 | -0.0422 | `{"gbr": 0.3332275939679287, "rf": 0.33246289334868173, "ridge": 0.3343095126833895}` |
| 2023-24 | previous_season_only | 19165 | 7.5408 | 9.7667 | -0.0347 | `{"gbr": 0.3337022748751325, "rf": 0.3319900468577341, "ridge": 0.33430767826713337}` |
| 2023-24 | all_prior_seasons | 55249 | 7.5130 | 9.7463 | -0.0338 | `{"gbr": 0.33385064803479403, "rf": 0.3322540408292695, "ridge": 0.3338953111359365}` |
| 2023-24 | all_prior_seasons_low_history_weighted | 55249 | 7.4985 | 9.7462 | -0.1796 | `{"gbr": 0.3341286293199137, "rf": 0.33218257906262877, "ridge": 0.3336887916174575}` |
| 2024-25 | previous_season_only | 18927 | 7.5241 | 9.8082 | -0.0586 | `{"gbr": 0.33289850077269667, "rf": 0.3326947594221258, "ridge": 0.3344067398051776}` |
| 2024-25 | all_prior_seasons | 74176 | 7.5212 | 9.7939 | -0.1014 | `{"gbr": 0.3331370374379901, "rf": 0.3327626902670821, "ridge": 0.3341002722949277}` |
| 2024-25 | all_prior_seasons_low_history_weighted | 74176 | 7.5183 | 9.7932 | -0.1137 | `{"gbr": 0.3321623919327591, "rf": 0.3332917289879875, "ridge": 0.33454587907925337}` |

## Cohort metrics

| Test season | Method | Cohort | N | MAE | RMSE | Bias |
|---|---|---|---:|---:|---:|---:|
| 2022-23 | all_prior_seasons | all | 19165 | 7.5229 | 9.7590 | -0.0520 |
| 2022-23 | all_prior_seasons | actual_ge_25 | 4310 | 12.1503 | 14.6406 | -11.1467 |
| 2022-23 | all_prior_seasons | actual_ge_30 | 2903 | 14.0247 | 16.4249 | -13.4782 |
| 2022-23 | all_prior_seasons | low_history_le_5 | 456 | 5.4945 | 7.4872 | -0.1191 |
| 2022-23 | all_prior_seasons | history_gt_5 | 18709 | 7.5724 | 9.8078 | -0.0504 |
| 2022-23 | all_prior_seasons_low_history_weighted | all | 19165 | 7.5193 | 9.7538 | -0.0422 |
| 2022-23 | all_prior_seasons_low_history_weighted | actual_ge_25 | 4310 | 12.1316 | 14.6188 | -11.1100 |
| 2022-23 | all_prior_seasons_low_history_weighted | actual_ge_30 | 2903 | 13.9974 | 16.3979 | -13.4393 |
| 2022-23 | all_prior_seasons_low_history_weighted | low_history_le_5 | 456 | 5.4894 | 7.4769 | -0.1625 |
| 2022-23 | all_prior_seasons_low_history_weighted | history_gt_5 | 18709 | 7.5688 | 9.8026 | -0.0393 |
| 2022-23 | previous_season_only | all | 19165 | 7.5432 | 9.7648 | 0.1302 |
| 2022-23 | previous_season_only | actual_ge_25 | 4310 | 11.9929 | 14.4754 | -10.7819 |
| 2022-23 | previous_season_only | actual_ge_30 | 2903 | 13.7769 | 16.2014 | -13.0634 |
| 2022-23 | previous_season_only | low_history_le_5 | 456 | 5.5521 | 7.5122 | -0.0339 |
| 2022-23 | previous_season_only | history_gt_5 | 18709 | 7.5918 | 9.8132 | 0.1342 |
| 2023-24 | all_prior_seasons | all | 18927 | 7.5130 | 9.7463 | -0.0338 |
| 2023-24 | all_prior_seasons | actual_ge_25 | 4369 | 12.0430 | 14.4614 | -10.9541 |
| 2023-24 | all_prior_seasons | actual_ge_30 | 2972 | 13.9132 | 16.1934 | -13.3175 |
| 2023-24 | all_prior_seasons | low_history_le_5 | 518 | 5.3626 | 7.2542 | 0.2413 |
| 2023-24 | all_prior_seasons | history_gt_5 | 18409 | 7.5735 | 9.8073 | -0.0415 |
| 2023-24 | all_prior_seasons_low_history_weighted | all | 18927 | 7.4985 | 9.7462 | -0.1796 |
| 2023-24 | all_prior_seasons_low_history_weighted | actual_ge_25 | 4369 | 12.1809 | 14.5913 | -11.1190 |
| 2023-24 | all_prior_seasons_low_history_weighted | actual_ge_30 | 2972 | 14.0563 | 16.3336 | -13.4767 |
| 2023-24 | all_prior_seasons_low_history_weighted | low_history_le_5 | 518 | 5.3571 | 7.2519 | 0.1862 |
| 2023-24 | all_prior_seasons_low_history_weighted | history_gt_5 | 18409 | 7.5587 | 9.8073 | -0.1898 |
| 2023-24 | previous_season_only | all | 18927 | 7.5408 | 9.7667 | -0.0347 |
| 2023-24 | previous_season_only | actual_ge_25 | 4369 | 12.1281 | 14.5221 | -11.0769 |
| 2023-24 | previous_season_only | actual_ge_30 | 2972 | 14.0392 | 16.2784 | -13.4513 |
| 2023-24 | previous_season_only | low_history_le_5 | 518 | 5.6155 | 7.3327 | 1.1193 |
| 2023-24 | previous_season_only | history_gt_5 | 18409 | 7.5950 | 9.8265 | -0.0672 |
| 2024-25 | all_prior_seasons | all | 19590 | 7.5212 | 9.7939 | -0.1014 |
| 2024-25 | all_prior_seasons | actual_ge_25 | 4425 | 11.9415 | 14.5212 | -10.8800 |
| 2024-25 | all_prior_seasons | actual_ge_30 | 2919 | 14.0147 | 16.4903 | -13.4038 |
| 2024-25 | all_prior_seasons | low_history_le_5 | 480 | 4.9798 | 6.7845 | 0.3896 |
| 2024-25 | all_prior_seasons | history_gt_5 | 19110 | 7.5851 | 9.8577 | -0.1138 |
| 2024-25 | all_prior_seasons_low_history_weighted | all | 19590 | 7.5183 | 9.7932 | -0.1137 |
| 2024-25 | all_prior_seasons_low_history_weighted | actual_ge_25 | 4425 | 11.9480 | 14.5289 | -10.8951 |
| 2024-25 | all_prior_seasons_low_history_weighted | actual_ge_30 | 2919 | 14.0241 | 16.4992 | -13.4190 |
| 2024-25 | all_prior_seasons_low_history_weighted | low_history_le_5 | 480 | 4.9534 | 6.7731 | 0.3194 |
| 2024-25 | all_prior_seasons_low_history_weighted | history_gt_5 | 19110 | 7.5827 | 9.8572 | -0.1246 |
| 2024-25 | previous_season_only | all | 19590 | 7.5241 | 9.8082 | -0.0586 |
| 2024-25 | previous_season_only | actual_ge_25 | 4425 | 11.8764 | 14.4767 | -10.8022 |
| 2024-25 | previous_season_only | actual_ge_30 | 2919 | 13.9745 | 16.4512 | -13.3372 |
| 2024-25 | previous_season_only | low_history_le_5 | 480 | 5.0774 | 6.8729 | 0.4866 |
| 2024-25 | previous_season_only | history_gt_5 | 19110 | 7.5855 | 9.8707 | -0.0723 |

## Limitations and decision

- 2025/26 is excluded because it has already been inspected by prior experiments; these folds are validation evidence, not a pristine final holdout.
- This tests player-game forecasts, not full lineup strategy performance.
- Low-history means at most five prior Dunkest rows, not a verified draft-rookie label.
- No production model/configuration or frozen 2026/27 GW1 artifact was modified.
- Promotion requires stable gains across folds and cohorts plus independent lineup-level evidence.

## Artifacts

- Metrics: `reports/audit/dunkest_multiseason_production_ensemble_walk_forward_20261018_v1_metrics.csv`
- Predictions: `reports/audit/dunkest_multiseason_production_ensemble_walk_forward_20261018_v1_predictions.csv`
