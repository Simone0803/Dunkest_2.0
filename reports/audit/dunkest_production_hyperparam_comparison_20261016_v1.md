# Production PDK hyperparameter comparison — 2026-10-16

## Method

Compared the exact production ensemble walk-forward baseline with two targeted alternatives. Production baseline numbers are from the previously persisted exact-trainer evaluation; alternative settings were trained with the same production feature adapter and past-only fold scheme. Fold seasons are 2022/23, 2023/24 and 2024/25. 2025/26 is excluded from tuning/evaluation; prospective 2026/27 outcomes are not used.

## Pooled results

         candidate           n  weighted_mae  weighted_rmse  weighted_bias  mae_actual_ge25  mae_actual_ge30
production_default 57682.00000       7.55239        9.82091       -0.14472         12.21193         14.19673
   gbr_regularized 57682.00000       7.55902        9.82051       -0.07676         12.13430         14.10189
      rf_shallower 57682.00000       7.55927        9.83288       -0.18195         12.26283         14.25689

## Per-fold results

         candidate fold_season     mae    rmse     bias    mae25  n25    mae30  n30     n
production_default     2022-23 7.56017 9.81598 -0.13208 12.32028 4310 14.23187 2903 19165
production_default     2023-24 7.53431 9.79575 -0.22639 12.32883 4369 14.26164 2972 18927
production_default     2024-25 7.56224 9.84995 -0.07818 11.99096 4425 14.09568 2919 19590
      rf_shallower     2022-23 7.55969 9.82490 -0.19610 12.38470 4310 14.30770 2903 19165
      rf_shallower     2023-24 7.54167 9.80860 -0.26030 12.36870 4369 14.30310 2972 18927
      rf_shallower     2024-25 7.57585 9.86406 -0.09240 12.03960 4425 14.15930 2919 19590
   gbr_regularized     2022-23 7.55826 9.81427 -0.12310 12.28500 4310 14.19390 2903 19165
   gbr_regularized     2023-24 7.54804 9.78768 -0.02410 12.11030 4369 13.99100 2972 18927
   gbr_regularized     2024-25 7.57036 9.85821 -0.08230 12.01120 4425 14.12330 2919 19590

## Decision

**Keep the current production ensemble.** The shallower Random Forest has slightly lower MAE in the first fold but worse pooled MAE, RMSE, bias and high-score errors. The regularized Gradient Boosting variant has marginally better pooled RMSE/bias and high-score errors, but worse pooled MAE; its gains are too small and mixed to justify replacing the established configuration. The separate Extra Trees model search previously also failed to beat this production ensemble on pooled validation MAE.

No production model code or prediction weights were changed. The conservative current-season rate prior strength remains 12, which was the best pooled MAE/RMSE among the previously tested strengths.
