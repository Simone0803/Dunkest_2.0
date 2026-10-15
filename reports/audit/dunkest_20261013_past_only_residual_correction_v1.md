# Past-only residual correction experiment — V1

## Design

A second-stage residual learner is fitted only on earlier-season saved OOF predictions. Validation is expanding-origin: 2023/24 is corrected using 2022/23 residuals; 2024/25 is corrected using 2022/23 and 2023/24 residuals. Only the V6 rest/schedule predictor family is used. 2025/26 and the prospective 2026/27 run are excluded.

## Overall results

 season         method     n  date_clusters  raw_mae  corrected_mae  delta_mae_corrected_minus_raw  ci95_low  ci95_high
2023-24    et_residual 18918            153  7.46376        7.45464                       -0.00912  -0.01567   -0.00243
2023-24   hgb_residual 18918            153  7.46376        7.45159                       -0.01217  -0.01889   -0.00511
2023-24 ridge_residual 18918            153  7.46376        7.48407                        0.02031   0.00824    0.03163
2024-25    et_residual 19589            158  7.46322        7.45330                       -0.00992  -0.02115    0.00137
2024-25   hgb_residual 19589            158  7.46322        7.46267                       -0.00055  -0.01178    0.01088
2024-25 ridge_residual 19589            158  7.46322        7.46852                        0.00530  -0.00543    0.01583

## Segment metrics

 season         method         segment prediction_version     n      mae     rmse  bias_pred_minus_actual
2023-24 ridge_residual             all                raw 18918  7.46376  9.74769                -0.89393
2023-24 ridge_residual             all          corrected 18918  7.48407  9.75804                -0.91381
2023-24 ridge_residual    actual_ge_25                raw  4366 12.87929 15.22002               -12.15491
2023-24 ridge_residual    actual_ge_25          corrected  4366 12.95890 15.30236               -12.23822
2023-24 ridge_residual predicted_ge_25                raw  2737 10.21217 12.78539                -2.58742
2023-24 ridge_residual predicted_ge_25          corrected  2737 10.21631 12.80023                -2.65436
2023-24 ridge_residual    actual_ge_30                raw  2970 14.92784 17.05550               -14.48719
2023-24 ridge_residual    actual_ge_30          corrected  2970 15.01138 17.14158               -14.56517
2023-24   hgb_residual             all                raw 18918  7.46376  9.74769                -0.89393
2023-24   hgb_residual             all          corrected 18918  7.45159  9.74667                -0.96351
2023-24   hgb_residual    actual_ge_25                raw  4366 12.87929 15.22002               -12.15491
2023-24   hgb_residual    actual_ge_25          corrected  4366 12.93485 15.25914               -12.10835
2023-24   hgb_residual predicted_ge_25                raw  2737 10.21217 12.78539                -2.58742
2023-24   hgb_residual predicted_ge_25          corrected  2737 10.19460 12.76182                -2.44607
2023-24   hgb_residual    actual_ge_30                raw  2970 14.92784 17.05550               -14.48719
2023-24   hgb_residual    actual_ge_30          corrected  2970 14.96157 17.07350               -14.38867
2023-24    et_residual             all                raw 18918  7.46376  9.74769                -0.89393
2023-24    et_residual             all          corrected 18918  7.45464  9.75287                -1.00869
2023-24    et_residual    actual_ge_25                raw  4366 12.87929 15.22002               -12.15491
2023-24    et_residual    actual_ge_25          corrected  4366 13.02841 15.33757               -12.26680
2023-24    et_residual predicted_ge_25                raw  2737 10.21217 12.78539                -2.58742
2023-24    et_residual predicted_ge_25          corrected  2737 10.22333 12.80222                -2.72598
2023-24    et_residual    actual_ge_30                raw  2970 14.92784 17.05550               -14.48719
2023-24    et_residual    actual_ge_30          corrected  2970 15.08997 17.18283               -14.57399
2024-25 ridge_residual             all                raw 19589  7.46322  9.76162                -0.68642
2024-25 ridge_residual             all          corrected 19589  7.46852  9.71818                -0.21878
2024-25 ridge_residual    actual_ge_25                raw  4425 12.55302 15.07062               -11.82429
2024-25 ridge_residual    actual_ge_25          corrected  4425 12.00882 14.57282               -11.01631
2024-25 ridge_residual predicted_ge_25                raw  2869 10.20682 12.82200                -1.61723
2024-25 ridge_residual predicted_ge_25          corrected  2869 10.11735 12.69817                -0.48927
2024-25 ridge_residual    actual_ge_30                raw  2919 14.72074 17.12126               -14.31988
2024-25 ridge_residual    actual_ge_30          corrected  2919 13.99758 16.50932               -13.41834
2024-25   hgb_residual             all                raw 19589  7.46322  9.76162                -0.68642
2024-25   hgb_residual             all          corrected 19589  7.46267  9.73318                -0.22590
2024-25   hgb_residual    actual_ge_25                raw  4425 12.55302 15.07062               -11.82429
2024-25   hgb_residual    actual_ge_25          corrected  4425 11.98897 14.54328               -10.94841
2024-25   hgb_residual predicted_ge_25                raw  2869 10.20682 12.82200                -1.61723
2024-25   hgb_residual predicted_ge_25          corrected  2869 10.16626 12.75421                -0.43372
2024-25   hgb_residual    actual_ge_30                raw  2919 14.72074 17.12126               -14.31988
2024-25   hgb_residual    actual_ge_30          corrected  2919 13.97766 16.48463               -13.35277
2024-25    et_residual             all                raw 19589  7.46322  9.76162                -0.68642
2024-25    et_residual             all          corrected 19589  7.45330  9.72138                -0.21782
2024-25    et_residual    actual_ge_25                raw  4425 12.55302 15.07062               -11.82429
2024-25    et_residual    actual_ge_25          corrected  4425 11.95640 14.51451               -10.91556
2024-25    et_residual predicted_ge_25                raw  2869 10.20682 12.82200                -1.61723
2024-25    et_residual predicted_ge_25          corrected  2869 10.14459 12.72799                -0.38302
2024-25    et_residual    actual_ge_30                raw  2919 14.72074 17.12126               -14.31988
2024-25    et_residual    actual_ge_30          corrected  2919 13.93964 16.45382               -13.32155

## Decision

No production change is made. A correction is only a candidate if the direction is stable across both seasons, the date-cluster interval supports an improvement, and the gain also holds for high-scoring players without materially damaging ordinary-score players. These folds are exploratory and do not replace the reserved final holdout.

## Artifacts

- Predictions: reports/audit/dunkest_20261013_past_only_residual_correction_v1_predictions.csv
- Metrics: reports/audit/dunkest_20261013_past_only_residual_correction_v1_metrics.csv
- Audit: reports/audit/dunkest_20261013_past_only_residual_correction_v1.json
