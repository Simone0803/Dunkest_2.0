# Recovered historical lineup score audit — V2

Generated UTC: 2026-10-14T13:42:13.281586+00:00

Fully scored lineups under recovered-outcome proxy: **806 / 916**.
Paired rounds with both strategies scoreable: **366**.

## Paired strategy comparison

- Model minus baseline mean: **44.17 PDK**
- Median delta: 41.38 PDK
- Model win rate: 75.4%
- Season-stratified paired bootstrap 95% CI: **[38.22, 50.11]**

| Season ID | Paired rounds | Mean delta | Model win rate |
|---:|---:|---:|---:|
| 13 | 131 | 50.02 | 79.4% |
| 19 | 98 | 48.37 | 80.6% |
| 9 | 137 | 35.56 | 67.9% |

## Expected lineup score calibration

| Strategy | n | Expected mean | Recovered actual mean | MAE | RMSE | Bias expected − actual | Zero candidate share |
|---|---:|---:|---:|---:|---:|---:|---:|
| model | 428 | 169.71 | 162.33 | 44.06 | 57.99 | 7.38 | 22.2% |
| previous5_baseline | 378 | 229.44 | 118.78 | 111.87 | 128.21 | 110.66 | 48.3% |

## Interpretation

The score reconstruction now applies the saved roster slot multipliers and joins coach actuals independently by team/date, avoiding the previous sparse coach-score lookup. Results remain proxy-based because missing weekly outcomes are not always distinguishable from historical identity/availability errors.

## Limitations

- Zero candidates are a sensitivity proxy, not certified official Dunkest scores.
- Lagged team assignment may be stale after trades; 123 selected-player instances have team/date mismatches and exclude their lineups.
- Coach credits/multipliers and transfer malus remain historical proxies; this evaluates fresh independent lineups, not sequential roster management.

Per-lineup scores: `reports/audit/dunkest_lineups_recovered_actuals_20261014_v2_rounds.csv`
Paired rounds: `reports/audit/dunkest_lineups_recovered_actuals_20261014_v2_paired_bootstrap.csv`
Machine-readable report: `reports/audit/dunkest_lineups_recovered_actuals_20261014_v2.json`
