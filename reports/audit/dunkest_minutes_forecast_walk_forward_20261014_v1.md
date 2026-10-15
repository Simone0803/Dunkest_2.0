# Player expected-minutes walk-forward — V1

Generated UTC: 2026-10-14T19:50:41.574454+00:00

## Objective

Measure whether a learned expected-minutes forecast improves on recent-minute baselines before considering any production integration. Target-game NBA minutes are labels only; predictors are past-only. Folds are expanding-origin seasons 2022/23, 2023/24 and 2024/25. The 2025/26 holdout and frozen 2026/27 prospective bundle are excluded.

## Data integrity

- Rows with linked target minutes: 93,753
- Target-minute label coverage after the join: 100.000%
- Conflicting duplicate target-minute keys: 0
- Candidate models: ExtraTrees leaf 12/20, HistGradientBoosting, Random Forest; baselines use previous 1/3/5 games.

## Pooled metrics

         candidate     n    mae   rmse  bias_pred_minus_actual  within_5_min  mae_actual_minutes_ge25  n_actual_minutes_ge25  mae_history_lt5  n_history_lt5  mae_zero_minutes  n_zero_minutes
         model_hgb 57682 4.9831 6.4512                  0.2878        0.5939                   4.5721                  28113           5.6790           1222           10.6455             178
        model_rf12 57682 4.9975 6.4710                  0.1997        0.5937                   4.6378                  28113           5.6561           1222           10.6094             178
        model_et12 57682 5.0120 6.5002                  0.1829        0.5926                   4.6479                  28113           5.7586           1222           10.7518             178
        model_et20 57682 5.0140 6.5047                  0.1754        0.5926                   4.6509                  28113           5.7669           1222           10.7918             178
baseline_blend_3_5 57500 5.0959 6.7556                  0.0438        0.5990                   4.7746                  28099           5.4553           1040            9.1840             177
    baseline_prev5 57500 5.1269 6.7808                  0.0314        0.6031                   4.7810                  28099           5.4906           1040            9.4419             177
    baseline_prev3 57500 5.1908 6.8843                  0.0504        0.6037                   4.8693                  28099           5.5162           1040            9.0452             177
baseline_last_game 57500 5.8819 7.8758                  0.0552        0.5794                   5.5651                  28099           6.0067           1040            8.3107             177

## Fold metrics

fold_season_id fold_season          candidate     n    mae   rmse  bias_pred_minus_actual  within_5_min  mae_actual_minutes_ge25  n_actual_minutes_ge25  mae_history_lt5  n_history_lt5  mae_zero_minutes  n_zero_minutes
             9     2022-23     baseline_prev5 19111 5.2527 6.9502                  0.0679        0.5920                   4.8292                   9463           5.4939            330           10.9510              48
             9     2022-23     baseline_prev3 19111 5.3062 7.0517                  0.0737        0.5964                   4.9360                   9463           5.4389            330           10.5556              48
             9     2022-23 baseline_blend_3_5 19111 5.2147 6.9241                  0.0717        0.5921                   4.8352                   9463           5.4132            330           10.6940              48
             9     2022-23 baseline_last_game 19111 5.9948 8.0253                  0.0975        0.5743                   5.6125                   9463           6.2909            330            9.7500              48
             9     2022-23         model_et12 19165 5.1126 6.6524                  0.1601        0.5848                   4.7017                   9470           5.9149            384           11.8182              48
             9     2022-23         model_et20 19165 5.1118 6.6543                  0.1495        0.5859                   4.7043                   9470           5.9080            384           11.8968              48
             9     2022-23          model_hgb 19165 5.0915 6.6028                  0.3038        0.5843                   4.6213                   9470           5.9370            384           11.7270              48
             9     2022-23         model_rf12 19165 5.1045 6.6236                  0.1811        0.5850                   4.6980                   9470           5.8671            384           11.5154              48
            13     2023-24     baseline_prev5 18866 5.0985 6.6989                 -0.0063        0.6035                   4.8107                   9163           6.1915            373            8.0014              70
            13     2023-24     baseline_prev3 18866 5.1614 6.8096                  0.0378        0.6047                   4.8739                   9163           6.2158            373            7.6238              70
            13     2023-24 baseline_blend_3_5 18866 5.0685 6.6789                  0.0224        0.5985                   4.7865                   9163           6.1574            373            7.7560              70
            13     2023-24 baseline_last_game 18866 5.8809 7.8659                  0.0338        0.5779                   5.6240                   9163           6.5630            373            7.0000              70
            13     2023-24         model_et12 18927 5.0268 6.4576                  0.2006        0.5870                   4.6920                   9168           6.0854            434            9.8455              71
            13     2023-24         model_et20 18927 5.0238 6.4588                  0.1966        0.5867                   4.6853                   9168           6.1092            434            9.8662              71
            13     2023-24          model_hgb 18927 5.0087 6.4208                  0.4004        0.5857                   4.5757                   9168           5.9395            434            9.9242              71
            13     2023-24         model_rf12 18927 5.0113 6.4243                  0.2229        0.5857                   4.6734                   9168           5.9867            434            9.8480              71
            19     2024-25     baseline_prev5 19523 5.0313 6.6911                  0.0321        0.6136                   4.7041                   9473           4.7117            337            9.9232              59
            19     2024-25     baseline_prev3 19523 5.1061 6.7895                  0.0399        0.6097                   4.7983                   9473           4.8175            337            9.5028              59
            19     2024-25 baseline_blend_3_5 19523 5.0060 6.6616                  0.0372        0.6064                   4.7026                   9473           4.7196            337            9.6499              59
            19     2024-25 baseline_last_game 19523 5.7725 7.7363                  0.0346        0.5858                   5.4608                   9473           5.1128            337            8.6949              59
            19     2024-25         model_et12 19590 4.8993 6.3895                  0.1880        0.6057                   4.5515                   9475           5.2591            404           10.9748              59
            19     2024-25         model_et20 19590 4.9090 6.3999                  0.1802        0.6050                   4.5643                   9475           5.2650            404           11.0067              59
            19     2024-25          model_hgb 19590 4.8522 6.3295                  0.1633        0.6112                   4.5195                   9475           5.1539            404           10.6337              59
            19     2024-25         model_rf12 19590 4.8796 6.3640                  0.1954        0.6099                   4.5433                   9475           5.1004            404           10.7887              59

## Decision

A learned minute forecast is eligible for a production shadow component only if it improves pooled and per-season MAE against the strongest recent-minute baseline, does not materially worsen zero-minute and low-history cohorts, and has stable bias. A lower minutes MAE alone does not certify higher PDK accuracy; downstream score predictions need a separate paired player-game test before changing their blend.

No production code/config/weights were changed by this experiment. No commit or push.
