# Game-level historical lineup proxy — paired bootstrap

Generated UTC: 2026-10-14T13:29:05.818975+00:00

## Pooled comparison

- Paired rounds: 13
- Mean model minus baseline: **6.535 PDK**
- Median paired difference: **3.150 PDK**
- Model wins on **53.8%** of rounds
- Season-stratified paired-round bootstrap 95% CI: **[-4.456, 18.448] PDK**
- Bootstrap replicates with non-positive mean difference: 6678 / 50000

| Season ID | Rounds | Mean delta | Median delta | Model win rate |
|---:|---:|---:|---:|---:|
| 9 | 7 | -22.571 | -20.415 | 14.3% |
| 13 | 5 | 26.588 | 21.180 | 100.0% |
| 19 | 1 | 110.020 | 110.020 | 100.0% |

## Interpretation

This interval uses weekly-round scores where present, recovers valid game-level scores when available, and assigns 0 only when the official game-level source has an explicit gameValidForDunkest=False row. This is a sensitivity analysis; a non-valid row does not prove that the player was eligible in the historical pre-lock market. Unknown scores are not imputed.

## Limitations

- This estimates uncertainty conditional on the reconstructed candidate pool, explicit non-valid-game zero sensitivity, and past-only group calibration.
- It does not correct missing historical pre-lock prices/availability, unknown coach credits, or transfer malus.
- It compares fresh independent round lineups, not a sequential roster with carried players and transfer constraints.

Machine-readable output: reports/audit/dunkest_historical_lineups_gamelevel_actuals_20261014_v8_expanded_bootstrap.json
