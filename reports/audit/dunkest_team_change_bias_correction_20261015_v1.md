# Team-change bias correction: paired outer walk-forward check — V1

Generated UTC: 2026-10-15T07:36:10.876705+00:00

This compares corrected and uncorrected predictions from the same exact production-model run. The uncorrected prediction is recovered by subtracting the recorded correction; no model refit or future target is involved. Correction coefficients were estimated from OOF predictions in the training window before each outer test season.

## Correction by outer fold

{'2022-23': 0.13646688499595458, '2023-24': -0.053200345396334066, '2024-25': 0.011007470130675904}

## MAE / RMSE / bias by cohort

 season           cohort     version     n    mae   rmse  bias_pred_minus_actual
2022-23              all uncorrected 19165 7.5600 9.8159                 -0.1332
2022-23              all   corrected 19165 7.5602 9.8160                 -0.1321
2022-23     team_changed uncorrected   161 7.2081 8.8687                  0.3616
2022-23     team_changed   corrected   161 7.2259 8.8754                  0.4981
2022-23   no_team_change uncorrected 19004 7.5630 9.8236                 -0.1374
2022-23   no_team_change   corrected 19004 7.5630 9.8236                 -0.1374
2022-23 low_history_le_5 uncorrected   456 5.4336 7.4497                 -0.2771
2022-23 low_history_le_5   corrected   456 5.4327 7.4492                 -0.2762
2023-24              all uncorrected 18927 7.5345 9.7958                 -0.2258
2023-24              all   corrected 18927 7.5343 9.7958                 -0.2264
2023-24     team_changed uncorrected   207 7.0401 8.9089                  0.5934
2023-24     team_changed   corrected   207 7.0249 8.9055                  0.5402
2023-24   no_team_change uncorrected 18720 7.5399 9.8051                 -0.2349
2023-24   no_team_change   corrected 18720 7.5399 9.8051                 -0.2349
2023-24 low_history_le_5 uncorrected   518 5.3473 7.2406                  0.1183
2023-24 low_history_le_5   corrected   518 5.3471 7.2407                  0.1174
2024-25              all uncorrected 19590 7.5622 9.8499                 -0.0783
2024-25              all   corrected 19590 7.5622 9.8499                 -0.0782
2024-25     team_changed uncorrected   187 6.7196 8.8261                  1.4558
2024-25     team_changed   corrected   187 6.7223 8.8280                  1.4668
2024-25   no_team_change uncorrected 19403 7.5703 9.8593                 -0.0931
2024-25   no_team_change   corrected 19403 7.5703 9.8593                 -0.0931
2024-25 low_history_le_5 uncorrected   480 4.9392 6.7582                  0.2607
2024-25 low_history_le_5   corrected   480 4.9393 6.7582                  0.2608

## Paired game-cluster bootstrap: corrected MAE minus uncorrected MAE

 season           cohort  n_rows  game_clusters  delta_mae_corrected_minus_uncorrected  ci95_low  ci95_high
2022-23              all   19165           1042                                 0.0001   -0.0001     0.0003
2022-23     team_changed     161             96                                 0.0123   -0.0129     0.0372
2022-23   no_team_change   19004           1042                                 0.0000    0.0000     0.0000
2022-23 low_history_le_5     456            286                                -0.0012   -0.0029     0.0000
2023-24              all   18927           1013                                -0.0001   -0.0002    -0.0001
2023-24     team_changed     207            114                                -0.0158   -0.0240    -0.0076
2023-24   no_team_change   18720           1013                                 0.0000    0.0000     0.0000
2023-24 low_history_le_5     518            330                                 0.0001   -0.0006     0.0008
2024-25              all   19590           1038                                 0.0000    0.0000     0.0000
2024-25     team_changed     187            126                                 0.0030    0.0013     0.0046
2024-25   no_team_change   19403           1038                                 0.0000    0.0000     0.0000
2024-25 low_history_le_5     480            279                                 0.0001   -0.0000     0.0003

## Decision

- **Not promoted to production.** The correction has negligible overall effect (absolute MAE change below 0.0002 PDK) and inconsistent team-change effects: it helps in 2023-24, but worsens MAE in 2022-23 and 2024-25. The later-season paired bootstrap does not support a stable benefit.
- The audit confirms a team-change cohort worth monitoring, but the current evidence does not justify a fixed correction. Keep the original production predictor unchanged.
- High-score and low-history cohorts are diagnostics only; they are not used to select players.
- No historical lineup backtest or 2026/27 prospective data are used.

## Artifacts

reports/audit/dunkest_team_change_bias_correction_20261015_v1_metrics.csv
reports/audit/dunkest_team_change_bias_correction_20261015_v1_bootstrap.csv
reports/audit/dunkest_team_change_bias_correction_20261015_v1.json
