# Recovered historical lineup score audit — V1

Generated UTC: 2026-10-14T13:38:48.946777+00:00

Lineup-strategy rows fully scored under recovered-outcome proxy: **124 / 916**.

## Strategy comparison

- Paired rounds: **8**
- Model minus baseline mean: **-12.75 PDK**
- Median delta: -15.50 PDK
- Model win rate: 25.0%
- Season-stratified paired bootstrap 95% CI: **[-22.97, -3.40]**

| Season ID | Paired rounds | Mean delta | Model win rate |
|---:|---:|---:|---:|
| 13 | 2 | 19.02 | 100.0% |
| 9 | 6 | -23.35 | 0.0% |

## Expected lineup score calibration diagnostics

| Strategy | n | Mean expected | Mean recovered proxy actual | MAE | RMSE | Bias expected − actual | Mean zero-candidate share |
|---|---:|---:|---:|---:|---:|---:|---:|
| model | 113 | 172.72 | 198.35 | 34.80 | 44.73 | -25.63 | 0.0% |
| previous5_baseline | 11 | 254.57 | 202.38 | 55.06 | 72.75 | 52.19 | 0.0% |

## Interpretation

This is a broader sensitivity analysis than the previous strict observed-only subset, because it includes explicit zero candidates backed by a game row or a team fixture. It remains a proxy: it cannot distinguish a true DNP from an incorrect historical identity with full certainty. Do not treat this as production validation.

## Limitations

- This is not a certified historical Dunkest backtest: zero candidates and coach scores remain proxy-derived.
- Lagged team codes may be stale after trades; no-fixture mismatches are excluded.
- Lineups are independently optimized per round, not a sequential roster with transfer malus.

Per-lineup outcomes: `reports/audit/dunkest_lineups_recovered_actuals_20261014_v1_rounds.csv`
Paired-round table: `reports/audit/dunkest_lineups_recovered_actuals_20261014_v1_paired_bootstrap.csv`
Machine-readable summary: `reports/audit/dunkest_lineups_recovered_actuals_20261014_v1.json`
