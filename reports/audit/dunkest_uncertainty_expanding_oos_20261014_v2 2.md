# Dunkest uncertainty calibration — expanding-origin OOS audit

Generated UTC: 2026-10-14T11:01:15.756116+00:00

## Protocol

- Saved expanding-window RF predictions; residual calibration uses only strictly earlier seasons.
- Test seasons: 2023/24, 2024/25, 2025/26.
- Compares pooled residual quantiles with per-history-cohort quantiles on the same cohort rows.
- Quantiles are prediction residuals (prediction minus actual); interval endpoints are prediction plus q10/q90.
- No production configuration or forecasts are changed.

## Overall test-fold metrics

| test_season | calibration_seasons     | n     | q10_residual | q50_residual | q90_residual | lower_tail_coverage | upper_tail_coverage | central_80_coverage | mean_interval_width | median_bias_after_offset | raw_mae | median_adjusted_mae |
| ----------- | ----------------------- | ----- | ------------ | ------------ | ------------ | ------------------- | ------------------- | ------------------- | ------------------- | ------------------------ | ------- | ------------------- |
| 2023-24     | 2022-23                 | 18927 | -13.5221     | 1.191        | 10.7959      | 0.8953              | 0.9027              | 0.798               | 24.318              | -1.1695                  | 7.5971  | 7.5062              |
| 2024-25     | 2022-23;2023-24         | 19590 | -13.4368     | 1.3227       | 10.8878      | 0.899               | 0.9052              | 0.8042              | 24.3245             | -1.4364                  | 7.5886  | 7.5261              |
| 2025-26     | 2022-23;2023-24;2024-25 | 18412 | -13.3033     | 1.2866       | 10.9011      | 0.8995              | 0.9027              | 0.8022              | 24.2044             | -1.4591                  | 7.5775  | 7.5309              |

## Cohort interval diagnostics

| test_season | method                    | cohort          | n     | q10_residual | q50_residual | q90_residual | lower_tail_coverage | upper_tail_coverage | central_80_coverage | mean_interval_width | median_bias_after_offset | raw_mae | median_adjusted_mae |
| ----------- | ------------------------- | --------------- | ----- | ------------ | ------------ | ------------ | ------------------- | ------------------- | ------------------- | ------------------- | ------------------------ | ------- | ------------------- |
| 2023-24     | cohort_residual_quantiles | history_over_10 | 18015 | -13.6651     | 1.1572       | 10.9164      | 0.8949              | 0.9022              | 0.7971              | 24.5815             | -1.1366                  | 7.7127  | 7.626               |
| 2023-24     | pooled_residual_quantiles | history_over_10 | 18015 | -13.5221     | 1.191        | 10.7959      | 0.8915              | 0.9002              | 0.7917              | 24.318              | -1.1704                  | 7.7127  | 7.6252              |
| 2024-25     | cohort_residual_quantiles | low_history_0_5 | 480   | -9.0615      | 1.6641       | 6.7653       | 0.9125              | 0.9083              | 0.8208              | 15.8268             | -1.4802                  | 4.8803  | 4.6651              |
| 2024-25     | pooled_residual_quantiles | low_history_0_5 | 480   | -13.4368     | 1.3227       | 10.8878      | 0.9812              | 0.9625              | 0.9438              | 24.3245             | -1.1388                  | 4.8803  | 4.6744              |
| 2024-25     | cohort_residual_quantiles | history_6_10    | 384   | -10.3345     | 1.5117       | 7.0379       | 0.8854              | 0.9141              | 0.7995              | 17.3723             | -1.442                   | 5.1609  | 4.9911              |
| 2024-25     | pooled_residual_quantiles | history_6_10    | 384   | -13.4368     | 1.3227       | 10.8878      | 0.974               | 0.9427              | 0.9167              | 24.3245             | -1.253                   | 5.1609  | 4.9937              |
| 2024-25     | cohort_residual_quantiles | history_over_10 | 18726 | -13.5746     | 1.2986       | 11.0214      | 0.8984              | 0.9047              | 0.8031              | 24.596              | -1.4236                  | 7.7078  | 7.6508              |
| 2024-25     | pooled_residual_quantiles | history_over_10 | 18726 | -13.4368     | 1.3227       | 10.8878      | 0.8953              | 0.903               | 0.7983              | 24.3245             | -1.4477                  | 7.7078  | 7.6511              |
| 2025-26     | cohort_residual_quantiles | low_history_0_5 | 524   | -8.9689      | 1.6454       | 6.653        | 0.8989              | 0.8989              | 0.7977              | 15.6219             | -1.5614                  | 5.1258  | 4.9623              |
| 2025-26     | pooled_residual_quantiles | low_history_0_5 | 524   | -13.3033     | 1.2866       | 10.9011      | 0.9676              | 0.9523              | 0.9198              | 24.2044             | -1.2026                  | 5.1258  | 4.9651              |
| 2025-26     | cohort_residual_quantiles | history_6_10    | 387   | -10.0589     | 1.496        | 7.1156       | 0.8708              | 0.8941              | 0.7649              | 17.1745             | -1.8024                  | 5.8783  | 5.8432              |
| 2025-26     | pooled_residual_quantiles | history_6_10    | 387   | -13.3033     | 1.2866       | 10.9011      | 0.9587              | 0.9173              | 0.876               | 24.2044             | -1.5929                  | 5.8783  | 5.8342              |
| 2025-26     | cohort_residual_quantiles | history_over_10 | 17501 | -13.4709     | 1.2596       | 11.0429      | 0.8996              | 0.9025              | 0.8021              | 24.5138             | -1.4367                  | 7.6885  | 7.6446              |
| 2025-26     | pooled_residual_quantiles | history_over_10 | 17501 | -13.3033     | 1.2866       | 10.9011      | 0.8962              | 0.9009              | 0.797               | 24.2044             | -1.4638                  | 7.6885  | 7.6453              |

## Interpretation

A nominal 80% central interval should have central_80_coverage near 0.80; lower- and upper-tail coverages near 0.90 are the marginal one-sided checks. Cohort quantiles should only be preferred if they improve out-of-sample coverage without making intervals needlessly wide. This audit uses RF OOF forecasts as a calibration proxy and does not certify the current production ensemble. The point-score median offset is diagnostic only and is not promoted without consistent OOS MAE improvement.

## Artifacts

- Metrics: `reports/audit/dunkest_uncertainty_expanding_oos_20261014_v2_metrics.csv`
- Cohorts: `reports/audit/dunkest_uncertainty_expanding_oos_20261014_v2_cohorts.csv`
- Audit: `reports/audit/dunkest_uncertainty_expanding_oos_20261014_v2.json`
