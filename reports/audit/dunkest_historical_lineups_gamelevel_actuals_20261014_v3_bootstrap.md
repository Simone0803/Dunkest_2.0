# Game-level historical lineup proxy — paired bootstrap

Generated UTC: 2026-10-14T12:04:36.781338+00:00

## Pooled comparison

- Paired rounds: 409
- Mean model minus baseline: **20.489 PDK**
- Median paired difference: **16.820 PDK**
- Model wins on **64.1%** of rounds
- Season-stratified paired-round bootstrap 95% CI: **[15.189, 25.776] PDK**
- Bootstrap replicates with non-positive mean difference: 0 / 50000

| Season ID | Rounds | Mean delta | Median delta | Model win rate |
|---:|---:|---:|---:|---:|
| 9 | 139 | 15.456 | 12.235 | 59.0% |
| 13 | 132 | 20.459 | 16.162 | 64.4% |
| 19 | 138 | 25.588 | 23.423 | 68.8% |

## Interpretation

The player-model lineup proxy beats the raw previous-five-observation mean baseline on the paired sample, and the bootstrap interval is positive. However, the raw baseline is severely overoptimistic after lineup selection (mean expected team score 271.72 versus realized 140.34; model 207.82 versus 160.83). Interpret the CI as conditional evidence against a naïve baseline, not proof of superiority over a calibrated strategy. Historical market state, coach prices and transfer penalties remain unobserved.

## Limitations

- This estimates uncertainty conditional on the restricted historical candidate pool and reconstructed official player actuals.
- It does not correct missing historical pre-lock prices/availability, unknown coach credits, or transfer malus.
- It compares fresh independent round lineups, not a sequential roster with carried players and transfer constraints.

Machine-readable output: reports/audit/dunkest_historical_lineups_gamelevel_actuals_20261014_v3_bootstrap.json
