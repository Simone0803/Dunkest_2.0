# Past-only calibration of recovered Dunkest lineup scores — V1

Generated UTC: 2026-10-14T13:42:40.346766+00:00

For each strategy, fit actual recovered proxy score = intercept + slope * expected lineup score on earlier fully scored rounds only. Calibration begins after 20 previous rounds, slope clipped to [0,2], and is used only to forecast the next round score; lineups are unchanged.

## Results

| Strategy | Variant | n | MAE | RMSE | Bias | Mean zero-candidate share |
|---|---|---:|---:|---:|---:|---:|
| model | raw | 428 | 44.062 | 57.988 | 7.380 | 0.222 |
| model | past_only_calibrated | 408 | 44.703 | 57.566 | -0.441 | 0.222 |
| previous5_baseline | raw | 378 | 111.872 | 128.211 | 110.660 | 0.483 |
| previous5_baseline | past_only_calibrated | 358 | 52.637 | 63.918 | 10.101 | 0.492 |

## Limitations

- Outcome scores include explicit zero candidates and are not certified official actuals.
- Historical coach credit multipliers and transfer malus are still proxies.
- This calibrates expected score after selection; it does not correct which players the optimizer selected.

Per-round calibration: `reports/audit/dunkest_recovered_lineup_postselection_calibration_20261014_v1.csv`
Machine-readable summary: `reports/audit/dunkest_recovered_lineup_postselection_calibration_20261014_v1.json`
