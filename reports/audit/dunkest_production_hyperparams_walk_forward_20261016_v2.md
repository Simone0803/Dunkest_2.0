# Production PDK hyperparameter walk-forward — V1

Generated UTC: 2026-10-16T07:54:04.379584+00:00

## Protocol

Exact production feature adapter and target; each fold trains only on earlier certified official Dunkest PDK rows. Validation seasons: 2022/23, 2023/24, 2024/25. 2025/26 is excluded from training/evaluation folds; prospective 2026/27 outcomes are not used. The model zoo is varied only in Random Forest and Gradient Boosting settings; Ridge regularization and ensemble weights remain past-only learned by the production trainer. Forest jobs capped at 2 to avoid overloading the season-opener process.

## Pooled summary

      candidate           n  weighted_mae  weighted_rmse  weighted_bias  mae_actual_ge25  mae_actual_ge30   folds
gbr_regularized 57682.00000       7.55902        9.82051       -0.07675         12.13429         14.10189 3.00000

## Per-fold results

      candidate fold_season     n     mae    rmse  bias_pred_minus_actual  mae_actual_ge25  n_actual_ge25  mae_actual_ge30  n_actual_ge30  baseline_mae  baseline_rmse  rf_n  rf_depth  rf_leaf  gbr_n  gbr_lr  gbr_depth  gbr_leaf  gbr_subsample
gbr_regularized     2022-23 19165 7.55826 9.81427                -0.12308         12.28498           4310         14.19388           2903       7.76894       10.11342   200         6        1    180 0.04000          2         5        0.85000
gbr_regularized     2023-24 18927 7.54804 9.78768                -0.02413         12.11030           4369         13.99100           2972       7.76522       10.10028   200         6        1    180 0.04000          2         5        0.85000
gbr_regularized     2024-25 19590 7.57036 9.85821                -0.08225         12.01120           4425         14.12332           2919       7.79200       10.17953   200         6        1    180 0.04000          2         5        0.85000

## Interpretation

No candidate is promoted automatically. A candidate should be promoted only if it improves pooled MAE/RMSE without materially worsening bias, extreme-score error, or a specific season. This is player-game validation, not lineup-level proof.

Production code was not changed by this experiment.
