# NBA appearance-continuity proxy — walk-forward audit

Generated UTC: 2026-10-13T10:26:37.056335+00:00

## What this estimates

Probability of positive minutes in a team's next NBA game, conditional on a recorded appearance for that team within the previous five team games. It is not a Dunkest pre-lock p_play model.

## Walk-forward metrics

 season                    method  rows  positive_rate    brier  log_loss  roc_auc  average_precision  mean_predicted_probability  observed_target_row_coverage
2021-22   logistic_lagged_history 31166       0.744818 0.137755  0.432966 0.823314           0.915267                    0.760112                      0.746904
2021-22  baseline_previous_5_rate 31166       0.744818 0.159593  0.811153 0.777601           0.884684                    0.773585                      0.746904
2021-22 baseline_previous_10_rate 31166       0.744818 0.172909  0.717832 0.750943           0.881252                    0.754255                      0.746904
2021-22   baseline_constant_90pct 31166       0.744818 0.214146  0.666053 0.500000           0.744818                    0.900000                      0.746904
2022-23   logistic_lagged_history 31835       0.759227 0.130319  0.414071 0.831994           0.924888                    0.764803                      0.760892
2022-23  baseline_previous_5_rate 31835       0.759227 0.149543  0.780328 0.785423           0.893776                    0.785166                      0.760892
2022-23 baseline_previous_10_rate 31835       0.759227 0.161795  0.692850 0.765162           0.892894                    0.769168                      0.760892
2022-23   baseline_constant_90pct 31835       0.759227 0.202618  0.634392 0.500000           0.759227                    0.900000                      0.760892
2023-24   logistic_lagged_history 32739       0.748648 0.128931  0.409057 0.846575           0.929420                    0.749790                      0.751367
2023-24  baseline_previous_5_rate 32739       0.748648 0.146786  0.738837 0.803205           0.898824                    0.776448                      0.751367
2023-24 baseline_previous_10_rate 32739       0.748648 0.157947  0.659282 0.788305           0.900547                    0.758272                      0.751367
2023-24   baseline_constant_90pct 32739       0.748648 0.211081  0.657636 0.500000           0.748648                    0.900000                      0.751367
2024-25   logistic_lagged_history 32944       0.740772 0.136381  0.429637 0.832146           0.919632                    0.750767                      0.742836
2024-25  baseline_previous_5_rate 32944       0.740772 0.155923  0.793851 0.786299           0.885920                    0.771893                      0.742836
2024-25 baseline_previous_10_rate 32944       0.740772 0.168306  0.708236 0.766522           0.885573                    0.754669                      0.742836
2024-25   baseline_constant_90pct 32944       0.740772 0.217382  0.674942 0.500000           0.740772                    0.900000                      0.742836

## Cohort coverage

- Team games: 19,038
- Player-game rows: 172,084
- Candidate-game rows: 216,864
- Observed target rows: 164,452
- Missing target rows treated as proxy non-appearances: 52,412

## Decision

Keep experimental. Consider only if held-out Brier/log loss improve consistently. Do not describe missing rows as verified DNP/OUT and do not feed these probabilities to production without full pre-lock snapshots.

## Artifacts

reports/audit/dunkest_nba_appearance_probability_proxy_walk_forward_20261013_v1_predictions.csv
reports/audit/dunkest_nba_appearance_probability_proxy_walk_forward_20261013_v1_metrics.csv
reports/audit/dunkest_nba_appearance_probability_proxy_walk_forward_20261013_v1.json
