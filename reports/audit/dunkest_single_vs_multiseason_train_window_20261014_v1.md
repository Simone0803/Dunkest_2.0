# Single-season vs multi-season Dunkest PDK training — V1

Generated UTC: 2026-10-14T10:09:19.142011+00:00

## Design

Both training windows use the same audited past-only feature adapter and the same ExtraTrees configuration. The single-season model sees only the immediately preceding season; the multi-season model sees every certified prior season. No production model/configuration is changed.

## Results by test season

 training_window test_season_id test_season                        training_seasons  train_rows     n     mae     rmse  bias_pred_minus_actual
previous_10_mean              9     2022-23                                    none           0 19165 7.76894 10.11342                -0.06874
   single_season              9     2022-23                                 2021-22       18422 19165 7.55905  9.83273                -0.21895
    multi_season              9     2022-23                         2020-21;2021-22       36084 19165 7.54862  9.82521                -0.28398
previous_10_mean             13     2023-24                                    none           0 18927 7.76522 10.10028                 0.04785
   single_season             13     2023-24                                 2022-23       19165 18927 7.57810  9.80758                 0.06826
    multi_season             13     2023-24                 2020-21;2021-22;2022-23       55249 18927 7.55815  9.80971                -0.12730
previous_10_mean             19     2024-25                                    none           0 19590 7.79200 10.17953                -0.06938
   single_season             19     2024-25                                 2023-24       18927 19590 7.58168  9.88228                -0.02896
    multi_season             19     2024-25         2020-21;2021-22;2022-23;2023-24       74176 19590 7.57515  9.86926                -0.14576
previous_10_mean             25     2025-26                                    none           0 18412 7.78863 10.15390                -0.04792
   single_season             25     2025-26                                 2024-25       19590 18412 7.58551  9.85114                -0.03550
    multi_season             25     2025-26 2020-21;2021-22;2022-23;2023-24;2024-25       93766 18412 7.55780  9.83654                -0.18321

## Pooled comparison

training_window           n     mae    rmse  bias_pred_minus_actual
   multi_season 76094.00000 7.56004 9.83546                -0.18504
  single_season 76094.00000 7.57601 9.84372                -0.05421

- Paired pooled MAE difference (multi minus single): -0.01598.
- 95% date-cluster bootstrap interval: [-0.02254, -0.00924].
- 2025/26 single-season MAE: 7.58551; multi-season MAE: 7.55780; difference: -0.02771.

## Interpretation

A negative difference favours multi-season training. Promote a production change only if the gain is stable across season folds/cohorts and the production-equivalent inference path reproduces the same feature definitions. The 2025/26 fold trains on 2020/21–2024/25 and is the closest match to the requested historical holdout experiment, but it is not globally untouched because other project audits have inspected this season.

## Artifacts

- Metrics: `reports/audit/dunkest_single_vs_multiseason_train_window_20261014_v1_metrics.csv`
- Predictions: `reports/audit/dunkest_single_vs_multiseason_train_window_20261014_v1_predictions.csv`
- Audit: `reports/audit/dunkest_single_vs_multiseason_train_window_20261014_v1.json`
