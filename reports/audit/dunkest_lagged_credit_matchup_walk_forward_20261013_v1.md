# Dunkest historical lagged-credit walk-forward — V1

Generated (UTC): 2026-10-13T08:16:12.309314+00:00

## Method

Each target is the official-valid player PDK total in a historical Dunkest week/round. Features are built by shifting player CR, PDK, minutes, plusvalenza and box-score summaries from earlier observed rounds only. Matchup features use high-confidence reconstructed round dates and opponent defensive trends strictly before the target date. No current-round CR or statistics enter the predictor.

The test is expanding-origin by season: train on earlier valid seasons and predict a later season. Seasons 2018/19 and 2019/20 are excluded as supervised targets because their official validity flags are false in the local archive.

## Pooled out-of-fold metrics

                                feature_family     n  pooled_mae  pooled_rmse  pooled_bias
                           baseline_last_round 54142    9.918777    13.108231    -0.096537
                       baseline_previous5_mean 54142    8.002494    10.507355    -0.275650
                         baseline_train_median 55565   10.504389    13.769767    -3.395153
                          historical_form_only 55565    7.717592    10.041077    -0.246706
            historical_form_plus_lagged_credit 55565    7.520941     9.824106    -0.766190
historical_form_plus_lagged_credit_and_matchup 55565    7.512161     9.809630    -0.630031

## Metrics by held-out season

test_season_id test_season                                 feature_family     n       mae      rmse  bias_pred_minus_actual
             9     2022-23                            baseline_last_round 17951  9.913281 13.074394               -0.132309
             9     2022-23                        baseline_previous5_mean 17951  7.996101 10.519849               -0.308954
             9     2022-23                          baseline_train_median 18404 10.403842 13.752563               -3.800301
             9     2022-23                           historical_form_only 18404  7.696682 10.041013               -0.387315
             9     2022-23             historical_form_plus_lagged_credit 18404  7.493187  9.741778               -0.178582
             9     2022-23 historical_form_plus_lagged_credit_and_matchup 18404  7.489628  9.740679               -0.081377
            13     2023-24                            baseline_last_round 17787  9.892343 13.127910               -0.057328
            13     2023-24                        baseline_previous5_mean 17787  7.986133 10.493967               -0.226886
            13     2023-24                          baseline_train_median 18279 10.697235 13.990180               -3.357495
            13     2023-24                           historical_form_only 18279  7.733339 10.031816               -0.128378
            13     2023-24             historical_form_plus_lagged_credit 18279  7.535738  9.868543               -1.159129
            13     2023-24 historical_form_plus_lagged_credit_and_matchup 18279  7.533677  9.850588               -0.999160
            19     2024-25                            baseline_last_round 18404  9.949685 13.122153               -0.099540
            19     2024-25                        baseline_previous5_mean 18404  8.024544 10.508092               -0.290295
            19     2024-25                          baseline_train_median 18882 10.415704 13.569995               -3.036717
            19     2024-25                           historical_form_only 18882  7.722728 10.050096               -0.224206
            19     2024-25             historical_form_plus_lagged_credit 18882  7.533667  9.860828               -0.958534
            19     2024-25 historical_form_plus_lagged_credit_and_matchup 18882  7.513295  9.836828               -0.807454

## Coverage and interpretation

- Matchup date mapping: 768/779 historical rounds accepted; 90,219 rows linked to a target opponent.
- Season ID 9: 18,404 matchup-ready test rows out of 19,165 total rows; lagged CR present on 17,951 rows; exact prior archived-round row on 1,392 rows.
- Season ID 13: 18,279 matchup-ready test rows out of 18,927 total rows; lagged CR present on 17,787 rows; exact prior archived-round row on 1,423 rows.
- Season ID 19: 18,882 matchup-ready test rows out of 19,590 total rows; lagged CR present on 18,404 rows; exact prior archived-round row on 1,631 rows.

## Limitations

This is a market- and matchup-aware player-score backtest, not yet a complete optimal-lineup backtest. The weekly-round files contain outcome rows rather than a full timestamped pre-lock market universe. A valid lineup backtest must avoid using the target-round player list as if it were known before lock.

The local player archives also lack historical coach CR markets. NBA final team points and margins can reconstruct the coach score before the credit-difference multiplier; exact historical coach PDK needs the historical coach prices or a validated reconstruction.

Production model/configuration remains unchanged.

## Artifacts

- Metrics: `reports/audit/dunkest_lagged_credit_matchup_walk_forward_20261013_v1_metrics.csv`
- Predictions: `reports/audit/dunkest_lagged_credit_matchup_walk_forward_20261013_v1_predictions.csv`
- Audit JSON: `reports/audit/dunkest_lagged_credit_matchup_walk_forward_20261013_v1.json`
