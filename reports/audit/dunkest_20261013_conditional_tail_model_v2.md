# Conditional high-score tail model — V2

Generated UTC: 2026-10-13T14:03:18.083469+00:00

## Method

For each expanding-origin fold, fit a classifier for PDK >=25 or >=30 and two conditional regressors, then combine their means with the predicted tail probability. Current-game statistics are target labels only. The classifier is unweighted to preserve the natural event prevalence; probability calibration is explicitly audited and is a promotion gate. Only verified training data through 2024/25 is loaded.

## Pooled model comparison

           candidate     n     mae    rmse  bias_pred_minus_actual  mae_actual_ge25  n_actual_ge25  mae_actual_ge30  n_actual_ge30
mixture_threshold_25 57682 7.56329 9.83079                -0.05043         12.04410          13104         13.97933           8794
         direct_et12 57682 7.56576 9.83902                -0.19890         12.29172          13104         14.31164           8794
mixture_threshold_30 57682 7.56749 9.83375                -0.07085         12.11427          13104         14.05284           8794
          direct_hgb 57682 7.57227 9.83061                 0.02212         12.02739          13104         13.90933           8794

## Fold metrics

fold_season_id fold_season            candidate     n     mae    rmse  bias_pred_minus_actual  mae_actual_ge25  n_actual_ge25  mae_actual_ge30  n_actual_ge30
             9     2022-23 mixture_threshold_25 19165 7.55992 9.81894                -0.01999         12.07774           4310         13.85941           2903
             9     2022-23 mixture_threshold_30 19165 7.55788 9.82330                -0.19278         12.31782           4310         14.23791           2903
            13     2023-24 mixture_threshold_25 18927 7.56483 9.80784                -0.01936         12.10119           4369         14.01306           2972
            13     2023-24 mixture_threshold_30 18927 7.57573 9.81287                 0.02891         12.08565           4369         13.93877           2972
            19     2024-25 mixture_threshold_25 19590 7.56510 9.86446                -0.11022         11.95496           4425         14.06426           2919
            19     2024-25 mixture_threshold_30 19590 7.56893 9.86408                -0.04794         11.94428           4425         13.98493           2919

## Tail-probability calibration

fold_season_id fold_season  threshold  prevalence  mean_predicted_probability   brier  roc_auc  observed_high_count
             9     2022-23   25.00000     0.22489                     0.22933 0.12362  0.84032                 4310
             9     2022-23   30.00000     0.15147                     0.15083 0.09487  0.85320                 2903
            13     2023-24   25.00000     0.23083                     0.22972 0.12295  0.84863                 4369
            13     2023-24   30.00000     0.15702                     0.15804 0.09619  0.85885                 2972
            19     2024-25   25.00000     0.22588                     0.22887 0.12397  0.84202                 4425
            19     2024-25   30.00000     0.14900                     0.15414 0.09386  0.85263                 2919

## Decision

Do not promote unless overall error, tail-segment error, and probability calibration jointly improve across seasons. The unweighted classifier probability is not automatically calibrated; calibration metrics are a promotion gate. No production source, model, configuration, weights, 2025/26 holdout, or frozen prospective snapshot is changed or loaded.

## Artifacts

- Metrics: `reports/audit/dunkest_20261013_conditional_tail_model_v2_metrics.csv`
- Predictions: `reports/audit/dunkest_20261013_conditional_tail_model_v2_predictions.csv`
- Audit: `reports/audit/dunkest_20261013_conditional_tail_model_v2.json`

No commit or push.
