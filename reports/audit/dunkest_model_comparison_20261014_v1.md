# Dunkest model comparison: training window, recent-score baselines and cohorts

Generated UTC: 2026-10-14T10:50:18.337585+00:00

## Protocol

- Official certified PDK targets only; test seasons 2022/23–2025/26.
- Identical test rows for single-season, multi-season, low-history-weighted multi-season, and previous-3/5/10-score baselines.
- The Ridge learner uses the production feature adapter; training windows and weights are the only model-side comparison.
- All training seasons precede the test season. Recent-score baselines use lagged values; missing history falls back to a median computed from prior seasons only.
- Rookie class is name/draft-year matched and is not a perfect NBA debut label. History cohorts are a complementary, broader proxy.
- Historical position is unavailable in this certified dataset, so position-wise claims are intentionally omitted.

## Metrics by season

| season  | method                            | n     | mae   | rmse   | bias_pred_minus_actual |
| ------- | --------------------------------- | ----- | ----- | ------ | ---------------------- |
| 2022-23 | single_season                     | 19165 | 7.585 | 9.877  | -0.374                 |
| 2022-23 | multi_season                      | 19165 | 7.575 | 9.886  | -0.558                 |
| 2022-23 | multi_season_low_history_weighted | 19165 | 7.574 | 9.889  | -0.593                 |
| 2022-23 | baseline_prev3_mean               | 19165 | 8.297 | 10.888 | -0.041                 |
| 2022-23 | baseline_prev5_mean               | 19165 | 7.975 | 10.440 | -0.057                 |
| 2022-23 | baseline_prev10_mean              | 19165 | 7.769 | 10.113 | -0.069                 |
| 2023-24 | single_season                     | 18927 | 7.595 | 9.858  | -0.058                 |
| 2023-24 | multi_season                      | 18927 | 7.576 | 9.872  | -0.410                 |
| 2023-24 | multi_season_low_history_weighted | 18927 | 7.575 | 9.874  | -0.438                 |
| 2023-24 | baseline_prev3_mean               | 18927 | 8.319 | 10.888 | 0.073                  |
| 2023-24 | baseline_prev5_mean               | 18927 | 7.969 | 10.415 | 0.064                  |
| 2023-24 | baseline_prev10_mean              | 18927 | 7.765 | 10.100 | 0.048                  |
| 2024-25 | single_season                     | 19590 | 7.651 | 9.946  | -0.025                 |
| 2024-25 | multi_season                      | 19590 | 7.633 | 9.947  | -0.344                 |
| 2024-25 | multi_season_low_history_weighted | 19590 | 7.632 | 9.948  | -0.364                 |
| 2024-25 | baseline_prev3_mean               | 19590 | 8.359 | 10.957 | -0.014                 |
| 2024-25 | baseline_prev5_mean               | 19590 | 8.003 | 10.458 | -0.023                 |
| 2024-25 | baseline_prev10_mean              | 19590 | 7.792 | 10.180 | -0.069                 |
| 2025-26 | single_season                     | 18412 | 7.633 | 9.895  | -0.017                 |
| 2025-26 | multi_season                      | 18412 | 7.605 | 9.893  | -0.279                 |
| 2025-26 | multi_season_low_history_weighted | 18412 | 7.604 | 9.893  | -0.296                 |
| 2025-26 | baseline_prev3_mean               | 18412 | 8.328 | 10.905 | 0.007                  |
| 2025-26 | baseline_prev5_mean               | 18412 | 8.005 | 10.443 | -0.014                 |
| 2025-26 | baseline_prev10_mean              | 18412 | 7.789 | 10.154 | -0.048                 |

## Stability across seasons

| method                            | seasons | mean_season_mae | std_season_mae | min_season_mae | max_season_mae | mean_rmse | mean_bias |
| --------------------------------- | ------- | --------------- | -------------- | -------------- | -------------- | --------- | --------- |
| baseline_prev10_mean              | 4       | 7.779           | 0.014          | 7.765          | 7.792          | 10.137    | -0.035    |
| baseline_prev3_mean               | 4       | 8.326           | 0.025          | 8.297          | 8.359          | 10.909    | 0.006     |
| baseline_prev5_mean               | 4       | 7.988           | 0.019          | 7.969          | 8.005          | 10.439    | -0.007    |
| multi_season                      | 4       | 7.598           | 0.028          | 7.575          | 7.633          | 9.900     | -0.398    |
| multi_season_low_history_weighted | 4       | 7.596           | 0.028          | 7.574          | 7.632          | 9.901     | -0.423    |
| single_season                     | 4       | 7.616           | 0.031          | 7.585          | 7.651          | 9.894     | -0.119    |

## Draft-rookie cohort

| season  | method                            | cohort                 | n     | mae   | rmse   | bias_pred_minus_actual |
| ------- | --------------------------------- | ---------------------- | ----- | ----- | ------ | ---------------------- |
| 2022-23 | baseline_prev10_mean              | non_draft_rookie_class | 17749 | 7.854 | 10.215 | -0.040                 |
| 2022-23 | baseline_prev10_mean              | draft_rookie_class     | 1416  | 6.703 | 8.740  | -0.429                 |
| 2022-23 | baseline_prev3_mean               | non_draft_rookie_class | 17749 | 8.389 | 10.998 | -0.033                 |
| 2022-23 | baseline_prev3_mean               | draft_rookie_class     | 1416  | 7.142 | 9.401  | -0.146                 |
| 2022-23 | baseline_prev5_mean               | non_draft_rookie_class | 17749 | 8.068 | 10.554 | -0.043                 |
| 2022-23 | baseline_prev5_mean               | draft_rookie_class     | 1416  | 6.803 | 8.893  | -0.230                 |
| 2022-23 | multi_season                      | non_draft_rookie_class | 17749 | 7.650 | 9.983  | -0.613                 |
| 2022-23 | multi_season                      | draft_rookie_class     | 1416  | 6.642 | 8.579  | 0.134                  |
| 2022-23 | multi_season_low_history_weighted | non_draft_rookie_class | 17749 | 7.648 | 9.986  | -0.649                 |
| 2022-23 | multi_season_low_history_weighted | draft_rookie_class     | 1416  | 6.640 | 8.581  | 0.106                  |
| 2022-23 | single_season                     | non_draft_rookie_class | 17749 | 7.659 | 9.973  | -0.425                 |
| 2022-23 | single_season                     | draft_rookie_class     | 1416  | 6.657 | 8.585  | 0.260                  |
| 2023-24 | baseline_prev10_mean              | non_draft_rookie_class | 17686 | 7.869 | 10.207 | 0.067                  |
| 2023-24 | baseline_prev10_mean              | draft_rookie_class     | 1241  | 6.293 | 8.426  | -0.223                 |
| 2023-24 | baseline_prev3_mean               | non_draft_rookie_class | 17686 | 8.445 | 11.020 | 0.077                  |
| 2023-24 | baseline_prev3_mean               | draft_rookie_class     | 1241  | 6.516 | 8.786  | 0.014                  |
| 2023-24 | baseline_prev5_mean               | non_draft_rookie_class | 17686 | 8.078 | 10.532 | 0.074                  |
| 2023-24 | baseline_prev5_mean               | draft_rookie_class     | 1241  | 6.404 | 8.574  | -0.086                 |
| 2023-24 | multi_season                      | non_draft_rookie_class | 17686 | 7.673 | 9.983  | -0.469                 |
| 2023-24 | multi_season                      | draft_rookie_class     | 1241  | 6.197 | 8.141  | 0.418                  |
| 2023-24 | multi_season_low_history_weighted | non_draft_rookie_class | 17686 | 7.672 | 9.984  | -0.496                 |
| 2023-24 | multi_season_low_history_weighted | draft_rookie_class     | 1241  | 6.192 | 8.138  | 0.397                  |
| 2023-24 | single_season                     | non_draft_rookie_class | 17686 | 7.688 | 9.965  | -0.110                 |
| 2023-24 | single_season                     | draft_rookie_class     | 1241  | 6.268 | 8.191  | 0.693                  |
| 2024-25 | baseline_prev10_mean              | non_draft_rookie_class | 18100 | 7.882 | 10.274 | -0.010                 |
| 2024-25 | baseline_prev10_mean              | draft_rookie_class     | 1490  | 6.700 | 8.947  | -0.790                 |
| 2024-25 | baseline_prev3_mean               | non_draft_rookie_class | 18100 | 8.472 | 11.080 | 0.009                  |
| 2024-25 | baseline_prev3_mean               | draft_rookie_class     | 1490  | 6.986 | 9.327  | -0.291                 |
| 2024-25 | baseline_prev5_mean               | non_draft_rookie_class | 18100 | 8.105 | 10.568 | 0.013                  |
| 2024-25 | baseline_prev5_mean               | draft_rookie_class     | 1490  | 6.765 | 9.026  | -0.460                 |
| 2024-25 | multi_season                      | non_draft_rookie_class | 18100 | 7.727 | 10.049 | -0.370                 |
| 2024-25 | multi_season                      | draft_rookie_class     | 1490  | 6.497 | 8.606  | -0.018                 |
| 2024-25 | multi_season_low_history_weighted | non_draft_rookie_class | 18100 | 7.726 | 10.051 | -0.391                 |
| 2024-25 | multi_season_low_history_weighted | draft_rookie_class     | 1490  | 6.493 | 8.604  | -0.036                 |
| 2024-25 | single_season                     | non_draft_rookie_class | 18100 | 7.746 | 10.047 | -0.036                 |
| 2024-25 | single_season                     | draft_rookie_class     | 1490  | 6.509 | 8.627  | 0.108                  |
| 2025-26 | baseline_prev10_mean              | non_draft_rookie_class | 16736 | 7.890 | 10.264 | 0.000                  |
| 2025-26 | baseline_prev10_mean              | draft_rookie_class     | 1676  | 6.780 | 8.984  | -0.528                 |
| 2025-26 | baseline_prev3_mean               | non_draft_rookie_class | 16736 | 8.438 | 11.028 | 0.024                  |
| 2025-26 | baseline_prev3_mean               | draft_rookie_class     | 1676  | 7.230 | 9.591  | -0.159                 |
| 2025-26 | baseline_prev5_mean               | non_draft_rookie_class | 16736 | 8.110 | 10.559 | 0.013                  |
| 2025-26 | baseline_prev5_mean               | draft_rookie_class     | 1676  | 6.961 | 9.215  | -0.284                 |
| 2025-26 | multi_season                      | non_draft_rookie_class | 16736 | 7.701 | 10.007 | -0.335                 |
| 2025-26 | multi_season                      | draft_rookie_class     | 1676  | 6.642 | 8.669  | 0.283                  |
| 2025-26 | multi_season_low_history_weighted | non_draft_rookie_class | 16736 | 7.700 | 10.008 | -0.353                 |
| 2025-26 | multi_season_low_history_weighted | draft_rookie_class     | 1676  | 6.640 | 8.667  | 0.268                  |
| 2025-26 | single_season                     | non_draft_rookie_class | 16736 | 7.727 | 10.007 | -0.073                 |
| 2025-26 | single_season                     | draft_rookie_class     | 1676  | 6.700 | 8.704  | 0.548                  |

## Interpretation

A multi-season model is preferable only if it improves error consistently without unacceptable bias. Compare its gains against the previous-score means: a small improvement over a weak single-season model is not sufficient if the simple baseline remains competitive. Rookie estimates should be read alongside cohort size and bias; name-based draft-year cohorts are imperfect, and the low-history proxy is not equivalent to a rookie label. 2025/26 is not a pristine holdout.

## Artifacts

- Metrics: `reports/audit/dunkest_model_comparison_20261014_v1_metrics.csv`
- Cohorts: `reports/audit/dunkest_model_comparison_20261014_v1_cohorts.csv`
- Per-game predictions: `reports/audit/dunkest_model_comparison_20261014_v1_predictions.csv`
- Audit: `reports/audit/dunkest_model_comparison_20261014_v1.json`
