# Dunkest model comparison: training window, recent-score baselines and cohorts

Generated UTC: 2026-10-14T10:55:31.688582+00:00

## Protocol

- Official certified PDK targets only; test seasons 2022/23–2025/26.
- Identical test rows for single-season, multi-season, low-history-weighted multi-season, and previous-3/5/10-score baselines.
- The Ridge learner uses the production feature adapter; training windows and weights are the only model-side comparison.
- All training seasons precede the test season. Recent-score baselines use lagged values; missing history falls back to a median computed from prior seasons only.
- Rookie class is name/draft-year matched and is not a perfect NBA debut label. History cohorts are a complementary, broader proxy.
- Historical position is unavailable in this certified dataset, so position-wise claims are intentionally omitted.
- Confidence intervals use 1,000 bootstrap resamples of calendar-date clusters.

## Pooled metrics

| method                            | n       | mae   | rmse   | bias_pred_minus_actual |
| --------------------------------- | ------- | ----- | ------ | ---------------------- |
| baseline_prev10_mean              | 76094.0 | 7.779 | 10.137 | -0.035                 |
| baseline_prev3_mean               | 76094.0 | 8.326 | 10.910 | 0.006                  |
| baseline_prev5_mean               | 76094.0 | 7.988 | 10.440 | -0.008                 |
| multi_season                      | 76094.0 | 7.598 | 9.900  | -0.398                 |
| multi_season_low_history_weighted | 76094.0 | 7.596 | 9.901  | -0.424                 |
| single_season                     | 76094.0 | 7.616 | 9.895  | -0.119                 |

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

## Paired MAE comparisons (negative favours first method)

| season  | comparison                              | n     | mae_delta_a_minus_b | ci95_low | ci95_high |
| ------- | --------------------------------------- | ----- | ------------------- | -------- | --------- |
| 2022-23 | multi_season minus single_season        | 19165 | -0.009              | -0.014   | -0.004    |
| 2022-23 | multi_season minus baseline_prev10_mean | 19165 | -0.193              | -0.229   | -0.161    |
| 2023-24 | multi_season minus single_season        | 18927 | -0.019              | -0.026   | -0.011    |
| 2023-24 | multi_season minus baseline_prev10_mean | 18927 | -0.189              | -0.225   | -0.152    |
| 2024-25 | multi_season minus single_season        | 19590 | -0.018              | -0.026   | -0.010    |
| 2024-25 | multi_season minus baseline_prev10_mean | 19590 | -0.159              | -0.188   | -0.125    |
| 2025-26 | multi_season minus single_season        | 18412 | -0.028              | -0.033   | -0.023    |
| 2025-26 | multi_season minus baseline_prev10_mean | 18412 | -0.184              | -0.213   | -0.153    |

## Draft-rookie cohort (date-cluster MAE intervals)

| season  | method                            | cohort                 | n     | date_clusters | mae   | mae_ci95_low | mae_ci95_high | rmse   | bias_pred_minus_actual |
| ------- | --------------------------------- | ---------------------- | ----- | ------------- | ----- | ------------ | ------------- | ------ | ---------------------- |
| 2022-23 | baseline_prev10_mean              | non_draft_rookie_class | 17749 | 163           | 7.854 | 7.737        | 8.003         | 10.215 | -0.040                 |
| 2022-23 | baseline_prev10_mean              | draft_rookie_class     | 1416  | 155           | 6.703 | 6.400        | 7.014         | 8.740  | -0.429                 |
| 2022-23 | baseline_prev3_mean               | non_draft_rookie_class | 17749 | 163           | 8.389 | 8.256        | 8.523         | 10.998 | -0.033                 |
| 2022-23 | baseline_prev3_mean               | draft_rookie_class     | 1416  | 155           | 7.142 | 6.822        | 7.502         | 9.401  | -0.146                 |
| 2022-23 | baseline_prev5_mean               | non_draft_rookie_class | 17749 | 163           | 8.068 | 7.948        | 8.205         | 10.554 | -0.043                 |
| 2022-23 | baseline_prev5_mean               | draft_rookie_class     | 1416  | 155           | 6.803 | 6.494        | 7.131         | 8.893  | -0.230                 |
| 2022-23 | multi_season                      | non_draft_rookie_class | 17749 | 163           | 7.650 | 7.540        | 7.770         | 9.983  | -0.613                 |
| 2022-23 | multi_season                      | draft_rookie_class     | 1416  | 155           | 6.642 | 6.346        | 6.967         | 8.579  | 0.134                  |
| 2022-23 | multi_season_low_history_weighted | non_draft_rookie_class | 17749 | 163           | 7.648 | 7.532        | 7.778         | 9.986  | -0.649                 |
| 2022-23 | multi_season_low_history_weighted | draft_rookie_class     | 1416  | 155           | 6.640 | 6.346        | 6.978         | 8.581  | 0.106                  |
| 2022-23 | single_season                     | non_draft_rookie_class | 17749 | 163           | 7.659 | 7.541        | 7.791         | 9.973  | -0.425                 |
| 2022-23 | single_season                     | draft_rookie_class     | 1416  | 155           | 6.657 | 6.338        | 6.973         | 8.585  | 0.260                  |
| 2023-24 | baseline_prev10_mean              | non_draft_rookie_class | 17686 | 154           | 7.869 | 7.779        | 7.954         | 10.207 | 0.067                  |
| 2023-24 | baseline_prev10_mean              | draft_rookie_class     | 1241  | 148           | 6.293 | 5.953        | 6.643         | 8.426  | -0.223                 |
| 2023-24 | baseline_prev3_mean               | non_draft_rookie_class | 17686 | 154           | 8.445 | 8.352        | 8.543         | 11.020 | 0.077                  |
| 2023-24 | baseline_prev3_mean               | draft_rookie_class     | 1241  | 148           | 6.516 | 6.162        | 6.856         | 8.786  | 0.014                  |
| 2023-24 | baseline_prev5_mean               | non_draft_rookie_class | 17686 | 154           | 8.078 | 7.986        | 8.170         | 10.532 | 0.074                  |
| 2023-24 | baseline_prev5_mean               | draft_rookie_class     | 1241  | 148           | 6.404 | 6.078        | 6.766         | 8.574  | -0.086                 |
| 2023-24 | multi_season                      | non_draft_rookie_class | 17686 | 154           | 7.673 | 7.585        | 7.769         | 9.983  | -0.469                 |
| 2023-24 | multi_season                      | draft_rookie_class     | 1241  | 148           | 6.197 | 5.869        | 6.560         | 8.141  | 0.418                  |
| 2023-24 | multi_season_low_history_weighted | non_draft_rookie_class | 17686 | 154           | 7.672 | 7.592        | 7.759         | 9.984  | -0.496                 |
| 2023-24 | multi_season_low_history_weighted | draft_rookie_class     | 1241  | 148           | 6.192 | 5.853        | 6.546         | 8.138  | 0.397                  |
| 2023-24 | single_season                     | non_draft_rookie_class | 17686 | 154           | 7.688 | 7.602        | 7.771         | 9.965  | -0.110                 |
| 2023-24 | single_season                     | draft_rookie_class     | 1241  | 148           | 6.268 | 5.950        | 6.612         | 8.191  | 0.693                  |
| 2024-25 | baseline_prev10_mean              | non_draft_rookie_class | 18100 | 158           | 7.882 | 7.784        | 7.969         | 10.274 | -0.010                 |
| 2024-25 | baseline_prev10_mean              | draft_rookie_class     | 1490  | 153           | 6.700 | 6.391        | 6.996         | 8.947  | -0.790                 |
| 2024-25 | baseline_prev3_mean               | non_draft_rookie_class | 18100 | 158           | 8.472 | 8.361        | 8.577         | 11.080 | 0.009                  |
| 2024-25 | baseline_prev3_mean               | draft_rookie_class     | 1490  | 153           | 6.986 | 6.687        | 7.281         | 9.327  | -0.291                 |
| 2024-25 | baseline_prev5_mean               | non_draft_rookie_class | 18100 | 158           | 8.105 | 8.001        | 8.203         | 10.568 | 0.013                  |
| 2024-25 | baseline_prev5_mean               | draft_rookie_class     | 1490  | 153           | 6.765 | 6.478        | 7.090         | 9.026  | -0.460                 |
| 2024-25 | multi_season                      | non_draft_rookie_class | 18100 | 158           | 7.727 | 7.638        | 7.815         | 10.049 | -0.370                 |
| 2024-25 | multi_season                      | draft_rookie_class     | 1490  | 153           | 6.497 | 6.222        | 6.796         | 8.606  | -0.018                 |
| 2024-25 | multi_season_low_history_weighted | non_draft_rookie_class | 18100 | 158           | 7.726 | 7.638        | 7.814         | 10.051 | -0.391                 |
| 2024-25 | multi_season_low_history_weighted | draft_rookie_class     | 1490  | 153           | 6.493 | 6.188        | 6.782         | 8.604  | -0.036                 |
| 2024-25 | single_season                     | non_draft_rookie_class | 18100 | 158           | 7.746 | 7.653        | 7.837         | 10.047 | -0.036                 |
| 2024-25 | single_season                     | draft_rookie_class     | 1490  | 153           | 6.509 | 6.216        | 6.805         | 8.627  | 0.108                  |
| 2025-26 | baseline_prev10_mean              | non_draft_rookie_class | 16736 | 160           | 7.890 | 7.789        | 7.985         | 10.264 | 0.000                  |
| 2025-26 | baseline_prev10_mean              | draft_rookie_class     | 1676  | 158           | 6.780 | 6.498        | 7.103         | 8.984  | -0.528                 |
| 2025-26 | baseline_prev3_mean               | non_draft_rookie_class | 16736 | 160           | 8.438 | 8.326        | 8.554         | 11.028 | 0.024                  |
| 2025-26 | baseline_prev3_mean               | draft_rookie_class     | 1676  | 158           | 7.230 | 6.913        | 7.538         | 9.591  | -0.159                 |
| 2025-26 | baseline_prev5_mean               | non_draft_rookie_class | 16736 | 160           | 8.110 | 8.004        | 8.213         | 10.559 | 0.013                  |
| 2025-26 | baseline_prev5_mean               | draft_rookie_class     | 1676  | 158           | 6.961 | 6.647        | 7.263         | 9.215  | -0.284                 |
| 2025-26 | multi_season                      | non_draft_rookie_class | 16736 | 160           | 7.701 | 7.604        | 7.794         | 10.007 | -0.335                 |
| 2025-26 | multi_season                      | draft_rookie_class     | 1676  | 158           | 6.642 | 6.350        | 6.917         | 8.669  | 0.283                  |
| 2025-26 | multi_season_low_history_weighted | non_draft_rookie_class | 16736 | 160           | 7.700 | 7.608        | 7.800         | 10.008 | -0.353                 |
| 2025-26 | multi_season_low_history_weighted | draft_rookie_class     | 1676  | 158           | 6.640 | 6.349        | 6.926         | 8.667  | 0.268                  |
| 2025-26 | single_season                     | non_draft_rookie_class | 16736 | 160           | 7.727 | 7.631        | 7.823         | 10.007 | -0.073                 |
| 2025-26 | single_season                     | draft_rookie_class     | 1676  | 158           | 6.700 | 6.434        | 7.007         | 8.704  | 0.548                  |

## Interpretation

A multi-season model is preferable only if it improves error consistently without unacceptable bias. Compare its gains against the previous-score means: a small improvement over a weak single-season model is not sufficient if the simple baseline remains competitive. Rookie estimates should be read alongside cohort size, date-cluster confidence intervals and bias; name-based draft-year cohorts are imperfect, and the low-history proxy is not equivalent to a rookie label. 2025/26 is not a pristine holdout.

## Artifacts

- Metrics: `reports/audit/dunkest_model_comparison_20261014_v2_metrics.csv`
- Cohorts: `reports/audit/dunkest_model_comparison_20261014_v2_cohorts.csv`
- Paired bootstrap: `reports/audit/dunkest_model_comparison_20261014_v2_paired_bootstrap.csv`
- Per-game predictions: `reports/audit/dunkest_model_comparison_20261014_v2_predictions.csv`
- Audit: `reports/audit/dunkest_model_comparison_20261014_v2.json`
