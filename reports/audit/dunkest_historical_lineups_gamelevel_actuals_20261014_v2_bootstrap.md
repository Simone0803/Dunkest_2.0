# Game-level historical lineup proxy — paired bootstrap

Generated UTC: 2026-10-14T11:54:46.308515+00:00

## Pooled comparison

- Paired rounds: 409
- Mean model minus baseline: **20.538 PDK**
- Median paired difference: **17.655 PDK**
- Model wins on **63.8%** of rounds
- Season-stratified paired-round bootstrap 95% CI: **[15.064, 25.898] PDK**
- Bootstrap replicates with non-positive mean difference: 0 / 50000

| Season ID | Rounds | Mean delta | Median delta | Model win rate |
|---:|---:|---:|---:|---:|
| 9 | 139 | 17.009 | 17.925 | 62.6% |
| 13 | 132 | 20.624 | 15.982 | 62.9% |
| 19 | 138 | 24.011 | 20.890 | 65.9% |

## Interpretation

The player-model lineup proxy beats the previous-five-round baseline on the paired sample, and the bootstrap interval is positive. This is evidence for the forecasting/selection signal under the reconstructed candidate universe; it is not proof of full official Dunkest strategy superiority because historical market state, coach prices and transfer penalties remain unobserved.

## Limitations

- This estimates uncertainty conditional on the restricted historical candidate pool and reconstructed official player actuals.
- It does not correct missing historical pre-lock prices/availability, unknown coach credits, or transfer malus.
- It compares fresh independent round lineups, not a sequential roster with carried players and transfer constraints.

Machine-readable output: reports/audit/dunkest_historical_lineups_gamelevel_actuals_20261014_v2_bootstrap.json
