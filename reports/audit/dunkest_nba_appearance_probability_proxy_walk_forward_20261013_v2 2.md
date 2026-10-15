# NBA appearance-continuity proxy — walk-forward audit

> **Label caveat / superseded interpretation:** V2 treats missing target rows as proxy negatives. Since these rows may be absent for reasons other than non-participation, the resulting metrics are not reliable participation-model validation. See V3, which excludes missing rows and shows that the observed target rows are almost all positive-minute appearances.

Generated UTC: 2026-10-13T10:28:20.141913+00:00

## What this estimates

Probability of positive minutes in a team's next NBA game, conditional on a recorded appearance for that team within the previous five team games. It is not a Dunkest pre-lock p_play model.

## Walk-forward metrics

 season                    method  rows  positive_rate    brier  log_loss  roc_auc  average_precision  mean_predicted_probability  observed_target_row_coverage
2021-22   logistic_lagged_history 31123       0.745558 0.138008  0.433418 0.822528           0.915417                    0.760773                      0.747550
2021-22  baseline_previous_5_rate 31123       0.745558 0.159374  0.805760 0.777915           0.885375                    0.772317                      0.747550
2021-22 baseline_previous_10_rate 31123       0.745558 0.172672  0.715180 0.751210           0.881844                    0.752979                      0.747550
2021-22   baseline_constant_90pct 31123       0.745558 0.213554  0.664427 0.500000           0.745558                    0.900000                      0.747550
2022-23   logistic_lagged_history 31787       0.759839 0.130193  0.413581 0.831702           0.924997                    0.765449                      0.761475
2022-23  baseline_previous_5_rate 31787       0.759839 0.149320  0.776615 0.785792           0.894338                    0.784277                      0.761475
2022-23 baseline_previous_10_rate 31787       0.759839 0.161707  0.690695 0.765210           0.893311                    0.768110                      0.761475
2022-23   baseline_constant_90pct 31787       0.759839 0.202129  0.633048 0.500000           0.759839                    0.900000                      0.761475
2023-24   logistic_lagged_history 32686       0.749434 0.128861  0.408713 0.846210           0.929530                    0.750384                      0.752157
2023-24  baseline_previous_5_rate 32686       0.749434 0.146545  0.733385 0.803561           0.899538                    0.774749                      0.752157
2023-24 baseline_previous_10_rate 32686       0.749434 0.157742  0.656732 0.788529           0.901082                    0.756532                      0.752157
2023-24   baseline_constant_90pct 32686       0.749434 0.210453  0.655910 0.500000           0.749434                    0.900000                      0.752157
2024-25   logistic_lagged_history 32887       0.741722 0.136509  0.429843 0.831269           0.919639                    0.751735                      0.743729
2024-25  baseline_previous_5_rate 32887       0.741722 0.155813  0.790373 0.786225           0.886521                    0.770837                      0.743729
2024-25 baseline_previous_10_rate 32887       0.741722 0.168218  0.706725 0.766294           0.886036                    0.753550                      0.743729
2024-25   baseline_constant_90pct 32887       0.741722 0.216623  0.672856 0.500000           0.741722                    0.900000                      0.743729

## Cohort coverage

- Team games: 19,038
- Player-game rows: 172,084
- Candidate-game rows: 216,502
- Observed target rows: 164,331
- Missing target rows treated as proxy non-appearances: 52,171

## Decision

Keep experimental. Consider only if held-out Brier/log loss improve consistently. Do not describe missing rows as verified DNP/OUT and do not feed these probabilities to production without full pre-lock snapshots.

## Artifacts

reports/audit/dunkest_nba_appearance_probability_proxy_walk_forward_20261013_v2_predictions.csv
reports/audit/dunkest_nba_appearance_probability_proxy_walk_forward_20261013_v2_metrics.csv
reports/audit/dunkest_nba_appearance_probability_proxy_walk_forward_20261013_v2.json
