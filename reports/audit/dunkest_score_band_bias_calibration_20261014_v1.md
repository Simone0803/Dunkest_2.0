# Past-only score-band residual calibration audit

Generated UTC: 2026-10-14T18:38:35.506892+00:00

## Protocol

- Uses production-ensemble out-of-fold predictions only.
- Calibrators for each test season use strictly earlier seasons.
- Correction is residual median by predicted-score band, shrunk toward global median by n/(n+1000).
- Paired date-cluster bootstrap, 2,000 resamples, compares calibrated and raw MAE.
- This is an offline experiment only; no production model, weights, configuration, or frozen GW1 artifact changed.

## Fold decisions

| Test season | Calibration seasons | N | Raw MAE | Calibrated MAE | Delta MAE | 95% paired CI | Decision |
|---|---|---:|---:|---:|---:|---|---|
| 2023-24 | 2022-23 | 18927 | 7.5573 | 7.4891 | -0.0683 | [-0.0818, -0.0544] | candidate |
| 2024-25 | 2022-23;2023-24 | 19590 | 7.6088 | 7.5592 | -0.0496 | [-0.0667, -0.0310] | candidate |

## Cohort metrics

| Test season | Method | Cohort | N | MAE | RMSE | Bias |
|---|---|---|---:|---:|---:|---:|
| 2023-24 | raw | all | 18927 | 7.5573 | 9.8382 | -0.3593 |
| 2023-24 | raw | actual_ge_25 | 4369 | 12.4294 | 14.8560 | -11.4729 |
| 2023-24 | raw | actual_ge_30 | 2972 | 14.3556 | 16.6157 | -13.8627 |
| 2023-24 | raw | predicted_ge_20 | 5361 | 9.8234 | 12.3045 | -0.9313 |
| 2023-24 | raw | low_history_le_5 | 518 | 5.7430 | 7.5935 | 0.9712 |
| 2023-24 | raw | history_gt_5 | 18409 | 7.6084 | 9.8940 | -0.3967 |
| 2023-24 | pooled_median_offset | all | 18927 | 7.5086 | 9.9076 | -1.2248 |
| 2023-24 | pooled_median_offset | actual_ge_25 | 4369 | 13.1096 | 15.5343 | -12.3387 |
| 2023-24 | pooled_median_offset | actual_ge_30 | 2972 | 15.1248 | 17.3446 | -14.7284 |
| 2023-24 | pooled_median_offset | predicted_ge_20 | 5361 | 9.8519 | 12.4001 | -1.7970 |
| 2023-24 | pooled_median_offset | low_history_le_5 | 518 | 5.5744 | 7.5300 | 0.1115 |
| 2023-24 | pooled_median_offset | history_gt_5 | 18409 | 7.5630 | 9.9663 | -1.2624 |
| 2023-24 | score_band_shrinkage | all | 18927 | 7.4891 | 9.8850 | -1.0680 |
| 2023-24 | score_band_shrinkage | actual_ge_25 | 4369 | 12.6262 | 15.1172 | -11.6063 |
| 2023-24 | score_band_shrinkage | actual_ge_30 | 2972 | 14.4349 | 16.7813 | -13.9077 |
| 2023-24 | score_band_shrinkage | predicted_ge_20 | 5361 | 9.8228 | 12.2947 | -0.7875 |
| 2023-24 | score_band_shrinkage | low_history_le_5 | 518 | 5.5253 | 7.5159 | -0.1640 |
| 2023-24 | score_band_shrinkage | history_gt_5 | 18409 | 7.5443 | 9.9435 | -1.0934 |
| 2024-25 | raw | all | 19590 | 7.6088 | 9.9184 | -0.3275 |
| 2024-25 | raw | actual_ge_25 | 4425 | 12.3269 | 14.9203 | -11.4045 |
| 2024-25 | raw | actual_ge_30 | 2919 | 14.4856 | 16.9488 | -13.9881 |
| 2024-25 | raw | predicted_ge_20 | 5376 | 9.8686 | 12.3569 | -0.3992 |
| 2024-25 | raw | low_history_le_5 | 480 | 5.4686 | 7.2078 | 1.1357 |
| 2024-25 | raw | history_gt_5 | 19110 | 7.6626 | 9.9770 | -0.3643 |
| 2024-25 | pooled_median_offset | all | 19590 | 7.5652 | 9.9985 | -1.3054 |
| 2024-25 | pooled_median_offset | actual_ge_25 | 4425 | 13.0990 | 15.6805 | -12.3825 |
| 2024-25 | pooled_median_offset | actual_ge_30 | 2919 | 15.3515 | 17.7645 | -14.9661 |
| 2024-25 | pooled_median_offset | predicted_ge_20 | 5376 | 9.8791 | 12.4270 | -1.3772 |
| 2024-25 | pooled_median_offset | low_history_le_5 | 480 | 5.1940 | 7.1128 | 0.1612 |
| 2024-25 | pooled_median_offset | history_gt_5 | 19110 | 7.6248 | 10.0603 | -1.3422 |
| 2024-25 | score_band_shrinkage | all | 19590 | 7.5592 | 9.9959 | -1.1254 |
| 2024-25 | score_band_shrinkage | actual_ge_25 | 4425 | 12.5752 | 15.2411 | -11.5964 |
| 2024-25 | score_band_shrinkage | actual_ge_30 | 2919 | 14.6174 | 17.1824 | -14.0883 |
| 2024-25 | score_band_shrinkage | predicted_ge_20 | 5376 | 9.8729 | 12.3547 | -0.2735 |
| 2024-25 | score_band_shrinkage | low_history_le_5 | 480 | 5.1179 | 7.1246 | -0.2266 |
| 2024-25 | score_band_shrinkage | history_gt_5 | 19110 | 7.6205 | 10.0575 | -1.1480 |

## Predicted-score bands

| Test season | Band | Method | N | Mean prediction | Mean actual | Bias |
|---|---|---|---:|---:|---:|---:|
| 2023-24 | <5 | raw | 1519 | 3.789 | 3.579 | +0.210 |
| 2023-24 | <5 | score_band_shrinkage | 1519 | 2.753 | 3.579 | -0.825 |
| 2023-24 | 5-10 | raw | 4531 | 7.664 | 7.620 | +0.044 |
| 2023-24 | 5-10 | score_band_shrinkage | 4531 | 6.284 | 7.620 | -1.335 |
| 2023-24 | 10-15 | raw | 4323 | 12.311 | 12.557 | -0.247 |
| 2023-24 | 10-15 | score_band_shrinkage | 4323 | 11.193 | 12.557 | -1.365 |
| 2023-24 | 15-20 | raw | 3193 | 17.437 | 17.832 | -0.395 |
| 2023-24 | 15-20 | score_band_shrinkage | 3193 | 16.959 | 17.832 | -0.873 |
| 2023-24 | 20-25 | raw | 2250 | 22.247 | 23.121 | -0.874 |
| 2023-24 | 20-25 | score_band_shrinkage | 2250 | 22.222 | 23.121 | -0.899 |
| 2023-24 | 25+ | raw | 3111 | 30.815 | 31.788 | -0.973 |
| 2023-24 | 25+ | score_band_shrinkage | 3111 | 31.081 | 31.788 | -0.707 |
| 2024-25 | <5 | raw | 1595 | 3.659 | 3.895 | -0.237 |
| 2024-25 | <5 | score_band_shrinkage | 1595 | 2.269 | 3.895 | -1.626 |
| 2024-25 | 5-10 | raw | 4256 | 7.704 | 7.806 | -0.102 |
| 2024-25 | 5-10 | score_band_shrinkage | 4256 | 6.135 | 7.806 | -1.671 |
| 2024-25 | 10-15 | raw | 4888 | 12.352 | 13.046 | -0.694 |
| 2024-25 | 10-15 | score_band_shrinkage | 4888 | 11.255 | 13.046 | -1.791 |
| 2024-25 | 15-20 | raw | 3475 | 17.362 | 17.381 | -0.019 |
| 2024-25 | 15-20 | score_band_shrinkage | 3475 | 16.772 | 17.381 | -0.608 |
| 2024-25 | 20-25 | raw | 2254 | 22.284 | 22.750 | -0.466 |
| 2024-25 | 20-25 | score_band_shrinkage | 2254 | 22.260 | 22.750 | -0.490 |
| 2024-25 | 25+ | raw | 3122 | 30.724 | 31.074 | -0.351 |
| 2024-25 | 25+ | score_band_shrinkage | 3122 | 30.957 | 31.074 | -0.117 |

## Interpretation

A calibration method is not promoted based on pooled MAE alone. It must improve paired date-cluster MAE in both folds and avoid material regressions in the high-score cohort. Conditional-on-actual high-score metrics are diagnostic only because actual score is unknown at inference. The predicted-score-band analysis is the actionable counterpart.

## Artifacts

- Metrics: `reports/audit/dunkest_score_band_bias_calibration_20261014_v1_metrics.csv`
- Calibrated predictions: `reports/audit/dunkest_score_band_bias_calibration_20261014_v1_predictions.csv`
- Predicted-band diagnostics: `reports/audit/dunkest_score_band_bias_calibration_20261014_v1_cohorts.csv`
- Audit JSON: `reports/audit/dunkest_score_band_bias_calibration_20261014_v1.json`
