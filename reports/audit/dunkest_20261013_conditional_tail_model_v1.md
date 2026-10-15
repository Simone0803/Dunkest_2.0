# Conditional high-score tail model — V1

Generated UTC: 2026-10-13T14:01:20.973493+00:00

## Method

For each expanding-origin fold, fit a classifier for PDK >=25 or >=30 and two conditional regressors, then combine their means with the predicted tail probability. Current-game statistics are target labels only. Balanced class weights are used, so probability calibration is explicitly audited and is a promotion gate. Only verified training data through 2024/25 is loaded.

## Pooled model comparison

           candidate     n     mae     rmse  bias_pred_minus_actual  mae_actual_ge25  n_actual_ge25  mae_actual_ge30  n_actual_ge30
         direct_et12 57682 7.56576  9.83902                -0.19890         12.29172          13104         14.31164           8794
          direct_hgb 57682 7.57227  9.83061                 0.02212         12.02739          13104         13.90933           8794
mixture_threshold_25 57682 8.53200 10.68999                 3.83160          8.95929          13104         10.11741           8794
mixture_threshold_30 57682 9.04216 11.33652                 4.96242          8.55127          13104          9.02623           8794

## Fold metrics

fold_season_id fold_season            candidate     n     mae     rmse  bias_pred_minus_actual  mae_actual_ge25  n_actual_ge25  mae_actual_ge30  n_actual_ge30
             9     2022-23 mixture_threshold_25 19165 8.62905 10.76854                 4.07071          8.95380           4310          9.99315           2903
             9     2022-23 mixture_threshold_30 19165 9.11674 11.38121                 5.06108          8.64304           4310          9.08923           2903
            13     2023-24 mixture_threshold_25 18927 8.52115 10.65780                 3.84348          8.89641           4369          9.98975           2972
            13     2023-24 mixture_threshold_30 18927 9.08865 11.35716                 5.14075          8.38385           4369          8.75352           2972
            19     2024-25 mixture_threshold_25 19590 8.44753 10.64383                 3.58619          9.02672           4425         10.37095           2919
            19     2024-25 mixture_threshold_30 19590 8.92428 11.27257                 4.69360          8.62717           4425          9.24123           2919

## Tail-probability calibration

fold_season_id fold_season  threshold  prevalence  mean_predicted_probability   brier  roc_auc  observed_high_count
             9     2022-23   25.00000     0.22489                     0.42648 0.17427  0.84022                 4310
             9     2022-23   30.00000     0.15147                     0.38393 0.17056  0.85216                 2903
            13     2023-24   25.00000     0.23083                     0.41767 0.16753  0.84848                 4369
            13     2023-24   30.00000     0.15702                     0.38696 0.16770  0.85893                 2972
            19     2024-25   25.00000     0.22588                     0.40962 0.16695  0.84155                 4425
            19     2024-25   30.00000     0.14900                     0.36932 0.16286  0.85285                 2919

## Decision

Do not promote unless overall error, tail-segment error, and probability calibration jointly improve across seasons. The classifier uses balanced class weights; its raw probability is not automatically a calibrated event probability. No production source, model, configuration, weights, 2025/26 holdout, or frozen prospective snapshot is changed or loaded.

## Artifacts

- Metrics: `reports/audit/dunkest_20261013_conditional_tail_model_v1_metrics.csv`
- Predictions: `reports/audit/dunkest_20261013_conditional_tail_model_v1_predictions.csv`
- Audit: `reports/audit/dunkest_20261013_conditional_tail_model_v1.json`

No commit or push.
