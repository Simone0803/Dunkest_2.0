# Paired bootstrap: coach-score Monte Carlo vs baselines — V1

10,000 paired bootstrap replicates, resampling NBA games as clusters so the two opposing coach outcomes remain together. Pooled intervals are stratified by season. Negative MAE delta favours Monte Carlo.

| Period | Comparator | MAE delta MC − comparator | 95% bootstrap CI | P(MC better) | Game win rate |
|---|---|---:|---:|---:|---:|
| pooled_2022-26 | direct | -0.871 | [-1.000, -0.740] | 1.000 | 0.584 |
| pooled_2022-26 | prev10 | -1.394 | [-1.531, -1.260] | 1.000 | 0.622 |
| 2022-23 | direct | -0.688 | [-0.930, -0.446] | 1.000 | 0.558 |
| 2022-23 | prev10 | -1.197 | [-1.448, -0.940] | 1.000 | 0.611 |
| 2023-24 | direct | -1.003 | [-1.263, -0.746] | 1.000 | 0.607 |
| 2023-24 | prev10 | -1.360 | [-1.617, -1.097] | 1.000 | 0.628 |
| 2024-25 | direct | -0.942 | [-1.226, -0.667] | 1.000 | 0.580 |
| 2024-25 | prev10 | -1.433 | [-1.711, -1.159] | 1.000 | 0.613 |
| 2025-26 | direct | -0.852 | [-1.125, -0.581] | 1.000 | 0.592 |
| 2025-26 | prev10 | -1.586 | [-1.870, -1.306] | 1.000 | 0.638 |

## Interpretation

These are paired predictive-error comparisons for neutral-credit base coach scores, not exact credit-adjusted historical Dunkest PDK. Historical coach CR pairs remain unavailable. No production code/configuration changed.

## Artifacts

- CSV: `reports/audit/dunkest_coach_score_monte_carlo_paired_bootstrap_2018-26_v3.csv`
- JSON: `reports/audit/dunkest_coach_score_monte_carlo_paired_bootstrap_2018-26_v3.json`
