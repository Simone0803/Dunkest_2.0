# Nested expected-minutes hybrid — V1

Generated UTC: 2026-10-14T20:23:00.084876+00:00

## Method

For each outer held-out season (2022/23, 2023/24, 2024/25), the HGB minutes model is fitted only on earlier data. Blend weights are selected on a later-in-time 20% validation slice within the outer training block, separately for fewer than five prior Dunkest games and at least five. When the previous-five-minute baseline is missing, the model forecast is used. The 2025/26 holdout and prospective 2026/27 bundle are excluded.

## Pooled minutes metrics by subgroup

     candidate                  cohort     n    mae   rmse  bias_pred_minus_actual
           hgb                     all 57682 4.9839 6.4530                  0.2943
           hgb         low_history_lt5  1222 5.6774 7.1936                  0.2343
           hgb             history_ge5 56460 4.9689 6.4360                  0.2956
           hgb         nba_history_lt5   829 5.7916 7.3459                  0.2057
           hgb recent_minutes_drop_ge8  3541 5.9511 7.4549                  0.4913
         prev5                     all 57500 5.1269 6.7808                  0.0314
         prev5         low_history_lt5  1040 5.4906 7.6855                 -1.2860
         prev5             history_ge5 56460 5.1202 6.7630                  0.0557
         prev5         nba_history_lt5   647 5.3395 7.7031                 -1.5484
         prev5 recent_minutes_drop_ge8  3541 6.7515 8.4035                  3.2252
  nested_gated                     all 57682 4.9758 6.4619                  0.2654
  nested_gated         low_history_lt5  1222 5.6327 7.1889                  0.1244
  nested_gated             history_ge5 56460 4.9616 6.4453                  0.2684
  nested_gated         nba_history_lt5   829 5.7371 7.3426                  0.0988
  nested_gated recent_minutes_drop_ge8  3541 6.0208 7.5182                  0.9563
fixed_blend_50                     all 57682 4.9786 6.5129                  0.1648
fixed_blend_50         low_history_lt5  1222 5.6139 7.3963                 -0.3375
fixed_blend_50             history_ge5 56460 4.9649 6.4925                  0.1756
fixed_blend_50         nba_history_lt5   829 5.7025 7.5480                 -0.3648
fixed_blend_50 recent_minutes_drop_ge8  3541 6.2283 7.7495                  1.8583
fixed_blend_75                     all 57682 4.9614 6.4551                  0.2296
fixed_blend_75         low_history_lt5  1222 5.6194 7.2591                 -0.0516
fixed_blend_75             history_ge5 56460 4.9472 6.4366                  0.2356
fixed_blend_75         nba_history_lt5   829 5.7199 7.4181                 -0.0796
fixed_blend_75 recent_minutes_drop_ge8  3541 6.0594 7.5534                  1.1748

## Outer-fold metrics

fold_season_id fold_season      candidate                  cohort     n    mae   rmse  bias_pred_minus_actual
             9     2022-23            hgb                     all 19165 5.0907 6.6038                  0.2930
             9     2022-23            hgb         low_history_lt5   384 5.9411 7.6054                  0.0522
             9     2022-23            hgb             history_ge5 18781 5.0733 6.5817                  0.2979
             9     2022-23            hgb         nba_history_lt5   247 5.9755 7.7244                  0.1005
             9     2022-23            hgb recent_minutes_drop_ge8  1191 6.1978 7.6694                  0.5978
             9     2022-23          prev5                     all 19111 5.2527 6.9502                  0.0679
             9     2022-23          prev5         low_history_lt5   330 5.4939 7.5059                 -1.0296
             9     2022-23          prev5             history_ge5 18781 5.2485 6.9400                  0.0872
             9     2022-23          prev5         nba_history_lt5   193 5.1140 7.2451                 -1.1408
             9     2022-23          prev5 recent_minutes_drop_ge8  1191 6.8959 8.4818                  3.2626
             9     2022-23   nested_gated                     all 19165 5.0738 6.6144                  0.2413
             9     2022-23   nested_gated         low_history_lt5   384 5.9411 7.6054                  0.0522
             9     2022-23   nested_gated             history_ge5 18781 5.0561 6.5926                  0.2452
             9     2022-23   nested_gated         nba_history_lt5   247 5.9755 7.7244                  0.1005
             9     2022-23   nested_gated recent_minutes_drop_ge8  1191 6.2820 7.7384                  1.2520
             9     2022-23 fixed_blend_50                     all 19165 5.0954 6.6790                  0.1816
             9     2022-23 fixed_blend_50         low_history_lt5   384 5.8577 7.6752                 -0.3543
             9     2022-23 fixed_blend_50             history_ge5 18781 5.0798 6.6571                  0.1925
             9     2022-23 fixed_blend_50         nba_history_lt5   247 5.8882 7.8054                 -0.2991
             9     2022-23 fixed_blend_50 recent_minutes_drop_ge8  1191 6.4239 7.9006                  1.9302
             9     2022-23 fixed_blend_75                     all 19165 5.0726 6.6145                  0.2373
             9     2022-23 fixed_blend_75         low_history_lt5   384 5.8793 7.6111                 -0.1510
             9     2022-23 fixed_blend_75             history_ge5 18781 5.0561 6.5926                  0.2452
             9     2022-23 fixed_blend_75         nba_history_lt5   247 5.9134 7.7461                 -0.0993
             9     2022-23 fixed_blend_75 recent_minutes_drop_ge8  1191 6.2812 7.7381                  1.2640
            13     2023-24            hgb                     all 18927 5.0120 6.4229                  0.4195
            13     2023-24            hgb         low_history_lt5   434 5.9600 7.4526                  0.2931
            13     2023-24            hgb             history_ge5 18493 4.9897 6.3968                  0.4224
            13     2023-24            hgb         nba_history_lt5   278 6.2179 7.6940                  0.5232
            13     2023-24            hgb recent_minutes_drop_ge8  1158 5.7046 7.1610                  0.4895
            13     2023-24          prev5                     all 18866 5.0985 6.6989                 -0.0063
            13     2023-24          prev5         low_history_lt5   373 6.1915 8.6156                 -1.4253
            13     2023-24          prev5             history_ge5 18493 5.0764 6.6546                  0.0223
            13     2023-24          prev5         nba_history_lt5   217 6.2830 8.8847                 -1.6555
            13     2023-24          prev5 recent_minutes_drop_ge8  1158 6.5348 8.1619                  3.1128
            13     2023-24   nested_gated                     all 18927 5.0120 6.4229                  0.4195
            13     2023-24   nested_gated         low_history_lt5   434 5.9600 7.4526                  0.2931
            13     2023-24   nested_gated             history_ge5 18493 4.9897 6.3968                  0.4224
            13     2023-24   nested_gated         nba_history_lt5   278 6.2179 7.6940                  0.5232
            13     2023-24   nested_gated recent_minutes_drop_ge8  1158 5.7046 7.1610                  0.4895
            13     2023-24 fixed_blend_50                     all 18927 4.9703 6.4434                  0.2095
            13     2023-24 fixed_blend_50         low_history_lt5   434 6.0545 7.9054                 -0.3386
            13     2023-24 fixed_blend_50             history_ge5 18493 4.9448 6.4051                  0.2224
            13     2023-24 fixed_blend_50         nba_history_lt5   278 6.2950 8.1585                 -0.1857
            13     2023-24 fixed_blend_50 recent_minutes_drop_ge8  1158 6.0066 7.4837                  1.8012
            13     2023-24 fixed_blend_75                     all 18927 4.9694 6.4019                  0.3145
            13     2023-24 fixed_blend_75         low_history_lt5   434 5.9772 7.6365                 -0.0227
            13     2023-24 fixed_blend_75             history_ge5 18493 4.9457 6.3701                  0.3224
            13     2023-24 fixed_blend_75         nba_history_lt5   278 6.2219 7.8878                  0.1688
            13     2023-24 fixed_blend_75 recent_minutes_drop_ge8  1158 5.8234 7.2737                  1.1453
            19     2024-25            hgb                     all 19590 4.8524 6.3316                  0.1748
            19     2024-25            hgb         low_history_lt5   404 5.1232 6.4716                  0.3441
            19     2024-25            hgb             history_ge5 19186 4.8467 6.3286                  0.1712
            19     2024-25            hgb         nba_history_lt5   304 5.2524 6.6738                  0.0009
            19     2024-25            hgb recent_minutes_drop_ge8  1192 5.9440 7.5170                  0.3866
            19     2024-25          prev5                     all 19523 5.0313 6.6911                  0.0321
            19     2024-25          prev5         low_history_lt5   337 4.7117 6.7049                 -1.3828
            19     2024-25          prev5             history_ge5 19186 5.0369 6.6909                  0.0570
            19     2024-25          prev5         nba_history_lt5   237 4.6593 6.8532                 -1.7823
            19     2024-25          prev5 recent_minutes_drop_ge8  1192 6.8179 8.5548                  3.2971
            19     2024-25   nested_gated                     all 19590 4.8450 6.3476                  0.1400
            19     2024-25   nested_gated         low_history_lt5   404 4.9878 6.4558                  0.0119
            19     2024-25   nested_gated             history_ge5 19186 4.8420 6.3452                  0.1427
            19     2024-25   nested_gated         nba_history_lt5   304 5.1037 6.6641                 -0.2906
            19     2024-25   nested_gated recent_minutes_drop_ge8  1192 6.0671 7.6328                  1.1142
            19     2024-25 fixed_blend_50                     all 19590 4.8725 6.4143                  0.1051
            19     2024-25 fixed_blend_50         low_history_lt5   404 4.9089 6.5072                 -0.3203
            19     2024-25 fixed_blend_50             history_ge5 19186 4.8717 6.4124                  0.1141
            19     2024-25 fixed_blend_50         nba_history_lt5   304 5.0098 6.7076                 -0.5821
            19     2024-25 fixed_blend_50 recent_minutes_drop_ge8  1192 6.2482 7.8501                  1.8418
            19     2024-25 fixed_blend_75                     all 19590 4.8450 6.3476                  0.1400
            19     2024-25 fixed_blend_75         low_history_lt5   404 4.9878 6.4558                  0.0119
            19     2024-25 fixed_blend_75             history_ge5 19186 4.8420 6.3452                  0.1427
            19     2024-25 fixed_blend_75         nba_history_lt5   304 5.1037 6.6641                 -0.2906
            19     2024-25 fixed_blend_75 recent_minutes_drop_ge8  1192 6.0671 7.6328                  1.1142

## Downstream PDK rescaling experiment

Diagnostic only: the direct expanded-lag HGB PDK prediction is rescaled toward a minutes-ratio correction (minutes candidate / previous-five-minute mean), with ratio clipped to [0.25, 1.75]. The weight is not tuned on outer holdout; table reports a sensitivity sweep. This is not production integration.

minute_candidate  scale_weight     n    mae   rmse  bias_pred_minus_actual  n_scaled_rows
             hgb        0.0000 57682 7.5721 9.8304                  0.0275          57499
             hgb        0.1000 57682 7.5816 9.8314                  0.0595          57499
             hgb        0.2000 57682 7.5934 9.8353                  0.0915          57499
             hgb        0.3000 57682 7.6075 9.8419                  0.1235          57499
             hgb        0.5000 57682 7.6421 9.8636                  0.1875          57499
             hgb        1.0000 57682 7.7646 9.9660                  0.3475          57499
           prev5        0.0000 57682 7.5721 9.8304                  0.0275          57499
           prev5        0.1000 57682 7.5721 9.8304                  0.0275          57499
           prev5        0.2000 57682 7.5721 9.8304                  0.0275          57499
           prev5        0.3000 57682 7.5721 9.8304                  0.0275          57499
           prev5        0.5000 57682 7.5721 9.8304                  0.0275          57499
           prev5        1.0000 57682 7.5721 9.8304                  0.0275          57499
    nested_gated        0.0000 57682 7.5721 9.8304                  0.0275          57499
    nested_gated        0.1000 57682 7.5807 9.8314                  0.0565          57499
    nested_gated        0.2000 57682 7.5912 9.8346                  0.0855          57499
    nested_gated        0.3000 57682 7.6035 9.8399                  0.1145          57499
    nested_gated        0.5000 57682 7.6329 9.8570                  0.1725          57499
    nested_gated        1.0000 57682 7.7339 9.9368                  0.3174          57499

## Decision

Only integrate a minutes model if the nested gate improves minutes error in each cohort without worsening low-history or rotation-change cohorts, and if a downstream PDK adjustment improves MAE/RMSE consistently across outer seasons. A minutes-only gain is insufficient. No production code, configuration or weights were changed.

No commit or push.
