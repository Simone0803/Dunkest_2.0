# Score-band prediction interval calibration — past-only OOS

Generated UTC: 2026-10-14T18:39:54.069661+00:00

## Protocol

- Residuals are prediction minus actual from the production-ensemble OOF predictions.
- For each test season, residual quantiles are fitted only on strictly earlier seasons.
- Quantiles are estimated by forecast score band and shrunk toward the pooled residual quantiles with alpha = n/(n+1000).
- Target score is never used to choose the band. 2025/26 and 2026/27 GW1 are excluded. No production code/configuration changed.

## Overall interval metrics

| Season | Method | N | Lower-tail coverage | Upper-tail coverage | Central 80% coverage | Mean width | Median-offset bias | Median-adjusted MAE |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 2023-24 | pooled_residual_quantiles | 18927 | 0.8982 | 0.9024 | 0.8006 | 24.458 | -1.225 | 7.5087 |
| 2023-24 | score_band_residual_quantiles | 18927 | 0.9033 | 0.9050 | 0.8083 | 24.303 | -1.068 | 7.4892 |
| 2024-25 | pooled_residual_quantiles | 19590 | 0.8946 | 0.9061 | 0.8007 | 24.413 | -1.306 | 7.5654 |
| 2024-25 | score_band_residual_quantiles | 19590 | 0.9027 | 0.9048 | 0.8075 | 24.261 | -1.126 | 7.5594 |

## Score-band coverage

| Season | Method | Forecast band | N | Lower tail | Upper tail | Central 80% | Mean width | Median bias |
|---|---|---|---:|---:|---:|---:|---:|---:|
| 2023-24 | score_band_residual_quantiles | <5 | 1519 | 0.9895 | 0.9559 | 0.9454 | 18.443 | -0.828 |
| 2023-24 | pooled_residual_quantiles | <5 | 1519 | 1.0000 | 0.9697 | 0.9697 | 24.458 | -0.656 |
| 2023-24 | score_band_residual_quantiles | 5-10 | 4531 | 0.9190 | 0.9159 | 0.8349 | 19.453 | -1.335 |
| 2023-24 | pooled_residual_quantiles | 5-10 | 4531 | 0.9806 | 0.9448 | 0.9254 | 24.458 | -0.821 |
| 2023-24 | score_band_residual_quantiles | 10-15 | 4323 | 0.8985 | 0.9022 | 0.8006 | 23.489 | -1.365 |
| 2023-24 | pooled_residual_quantiles | 10-15 | 4323 | 0.9003 | 0.9128 | 0.8131 | 24.458 | -1.112 |
| 2023-24 | score_band_residual_quantiles | 15-20 | 3193 | 0.8926 | 0.8948 | 0.7873 | 26.536 | -0.873 |
| 2023-24 | pooled_residual_quantiles | 15-20 | 3193 | 0.8537 | 0.8857 | 0.7394 | 24.458 | -1.261 |
| 2023-24 | score_band_residual_quantiles | 20-25 | 2250 | 0.8809 | 0.9004 | 0.7813 | 28.042 | -0.899 |
| 2023-24 | pooled_residual_quantiles | 20-25 | 2250 | 0.8449 | 0.8676 | 0.7124 | 24.458 | -1.740 |
| 2023-24 | score_band_residual_quantiles | 25+ | 3111 | 0.8724 | 0.8817 | 0.7541 | 30.361 | -0.707 |
| 2023-24 | pooled_residual_quantiles | 25+ | 3111 | 0.8097 | 0.8357 | 0.6455 | 24.458 | -1.839 |
| 2024-25 | score_band_residual_quantiles | <5 | 1595 | 0.9787 | 0.9223 | 0.9009 | 15.624 | -1.629 |
| 2024-25 | pooled_residual_quantiles | <5 | 1595 | 1.0000 | 0.9618 | 0.9618 | 24.413 | -1.215 |
| 2024-25 | score_band_residual_quantiles | 5-10 | 4256 | 0.9055 | 0.9044 | 0.8099 | 18.792 | -1.671 |
| 2024-25 | pooled_residual_quantiles | 5-10 | 4256 | 0.9772 | 0.9431 | 0.9203 | 24.413 | -1.080 |
| 2024-25 | score_band_residual_quantiles | 10-15 | 4888 | 0.9126 | 0.9016 | 0.8142 | 23.413 | -1.791 |
| 2024-25 | pooled_residual_quantiles | 10-15 | 4888 | 0.9141 | 0.9145 | 0.8286 | 24.413 | -1.672 |
| 2024-25 | score_band_residual_quantiles | 15-20 | 3475 | 0.8935 | 0.9134 | 0.8069 | 26.830 | -0.608 |
| 2024-25 | pooled_residual_quantiles | 15-20 | 3475 | 0.8538 | 0.9001 | 0.7540 | 24.413 | -0.997 |
| 2024-25 | score_band_residual_quantiles | 20-25 | 2254 | 0.8705 | 0.8971 | 0.7675 | 28.450 | -0.490 |
| 2024-25 | pooled_residual_quantiles | 20-25 | 2254 | 0.8234 | 0.8691 | 0.6925 | 24.413 | -1.444 |
| 2024-25 | score_band_residual_quantiles | 25+ | 3122 | 0.8780 | 0.8975 | 0.7755 | 31.575 | -0.117 |
| 2024-25 | pooled_residual_quantiles | 25+ | 3122 | 0.7944 | 0.8475 | 0.6419 | 24.413 | -1.329 |

## Other cohorts

| Season | Method | Cohort | N | Central 80% | Mean width | Median bias |
|---|---|---|---:|---:|---:|---:|
| 2023-24 | pooled_residual_quantiles | predicted_ge_20 | 5361 | 0.6736 | 24.458 | -1.797 |
| 2023-24 | pooled_residual_quantiles | low_history_le_5 | 518 | 0.8996 | 24.458 | +0.105 |
| 2023-24 | pooled_residual_quantiles | history_gt_5 | 18409 | 0.7978 | 24.458 | -1.262 |
| 2024-25 | pooled_residual_quantiles | predicted_ge_20 | 5376 | 0.6631 | 24.413 | -1.377 |
| 2024-25 | pooled_residual_quantiles | low_history_le_5 | 480 | 0.9083 | 24.413 | +0.158 |
| 2024-25 | pooled_residual_quantiles | history_gt_5 | 19110 | 0.7980 | 24.413 | -1.342 |

## Decision

This experiment is diagnostic only. A band-specific calibrator is not automatically better: its central coverage should approach 0.80, marginal lower/upper coverage 0.90, and widths should not expand excessively. These are historical folds, not a pristine final holdout.

- Metrics: `reports/audit/dunkest_score_band_interval_calibration_20261014_v1_metrics.csv`
- Cohorts: `reports/audit/dunkest_score_band_interval_calibration_20261014_v1_cohorts.csv`
- Audit JSON: `reports/audit/dunkest_score_band_interval_calibration_20261014_v1.json`
