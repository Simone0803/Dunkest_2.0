# Multi-season production-adapter walk-forward validation

Generated UTC: 2026-10-14T10:34:03.002809+00:00

This experiment evaluates the exact production adapter on chronological test seasons. It changes no production model weights.

## Point metrics

| Test season | Method | Train rows | Train seasons | N | MAE | RMSE | Bias | Ridge alpha |
|---|---|---:|---|---:|---:|---:|---:|---:|
| 2022-23 | previous_season_only | 18422 | 2021-22 | 19165 | 7.585 | 9.877 | -0.374 | 10.0 |
| 2022-23 | all_prior_certified_seasons | 36084 | 2020-21;2021-22 | 19165 | 7.575 | 9.886 | -0.558 | 30.0 |
| 2022-23 | all_prior_certified_seasons_rookie_weighted | 36084 | 2020-21;2021-22 | 19165 | 7.574 | 9.889 | -0.593 | 30.0 |
| 2023-24 | previous_season_only | 19165 | 2022-23 | 18927 | 7.595 | 9.858 | -0.058 | 30.0 |
| 2023-24 | all_prior_certified_seasons | 55249 | 2020-21;2021-22;2022-23 | 18927 | 7.576 | 9.872 | -0.410 | 30.0 |
| 2023-24 | all_prior_certified_seasons_rookie_weighted | 55249 | 2020-21;2021-22;2022-23 | 18927 | 7.575 | 9.874 | -0.438 | 30.0 |
| 2024-25 | previous_season_only | 18927 | 2023-24 | 19590 | 7.651 | 9.946 | -0.025 | 30.0 |
| 2024-25 | all_prior_certified_seasons | 74176 | 2020-21;2021-22;2022-23;2023-24 | 19590 | 7.633 | 9.947 | -0.344 | 0.3 |
| 2024-25 | all_prior_certified_seasons_rookie_weighted | 74176 | 2020-21;2021-22;2022-23;2023-24 | 19590 | 7.632 | 9.948 | -0.364 | 0.3 |
| 2025-26 | previous_season_only | 19590 | 2024-25 | 18412 | 7.633 | 9.895 | -0.017 | 0.3 |
| 2025-26 | all_prior_certified_seasons | 93766 | 2020-21;2021-22;2022-23;2023-24;2024-25 | 18412 | 7.605 | 9.893 | -0.279 | 0.3 |
| 2025-26 | all_prior_certified_seasons_rookie_weighted | 93766 | 2020-21;2021-22;2022-23;2023-24;2024-25 | 18412 | 7.604 | 9.893 | -0.296 | 0.3 |

## Paired date-cluster bootstrap: MAE differences

| Test season | Comparison | Paired rows | MAE difference | 95% CI |
|---|---|---:|---:|---|
| 2022-23 | all_prior_certified_seasons minus previous_season_only | 19165 | -0.0091 | [-0.0139, -0.0047] |
| 2022-23 | all_prior_certified_seasons_rookie_weighted minus all_prior_certified_seasons | 19165 | -0.0018 | [-0.0025, -0.0011] |
| 2023-24 | all_prior_certified_seasons minus previous_season_only | 18927 | -0.0189 | [-0.0256, -0.0111] |
| 2023-24 | all_prior_certified_seasons_rookie_weighted minus all_prior_certified_seasons | 18927 | -0.0015 | [-0.0021, -0.0009] |
| 2024-25 | all_prior_certified_seasons minus previous_season_only | 19590 | -0.0181 | [-0.0250, -0.0105] |
| 2024-25 | all_prior_certified_seasons_rookie_weighted minus all_prior_certified_seasons | 19590 | -0.0010 | [-0.0016, -0.0005] |
| 2025-26 | all_prior_certified_seasons minus previous_season_only | 18412 | -0.0282 | [-0.0331, -0.0228] |
| 2025-26 | all_prior_certified_seasons_rookie_weighted minus all_prior_certified_seasons | 18412 | -0.0012 | [-0.0017, -0.0008] |

## Low-history cohort

The cohort is defined as at most five prior observed Dunkest rows; it is not a verified NBA draft-rookie label.

| Test season | Method | Cohort | N | MAE | RMSE | Bias |
|---|---|---|---:|---:|---:|---:|
| 2022-23 | all_prior_certified_seasons | history_gt_5 | 18709 | 7.612 | 9.927 | -0.591 |
| 2022-23 | all_prior_certified_seasons | low_history_le_5 | 456 | 6.079 | 8.028 | 0.797 |
| 2022-23 | all_prior_certified_seasons_rookie_weighted | history_gt_5 | 18709 | 7.610 | 9.930 | -0.626 |
| 2022-23 | all_prior_certified_seasons_rookie_weighted | low_history_le_5 | 456 | 6.067 | 8.019 | 0.766 |
| 2022-23 | previous_season_only | history_gt_5 | 18709 | 7.620 | 9.917 | -0.407 |
| 2022-23 | previous_season_only | low_history_le_5 | 456 | 6.111 | 8.057 | 0.948 |
| 2023-24 | all_prior_certified_seasons | history_gt_5 | 18409 | 7.618 | 9.918 | -0.447 |
| 2023-24 | all_prior_certified_seasons | low_history_le_5 | 518 | 6.098 | 8.094 | 0.885 |
| 2023-24 | all_prior_certified_seasons_rookie_weighted | history_gt_5 | 18409 | 7.617 | 9.920 | -0.474 |
| 2023-24 | all_prior_certified_seasons_rookie_weighted | low_history_le_5 | 518 | 6.092 | 8.086 | 0.865 |
| 2023-24 | previous_season_only | history_gt_5 | 18409 | 7.634 | 9.899 | -0.093 |
| 2023-24 | previous_season_only | low_history_le_5 | 518 | 6.228 | 8.268 | 1.179 |
| 2024-25 | all_prior_certified_seasons | history_gt_5 | 19110 | 7.678 | 9.994 | -0.383 |
| 2024-25 | all_prior_certified_seasons | low_history_le_5 | 480 | 5.860 | 7.838 | 1.222 |
| 2024-25 | all_prior_certified_seasons_rookie_weighted | history_gt_5 | 19110 | 7.677 | 9.995 | -0.404 |
| 2024-25 | all_prior_certified_seasons_rookie_weighted | low_history_le_5 | 480 | 5.850 | 7.823 | 1.203 |
| 2024-25 | previous_season_only | history_gt_5 | 19110 | 7.695 | 9.991 | -0.057 |
| 2024-25 | previous_season_only | low_history_le_5 | 480 | 5.922 | 7.979 | 1.245 |
| 2025-26 | all_prior_certified_seasons | history_gt_5 | 17888 | 7.658 | 9.949 | -0.318 |
| 2025-26 | all_prior_certified_seasons | low_history_le_5 | 524 | 5.802 | 7.724 | 1.044 |
| 2025-26 | all_prior_certified_seasons_rookie_weighted | history_gt_5 | 17888 | 7.657 | 9.950 | -0.335 |
| 2025-26 | all_prior_certified_seasons_rookie_weighted | low_history_le_5 | 524 | 5.795 | 7.716 | 1.035 |
| 2025-26 | previous_season_only | history_gt_5 | 17888 | 7.683 | 9.949 | -0.057 |
| 2025-26 | previous_season_only | low_history_le_5 | 524 | 5.939 | 7.857 | 1.347 |

## Limitations

- 2025/26 has already been examined in prior project experiments; it is not a globally untouched final holdout.
- The learner is Ridge, used to isolate the effect of the training window; this is not a full comparison of the production ensemble.
- The V3 dataset provides certified PDK targets from 2020/21 onward. 2018/19–2019/20 are not supervised Dunkest targets because archived validity flags are false.
- Production multi-season training remains enabled only for opening-round forecasts and continues to use the separate 2025/26 inference feature matrix.

## Artifacts

- JSON: reports/audit/dunkest_multiseason_production_adapter_walk_forward_20261014_v3.json
- Metrics: reports/audit/dunkest_multiseason_production_adapter_walk_forward_20261014_v3_metrics.csv
- Predictions: reports/audit/dunkest_multiseason_production_adapter_walk_forward_20261014_v3_predictions.csv
