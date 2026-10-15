# Game-level historical lineup proxy — paired bootstrap

Generated UTC: 2026-10-14T13:15:34.274501+00:00

## Pooled comparison

- Paired rounds: 458
- Mean model minus baseline: **43.832 PDK**
- Median paired difference: **41.925 PDK**
- Model wins on **75.5%** of rounds
- Season-stratified paired-round bootstrap 95% CI: **[38.608, 49.050] PDK**
- Bootstrap replicates with non-positive mean difference: 0 / 50000

| Season ID | Rounds | Mean delta | Median delta | Model win rate |
|---:|---:|---:|---:|---:|
| 9 | 159 | 35.648 | 27.000 | 68.6% |
| 13 | 147 | 51.445 | 52.605 | 81.0% |
| 19 | 152 | 45.031 | 44.543 | 77.6% |

## Interpretation

This interval is conditional on zero-inclusive target labels for prior-observed candidates missing from the target-round archive, plus role/history calibration from expanding-season OOS residuals. It is exploratory, not a certified historical Dunkest result. Historical market state, availability, coach prices and transfer penalties remain unobserved.

## Limitations

- This estimates uncertainty conditional on the reconstructed candidate pool, zero-inclusive training/evaluation proxy, and past-only group calibration.
- It does not correct missing historical pre-lock prices/availability, unknown coach credits, or transfer malus.
- It compares fresh independent round lineups, not a sequential roster with carried players and transfer constraints.

Machine-readable output: reports/audit/dunkest_historical_lineups_gamelevel_actuals_20261014_v7_proxy_bootstrap.json
