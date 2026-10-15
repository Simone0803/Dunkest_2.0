# Dunkest historical lagged-credit walk-forward — V1

Generated (UTC): 2026-10-13T08:13:24.707176+00:00

## Method

Each target is the official-valid player PDK total in a historical Dunkest week/round. Features are built by shifting player CR, PDK, minutes, plusvalenza and box-score summaries from earlier observed rounds only. No current-round CR or statistics enter the predictor.

The test is expanding-origin by season: train on earlier valid seasons and predict a later season. Seasons 2018/19 and 2019/20 are excluded as supervised targets because their official validity flags are false in the local archive.

## Pooled out-of-fold metrics

                     feature_family     n  pooled_mae  pooled_rmse  pooled_bias
                baseline_last_round 56179    9.881301    13.067838    -0.098120
            baseline_previous5_mean 56179    7.969681    10.466105    -0.265892
              baseline_train_median 57682   10.467877    13.759229    -3.526099
               historical_form_only 57682    7.681378    10.002636    -0.244187
historical_form_plus_credit_no_team 57682    7.491778     9.790450    -0.765509
 historical_form_plus_lagged_credit 57682    7.501692     9.804042    -0.760177

## Metrics by held-out season

test_season_id test_season                      feature_family     n       mae      rmse  bias_pred_minus_actual
             9     2022-23                 baseline_last_round 18683  9.881082 13.032500               -0.126845
             9     2022-23             baseline_previous5_mean 18683  7.962407 10.468912               -0.307049
             9     2022-23               baseline_train_median 19165 10.375185 13.742520               -3.953062
             9     2022-23                historical_form_only 19165  7.658262  9.996786               -0.393677
             9     2022-23  historical_form_plus_lagged_credit 19165  7.468348  9.708895               -0.183184
             9     2022-23 historical_form_plus_credit_no_team 19165  7.464740  9.703663               -0.200558
            13     2023-24                 baseline_last_round 18415  9.841520 13.059897               -0.063789
            13     2023-24             baseline_previous5_mean 18415  7.949629 10.446324               -0.213361
            13     2023-24               baseline_train_median 18927 10.633117 13.949545               -3.461143
            13     2023-24                historical_form_only 18927  7.695723  9.981223               -0.115088
            13     2023-24  historical_form_plus_lagged_credit 18927  7.521733  9.849385               -1.155873
            13     2023-24 historical_form_plus_credit_no_team 18927  7.505159  9.825290               -1.139423
            19     2024-25                 baseline_last_round 19081  9.919909 13.109985               -0.103127
            19     2024-25             baseline_previous5_mean 19081  7.996156 10.482415               -0.276291
            19     2024-25               baseline_train_median 19590 10.398909 13.589370               -3.171156
            19     2024-25                historical_form_only 19590  7.690134 10.028987               -0.222672
            19     2024-25  historical_form_plus_lagged_credit 19590  7.514951  9.852645               -0.942349
            19     2024-25 historical_form_plus_credit_no_team 19590  7.505301  9.841126               -0.956943

## Coverage and interpretation

- Season ID 9: 19,165 test rows over 162 rounds; lagged CR present on 18,683 rows; exact prior archived-round row on 1,433 rows.
- Season ID 13: 18,927 test rows over 154 rounds; lagged CR present on 18,415 rows; exact prior archived-round row on 1,450 rows.
- Season ID 19: 19,590 test rows over 158 rounds; lagged CR present on 19,081 rows; exact prior archived-round row on 1,681 rows.

## Limitations

This is the first market-aware player-score backtest, not yet a complete optimal-lineup backtest. The weekly-round files contain outcome rows rather than a full timestamped pre-lock market universe. A valid lineup backtest must avoid using the target-round player list as if it were known before lock.

The local player archives also lack historical coach CR markets. NBA final team points and margins can reconstruct the coach score before the credit-difference multiplier; exact historical coach PDK needs the historical coach prices or a validated reconstruction.

Production model/configuration remains unchanged.

## Artifacts

- Metrics: `reports/audit/dunkest_lagged_credit_walk_forward_20261013_v1_metrics.csv`
- Predictions: `reports/audit/dunkest_lagged_credit_walk_forward_20261013_v1_predictions.csv`
- Audit JSON: `reports/audit/dunkest_lagged_credit_walk_forward_20261013_v1.json`
