# Dunkest historical lagged-credit walk-forward — V9 (persisted date-assisted linkage)

Generated (UTC): 2026-10-13T12:13:35.034558+00:00

## Method

Each target is the official-valid player PDK total in a historical Dunkest week/round. Player history features are shifted from earlier observed rounds only. This experiment consumes the persisted v3 full-stat/date-assisted linkage dataset. Round-date consensus is reconstructed exclusively from original v2 exact links (>=10 unique links and >=75% agreement), excluding date-assisted rows to avoid circular date inference. Persisted fallback links require a unique official-valid candidate on that independently established date, matching rounded PDK and all 17 box-score fields. It never uses source team_code to infer the NBA game team and never resolves gp>1 aggregates. Opponent and rest/schedule features use completed NBA team games strictly before the linked target date; same-day games are excluded. Within this corrected linkage, it compares the expanded-matchup model with the same model plus team/opponent rest, back-to-back, and prior-seven-day game-count features. No current-round CR or statistics enter predictors.

The test is expanding-origin by season: train on earlier valid seasons and predict a later season. Seasons 2018/19 and 2019/20 are excluded as supervised targets because their official validity flags are false in the local archive.

## Pooled out-of-fold metrics

                                                      feature_family     n  pooled_mae  pooled_rmse  pooled_bias
                                                 baseline_last_round 56159    9.880530    13.067299    -0.097946
                                             baseline_previous5_mean 56159    7.969267    10.466030    -0.267065
                                               baseline_train_median 57662   10.467580    13.759155    -3.525731
          historical_form_plus_lagged_credit_and_expanded_matchup_v2 57662    7.475367     9.762210    -0.619142
historical_form_plus_lagged_credit_expanded_matchup_rest_schedule_v6 57662    7.453370     9.723967    -0.563811

## Metrics by held-out season

test_season_id test_season                                                       feature_family     n       mae      rmse  bias_pred_minus_actual
             9     2022-23                                                  baseline_last_round 18673  9.880743 13.032462               -0.125419
             9     2022-23                                              baseline_previous5_mean 18673  7.961892 10.468687               -0.307375
             9     2022-23                                                baseline_train_median 19155 10.374783 13.742586               -3.952895
             9     2022-23           historical_form_plus_lagged_credit_and_expanded_matchup_v2 19155  7.455919  9.701314               -0.161451
             9     2022-23 historical_form_plus_lagged_credit_expanded_matchup_rest_schedule_v6 19155  7.433035  9.661723               -0.112393
            13     2023-24                                                  baseline_last_round 18406  9.839143 13.057938               -0.064508
            13     2023-24                                              baseline_previous5_mean 18406  7.948633 10.446063               -0.216400
            13     2023-24                                                baseline_train_median 18918 10.632770 13.949288               -3.459526
            13     2023-24           historical_form_plus_lagged_credit_and_expanded_matchup_v2 18918  7.494394  9.791327               -0.929055
            13     2023-24 historical_form_plus_lagged_credit_expanded_matchup_rest_schedule_v6 18918  7.463761  9.747693               -0.893929
            19     2024-25                                                  baseline_last_round 19080  9.920245 13.110304               -0.103316
            19     2024-25                                              baseline_previous5_mean 19080  7.996389 10.482658               -0.276490
            19     2024-25                                                baseline_train_median 19589 10.398789 13.589412               -3.171969
            19     2024-25           historical_form_plus_lagged_credit_and_expanded_matchup_v2 19589  7.476009  9.793360               -0.767396
            19     2024-25 historical_form_plus_lagged_credit_expanded_matchup_rest_schedule_v6 19589  7.463218  9.761622               -0.686416

## Coverage and interpretation

- Matchup date mapping: 778/779 historical rounds accepted; 93,725 rows linked to a target opponent.
- Persisted v3 date-assisted mapping contains 441 unique links; 36 use a linked NBA team different from the source Dunkest team. Round-date consensus is based on v2 links only; no unresolved row is retried in this run.
- Season ID 9: 19,155 matchup-ready test rows out of 19,165 total rows; lagged CR present on 18,673 rows; exact prior archived-round row on 1,433 rows.
- Season ID 13: 18,918 matchup-ready test rows out of 18,927 total rows; lagged CR present on 18,406 rows; exact prior archived-round row on 1,450 rows.
- Season ID 19: 19,589 matchup-ready test rows out of 19,590 total rows; lagged CR present on 19,080 rows; exact prior archived-round row on 1,681 rows.

## Limitations

This is a market- and matchup-aware player-score backtest, not yet a complete optimal-lineup backtest. Date-assisted mapping improves linkage only where the independent round date and full PDK+box-score signature agree; it remains a retrospective outcome linkage, not a pre-lock snapshot. The weekly-round files contain outcome rows rather than a full timestamped pre-lock market universe. A valid lineup backtest must avoid using the target-round player list as if it were known before lock.

The local player archives also lack historical coach CR markets. NBA final team points and margins can reconstruct the coach score before the credit-difference multiplier; exact historical coach PDK needs the historical coach prices or a validated reconstruction.

## Rest/schedule feature coverage

- Rows with prior own-team game: 93,736; opponent prior game: 93,725.
- Rows with all rest/schedule inputs: 93,725. Same-day games excluded: yes.

Production model/configuration remains unchanged. This V9 run is an experimental walk-forward ablation; it does not replace V6 without paired evaluation on common rows.

## Artifacts

- Metrics: `reports/audit/dunkest_lagged_credit_matchup_walk_forward_20261013_v9_persisted_date_link_metrics.csv`
- Predictions: `reports/audit/dunkest_lagged_credit_matchup_walk_forward_20261013_v9_persisted_date_link_predictions.csv`
- Audit JSON: `reports/audit/dunkest_lagged_credit_matchup_walk_forward_20261013_v9_persisted_date_link.json`
