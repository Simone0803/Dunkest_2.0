# Dunkest uncertainty calibration — expanding-origin OOS audit

Generated UTC: 2026-10-14T11:00:56.298975+00:00

## Protocol

- Saved expanding-window RF predictions; residual calibration uses only strictly earlier seasons.
- Test seasons: 2023/24, 2024/25, 2025/26.
- Compares pooled residual quantiles with per-history-cohort quantiles on the same cohort rows.
- Quantiles are prediction residuals (prediction minus actual); interval endpoints are prediction plus q10/q90.
- No production configuration or forecasts are changed.

## Overall test-fold metrics

| test_season | calibration_seasons     | n     | q10_residual | q50_residual | q90_residual | lower_tail_coverage | upper_tail_coverage | central_80_coverage | mean_interval_width | median_bias_after_offset | raw_mae | median_adjusted_mae |
| ----------- | ----------------------- | ----- | ------------ | ------------ | ------------ | ------------------- | ------------------- | ------------------- | ------------------- | ------------------------ | ------- | ------------------- |
| 2023-24     | 2022-23                 | 18927 | -13.5221     | 1.191        | 10.7959      | 0.9429              | 0.8625              | 0.8054              | 24.318              | 1.2126                   | 7.5971  | 7.8104              |
| 2024-25     | 2022-23;2023-24         | 19590 | -13.4368     | 1.3227       | 10.8878      | 0.941               | 0.8658              | 0.8068              | 24.3245             | 1.2091                   | 7.5886  | 7.8023              |
| 2025-26     | 2022-23;2023-24;2024-25 | 18412 | -13.3033     | 1.2866       | 10.9011      | 0.9412              | 0.865               | 0.8062              | 24.2044             | 1.1142                   | 7.5775  | 7.7615              |

## Cohort interval diagnostics

| test_season | method                    | cohort          | n     | q10_residual | q50_residual | q90_residual | lower_tail_coverage | upper_tail_coverage | central_80_coverage | mean_interval_width | median_bias_after_offset | raw_mae | median_adjusted_mae |
| ----------- | ------------------------- | --------------- | ----- | ------------ | ------------ | ------------ | ------------------- | ------------------- | ------------------- | ------------------- | ------------------------ | ------- | ------------------- |
| 2023-24     | cohort_residual_quantiles | history_over_10 | 18015 | -13.6651     | 1.1572       | 10.9164      | 0.9427              | 0.8618              | 0.8044              | 24.5815             | 1.1778                   | 7.7127  | 7.9131              |
| 2023-24     | pooled_residual_quantiles | history_over_10 | 18015 | -13.5221     | 1.191        | 10.7959      | 0.9409              | 0.8597              | 0.8006              | 24.318              | 1.2117                   | 7.7127  | 7.9206              |
| 2024-25     | cohort_residual_quantiles | low_history_0_5 | 480   | -9.0615      | 1.6641       | 6.7653       | 0.9521              | 0.8688              | 0.8208              | 15.8268             | 1.848                    | 4.8803  | 5.4542              |
| 2024-25     | pooled_residual_quantiles | low_history_0_5 | 480   | -13.4368     | 1.3227       | 10.8878      | 0.9958              | 0.9292              | 0.925               | 24.3245             | 1.5066                   | 4.8803  | 5.3119              |
| 2024-25     | cohort_residual_quantiles | history_6_10    | 384   | -10.3345     | 1.5117       | 7.0379       | 0.9661              | 0.8828              | 0.849               | 17.3723             | 1.5814                   | 5.1609  | 5.6503              |
| 2024-25     | pooled_residual_quantiles | history_6_10    | 384   | -13.4368     | 1.3227       | 10.8878      | 0.9922              | 0.9193              | 0.9115              | 24.3245             | 1.3924                   | 5.1609  | 5.5762              |
| 2024-25     | cohort_residual_quantiles | history_over_10 | 18726 | -13.5746     | 1.2986       | 11.0214      | 0.9399              | 0.8653              | 0.8052              | 24.596              | 1.1736                   | 7.7078  | 7.9068              |
| 2024-25     | pooled_residual_quantiles | history_over_10 | 18726 | -13.4368     | 1.3227       | 10.8878      | 0.9385              | 0.8631              | 0.8017              | 24.3245             | 1.1977                   | 7.7078  | 7.9118              |
| 2025-26     | cohort_residual_quantiles | low_history_0_5 | 524   | -8.9689      | 1.6454       | 6.653        | 0.9427              | 0.8702              | 0.813               | 15.6219             | 1.7295                   | 5.1258  | 5.6438              |
| 2025-26     | pooled_residual_quantiles | low_history_0_5 | 524   | -13.3033     | 1.2866       | 10.9011      | 0.9847              | 0.9294              | 0.9141              | 24.2044             | 1.3707                   | 5.1258  | 5.5086              |
| 2025-26     | cohort_residual_quantiles | history_6_10    | 387   | -10.0589     | 1.496        | 7.1156       | 0.9432              | 0.8527              | 0.7959              | 17.1745             | 1.1897                   | 5.8783  | 6.1579              |
| 2025-26     | pooled_residual_quantiles | history_6_10    | 387   | -13.3033     | 1.2866       | 10.9011      | 0.9793              | 0.8966              | 0.876               | 24.2044             | 0.9803                   | 5.8783  | 6.1017              |
| 2025-26     | cohort_residual_quantiles | history_over_10 | 17501 | -13.4709     | 1.2596       | 11.0429      | 0.9412              | 0.865               | 0.8062              | 24.5138             | 1.0824                   | 7.6885  | 7.8606              |
| 2025-26     | pooled_residual_quantiles | history_over_10 | 17501 | -13.3033     | 1.2866       | 10.9011      | 0.9391              | 0.8624              | 0.8014              | 24.2044             | 1.1094                   | 7.6885  | 7.8657              |

## Interpretation

A nominal 80% central interval should have central_80_coverage near 0.80; lower- and upper-tail coverages near 0.90 are the marginal one-sided checks. Cohort quantiles should only be preferred if they improve out-of-sample coverage without making intervals needlessly wide. This audit uses RF OOF forecasts as a calibration proxy and does not certify the current production ensemble. The point-score median offset is diagnostic only and is not promoted without consistent OOS MAE improvement.

## Artifacts

- Metrics: `reports/audit/dunkest_uncertainty_expanding_oos_20261014_v1_metrics.csv`
- Cohorts: `reports/audit/dunkest_uncertainty_expanding_oos_20261014_v1_cohorts.csv`
- Audit: `reports/audit/dunkest_uncertainty_expanding_oos_20261014_v1.json`
