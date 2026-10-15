# Plusvalenza history and probability calibration — V1

Generated UTC: 2026-10-15T07:22:36.389725+00:00

## Official data coverage

- Rows returned by official Dunkest stats endpoint: 93,744
- Seasons with verified broad NBA-team coverage: 5
- Distinct teams per season: {'5': 30, '7': 30, '9': 30, '13': 30, '19': 30}
- Observed gameweeks per season: {'2020-21': 59, '2021-22': 64, '2022-23': 64, '2023-24': 62, '2024-25': 64}
- Incomplete seasons excluded from fitting: []
- The previous archive contained non-NBA/partial seasons with only two NBA team codes. The v4 collector now requires at least 28 distinct NBA teams at season discovery and does not reuse those old v3 caches.

## ΔCR point forecast

- Training rows after validation: 87,626
- Past-only walk-forward validation rows: 17,256
- MAE: 0.069512 CR
- Training-window-mean baseline MAE: 0.182975 CR
- Mean calibrated OOF residual: -0.010944 CR

## Gain / flat / loss probability calibration

- Probability calibrator training rows: 16,509
- Sequential past-only OOF rows evaluated after calibration burn-in: 15,451
- Actual gain rate: 38.7224%
- Raw mean gain probability: 42.4090% (bias +3.687 percentage points)
- Calibrated mean gain probability: 38.9274% (bias +0.205 percentage points)
- Multiclass Brier: 0.318655 raw → 0.314660 calibrated
- Multiclass log loss: 0.644684 raw → 0.562063 calibrated

## Per-season sequential calibration

season_id  season    n  actual_gain_rate  raw_gain_bias_percentage_points  calibrated_gain_bias_percentage_points  raw_multiclass_brier  calibrated_multiclass_brier  raw_multiclass_log_loss  calibrated_multiclass_log_loss
        5 2020-21 1083           0.30471                         13.16749                                11.16463               0.48257                      0.46286                  1.89998                         1.24900
        7 2021-22 3386           0.42528                          1.26116                                -3.68275               0.27513                      0.28026                  0.48698                         0.48202
        9 2022-23 3697           0.41087                          1.56322                                -1.14406               0.28991                      0.28779                  0.50501                         0.48866
       13 2023-24 3499           0.35925                          6.55661                                 3.21502               0.34363                      0.33489                  0.60641                         0.54994
       19 2024-25 3786           0.37956                          2.56469                                -0.91740               0.31568                      0.31058                  0.59841                         0.52003

## Limits

- The calibration layer is trained only on earlier out-of-fold probability forecasts and observed official plusvalenza outcomes; it does not use the row being evaluated.
- The OOF calibration audit conditions on the observed official PDK score. It validates the CR conversion probabilities, not the full end-to-end probability when PDK itself is uncertain.
- Production still combines this calibrated conversion probability with the score-forecast distribution. End-to-end calibration would require historical pre-lock PDK forecast snapshots; none were fabricated.
- The 2026/27 GW1 prospective bundle was not read, trained on, or tuned.

## Artifact

reports/audit/dunkest_plusvalenza_calibration_20261015_v1.json
