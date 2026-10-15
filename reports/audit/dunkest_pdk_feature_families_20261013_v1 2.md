# Dunkest PDK feature-family comparison — 2026-10-13

## Protocol

- Expanding-origin training: all eligible seasons before the test season.
- Feature selection uses 2022/23, 2023/24 and 2024/25 only.
- 2025/26 is a secondary historical comparison, not used for feature selection; it is not a globally untouched holdout.
- Target labels are verified official PDK rows with valid-game flags and verified NBA identity matches.
- All candidates use identical Extra Trees estimator settings; only the feature family changes.
- Baseline: previous-10 valid PDK-game mean, falling back to the training-target median.
- No production model, configuration, or source dataset was changed.

## Validation summary

| feature_family            | weighted_mae | weighted_rmse | weighted_bias | validation_rows | folds  |
| ------------------------- | ------------ | ------------- | ------------- | --------------- | ------ |
| combined_full             | 7.5670       | 9.8382        | -0.1702       | 57682.0000      | 3.0000 |
| combined_without_opponent | 7.5672       | 9.8397        | -0.1595       | 57682.0000      | 3.0000 |
| nba_history_plus_opponent | 7.6238       | 9.9606        | -0.5783       | 57682.0000      | 3.0000 |
| pdk_history_plus_opponent | 7.8326       | 10.0761       | 0.2679        | 57682.0000      | 3.0000 |

Selected family by row-weighted validation MAE: **combined_full**.

## Per-fold metrics

| split                        | test_season | feature_family            | n_features | train_rows | test_rows | n     | mae    | rmse    | bias_pred_minus_actual | r2     | p90_absolute_error |
| ---------------------------- | ----------- | ------------------------- | ---------- | ---------- | --------- | ----- | ------ | ------- | ---------------------- | ------ | ------------------ |
| validation                   | 2022-23     | baseline_prev10_mean      | 1          | 36084      | 19165     | 19165 | 7.7689 | 10.1134 | -0.0687                | 0.4096 | 16.5856            |
| validation                   | 2022-23     | pdk_history_plus_opponent | 12         | 36084      | 19165     | 19165 | 7.8377 | 10.0636 | 0.2869                 | 0.4154 | 16.1961            |
| validation                   | 2022-23     | nba_history_plus_opponent | 69         | 36084      | 19165     | 19165 | 7.6209 | 9.9783  | -0.8174                | 0.4252 | 16.2032            |
| validation                   | 2022-23     | combined_full             | 79         | 36084      | 19165     | 19165 | 7.5599 | 9.8310  | -0.2602                | 0.4421 | 15.9645            |
| validation                   | 2022-23     | combined_without_opponent | 77         | 36084      | 19165     | 19165 | 7.5627 | 9.8389  | -0.2575                | 0.4412 | 15.9627            |
| validation                   | 2023-24     | baseline_prev10_mean      | 1          | 55249      | 18927     | 18927 | 7.7652 | 10.1003 | 0.0479                 | 0.4413 | 16.6088            |
| validation                   | 2023-24     | pdk_history_plus_opponent | 12         | 55249      | 18927     | 18927 | 7.8399 | 10.0599 | 0.3289                 | 0.4458 | 16.4571            |
| validation                   | 2023-24     | nba_history_plus_opponent | 69         | 55249      | 18927     | 18927 | 7.6111 | 9.9312  | -0.5554                | 0.4599 | 16.3546            |
| validation                   | 2023-24     | combined_full             | 79         | 55249      | 18927     | 18927 | 7.5610 | 9.8132  | -0.1148                | 0.4727 | 16.1002            |
| validation                   | 2023-24     | combined_without_opponent | 77         | 55249      | 18927     | 18927 | 7.5561 | 9.8044  | -0.0988                | 0.4736 | 16.0785            |
| validation                   | 2024-25     | baseline_prev10_mean      | 1          | 74176      | 19590     | 19590 | 7.7920 | 10.1795 | -0.0694                | 0.4066 | 16.5053            |
| validation                   | 2024-25     | pdk_history_plus_opponent | 12         | 74176      | 19590     | 19590 | 7.8205 | 10.1040 | 0.1905                 | 0.4153 | 16.3780            |
| validation                   | 2024-25     | nba_history_plus_opponent | 69         | 74176      | 19590     | 19590 | 7.6387 | 9.9716  | -0.3665                | 0.4306 | 16.3126            |
| validation                   | 2024-25     | combined_full             | 79         | 74176      | 19590     | 19590 | 7.5798 | 9.8694  | -0.1357                | 0.4422 | 16.0442            |
| validation                   | 2024-25     | combined_without_opponent | 77         | 74176      | 19590     | 19590 | 7.5824 | 9.8745  | -0.1222                | 0.4416 | 16.0894            |
| secondary_historical_2025_26 | 2025-26     | baseline_prev10_mean      | 1          | 93766      | 18412     | 18412 | 7.7886 | 10.1539 | -0.0479                | 0.3859 | 16.5447            |
| secondary_historical_2025_26 | 2025-26     | pdk_history_plus_opponent | 12         | 93766      | 18412     | 18412 | 7.7676 | 10.0344 | 0.1144                 | 0.4003 | 16.2248            |
| secondary_historical_2025_26 | 2025-26     | nba_history_plus_opponent | 69         | 93766      | 18412     | 18412 | 7.6290 | 9.9472  | -0.4276                | 0.4107 | 16.0245            |
| secondary_historical_2025_26 | 2025-26     | combined_full             | 79         | 93766      | 18412     | 18412 | 7.5639 | 9.8383  | -0.1682                | 0.4235 | 15.9057            |
| secondary_historical_2025_26 | 2025-26     | combined_without_opponent | 77         | 93766      | 18412     | 18412 | 7.5677 | 9.8420  | -0.1472                | 0.4231 | 16.0290            |

## Low-history cohort comparison

Cohorts use the number of previous valid Dunkest PDK games. They diagnose cold-start behavior and are not an authoritative NBA draft-year rookie label.

| feature_family            | cohort                            | n          | weighted_mae | weighted_rmse | weighted_bias |
| ------------------------- | --------------------------------- | ---------- | ------------ | ------------- | ------------- |
| baseline_prev10_mean      | established_history_over_10_games | 55109.0000 | 7.8635       | 10.2194       | -0.0194       |
| baseline_prev10_mean      | limited_history_4_to_10_games     | 1588.0000  | 5.5499       | 7.7656        | -1.1246       |
| baseline_prev10_mean      | low_history_1_to_3_games          | 736.0000   | 5.3502       | 7.5675        | -1.2370       |
| baseline_prev10_mean      | new_or_no_prior_pdk_history       | 249.0000   | 9.6840       | 10.5484       | 8.0002        |
| combined_full             | established_history_over_10_games | 55109.0000 | 7.6732       | 9.9447        | -0.1763       |
| combined_full             | limited_history_4_to_10_games     | 1588.0000  | 5.4456       | 7.3758        | -0.0679       |
| combined_full             | low_history_1_to_3_games          | 736.0000   | 5.0181       | 6.8947        | -0.1385       |
| combined_full             | new_or_no_prior_pdk_history       | 249.0000   | 5.1360       | 6.8331        | 0.4313        |
| combined_without_opponent | established_history_over_10_games | 55109.0000 | 7.6736       | 9.9464        | -0.1642       |
| combined_without_opponent | limited_history_4_to_10_games     | 1588.0000  | 5.4522       | 7.3740        | -0.0587       |
| combined_without_opponent | low_history_1_to_3_games          | 736.0000   | 5.0103       | 6.8918        | -0.2021       |
| combined_without_opponent | new_or_no_prior_pdk_history       | 249.0000   | 5.0754       | 6.7936        | 0.3604        |
| nba_history_plus_opponent | established_history_over_10_games | 55109.0000 | 7.7306       | 10.0696       | -0.6067       |
| nba_history_plus_opponent | limited_history_4_to_10_games     | 1588.0000  | 5.4872       | 7.4251        | -0.0266       |
| nba_history_plus_opponent | low_history_1_to_3_games          | 736.0000   | 5.0602       | 6.9247        | -0.0188       |
| nba_history_plus_opponent | new_or_no_prior_pdk_history       | 249.0000   | 5.1846       | 6.9649        | 0.5507        |
| pdk_history_plus_opponent | established_history_over_10_games | 55109.0000 | 7.9289       | 10.1765       | 0.2453        |
| pdk_history_plus_opponent | limited_history_4_to_10_games     | 1588.0000  | 5.7227       | 7.6412        | 0.2467        |
| pdk_history_plus_opponent | low_history_1_to_3_games          | 736.0000   | 5.3960       | 7.1374        | 0.7661        |
| pdk_history_plus_opponent | new_or_no_prior_pdk_history       | 249.0000   | 7.1565       | 8.7185        | 3.9448        |

## Interpretation

- The best feature family is selected only on chronological validation seasons; the secondary 2025/26 results are not used for selection.
- The full lineup optimizer is a separate evaluation problem. A lower player-game MAE does not establish better lineups, coach points, credit-budget use, availability decisions or transfer malus.
- The existing proxy-trained versus official-target comparison on 2025/26 is mixed; it does not justify changing production target mode on its own.
- The low-history cohort should not be described as actual NBA rookies. Use the separate draft-year-matched rookie audit for rookie-specific conclusions.
- Historical complete-lineup backtest remains blocked: available evidence has no rounds with both fixture-linked realized player results and coach results tied to authentic frozen pre-match market, credits and availability snapshots.

## Artifacts

- Experiment script: scripts/compare_dunkest_pdk_feature_families_walk_forward_v1.py
- Predictions: reports/audit/dunkest_pdk_feature_families_predictions_20261013_v1.csv
- Metrics: reports/audit/dunkest_pdk_feature_families_metrics_20261013_v1.csv
- Cohorts: reports/audit/dunkest_pdk_feature_families_cohorts_20261013_v1.csv
- Audit JSON: reports/audit/dunkest_pdk_feature_families_audit_20261013_v1.json
