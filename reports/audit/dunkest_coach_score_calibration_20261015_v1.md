# Coach Monte Carlo score calibration — V1

Generated UTC: 2026-10-15T07:22:56.479756+00:00

The model is trained on earlier walk-forward seasons (2022-23 and 2023-24), assessed on 2024-25, and additionally checked on 2025-26. The outcome is base coach PDK with CR=10 for both teams, isolating team-score simulation from the deterministic coach-CR multiplier. No full-lineup validation or 2026/27 prospective data are used.

## Point-score correction comparison

 season      method    n     mae    rmse  bias_pred_minus_actual
2024-25         raw 2460 15.0584 17.3863                  0.0814
2024-25 global_bias 2460 15.0573 17.3863                 -0.0794
2024-25      affine 2460 15.2271 17.3867                 -0.0720
2024-25  score_band 2460 15.1735 17.3948                 -0.0333
2025-26         raw 2460 15.0636 17.5845                  0.1377
2025-26 global_bias 2460 15.0624 17.5840                 -0.0230
2025-26      affine 2460 15.2693 17.5943                 -0.0249
2025-26  score_band 2460 15.1892 17.6102                  0.0199

## Paired game-cluster bootstrap: candidate MAE minus raw MAE

 season      method  delta_mae_candidate_minus_raw  ci95_low  ci95_high  game_clusters
2024-25 global_bias                        -0.0011   -0.0025     0.0003           1230
2024-25      affine                         0.1688    0.1296     0.2082           1230
2024-25  score_band                         0.1151    0.0863     0.1423           1230
2025-26 global_bias                        -0.0012   -0.0027     0.0003           1230
2025-26      affine                         0.2057    0.1665     0.2430           1230
2025-26  score_band                         0.1256    0.0978     0.1537           1230

## Monte Carlo interval coverage

 season    n  mean_mae  mean_rmse  mean_bias_pred_minus_actual  p10_p90_coverage  below_p10_rate  above_p90_rate  median_coverage_actual_le_p50  mean_interval_width
2022-23 2460   15.4333    17.3706                       0.1527            0.8663          0.0667          0.0671                         0.5524              44.1625
2023-24 2460   15.2353    17.4968                       0.1699            0.8337          0.0837          0.0825                         0.5488              43.7309
2024-25 2460   15.0542    17.3836                       0.0816            0.8516          0.0732          0.0752                         0.5398              44.0896
2025-26 2460   15.0656    17.5783                       0.1374            0.8358          0.0825          0.0817                         0.5459              44.3083
 pooled 9840   15.1971    17.4575                       0.1354            0.8468          0.0765          0.0766                         0.5467              44.0728

## Decision

- The raw Monte Carlo expected coach score is already close to unbiased on the validation and later-audit seasons.
- Global bias correction reduces MAE by only about 0.001 coach points; its paired game-cluster 95% interval crosses zero.
- Affine and score-band corrections worsen MAE in both seasons, so they are not promoted.
- The P10–P90 interval is conservative relative to its nominal 80% coverage; no interval narrowing is promoted without a stable out-of-sample improvement.
- This is an explicit calibration check, not proof that future coach scores are certain. It does not alter production weights or the frozen prospective test.

## Artifacts

reports/audit/dunkest_coach_score_calibration_20261015_v1_metrics.csv
reports/audit/dunkest_coach_score_calibration_20261015_v1_intervals.csv
reports/audit/dunkest_coach_score_calibration_20261015_v1.json
