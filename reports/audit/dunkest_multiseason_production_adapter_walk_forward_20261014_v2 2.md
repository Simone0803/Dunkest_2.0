# Multi-season production-adapter walk-forward validation

Generated UTC: 2026-10-14T10:31:54.447477+00:00

This experiment evaluates the exact production adapter on chronological test seasons. It changes no production model weights.

## Point metrics

| Test season | Method | Train rows | Train seasons | N | MAE | RMSE | Bias | Ridge alpha |
|---|---|---:|---|---:|---:|---:|---:|---:|
| 2022-23 | previous_season_only | 18422 | 2021-22 | 19165 | 7.585 | 9.877 | -0.374 | 30.0 |
| 2022-23 | all_prior_certified_seasons | 36084 | 2020-21;2021-22 | 19165 | 7.575 | 9.886 | -0.558 | 30.0 |
| 2023-24 | previous_season_only | 19165 | 2022-23 | 18927 | 7.595 | 9.858 | -0.058 | 30.0 |
| 2023-24 | all_prior_certified_seasons | 55249 | 2020-21;2021-22;2022-23 | 18927 | 7.576 | 9.873 | -0.411 | 30.0 |
| 2024-25 | previous_season_only | 18927 | 2023-24 | 19590 | 7.651 | 9.946 | -0.025 | 30.0 |
| 2024-25 | all_prior_certified_seasons | 74176 | 2020-21;2021-22;2022-23;2023-24 | 19590 | 7.633 | 9.947 | -0.343 | 30.0 |
| 2025-26 | previous_season_only | 19590 | 2024-25 | 18412 | 7.633 | 9.895 | -0.016 | 30.0 |
| 2025-26 | all_prior_certified_seasons | 93766 | 2020-21;2021-22;2022-23;2023-24;2024-25 | 18412 | 7.605 | 9.893 | -0.279 | 0.3 |

## Paired date-cluster bootstrap: MAE difference (multi-season − previous-season-only)

| Test season | Paired rows | MAE difference | 95% CI |
|---|---:|---:|---|
| 2022-23 | 19165 | -0.0092 | [-0.0138, -0.0048] |
| 2023-24 | 18927 | -0.0188 | [-0.0261, -0.0111] |
| 2024-25 | 19590 | -0.0180 | [-0.0257, -0.0104] |
| 2025-26 | 18412 | -0.0282 | [-0.0334, -0.0228] |

## Low-history cohort

The cohort is defined as at most five prior observed Dunkest rows; it is not a verified NBA draft-rookie label.

| Test season | Method | Cohort | N | MAE | RMSE | Bias |
|---|---|---|---:|---:|---:|---:|
| 2022-23 | all_prior_certified_seasons | history_gt_5 | 18709 | 7.612 | 9.927 | -0.591 |
| 2022-23 | all_prior_certified_seasons | low_history_le_5 | 456 | 6.078 | 8.027 | 0.797 |
| 2022-23 | previous_season_only | history_gt_5 | 18709 | 7.621 | 9.917 | -0.407 |
| 2022-23 | previous_season_only | low_history_le_5 | 456 | 6.112 | 8.057 | 0.947 |
| 2023-24 | all_prior_certified_seasons | history_gt_5 | 18409 | 7.618 | 9.918 | -0.448 |
| 2023-24 | all_prior_certified_seasons | low_history_le_5 | 518 | 6.097 | 8.093 | 0.886 |
| 2023-24 | previous_season_only | history_gt_5 | 18409 | 7.634 | 9.900 | -0.093 |
| 2023-24 | previous_season_only | low_history_le_5 | 518 | 6.227 | 8.265 | 1.181 |
| 2024-25 | all_prior_certified_seasons | history_gt_5 | 19110 | 7.678 | 9.994 | -0.383 |
| 2024-25 | all_prior_certified_seasons | low_history_le_5 | 480 | 5.859 | 7.837 | 1.221 |
| 2024-25 | previous_season_only | history_gt_5 | 19110 | 7.695 | 9.991 | -0.057 |
| 2024-25 | previous_season_only | low_history_le_5 | 480 | 5.923 | 7.981 | 1.245 |
| 2025-26 | all_prior_certified_seasons | history_gt_5 | 17888 | 7.658 | 9.949 | -0.317 |
| 2025-26 | all_prior_certified_seasons | low_history_le_5 | 524 | 5.803 | 7.724 | 1.044 |
| 2025-26 | previous_season_only | history_gt_5 | 17888 | 7.683 | 9.949 | -0.056 |
| 2025-26 | previous_season_only | low_history_le_5 | 524 | 5.936 | 7.857 | 1.344 |

## Limitations

- 2025/26 has already been examined in prior project experiments; it is not a globally untouched final holdout.
- The learner is Ridge, used to isolate the effect of the training window; this is not a full comparison of the production ensemble.
- The V3 dataset provides certified PDK targets from 2020/21 onward. 2018/19–2019/20 are not supervised Dunkest targets because archived validity flags are false.
- Production multi-season training remains enabled only for opening-round forecasts and continues to use the separate 2025/26 inference feature matrix.

## Artifacts

- JSON: reports/audit/dunkest_multiseason_production_adapter_walk_forward_20261014_v2.json
- Metrics: reports/audit/dunkest_multiseason_production_adapter_walk_forward_20261014_v2_metrics.csv
- Predictions: reports/audit/dunkest_multiseason_production_adapter_walk_forward_20261014_v2_predictions.csv
