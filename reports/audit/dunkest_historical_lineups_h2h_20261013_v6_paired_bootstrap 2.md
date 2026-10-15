# H2H lineup experiment — paired evaluation

## Pooled results

| Strategy | Mean realized lineup + coach base score | Mean expected score |
|---|---:|---:|
| Model without H2H | 160.99 | 207.77 |
| Model with H2H | 155.33 | 201.34 |
| Previous-five-round baseline | 140.34 | 271.72 |

On 409 paired rounds, the H2H lineup minus the model-without-H2H lineup is **-5.66 points per round** (median -2.12); the H2H lineup beats the no-H2H model in **45.2%** of rounds. Stratified paired bootstrap by season (10000 replicates) gives a 95% interval of **[-9.49, -1.77]** points.

## By season

| Season | Rounds | Model | H2H | Baseline | H2H − model | H2H win rate | 95% bootstrap interval |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2022-23 | 139 | 152.07 | 146.64 | 134.73 | -5.42 | 41.7% | [-12.25, 1.31] |
| 2023-24 | 132 | 163.16 | 155.79 | 142.54 | -7.37 | 45.5% | [-14.61, -0.53] |
| 2024-25 | 138 | 167.89 | 163.63 | 143.88 | -4.25 | 48.6% | [-10.39, 1.99] |

## Decision

**Do not integrate H2H into production from this experiment.** It reduces the mean realized score of the selected lineup versus the otherwise identical model by about 5.66 points per round, with a paired interval below zero. This contrasts with the small game-level MAE improvement in the separate 2025/26 holdout and suggests the game-level H2H feature is not transferring cleanly to weekly-round lineup optimization. A future challenger should align H2H aggregation with the weekly-round target and be evaluated on the same candidate universe before production consideration.

The experiment is still restricted: historical full-market roster snapshots, coach prices and transfer malus are missing. Results are comparative within this proxy setup, not official Dunkest team totals.

Artifacts: `reports/audit/dunkest_historical_lineups_h2h_20261013_v6_paired_bootstrap.json`, `reports/audit/dunkest_historical_lineups_h2h_20261013_v6_paired_bootstrap.csv`, `reports/audit/dunkest_historical_lineups_h2h_20261013_v6_paired_bootstrap.md`.
