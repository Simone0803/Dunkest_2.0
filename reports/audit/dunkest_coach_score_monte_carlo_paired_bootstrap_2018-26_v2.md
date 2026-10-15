# Paired bootstrap: coach-score Monte Carlo vs baselines — V1

10,000 paired bootstrap replicates, resampling NBA games as clusters so the two opposing coach outcomes remain together. Pooled intervals are stratified by season. Negative MAE delta favours Monte Carlo.

| Period | Comparator | MAE delta MC − comparator | 95% bootstrap CI | P(MC better) | Game win rate |
|---|---|---:|---:|---:|---:|
| pooled_2022-26 | direct | -0.889 | [-1.019, -0.757] | 1.000 | 0.586 |
| pooled_2022-26 | prev10 | -1.412 | [-1.548, -1.278] | 1.000 | 0.622 |
| 2022-23 | direct | -0.705 | [-0.947, -0.460] | 1.000 | 0.562 |
| 2022-23 | prev10 | -1.214 | [-1.468, -0.951] | 1.000 | 0.614 |
| 2023-24 | direct | -1.025 | [-1.290, -0.766] | 1.000 | 0.610 |
| 2023-24 | prev10 | -1.383 | [-1.642, -1.119] | 1.000 | 0.624 |
| 2024-25 | direct | -0.962 | [-1.247, -0.683] | 1.000 | 0.582 |
| 2024-25 | prev10 | -1.453 | [-1.733, -1.178] | 1.000 | 0.613 |
| 2025-26 | direct | -0.864 | [-1.137, -0.592] | 1.000 | 0.590 |
| 2025-26 | prev10 | -1.598 | [-1.885, -1.318] | 1.000 | 0.636 |

## Interpretation

These are paired predictive-error comparisons for neutral-credit base coach scores, not exact credit-adjusted historical Dunkest PDK. Historical coach CR pairs remain unavailable. No production code/configuration changed.

## Artifacts

- CSV: `reports/audit/dunkest_coach_score_monte_carlo_paired_bootstrap_2018-26_v2.csv`
- JSON: `reports/audit/dunkest_coach_score_monte_carlo_paired_bootstrap_2018-26_v2.json`
