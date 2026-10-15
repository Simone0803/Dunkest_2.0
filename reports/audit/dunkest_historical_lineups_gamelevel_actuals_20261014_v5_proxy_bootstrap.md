# Game-level historical lineup proxy — paired bootstrap

Generated UTC: 2026-10-14T12:42:29.823569+00:00

## Pooled comparison

- Paired rounds: 458
- Mean model minus baseline: **15.464 PDK**
- Median paired difference: **12.545 PDK**
- Model wins on **60.3%** of rounds
- Season-stratified paired-round bootstrap 95% CI: **[10.567, 20.406] PDK**
- Bootstrap replicates with non-positive mean difference: 0 / 50000

| Season ID | Rounds | Mean delta | Median delta | Model win rate |
|---:|---:|---:|---:|---:|
| 9 | 159 | 8.874 | 9.715 | 56.6% |
| 13 | 147 | 18.971 | 12.410 | 61.9% |
| 19 | 152 | 18.966 | 15.487 | 62.5% |

## Interpretation

This interval is conditional on the explicit assumption that a previously observed candidate with no valid player-game PDK row scores zero. It is exploratory, not a certified historical Dunkest result. The raw previous-five baseline is not post-selection calibrated; historical market state, availability, coach prices and transfer penalties remain unobserved.

## Limitations

- This estimates uncertainty conditional on the reconstructed candidate pool and the explicit zero-for-missing player outcome proxy.
- It does not correct missing historical pre-lock prices/availability, unknown coach credits, or transfer malus.
- It compares fresh independent round lineups, not a sequential roster with carried players and transfer constraints.

Machine-readable output: reports/audit/dunkest_historical_lineups_gamelevel_actuals_20261014_v5_proxy_bootstrap.json
