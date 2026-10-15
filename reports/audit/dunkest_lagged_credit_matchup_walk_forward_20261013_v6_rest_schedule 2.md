# Dunkest historical lagged-credit walk-forward — V6 (past-only rest and schedule features)

Generated (UTC): 2026-10-13T09:56:58.103715+00:00

## Method

Each target is the official-valid player PDK total in a historical Dunkest week/round. Features are built by shifting player CR, PDK, minutes, plusvalenza and box-score summaries from earlier observed rounds only. Matchup features use high-confidence reconstructed round dates and opponent defensive trends and pace strictly before the target date. V6 compares the existing expanded-matchup model with the same model plus team/opponent rest, back-to-back, and prior-seven-day game-count features. All rest features use completed game dates strictly before the target date; same-day games are excluded. No current-round CR or statistics enter the predictor.

The test is expanding-origin by season: train on earlier valid seasons and predict a later season. Seasons 2018/19 and 2019/20 are excluded as supervised targets because their official validity flags are false in the local archive.

## Pooled out-of-fold metrics

                                                      feature_family     n  pooled_mae  pooled_rmse  pooled_bias
                                                 baseline_last_round 54142    9.918777    13.108231    -0.096537
                                             baseline_previous5_mean 54142    8.002494    10.507355    -0.275650
                                               baseline_train_median 55565   10.504389    13.769767    -3.395153
          historical_form_plus_lagged_credit_and_expanded_matchup_v2 55565    7.502754     9.796561    -0.622456
historical_form_plus_lagged_credit_expanded_matchup_rest_schedule_v6 55565    7.477665     9.754387    -0.563336

## Metrics by held-out season

test_season_id test_season                                                       feature_family     n       mae      rmse  bias_pred_minus_actual
             9     2022-23                                                  baseline_last_round 17951  9.913281 13.074394               -0.132309
             9     2022-23                                              baseline_previous5_mean 17951  7.996101 10.519849               -0.308954
             9     2022-23                                                baseline_train_median 18404 10.403842 13.752563               -3.800301
             9     2022-23           historical_form_plus_lagged_credit_and_expanded_matchup_v2 18404  7.483174  9.738037               -0.133142
             9     2022-23 historical_form_plus_lagged_credit_expanded_matchup_rest_schedule_v6 18404  7.456478  9.694956               -0.076517
            13     2023-24                                                  baseline_last_round 17787  9.892343 13.127910               -0.057328
            13     2023-24                                              baseline_previous5_mean 17787  7.986133 10.493967               -0.226886
            13     2023-24                                                baseline_train_median 18279 10.697235 13.990180               -3.357495
            13     2023-24           historical_form_plus_lagged_credit_and_expanded_matchup_v2 18279  7.522331  9.830148               -0.960597
            13     2023-24 historical_form_plus_lagged_credit_expanded_matchup_rest_schedule_v6 18279  7.494350  9.790930               -0.911727
            19     2024-25                                                  baseline_last_round 18404  9.949685 13.122153               -0.099540
            19     2024-25                                              baseline_previous5_mean 18404  8.024544 10.508092               -0.290295
            19     2024-25                                                baseline_train_median 18882 10.415704 13.569995               -3.036717
            19     2024-25           historical_form_plus_lagged_credit_and_expanded_matchup_v2 18882  7.502886  9.820832               -0.772040
            19     2024-25 historical_form_plus_lagged_credit_expanded_matchup_rest_schedule_v6 18882  7.482163  9.776668               -0.700566

## Coverage and interpretation

- Matchup date mapping: 768/779 historical rounds accepted; 90,219 rows linked to a target opponent.
- Season ID 9: 18,404 matchup-ready test rows out of 19,165 total rows; lagged CR present on 17,951 rows; exact prior archived-round row on 1,392 rows.
- Season ID 13: 18,279 matchup-ready test rows out of 18,927 total rows; lagged CR present on 17,787 rows; exact prior archived-round row on 1,423 rows.
- Season ID 19: 18,882 matchup-ready test rows out of 19,590 total rows; lagged CR present on 18,404 rows; exact prior archived-round row on 1,631 rows.

## Limitations

This is a market- and matchup-aware player-score backtest, not yet a complete optimal-lineup backtest. The weekly-round files contain outcome rows rather than a full timestamped pre-lock market universe. A valid lineup backtest must avoid using the target-round player list as if it were known before lock.

The local player archives also lack historical coach CR markets. NBA final team points and margins can reconstruct the coach score before the credit-difference multiplier; exact historical coach PDK needs the historical coach prices or a validated reconstruction.

## Rest/schedule feature coverage

- Rows with prior own-team game: 93,652; opponent prior game: 90,219.
- Rows with all rest/schedule inputs: 90,219. Same-day games excluded: yes.

Production model/configuration remains unchanged.

## Artifacts

- Metrics: `reports/audit/dunkest_lagged_credit_matchup_walk_forward_20261013_v6_rest_schedule_metrics.csv`
- Predictions: `reports/audit/dunkest_lagged_credit_matchup_walk_forward_20261013_v6_rest_schedule_predictions.csv`
- Audit JSON: `reports/audit/dunkest_lagged_credit_matchup_walk_forward_20261013_v6_rest_schedule.json`
