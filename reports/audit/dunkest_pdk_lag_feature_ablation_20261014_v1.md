# PDK recent-lag feature ablation — V1

Generated UTC: 2026-10-14T19:52:42.508571+00:00

## Method

Compare identical expanding-origin folds (2022/23, 2023/24, 2024/25) and identical player-game rows using the same estimator but two feature sets: a reconstruction of the production multi-season adapter, and that set plus explicit lag-1…5 PDK, recent NBA minutes/stat lags, short-vs-long trends, history counts and opponent categories. Target-game PDK and minutes are labels only. The 2025/26 holdout and prospective 2026/27 bundle were not loaded.

## Pooled metrics

model      feature_set  feature_count     n    mae   rmse  bias_pred_minus_actual  mae_actual_ge25  n_actual_ge25  mae_actual_ge30  n_actual_ge30  mae_history_lt5  n_history_lt5
 et12 adapter_features             34 57682 7.6038 9.9070                 -0.3728          12.4810          13104          14.4736           8794           5.2115           1222
 et12    expanded_lags             62 57682 7.5727 9.8474                 -0.1354          12.2324          13104          14.2132           8794           5.1574           1222
  hgb adapter_features             34 57682 7.5810 9.8833                 -0.4366          12.5434          13104          14.5552           8794           5.2469           1222
  hgb    expanded_lags             62 57682 7.5856 9.8478                  0.0490          12.0168          13104          13.9038           8794           5.2123           1222

## Fold metrics

fold_season_id fold_season model      feature_set  feature_count     n    mae   rmse  bias_pred_minus_actual  mae_actual_ge25  n_actual_ge25  mae_actual_ge30  n_actual_ge30  mae_history_lt5  n_history_lt5
             9     2022-23   hgb adapter_features             34 19165 7.5854 9.8966                 -0.5420          12.7876           4310          14.7811           2903           5.5710            384
             9     2022-23   hgb    expanded_lags             62 19165 7.5926 9.8404                  0.0987          12.0661           4310          13.8551           2903           5.4261            384
             9     2022-23  et12 adapter_features             34 19165 7.5967 9.9116                 -0.4622          12.6537           4310          14.6164           2903           5.5057            384
             9     2022-23  et12    expanded_lags             62 19165 7.5630 9.8351                 -0.2061          12.3888           4310          14.3220           2903           5.3936            384
            13     2023-24   hgb adapter_features             34 18927 7.5625 9.8467                 -0.3884          12.4780           4369          14.3850           2972           5.4513            434
            13     2023-24   hgb    expanded_lags             62 18927 7.5826 9.8186                  0.1154          12.0007           4369          13.8191           2972           5.4548            434
            13     2023-24  et12 adapter_features             34 18927 7.5913 9.8729                 -0.3301          12.4583           4369          14.3444           2972           5.4093            434
            13     2023-24  et12    expanded_lags             62 18927 7.5669 9.8158                 -0.0738          12.2115           4369          14.0968           2972           5.3626            434
            19     2024-25   hgb adapter_features             34 19590 7.5947 9.9056                 -0.3802          12.3701           4425          14.5039           2919           4.7194            404
            19     2024-25   hgb    expanded_lags             62 19590 7.5817 9.8832                 -0.0637          11.9846           4425          14.0386           2919           4.7487            404
            19     2024-25  et12 adapter_features             34 19590 7.6229 9.9354                 -0.3264          12.3354           4425          14.4631           2919           4.7194            404
            19     2024-25  et12    expanded_lags             62 19590 7.5877 9.8897                 -0.1258          12.1007           4425          14.2236           2919           4.7125            404

## Decision

Promote expanded lags only if the improvement is consistent across seasons and does not worsen high-score or low-history cohorts. This experiment does not change production features or weights.

No commit or push.
