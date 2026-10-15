# NBA appearance-continuity proxy — walk-forward audit

> **Key finding:** once missing rows are excluded, 99.64%–99.79% of observed targets are positive-minute appearances. The historical archive does not contain a sufficiently informative negative class for a meaningful participation model; the low Brier score must not be interpreted as validation of Dunkest p_play.

Generated UTC: 2026-10-13T10:54:53.296402+00:00

## What this estimates

Probability of positive minutes in a team's next NBA game, conditional on a recorded appearance for that team within the previous five team games. It is not a Dunkest pre-lock p_play model.

## Walk-forward metrics

 season                    method  rows  positive_rate    brier  log_loss  roc_auc  average_precision  mean_predicted_probability  observed_target_row_coverage
2021-22   logistic_lagged_history 23266       0.997335 0.002619  0.016105 0.827968           0.999300                    0.997212                           1.0
2021-22  baseline_previous_5_rate 23266       0.997335 0.082213  0.239334 0.771317           0.998967                    0.845236                           1.0
2021-22 baseline_previous_10_rate 23266       0.997335 0.093664  0.284690 0.748036           0.998936                    0.812281                           1.0
2021-22   baseline_constant_90pct 23266       0.997335 0.012132  0.111216 0.500000           0.997335                    0.900000                           1.0
2022-23   logistic_lagged_history 24205       0.997852 0.002135  0.012677 0.890338           0.999648                    0.997424                           1.0
2022-23  baseline_previous_5_rate 24205       0.997852 0.073919  0.218959 0.816272           0.999287                    0.855701                           1.0
2022-23 baseline_previous_10_rate 24205       0.997852 0.084259  0.259590 0.811718           0.999320                    0.827884                           1.0
2022-23   baseline_constant_90pct 24205       0.997852 0.011719  0.110081 0.500000           0.997852                    0.900000                           1.0
2023-24   logistic_lagged_history 24585       0.996380 0.003586  0.020054 0.889868           0.999539                    0.997058                           1.0
2023-24  baseline_previous_5_rate 24585       0.996380 0.076687  0.225899 0.775015           0.998584                    0.855619                           1.0
2023-24 baseline_previous_10_rate 24585       0.996380 0.088122  0.265964 0.810875           0.998962                    0.827635                           1.0
2023-24   baseline_constant_90pct 24585       0.996380 0.012896  0.113315 0.500000           0.996380                    0.900000                           1.0
2024-25   logistic_lagged_history 24459       0.997302 0.002677  0.015979 0.862326           0.999476                    0.997083                           1.0
2024-25  baseline_previous_5_rate 24459       0.997302 0.079048  0.234252 0.747463           0.998798                    0.847756                           1.0
2024-25 baseline_previous_10_rate 24459       0.997302 0.090886  0.275989 0.776191           0.999074                    0.819030                           1.0
2024-25   baseline_constant_90pct 24459       0.997302 0.012159  0.111289 0.500000           0.997302                    0.900000                           1.0

## Cohort coverage

- Team games: 19,038
- Player-game rows: 172,084
- Candidate-game rows: 216,502
- Observed target rows: 164,331
- Missing target rows excluded as unlabeled: 52,171

## Decision

This V3 evaluation avoids treating missing target rows as negative labels, at the cost of evaluating only the observed-row subset. Keep experimental: an observed zero-minute row is not a verified pre-lock DNP/OUT snapshot, and this remains NBA next-game continuity rather than Dunkest round availability.

## Artifacts

reports/audit/dunkest_nba_appearance_probability_proxy_walk_forward_20261013_v3_predictions.csv
reports/audit/dunkest_nba_appearance_probability_proxy_walk_forward_20261013_v3_metrics.csv
reports/audit/dunkest_nba_appearance_probability_proxy_walk_forward_20261013_v3.json
