# Paired bootstrap: coach-score Monte Carlo vs baselines — V1

10,000 paired bootstrap replicates, resampling NBA games as clusters so the two opposing coach outcomes remain together. Pooled intervals are stratified by season. Negative MAE delta favours Monte Carlo.

| Period | Comparator | MAE delta MC − comparator | 95% bootstrap CI | P(MC better) | Game win rate |
|---|---|---:|---:|---:|---:|
| pooled_2022-26 | direct | -0.915 | [-1.046, -0.780] | 1.000 | 0.589 |
| pooled_2022-26 | prev10 | -1.438 | [-1.576, -1.302] | 1.000 | 0.621 |
| 2022-23 | direct | -0.761 | [-1.011, -0.508] | 1.000 | 0.568 |
| 2022-23 | prev10 | -1.270 | [-1.531, -1.002] | 1.000 | 0.609 |
| 2023-24 | direct | -1.055 | [-1.323, -0.792] | 1.000 | 0.611 |
| 2023-24 | prev10 | -1.412 | [-1.675, -1.144] | 1.000 | 0.627 |
| 2024-25 | direct | -0.978 | [-1.265, -0.698] | 1.000 | 0.585 |
| 2024-25 | prev10 | -1.469 | [-1.751, -1.192] | 1.000 | 0.612 |
| 2025-26 | direct | -0.866 | [-1.140, -0.592] | 1.000 | 0.591 |
| 2025-26 | prev10 | -1.600 | [-1.887, -1.319] | 1.000 | 0.634 |

## Interpretation

These are paired predictive-error comparisons for neutral-credit base coach scores, not exact credit-adjusted historical Dunkest PDK. Historical coach CR pairs remain unavailable. No production code/configuration changed.

## Artifacts

- CSV: `reports/audit/dunkest_coach_score_monte_carlo_paired_bootstrap_2018-26_v1.csv`
- JSON: `reports/audit/dunkest_coach_score_monte_carlo_paired_bootstrap_2018-26_v1.json`
