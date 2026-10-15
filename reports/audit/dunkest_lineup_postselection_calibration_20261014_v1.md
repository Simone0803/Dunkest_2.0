# Expanding post-selection calibration of Dunkest lineup forecasts

Generated UTC: 2026-10-14T13:16:43.283489+00:00

## Method

For each strategy, fit actual_proxy = intercept + slope * expected_team_pdk on prior rounds only, across prior test seasons and prior rounds of the current season. Calibration starts after 20 prior evaluated rounds. Slope is constrained to [0,2]. This adjusts the forecast score after lineup selection; it does not change selected lineups.

## Results

| Strategy | Raw MAE | Calibrated MAE | Raw RMSE | Calibrated RMSE | Raw bias | Calibrated bias | Calibrated rounds |
|---|---:|---:|---:|---:|---:|---:|---:|
| model | 43.833 | 43.372 | 57.708 | 57.075 | 7.250 | 6.801 | 438 |
| previous5_baseline | 111.642 | 52.662 | 127.835 | 63.584 | 110.516 | 3.655 | 438 |

## Limitations

- Realized outcomes use the explicit zero-for-missing proxy from V7, not fully observed official scores.
- Historical market/availability/coach credits and transfer malus remain incomplete.
- Post-selection calibration adjusts score forecasts only and does not change lineup selection.

Per-round output: `reports/audit/dunkest_lineup_postselection_calibration_20261014_v1.csv`
Machine-readable report: `reports/audit/dunkest_lineup_postselection_calibration_20261014_v1.json`
