# Walk-forward ensemble-weight tuning

Created UTC: 2026-10-12T17:26:31.988823+00:00

## Protocol

- Weights selected only on expanding-window out-of-fold folds from 2022/23–2024/25.
- Objective: minimize pooled MAE over those validation folds.
- Convex weights searched on a 0.05 grid across Random Forest, Ridge, and previous-10 PDK mean.
- Weights are frozen before evaluating the 2025/26 final holdout.
- Offline comparison only; production configuration is unchanged.

## Selected weights

- random_forest: 0.60
- ridge: 0.35
- baseline_prev10_mean: 0.05
- Validation ensemble MAE: 7.5658 over 57,682 player-game rows.
- Weight combinations evaluated: 231.

## Metrics

| split                         | model                 | n     | mae    | rmse    | bias_pred_minus_actual |
| ----------------------------- | --------------------- | ----- | ------ | ------- | ---------------------- |
| validation_2022-23_to_2024-25 | random_forest         | 57682 | 7.588  | 9.8549  | -0.088                 |
| validation_2022-23_to_2024-25 | ridge                 | 57682 | 7.6279 | 9.8778  | 0.157                  |
| validation_2022-23_to_2024-25 | baseline_prev10_mean  | 57682 | 7.7756 | 10.1316 | -0.0307                |
| validation_2022-23_to_2024-25 | tuned_convex_ensemble | 57682 | 7.5658 | 9.8203  | 0.0006                 |
| final_holdout_2025-26         | random_forest         | 18412 | 7.5775 | 9.8563  | -0.1725                |
| final_holdout_2025-26         | ridge                 | 18412 | 7.5887 | 9.8604  | 0.0495                 |
| final_holdout_2025-26         | baseline_prev10_mean  | 18412 | 7.7886 | 10.1539 | -0.0479                |
| final_holdout_2025-26         | tuned_convex_ensemble | 18412 | 7.5568 | 9.8306  | -0.0885                |

## Caveats

- Saved fold predictions are expanding-window out-of-fold predictions; this tunes ensemble weights, not RF/Ridge hyperparameters.
- The 2025/26 final holdout is evaluated after selection and must not be reused for further tuning.
- Game-level PDK metrics do not directly validate lineup optimization, coaches, prices, injuries, or transfer penalties.
- Supervised labels start in 2020/21 because 2018/19–2019/20 archive rows have unverified/false Dunkest-valid flags; those seasons remain available as prior NBA feature history.

## Artifacts

- Metrics CSV: reports/audit/dunkest_ensemble_weights_walk_forward_20261012T172631Z.csv
- Audit JSON: reports/audit/dunkest_ensemble_weights_walk_forward_20261012T172631Z.json
