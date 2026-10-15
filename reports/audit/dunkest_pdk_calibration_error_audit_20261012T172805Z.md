# Dunkest PDK calibration and error audit

Created UTC: 2026-10-12T17:28:05.601546+00:00

## Scope and safeguards

- Stored expanding-window walk-forward predictions only; no fitting or weight selection.
- 2025/26 is descriptive final holdout, not a tuning input.
- Realized-score bands are post-hoc diagnostics, not deployable pre-game features.
- Ensemble weights: 0.60 Random Forest / 0.35 Ridge / 0.05 previous-10 mean.

## Final holdout summary (2025/26)

                model     n  actual_mean  predicted_mean    mae    rmse  bias_pred_minus_actual  within_3_pdk_pct  within_5_pdk_pct
        random_forest 18412      16.1417         15.9692 7.5775  9.8563                 -0.1725           25.4019           42.4017
                ridge 18412      16.1417         16.1912 7.5887  9.8604                  0.0495           25.9885           42.2062
 baseline_prev10_mean 18412      16.1417         16.0937 7.7886 10.1539                 -0.0479           25.9070           41.8368
tuned_convex_ensemble 18412      16.1417         16.0531 7.5568  9.8306                 -0.0885           25.9559           42.6461

## Realized PDK bands

group_value                 model     n  actual_mean  predicted_mean     mae  bias_pred_minus_actual
      (0,5]         random_forest 11942       2.7580          9.7261  7.0179                  6.9681
      (0,5]                 ridge 11942       2.7580          9.6783  7.1439                  6.9202
      (0,5]  baseline_prev10_mean 11942       2.7580          9.3291  6.8558                  6.5711
      (0,5] tuned_convex_ensemble 11942       2.7580          9.6895  7.0206                  6.9315
        >30         random_forest 11386      39.7458         25.9509 14.3144                -13.7948
        >30                 ridge 11386      39.7458         26.3834 13.8986                -13.3624
        >30  baseline_prev10_mean 11386      39.7458         26.9669 13.7785                -12.7789
        >30 tuned_convex_ensemble 11386      39.7458         26.1531 14.1148                -13.5927
    (20,30]         random_forest 13339      24.6376         19.9074  7.2756                 -4.7302
    (20,30]                 ridge 13339      24.6376         20.3425  7.0470                 -4.2951
    (20,30]  baseline_prev10_mean 13339      24.6376         20.2949  7.7206                 -4.3427
    (20,30] tuned_convex_ensemble 13339      24.6376         20.0791  7.1760                 -4.5585
        <=0         random_forest  5889      -1.0541          8.1177  9.1718                  9.1718
        <=0                 ridge  5889      -1.0541          7.8220  8.8971                  8.8761
        <=0  baseline_prev10_mean  5889      -1.0541          7.5389  8.6110                  8.5930
        <=0 tuned_convex_ensemble  5889      -1.0541          7.9853  9.0402                  9.0393
    (10,15]         random_forest 11343      12.5989         14.6556  4.9491                  2.0567
    (10,15]                 ridge 11343      12.5989         15.0026  5.3318                  2.4037
    (10,15]  baseline_prev10_mean 11343      12.5989         14.5816  5.7035                  1.9827
    (10,15] tuned_convex_ensemble 11343      12.5989         14.7733  5.0542                  2.1744
    (15,20]         random_forest  9790      17.5201         16.8497  5.5703                 -0.6704
    (15,20]                 ridge  9790      17.5201         17.2576  5.6262                 -0.2625
    (15,20]  baseline_prev10_mean  9790      17.5201         16.9840  6.2718                 -0.5361
    (15,20] tuned_convex_ensemble  9790      17.5201         16.9991  5.5676                 -0.5209
     (5,10]         random_forest 12405       7.6249         12.2939  5.5366                  4.6689
     (5,10]                 ridge 12405       7.6249         12.4450  5.9816                  4.8201
     (5,10]  baseline_prev10_mean 12405       7.6249         12.0148  5.9144                  4.3899
     (5,10] tuned_convex_ensemble 12405       7.6249         12.3328  5.6592                  4.7079

## Interpretation cautions

- Conditioning on realized PDK changes the sample; use these results to diagnose errors, not to claim prospective performance.
- If ensemble improvement is negligible, do not change production weights based on this audit alone.
- Production validation still needs pre-game lineup/coach/price/injury snapshots linked to realized full-lineup PDK and transfer penalties.

## Artifacts

- Detailed metrics: reports/audit/dunkest_pdk_calibration_error_audit_20261012T172805Z.csv
- Machine-readable audit: reports/audit/dunkest_pdk_calibration_error_audit_20261012T172805Z.json
