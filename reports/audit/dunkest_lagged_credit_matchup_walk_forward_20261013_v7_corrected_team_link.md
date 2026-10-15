# Dunkest historical lagged-credit walk-forward — V7 (corrected historical game-team linkage)

Generated (UTC): 2026-10-13T11:43:34.095649+00:00

## Method

Each target is the official-valid player PDK total in a historical Dunkest week/round. Player-history features use earlier observed rounds only. Unlike V6, this experiment assigns target-game team/date from the versioned full-stat historical game-link dataset rather than source team_code plus PDK alone. Opponent and rest/schedule features use completed NBA team games strictly before the linked target date; same-day games are excluded. It compares the expanded-matchup model with the same model plus team/opponent rest, back-to-back, and prior-seven-day game-count features. No current-round CR or statistics enter predictors.

The test is expanding-origin by season: train on earlier valid seasons and predict a later season. Seasons 2018/19 and 2019/20 are excluded as supervised targets because their official validity flags are false in the local archive.

## Pooled out-of-fold metrics

                                                      feature_family     n  pooled_mae  pooled_rmse  pooled_bias
                                                 baseline_last_round 55855    9.918450    13.098469    -0.111430
                                             baseline_previous5_mean 55855    7.995647    10.490231    -0.284634
                                               baseline_train_median 57342   10.448639    13.734429    -3.498598
          historical_form_plus_lagged_credit_and_expanded_matchup_v2 57342    7.489723     9.781002    -0.633891
historical_form_plus_lagged_credit_expanded_matchup_rest_schedule_v6 57342    7.471617     9.743140    -0.576103

## Metrics by held-out season

test_season_id test_season                                                       feature_family     n       mae      rmse  bias_pred_minus_actual
             9     2022-23                                                  baseline_last_round 18605  9.906429 13.053513               -0.134463
             9     2022-23                                              baseline_previous5_mean 18605  7.978972 10.484981               -0.319959
             9     2022-23                                                baseline_train_median 19082 10.349134 13.678113               -3.763652
             9     2022-23           historical_form_plus_lagged_credit_and_expanded_matchup_v2 19082  7.462578  9.712357               -0.175965
             9     2022-23 historical_form_plus_lagged_credit_expanded_matchup_rest_schedule_v6 19082  7.442726  9.673719               -0.118229
            13     2023-24                                                  baseline_last_round 18268  9.891181 13.100714               -0.084183
            13     2023-24                                              baseline_previous5_mean 18268  7.984713 10.479027               -0.241238
            13     2023-24                                                baseline_train_median 18774 10.614003 13.935040               -3.481270
            13     2023-24           historical_form_plus_lagged_credit_and_expanded_matchup_v2 18774  7.516390  9.817414               -0.958565
            13     2023-24 historical_form_plus_lagged_credit_expanded_matchup_rest_schedule_v6 18774  7.490744  9.777178               -0.914764
            19     2024-25                                                  baseline_last_round 18982  9.956476 13.140231               -0.115077
            19     2024-25                                              baseline_previous5_mean 18982  8.022515 10.506139               -0.291775
            19     2024-25                                                baseline_train_median 19486 10.386758 13.594055               -3.255733
            19     2024-25           historical_form_plus_lagged_credit_and_expanded_matchup_v2 19486  7.490612  9.812790               -0.769514
            19     2024-25 historical_form_plus_lagged_credit_expanded_matchup_rest_schedule_v6 19486  7.481481  9.777966               -0.698197

## Coverage and interpretation

- Matchup date mapping: 778/779 historical rounds accepted; 93,284 rows linked to a target opponent.
- Season ID 9: 19,082 matchup-ready test rows out of 19,165 total rows; lagged CR present on 18,605 rows; exact prior archived-round row on 1,431 rows.
- Season ID 13: 18,774 matchup-ready test rows out of 18,927 total rows; lagged CR present on 18,268 rows; exact prior archived-round row on 1,444 rows.
- Season ID 19: 19,486 matchup-ready test rows out of 19,590 total rows; lagged CR present on 18,982 rows; exact prior archived-round row on 1,679 rows.

## Paired comparison with V6

On the same 55,252 held-out player-round predictions per model family, corrected-link V7 does not improve error metrics. For the expanded-matchup family, MAE changes from 7.5178 to 7.5186 (delta +0.0008; 95% round-cluster bootstrap CI [-0.0050, +0.0066]). For the rest/schedule family, MAE changes from 7.4931 to 7.4990 (delta +0.0060; 95% CI approximately [0.0000, +0.0120]). Both intervals include zero or touch it within rounding. The V7 full-sample MAE is lower than V6, but this is not an apples-to-apples improvement because V7 includes additional matchup-ready rows; on common rows it is neutral/slightly worse. Keep V7 experimental and do not promote the changed feature mapping into production based on this result alone. See the separate paired evaluation report for round-clustered metrics and season breakdown.

## Limitations

This is a market- and matchup-aware player-score backtest, not yet a complete optimal-lineup backtest. The corrected historical game-team mapping improves date/opponent coverage but is a retrospective outcome linkage, not a pre-lock snapshot. The weekly-round files contain outcome rows rather than a full timestamped pre-lock market universe. A valid lineup backtest must avoid using the target-round player list as if it were known before lock.

The local player archives also lack historical coach CR markets. NBA final team points and margins can reconstruct the coach score before the credit-difference multiplier; exact historical coach PDK needs the historical coach prices or a validated reconstruction.

## Rest/schedule feature coverage

- Rows with prior own-team game: 93,295; opponent prior game: 93,284.
- Rows with all rest/schedule inputs: 93,284. Same-day games excluded: yes.

Production model/configuration remains unchanged. V7 remains experimental pending paired evaluation on common held-out rows.

## Artifacts

- Metrics: `reports/audit/dunkest_lagged_credit_matchup_walk_forward_20261013_v7_corrected_team_link_metrics.csv`
- Predictions: `reports/audit/dunkest_lagged_credit_matchup_walk_forward_20261013_v7_corrected_team_link_predictions.csv`
- Audit JSON: `reports/audit/dunkest_lagged_credit_matchup_walk_forward_20261013_v7_corrected_team_link.json`
