# Production player forecast: cohort and score-band diagnostics — V1

Generated UTC: 2026-10-15T07:17:17.320152+00:00

This report evaluates individual-player forecasts from the exact production trainer's existing chronological out-of-sample predictions. It is not a historical lineup backtest. The 2025/26 holdout and frozen 2026/27 prospective bundle are excluded.

## Cohort metrics

fold_season                                cohort           candidate     n     mae    rmse  bias_pred_minus_actual  mean_predicted  mean_actual
    2022-23                                   all production_ensemble 19165  7.5582  9.8153                 -0.1083         15.8447      15.9531
    2022-23                                   all     baseline_prev10 19086  7.7635 10.1137                 -0.0944         15.9004      15.9948
    2022-23           official_draft_class_rookie production_ensemble  1416  6.4584  8.4615                 -0.4793         11.0846      11.5640
    2022-23           official_draft_class_rookie     baseline_prev10  1375  6.6279  8.6929                 -0.5767         11.1088      11.6855
    2022-23                      low_history_le_5 production_ensemble   456  5.4396  7.4537                 -0.2553          6.7419       6.9972
    2022-23                      low_history_le_5     baseline_prev10   377  5.8947  8.1556                 -0.8222          6.4112       7.2334
    2022-23                          history_gt_5 production_ensemble 18709  7.6098  9.8658                 -0.1048         16.0666      16.1713
    2022-23                          history_gt_5     baseline_prev10 18709  7.8012 10.1492                 -0.0797         16.0916      16.1713
    2022-23   team_changed_from_previous_nba_game production_ensemble   161  7.4359  9.0447                  1.5797         12.2076      10.6278
    2022-23   team_changed_from_previous_nba_game     baseline_prev10   161  7.4224  9.2152                  1.8135         12.4413      10.6278
    2022-23 no_team_change_from_previous_nba_game production_ensemble 19004  7.5592  9.8216                 -0.1226         15.8755      15.9982
    2022-23 no_team_change_from_previous_nba_game     baseline_prev10 18925  7.7664 10.1210                 -0.1106         15.9298      16.0405
    2022-23                       actual_pdk_ge25 production_ensemble  4310 12.3034 14.7990                -11.3428         24.2488      35.5917
    2022-23                       actual_pdk_ge25     baseline_prev10  4306 12.0781 14.7091                -10.4904         25.1082      35.5985
    2022-23                       actual_pdk_ge30 production_ensemble  2903 14.2199 16.6199                -13.7200         25.8542      39.5742
    2022-23                       actual_pdk_ge30     baseline_prev10  2902 13.7198 16.3196                -12.6760         26.9004      39.5764
    2023-24                                   all production_ensemble 18927  7.5464  9.7977                 -0.1471         15.8140      15.9611
    2023-24                                   all     baseline_prev10 18839  7.7546 10.0965                  0.0078         16.0254      16.0176
    2023-24           official_draft_class_rookie production_ensemble  1241  5.9764  7.9487                 -0.0886          9.1530       9.2416
    2023-24           official_draft_class_rookie     baseline_prev10  1197  6.1394  8.3007                 -0.5555          8.8909       9.4464
    2023-24                      low_history_le_5 production_ensemble   518  5.3541  7.2466                  0.1369          6.1300       5.9931
    2023-24                      low_history_le_5     baseline_prev10   430  5.5326  7.8023                 -1.4052          5.0225       6.4277
    2023-24                          history_gt_5 production_ensemble 18409  7.6081  9.8600                 -0.1551         16.0865      16.2416
    2023-24                          history_gt_5     baseline_prev10 18409  7.8065 10.1439                  0.0408         16.2824      16.2416
    2023-24   team_changed_from_previous_nba_game production_ensemble   207  7.2173  8.9608                  1.3529         10.5921       9.2393
    2023-24   team_changed_from_previous_nba_game     baseline_prev10   207  7.5683  9.3338                  1.5865         10.8258       9.2393
    2023-24 no_team_change_from_previous_nba_game production_ensemble 18720  7.5500  9.8066                 -0.1637         15.8718      16.0355
    2023-24 no_team_change_from_previous_nba_game     baseline_prev10 18632  7.7567 10.1046                 -0.0098         16.0832      16.0929
    2023-24                       actual_pdk_ge25 production_ensemble  4369 12.2774 14.6791                -11.2775         24.6097      35.8872
    2023-24                       actual_pdk_ge25     baseline_prev10  4368 11.9528 14.4539                -10.1976         25.6898      35.8874
    2023-24                       actual_pdk_ge30 production_ensemble  2972 14.2122 16.4459                -13.6759         26.2169      39.8928
    2023-24                       actual_pdk_ge30     baseline_prev10  2971 13.5252 15.9739                -12.3771         27.5174      39.8945
    2024-25                                   all production_ensemble 19590  7.5668  9.8548                 -0.0661         15.8550      15.9212
    2024-25                                   all     baseline_prev10 19508  7.7832 10.1775                 -0.1080         15.8648      15.9728
    2024-25           official_draft_class_rookie production_ensemble  1490  6.2612  8.4275                 -0.6035         10.0285      10.6320
    2024-25           official_draft_class_rookie     baseline_prev10  1449  6.6081  8.8891                 -1.0781          9.7597      10.8378
    2024-25                      low_history_le_5 production_ensemble   480  4.9413  6.7592                  0.2711          6.0172       5.7461
    2024-25                      low_history_le_5     baseline_prev10   398  5.3548  7.5982                 -1.3139          4.8692       6.1832
    2024-25                          history_gt_5 production_ensemble 19110  7.6328  9.9202                 -0.0746         16.1021      16.1767
    2024-25                          history_gt_5     baseline_prev10 19110  7.8337 10.2243                 -0.0829         16.0938      16.1767
    2024-25   team_changed_from_previous_nba_game production_ensemble   187  6.8978  8.9508                  2.1457         10.7077       8.5620
    2024-25   team_changed_from_previous_nba_game     baseline_prev10   187  7.0237  9.4949                  2.4796         11.0416       8.5620
    2024-25 no_team_change_from_previous_nba_game production_ensemble 19403  7.5733  9.8632                 -0.0874         15.9046      15.9921
    2024-25 no_team_change_from_previous_nba_game     baseline_prev10 19321  7.7905 10.1839                 -0.1331         15.9115      16.0446
    2024-25                       actual_pdk_ge25 production_ensemble  4425 11.9912 14.5936                -10.9581         24.5404      35.4985
    2024-25                       actual_pdk_ge25     baseline_prev10  4425 12.0151 14.6745                -10.4092         25.0893      35.4985
    2024-25                       actual_pdk_ge30 production_ensemble  2919 14.1106 16.5972                -13.5470         26.1647      39.7116
    2024-25                       actual_pdk_ge30     baseline_prev10  2919 13.8729 16.5178                -12.8398         26.8719      39.7116

## Prediction-band calibration

fold_season prediction_band    n     mae    rmse  bias_pred_minus_actual  mean_predicted  mean_actual  mean_error
    2022-23              <5 1016  4.3573  6.5627                 -0.6628          3.8656       4.5283     -0.6628
    2022-23            5-10 4456  5.7755  7.4982                  0.2838          7.7088       7.4250      0.2838
    2022-23           10-15 4897  7.0486  8.8764                  0.2558         12.3510      12.0953      0.2558
    2022-23           15-20 3439  8.1749 10.3573                 -0.3774         17.4022      17.7795     -0.3774
    2022-23           20-25 2377  9.1757 11.5299                 -0.7192         22.2177      22.9369     -0.7192
    2022-23             25+ 2980 10.1506 12.7091                 -0.3063         30.9551      31.2613     -0.3063
    2023-24              <5 1444  3.9279  5.3759                  0.2747          3.8085       3.5338      0.2747
    2023-24            5-10 4319  5.8157  7.5199                  0.3700          7.6818       7.3118      0.3700
    2023-24           10-15 4400  7.0452  8.9620                  0.0311         12.2974      12.2663      0.0311
    2023-24           15-20 3226  8.2854 10.3688                 -0.2140         17.4569      17.6710     -0.2140
    2023-24           20-25 2411  9.0655 11.3046                 -0.6425         22.2525      22.8950     -0.6425
    2023-24             25+ 3127 10.3795 12.9276                 -0.8560         30.8792      31.7352     -0.8560
    2024-25              <5 1670  3.9525  5.6198                 -0.0049          3.6960       3.7009     -0.0049
    2024-25            5-10 3933  5.9316  7.6568                  0.0423          7.6347       7.5924      0.0423
    2024-25           10-15 4871  7.1110  9.1222                 -0.3781         12.3992      12.7773     -0.3781
    2024-25           15-20 3522  8.2291 10.3410                  0.1357         17.3475      17.2118      0.1357
    2024-25           20-25 2283  9.1687 11.5144                 -0.1002         22.2378      22.3380     -0.1002
    2024-25             25+ 3311 10.1939 12.7063                  0.0420         30.8479      30.8059      0.0420

## Interpretation guardrails

- Official draft-class rookie labels require a name-key match and draft year equal to the target season start year; unmatched players are not guessed to be rookies.
- Low-history is a separate proxy cohort and is not called a rookie cohort.
- Team-change cohort comes from the adapter's chronological, past-only team-transition feature.
- High-score cohorts condition on the realized target and diagnose errors; they are not deployable selection features.
- No production model, weights, configuration, historical labels, or frozen prospective bundle was changed.

## Artifacts

- Metrics: reports/audit/dunkest_production_player_cohort_calibration_20261015_v1_metrics.csv
- Prediction-band diagnostics: reports/audit/dunkest_production_player_cohort_calibration_20261015_v1_prediction_bands.csv
- Audit JSON: reports/audit/dunkest_production_player_cohort_calibration_20261015_v1.json
