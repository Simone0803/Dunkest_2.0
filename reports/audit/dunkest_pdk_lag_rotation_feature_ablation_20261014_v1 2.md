# PDK recent-lag and rotation-feature ablation — V1

Generated UTC: 2026-10-14T20:24:03.510112+00:00

## Method

Compare identical expanding-origin folds (2022/23, 2023/24, 2024/25) and identical player-game rows using the same estimator: a reconstruction of the production multi-season adapter, expanded lags, and expanded lags plus explicit team-change/tenure and past-only minutes-volatility features. No categorical team/opponent features are added, so this isolates numeric lag value. Target-game PDK and minutes are labels only. The 2025/26 holdout and prospective 2026/27 bundle were not loaded.

## Pooled metrics

model      feature_set  feature_count     n    mae   rmse  bias_pred_minus_actual  mae_actual_ge25  n_actual_ge25  mae_actual_ge30  n_actual_ge30  mae_history_lt5  n_history_lt5
 et12 adapter_features             24 57682 7.6038 9.9071                 -0.3704          12.4774          13104          14.4717           8794           5.1991           1222
 et12    expanded_lags             50 57682 7.5696 9.8456                 -0.1274          12.2241          13104          14.2097           8794           5.1372           1222
 et12   rotation_aware             56 57682 7.5782 9.8446                 -0.0711          12.1920          13104          14.1809           8794           5.1418           1222
  hgb adapter_features             24 57682 7.5743 9.8830                 -0.4774          12.5727          13104          14.5749           8794           5.2247           1222
  hgb    expanded_lags             50 57682 7.5615 9.8241                 -0.0480          12.1245          13104          14.0625           8794           5.1876           1222
  hgb   rotation_aware             56 57682 7.5637 9.8279                 -0.0456          12.1320          13104          14.0632           8794           5.1910           1222

## Fold metrics

fold_season_id fold_season model      feature_set  feature_count     n    mae   rmse  bias_pred_minus_actual  mae_actual_ge25  n_actual_ge25  mae_actual_ge30  n_actual_ge30  mae_history_lt5  n_history_lt5
             9     2022-23   hgb adapter_features             24 19165 7.5680 9.8864                 -0.6066          12.8167           4310          14.7788           2903           5.5008            384
             9     2022-23   hgb    expanded_lags             50 19165 7.5622 9.8291                 -0.1156          12.3279           4310          14.2294           2903           5.3847            384
             9     2022-23   hgb   rotation_aware             56 19165 7.5819 9.8498                 -0.0861          12.3453           4310          14.2318           2903           5.4136            384
             9     2022-23  et12 adapter_features             24 19165 7.5980 9.9140                 -0.4617          12.6633           4310          14.6315           2903           5.5012            384
             9     2022-23  et12    expanded_lags             50 19165 7.5637 9.8401                 -0.2010          12.3927           4310          14.3305           2903           5.3693            384
             9     2022-23  et12   rotation_aware             56 19165 7.5800 9.8409                 -0.1042          12.3405           4310          14.2741           2903           5.3796            384
            13     2023-24   hgb adapter_features             24 18927 7.5668 9.8607                 -0.4144          12.5136           4369          14.4204           2972           5.4367            434
            13     2023-24   hgb    expanded_lags             50 18927 7.5717 9.7987                  0.1075          12.0313           4369          13.8789           2972           5.4343            434
            13     2023-24   hgb   rotation_aware             56 18927 7.5591 9.7860                  0.0891          12.0388           4369          13.8843           2972           5.4570            434
            13     2023-24  et12 adapter_features             24 18927 7.5930 9.8753                 -0.3326          12.4501           4369          14.3327           2972           5.3962            434
            13     2023-24  et12    expanded_lags             50 18927 7.5685 9.8180                 -0.0526          12.2000           4369          14.0926           2972           5.3499            434
            13     2023-24  et12   rotation_aware             56 18927 7.5729 9.8173                 -0.0181          12.1773           4369          14.0688           2972           5.3551            434
            19     2024-25   hgb adapter_features             24 19590 7.5877 9.9011                 -0.4117          12.3934           4425          14.5294           2919           4.7346            404
            19     2024-25   hgb    expanded_lags             50 19590 7.5509 9.8438                 -0.1322          12.0183           4425          14.0834           2919           4.7352            404
            19     2024-25   hgb   rotation_aware             56 19590 7.5504 9.8467                 -0.1360          12.0162           4425          14.0776           2919           4.6938            404
            19     2024-25  et12 adapter_features             24 19590 7.6199 9.9310                 -0.3175          12.3234           4425          14.4542           2919           4.7004            404
            19     2024-25  et12    expanded_lags             50 19590 7.5765 9.8776                 -0.1276          12.0836           4425          14.2089           2919           4.6881            404
            19     2024-25  et12   rotation_aware             56 19590 7.5815 9.8746                 -0.0899          12.0618           4425          14.2024           2919           4.6867            404

## Decision

Promote rotation-aware features only if they improve player-game MAE/RMSE and team-change/rookie/low-history cohorts consistently across outer folds. This experiment does not change production features or weights.

No commit or push.
