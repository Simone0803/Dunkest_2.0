# PDK recent-lag feature ablation — V1

Generated UTC: 2026-10-14T19:53:50.221072+00:00

## Method

Compare identical expanding-origin folds (2022/23, 2023/24, 2024/25) and identical player-game rows using the same numeric-only estimator but two feature sets: a reconstruction of the production multi-season adapter, and that set plus explicit lag-1…5 PDK, recent NBA minutes/stat lags, short-vs-long trends and history counts. No categorical team/opponent features are added, so this isolates numeric lag value. Target-game PDK and minutes are labels only. The 2025/26 holdout and prospective 2026/27 bundle were not loaded.

## Pooled metrics

model      feature_set  feature_count     n    mae   rmse  bias_pred_minus_actual  mae_actual_ge25  n_actual_ge25  mae_actual_ge30  n_actual_ge30  mae_history_lt5  n_history_lt5
 et12 adapter_features             24 57682 7.6042 9.9073                 -0.3700          12.4772          13104          14.4711           8794           5.2012           1222
 et12    expanded_lags             50 57682 7.5696 9.8458                 -0.1279          12.2249          13104          14.2108           8794           5.1388           1222
  hgb adapter_features             24 57682 7.5810 9.8833                 -0.4366          12.5434          13104          14.5552           8794           5.2469           1222
  hgb    expanded_lags             50 57682 7.5721 9.8304                  0.0275          12.0671          13104          13.9971           8794           5.1747           1222

## Fold metrics

fold_season_id fold_season model      feature_set  feature_count     n    mae   rmse  bias_pred_minus_actual  mae_actual_ge25  n_actual_ge25  mae_actual_ge30  n_actual_ge30  mae_history_lt5  n_history_lt5
             9     2022-23   hgb adapter_features             24 19165 7.5854 9.8966                 -0.5420          12.7876           4310          14.7811           2903           5.5710            384
             9     2022-23   hgb    expanded_lags             50 19165 7.5792 9.8284                  0.0238          12.1985           4310          14.0672           2903           5.4250            384
             9     2022-23  et12 adapter_features             24 19165 7.5980 9.9140                 -0.4617          12.6633           4310          14.6315           2903           5.5012            384
             9     2022-23  et12    expanded_lags             50 19165 7.5637 9.8401                 -0.2010          12.3927           4310          14.3305           2903           5.3693            384
            13     2023-24   hgb adapter_features             24 18927 7.5625 9.8467                 -0.3884          12.4780           4369          14.3850           2972           5.4513            434
            13     2023-24   hgb    expanded_lags             50 18927 7.5726 9.8055                  0.1331          12.0300           4369          13.8803           2972           5.3670            434
            13     2023-24  et12 adapter_features             24 18927 7.5934 9.8758                 -0.3319          12.4479           4369          14.3303           2972           5.3997            434
            13     2023-24  et12    expanded_lags             50 18927 7.5687 9.8191                 -0.0539          12.2020           4369          14.0943           2972           5.3524            434
            19     2024-25   hgb adapter_features             24 19590 7.5947 9.9056                 -0.3802          12.3701           4425          14.5039           2919           4.7194            404
            19     2024-25   hgb    expanded_lags             50 19590 7.5646 9.8563                 -0.0708          11.9756           4425          14.0461           2919           4.7301            404
            19     2024-25  et12 adapter_features             24 19590 7.6208 9.9311                 -0.3172          12.3250           4425          14.4549           2919           4.7029            404
            19     2024-25  et12    expanded_lags             50 19590 7.5763 9.8772                 -0.1279          12.0840           4425          14.2103           2919           4.6901            404

## Decision

Promote expanded lags only if the improvement is consistent across seasons and does not worsen high-score or low-history cohorts. This experiment does not change production features or weights.

No commit or push.
