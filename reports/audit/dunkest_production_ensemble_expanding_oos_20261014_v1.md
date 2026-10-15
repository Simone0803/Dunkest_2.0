# Production core ensemble: expanding-origin OOS and interval calibration audit

Generated UTC: 2026-10-14T11:20:27.162605+00:00

## Protocol

- Certified official Dunkest PDK labels only; no proxy label fallback.
- Exact production feature adapter, model zoo, inverse-MAE model weights, fold-local imputation, sample weighting, and projection-weight fitting.
- Each test season is predicted by a model trained only on earlier seasons; date cutoffs are asserted.
- For each test season, empirical residual quantiles use only earlier out-of-sample season predictions.
- Residual = prediction minus actual; score interval lower = prediction − q90(residual), upper = prediction − q10(residual).
- This is an audit only. No production code/configuration/model artifact was changed.

## Point-score metrics

| test_season | method                   | n     | train_rows | train_seasons                           | mae    | rmse    | bias_pred_minus_actual | median_error |
| ----------- | ------------------------ | ----- | ---------- | --------------------------------------- | ------ | ------- | ---------------------- | ------------ |
| 2021-22     | production_core_ensemble | 18422 | 17662      | 2020-21                                 | 7.8803 | 10.1983 | -0.2998                | 0.6791       |
| 2021-22     | baseline_prev10          | 18307 | 17662      | 2020-21                                 | 8.0942 | 10.4792 | -0.1771                | 0.675        |
| 2021-22     | baseline_season_mean     | 18307 | 17662      | 2020-21                                 | 8.0942 | 10.4792 | -0.1771                | 0.675        |
| 2022-23     | production_core_ensemble | 19165 | 36084      | 2020-21;2021-22                         | 7.5634 | 9.8726  | -0.5473                | 0.8627       |
| 2022-23     | baseline_prev10          | 19086 | 36084      | 2020-21;2021-22                         | 7.7635 | 10.1137 | -0.0944                | 1.022        |
| 2022-23     | baseline_season_mean     | 19086 | 36084      | 2020-21;2021-22                         | 7.7635 | 10.1137 | -0.0944                | 1.022        |
| 2023-24     | production_core_ensemble | 18927 | 55249      | 2020-21;2021-22;2022-23                 | 7.5574 | 9.8399  | -0.3766                | 1.0469       |
| 2023-24     | baseline_prev10          | 18839 | 55249      | 2020-21;2021-22;2022-23                 | 7.7546 | 10.0965 | 0.0078                 | 1.101        |
| 2023-24     | baseline_season_mean     | 18839 | 55249      | 2020-21;2021-22;2022-23                 | 7.7546 | 10.0965 | 0.0078                 | 1.101        |
| 2024-25     | production_core_ensemble | 19590 | 74176      | 2020-21;2021-22;2022-23;2023-24         | 7.6067 | 9.9199  | -0.344                 | 0.9602       |
| 2024-25     | baseline_prev10          | 19508 | 74176      | 2020-21;2021-22;2022-23;2023-24         | 7.7832 | 10.1775 | -0.108                 | 0.8585       |
| 2024-25     | baseline_season_mean     | 19508 | 74176      | 2020-21;2021-22;2022-23;2023-24         | 7.7832 | 10.1775 | -0.108                 | 0.8585       |
| 2025-26     | production_core_ensemble | 18412 | 93766      | 2020-21;2021-22;2022-23;2023-24;2024-25 | 7.587  | 9.8742  | -0.3154                | 0.9081       |
| 2025-26     | baseline_prev10          | 18322 | 93766      | 2020-21;2021-22;2022-23;2023-24;2024-25 | 7.7817 | 10.1544 | -0.0833                | 0.8495       |
| 2025-26     | baseline_season_mean     | 18322 | 93766      | 2020-21;2021-22;2022-23;2023-24;2024-25 | 7.7817 | 10.1544 | -0.0833                | 0.8495       |

## Expanding-origin interval calibration

| test_season | method                            | calibration_seasons             | cohort          | n     | lower_tail_coverage | upper_tail_coverage | central_80_coverage | mean_interval_width | raw_mae | median_corrected_mae | median_corrected_bias |
| ----------- | --------------------------------- | ------------------------------- | --------------- | ----- | ------------------- | ------------------- | ------------------- | ------------------- | ------- | -------------------- | --------------------- |
| 2022-23     | pooled_prior_oos_residuals        | 2021-22                         | all             | 19165 | 0.9241              | 0.8989              | 0.823               | 25.5058             | 7.5634  | 7.5338               | -1.2264               |
| 2022-23     | cohort_shrunk_prior_oos_residuals | 2021-22                         | low_history_0_5 | 456   | 0.9452              | 0.875               | 0.8202              | 17.4044             | 5.7943  | 5.5582               | -1.0699               |
| 2022-23     | pooled_prior_oos_residuals        | 2021-22                         | low_history_0_5 | 456   | 0.9693              | 0.9539              | 0.9232              | 25.5058             | 5.7943  | 5.6613               | -0.0593               |
| 2022-23     | pooled_prior_oos_residuals        | 2021-22                         | history_6_10    | 341   | 0.9736              | 0.9443              | 0.9179              | 25.5058             | 5.7528  | 5.6288               | -0.5357               |
| 2022-23     | cohort_shrunk_prior_oos_residuals | 2021-22                         | history_over_10 | 18368 | 0.9252              | 0.8999              | 0.8251              | 25.8867             | 7.6409  | 7.6165               | -1.1956               |
| 2022-23     | pooled_prior_oos_residuals        | 2021-22                         | history_over_10 | 18368 | 0.922               | 0.8967              | 0.8187              | 25.5058             | 7.6409  | 7.6156               | -1.2682               |
| 2023-24     | pooled_prior_oos_residuals        | 2021-22;2022-23                 | all             | 18927 | 0.91                | 0.9015              | 0.8115              | 24.9367             | 7.5574  | 7.5128               | -1.1343               |
| 2023-24     | cohort_shrunk_prior_oos_residuals | 2021-22;2022-23                 | low_history_0_5 | 518   | 0.9073              | 0.9073              | 0.8147              | 17.3965             | 5.7116  | 5.4629               | -0.9752               |
| 2023-24     | pooled_prior_oos_residuals        | 2021-22;2022-23                 | low_history_0_5 | 518   | 0.9575              | 0.9537              | 0.9112              | 24.9367             | 5.7116  | 5.5649               | 0.1232                |
| 2023-24     | cohort_shrunk_prior_oos_residuals | 2021-22;2022-23                 | history_6_10    | 394   | 0.9416              | 0.9086              | 0.8503              | 19.2842             | 5.3175  | 5.1451               | -1.4238               |
| 2023-24     | pooled_prior_oos_residuals        | 2021-22;2022-23                 | history_6_10    | 394   | 0.9695              | 0.9569              | 0.9264              | 24.9367             | 5.3175  | 5.2006               | -0.68                 |
| 2023-24     | cohort_shrunk_prior_oos_residuals | 2021-22;2022-23                 | history_over_10 | 18015 | 0.909               | 0.9016              | 0.8105              | 25.2151             | 7.6594  | 7.621                | -1.115                |
| 2023-24     | pooled_prior_oos_residuals        | 2021-22;2022-23                 | history_over_10 | 18015 | 0.9074              | 0.8988              | 0.8061              | 24.9367             | 7.6594  | 7.6194               | -1.1804               |
| 2024-25     | pooled_prior_oos_residuals        | 2021-22;2022-23;2023-24         | all             | 19590 | 0.9012              | 0.906               | 0.8072              | 24.7258             | 7.6067  | 7.5658               | -1.2146               |
| 2024-25     | cohort_shrunk_prior_oos_residuals | 2021-22;2022-23;2023-24         | low_history_0_5 | 480   | 0.9083              | 0.8958              | 0.8042              | 17.1749             | 5.4191  | 5.0186               | -0.863                |
| 2024-25     | pooled_prior_oos_residuals        | 2021-22;2022-23;2023-24         | low_history_0_5 | 480   | 0.9521              | 0.9708              | 0.9229              | 24.7258             | 5.4191  | 5.1806               | 0.1658                |
| 2024-25     | cohort_shrunk_prior_oos_residuals | 2021-22;2022-23;2023-24         | history_6_10    | 384   | 0.9193              | 0.9167              | 0.8359              | 18.4808             | 5.2272  | 5.0436               | -1.4807               |
| 2024-25     | pooled_prior_oos_residuals        | 2021-22;2022-23;2023-24         | history_6_10    | 384   | 0.9792              | 0.9479              | 0.9271              | 24.7258             | 5.2272  | 5.0841               | -0.7608               |
| 2024-25     | cohort_shrunk_prior_oos_residuals | 2021-22;2022-23;2023-24         | history_over_10 | 18726 | 0.9006              | 0.9061              | 0.8066              | 25.0373             | 7.7116  | 7.6781               | -1.193                |
| 2024-25     | pooled_prior_oos_residuals        | 2021-22;2022-23;2023-24         | history_over_10 | 18726 | 0.8983              | 0.9035              | 0.8018              | 24.7258             | 7.7116  | 7.6778               | -1.2593               |
| 2025-26     | pooled_prior_oos_residuals        | 2021-22;2022-23;2023-24;2024-25 | all             | 18412 | 0.9006              | 0.9064              | 0.807               | 24.5653             | 7.587   | 7.5501               | -1.2085               |
| 2025-26     | cohort_shrunk_prior_oos_residuals | 2021-22;2022-23;2023-24;2024-25 | low_history_0_5 | 524   | 0.9141              | 0.8969              | 0.8111              | 17.2166             | 5.4664  | 5.1147               | -1.2307               |
| 2025-26     | pooled_prior_oos_residuals        | 2021-22;2022-23;2023-24;2024-25 | low_history_0_5 | 524   | 0.9599              | 0.9618              | 0.9218              | 24.5653             | 5.4664  | 5.2473               | -0.0331               |
| 2025-26     | cohort_shrunk_prior_oos_residuals | 2021-22;2022-23;2023-24;2024-25 | history_6_10    | 387   | 0.8837              | 0.8915              | 0.7752              | 18.1624             | 6.0097  | 5.9682               | -1.7587               |
| 2025-26     | pooled_prior_oos_residuals        | 2021-22;2022-23;2023-24;2024-25 | history_6_10    | 387   | 0.9406              | 0.9251              | 0.8656              | 24.5653             | 6.0097  | 5.9431               | -1.0557               |
| 2025-26     | cohort_shrunk_prior_oos_residuals | 2021-22;2022-23;2023-24;2024-25 | history_over_10 | 17501 | 0.9001              | 0.9068              | 0.8069              | 24.9211             | 7.6854  | 7.6544               | -1.1815               |
| 2025-26     | pooled_prior_oos_residuals        | 2021-22;2022-23;2023-24;2024-25 | history_over_10 | 17501 | 0.8979              | 0.9043              | 0.8023              | 24.5653             | 7.6854  | 7.6545               | -1.2471               |

Nominal central 80% coverage is 80%; marginal lower/upper coverage is 90%. Cohort quantiles are shrunk toward pooled quantiles, and only used when the prior OOS cohort contains at least 500 rows.

## Critical boundary: core ensemble versus final player forecast

The audit validates the core production model-zoo ensemble and the projection layer that can be reconstructed from certified historical rows. It does **not** validate the complete final inference output consumed by the optimizer: current-market role/minutes allocation, the separately blended historical PDK model, rookie-prior adjustments, and play-probability weighting also affect the final score. Authentic historical pre-lock snapshots needed to reconstruct those transformations are not available consistently. Therefore these results can reject weak calibration candidates, but they are not sufficient to promote a new calibrator to production.

## Fold diagnostics

| Test season | Training seasons | Train rows | Test rows | Model weights | Projection weights |
|---|---|---:|---:|---|---|
| 2021-22 | 2020-21 | 17662 | 18422 | `{"gbr": 0.3329395584189963, "rf": 0.33364365554187203, "ridge": 0.33341678603913166}` | `{"ensemble": 0.8825896125817436, "minutes": 0.0, "prior": 0.11741038741825642}` |
| 2022-23 | 2020-21; 2021-22 | 36084 | 19165 | `{"gbr": 0.33417575921124615, "rf": 0.3320074651283845, "ridge": 0.3338167756603692}` | `{"ensemble": 1.0, "minutes": 6.762477515824468e-17, "prior": 0.0}` |
| 2023-24 | 2020-21; 2021-22; 2022-23 | 55249 | 18927 | `{"gbr": 0.33448582444781744, "rf": 0.3317857628956194, "ridge": 0.33372841265656306}` | `{"ensemble": 0.9827448024451939, "minutes": 0.0, "prior": 0.01725519755480613}` |
| 2024-25 | 2020-21; 2021-22; 2022-23; 2023-24 | 74176 | 19590 | `{"gbr": 0.33432167431588933, "rf": 0.3320869317000964, "ridge": 0.3335913939840143}` | `{"ensemble": 0.9736913327042035, "minutes": 1.2622864675557835e-16, "prior": 0.0263086672957964}` |
| 2025-26 | 2020-21; 2021-22; 2022-23; 2023-24; 2024-25 | 93766 | 18412 | `{"gbr": 0.33430222121430825, "rf": 0.3322594049458695, "ridge": 0.33343837383982233}` | `{"ensemble": 1.0, "minutes": 0.0, "prior": 0.0}` |

## Artifacts

- Metrics: `reports/audit/dunkest_production_ensemble_expanding_oos_20261014_v1_metrics.csv`
- Row-level predictions: `reports/audit/dunkest_production_ensemble_expanding_oos_20261014_v1_predictions.csv`
- Interval diagnostics: `reports/audit/dunkest_production_ensemble_expanding_oos_20261014_v1_intervals.csv`
- Audit JSON: `reports/audit/dunkest_production_ensemble_expanding_oos_20261014_v1.json`
