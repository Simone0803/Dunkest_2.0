# Dunkest PDK score calibration experiment

Created UTC: 2026-10-12T17:28:19.878918+00:00

## Protocol

- Fit linear and isotonic calibration mappings on walk-forward predictions from 2022/23–2024/25.
- Evaluated once on the untouched 2025/26 final fold.
- No production files/configuration were changed.
- Ensemble base weights: 0.60 Random Forest, 0.35 Ridge, 0.05 previous-10 mean.

## Final holdout metrics

                split                             method     n    mae   rmse  bias_pred_minus_actual  actual_mean  predicted_mean
final_holdout_2025-26                  random_forest_raw 18412 7.5775 9.8563                 -0.1725      16.1417         15.9692
final_holdout_2025-26   random_forest_linear_calibration 18412 7.5747 9.8584                 -0.0816      16.1417         16.0601
final_holdout_2025-26 random_forest_isotonic_calibration 18412 7.5790 9.8641                 -0.0657      16.1417         16.0760
final_holdout_2025-26                   ensemble_raw_raw 18412 7.5568 9.8306                 -0.0885      16.1417         16.0531
final_holdout_2025-26    ensemble_raw_linear_calibration 18412 7.5497 9.8331                 -0.0872      16.1417         16.0544
final_holdout_2025-26  ensemble_raw_isotonic_calibration 18412 7.5544 9.8393                 -0.0725      16.1417         16.0691

## Calibration parameters

{
  "random_forest_linear": {
    "intercept": -0.3086382544138857,
    "slope": 1.0250168552667815
  },
  "random_forest_isotonic": {
    "threshold_count": 274
  },
  "ensemble_raw_linear": {
    "intercept": -0.2810327831945223,
    "slope": 1.01758895255368
  },
  "ensemble_raw_isotonic": {
    "threshold_count": 264
  }
}

## Caveats

- Calibration maps are fitted only on earlier walk-forward prediction folds, never on 2025/26 targets.
- This is a separate game-level experiment and does not change production inference.
- Calibration may improve aggregate MAE while worsening subgroups; inspect residuals before any integration.
- The final holdout should be considered consumed for this calibration experiment and not reused for further iterative tuning.

## Artifacts

- Metrics CSV: reports/audit/dunkest_pdk_score_calibration_20261012T172819Z.csv
- Audit JSON: reports/audit/dunkest_pdk_score_calibration_20261012T172819Z.json
